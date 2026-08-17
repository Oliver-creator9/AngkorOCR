"""Engine registry plus the orchestration layer the handlers talk to."""

from __future__ import annotations

import asyncio
import io
import logging
import time
from typing import Sequence

from PIL import Image, UnidentifiedImageError

from ..config import Settings
from .base import OcrEngine, OcrError, OcrResult
from .preprocess import prepare, prepare_for_vision
from .tesseract import TesseractEngine
from .vision import VisionEngine

log = logging.getLogger(__name__)

# Pillow decompression-bomb guard: refuse absurd pixel counts outright.
Image.MAX_IMAGE_PIXELS = 80_000_000


class OcrService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sem = asyncio.Semaphore(settings.ocr_concurrency)
        self._engines: dict[str, OcrEngine] = {
            "tesseract": TesseractEngine(settings.tesseract_cmd, settings.ocr_timeout_s)
        }
        if settings.vision_enabled:
            self._engines["vision"] = VisionEngine(
                settings.anthropic_api_key, settings.anthropic_model, settings.ocr_timeout_s
            )
        self._langs_cache: list[str] | None = None

    # -- lifecycle ------------------------------------------------------------

    async def startup(self) -> None:
        for name, engine in self._engines.items():
            ok = await engine.healthcheck()
            log.info("engine %s: %s", name, "ok" if ok else "UNAVAILABLE")
        self._langs_cache = await self._engines["tesseract"].available_langs()

    async def shutdown(self) -> None:
        vision = self._engines.get("vision")
        if isinstance(vision, VisionEngine):
            await vision.aclose()

    # -- introspection --------------------------------------------------------

    def engine(self, name: str) -> OcrEngine:
        return self._engines.get(name) or self._engines["tesseract"]

    @property
    def engine_names(self) -> list[str]:
        return list(self._engines)

    @property
    def installed_langs(self) -> list[str]:
        return self._langs_cache or []

    def validate_langs(self, langs: str) -> tuple[bool, list[str]]:
        if not self._langs_cache:
            return True, []
        wanted = [p for p in langs.split("+") if p]
        missing = [p for p in wanted if p not in self._langs_cache]
        return not missing, missing

    # -- decoding -------------------------------------------------------------

    @staticmethod
    def decode_image(raw: bytes) -> Image.Image:
        try:
            img = Image.open(io.BytesIO(raw))
            img.load()
            return img
        except UnidentifiedImageError as exc:
            raise OcrError("That file is not an image I can read.") from exc
        except Image.DecompressionBombError as exc:
            raise OcrError("That image is too large to process safely.") from exc
        except Exception as exc:  # noqa: BLE001
            raise OcrError("That image appears to be corrupted.") from exc

    def pdf_to_images(self, raw: bytes, max_pages: int) -> list[Image.Image]:
        """Rasterise a PDF. Requires poppler-utils in the image."""
        try:
            from pdf2image import convert_from_bytes
            from pdf2image.exceptions import PDFPageCountError
        except ImportError as exc:
            raise OcrError("PDF support is not enabled on this server.") from exc
        try:
            return convert_from_bytes(raw, dpi=200, fmt="png", last_page=max_pages)
        except PDFPageCountError as exc:
            raise OcrError("I couldn't open that PDF — it may be encrypted.") from exc
        except Exception as exc:  # noqa: BLE001
            raise OcrError("I couldn't read that PDF.") from exc

    # -- the main entry point --------------------------------------------------

    async def run(
        self,
        images: Sequence[Image.Image],
        *,
        engine_name: str,
        langs: str,
        preprocess: bool = True,
    ) -> tuple[OcrResult, int]:
        """Preprocess + recognise. Returns (result, duration_ms).

        The semaphore is what keeps a burst of uploads from pinning every core and
        making the bot stop answering /start.
        """
        engine = self.engine(engine_name)
        started = time.perf_counter()

        async with self._sem:
            if engine.name == "vision":
                prepped = [await asyncio.to_thread(prepare_for_vision, i) for i in images]
            else:
                prepped = [await asyncio.to_thread(prepare, i, preprocess) for i in images]

            try:
                result = await asyncio.wait_for(
                    engine.recognize(prepped, langs),
                    timeout=self._settings.ocr_timeout_s * max(1, len(prepped)),
                )
            except asyncio.TimeoutError as exc:
                raise OcrError("That took too long. Try fewer or smaller pages.") from exc

        return result, int((time.perf_counter() - started) * 1000)

    async def searchable_pdf(
        self, images: Sequence[Image.Image], *, langs: str, preprocess: bool = True
    ) -> bytes:
        engine = self._engines["tesseract"]  # only Tesseract emits a text layer
        async with self._sem:
            prepped = [await asyncio.to_thread(prepare, i, preprocess) for i in images]
            return await engine.searchable_pdf(prepped, langs)
