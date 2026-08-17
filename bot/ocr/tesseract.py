"""The free, local OCR engine."""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Sequence

import pytesseract
from PIL import Image

from .base import OcrEngine, OcrResult

log = logging.getLogger(__name__)


class TesseractEngine(OcrEngine):
    def __init__(self, cmd: str, timeout_s: int) -> None:
        self.name = "tesseract"
        self._timeout = timeout_s
        pytesseract.pytesseract.tesseract_cmd = cmd

    async def healthcheck(self) -> bool:
        try:
            await asyncio.to_thread(pytesseract.get_tesseract_version)
            return True
        except Exception:  # noqa: BLE001
            return False

    async def available_langs(self) -> list[str]:
        try:
            return list(await asyncio.to_thread(pytesseract.get_languages, config=""))
        except Exception:  # noqa: BLE001
            return []

    async def recognize(self, images: Sequence[Image.Image], langs: str) -> OcrResult:
        def _run() -> OcrResult:
            pages: list[str] = []
            confidences: list[float] = []
            for image in images:
                data = pytesseract.image_to_data(
                    image, lang=langs, output_type=pytesseract.Output.DICT
                )
                page_text = pytesseract.image_to_string(image, lang=langs).strip()
                pages.append(page_text)
                confs = [float(c) for c in data.get("conf", []) if str(c) not in ("-1", "")]
                if confs:
                    confidences.append(sum(confs) / len(confs))

            full_text = "\n\n".join(p for p in pages if p)
            avg_conf = round(sum(confidences) / len(confidences), 1) if confidences else None
            return OcrResult(text=full_text, pages=pages, confidence=avg_conf, engine=self.name)

        return await asyncio.to_thread(_run)

    async def searchable_pdf(self, images: Sequence[Image.Image], langs: str) -> bytes:
        def _run() -> bytes:
            parts = [
                pytesseract.image_to_pdf_or_hocr(image, lang=langs, extension="pdf")
                for image in images
            ]
            if len(parts) == 1:
                return parts[0]

            from pypdf import PdfReader, PdfWriter

            writer = PdfWriter()
            for part in parts:
                reader = PdfReader(io.BytesIO(part))
                for page in reader.pages:
                    writer.add_page(page)
            buf = io.BytesIO()
            writer.write(buf)
            return buf.getvalue()

        return await asyncio.to_thread(_run)
