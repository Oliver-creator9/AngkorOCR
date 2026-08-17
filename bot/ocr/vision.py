"""Optional vision-model engine for handwriting and hard photos.

Inert unless ANTHROPIC_API_KEY is set — see config.py `vision_enabled`. OcrService
only constructs this class when a key is present, so an unconfigured bot never
imports `anthropic`'s network path and never spends anything.
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Sequence

from PIL import Image

from .base import OcrEngine, OcrError, OcrResult

log = logging.getLogger(__name__)

PROMPT = (
    "Transcribe every word of visible text in this image, in reading order. "
    "Return only the transcribed text, with no commentary, headers, or markdown."
)


class VisionEngine(OcrEngine):
    def __init__(self, api_key: str, model: str, timeout_s: int) -> None:
        self.name = "vision"
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_s
        self._client = None

    def _client_or_create(self):
        if self._client is None:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=self._api_key, timeout=self._timeout)
        return self._client

    async def healthcheck(self) -> bool:
        # No network call on purpose: this must never make a billed request just
        # because the bot started up. Presence of a key is all we assert here.
        return bool(self._api_key)

    async def available_langs(self) -> list[str]:
        return []  # the vision model reads any script; no fixed list to validate against

    @staticmethod
    def _encode_png(image: Image.Image) -> str:
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="PNG")
        return base64.standard_b64encode(buf.getvalue()).decode("utf-8")

    async def recognize(self, images: Sequence[Image.Image], langs: str) -> OcrResult:
        client = self._client_or_create()
        pages: list[str] = []
        try:
            for image in images:
                response = await client.messages.create(
                    model=self._model,
                    max_tokens=4096,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": self._encode_png(image),
                                    },
                                },
                                {"type": "text", "text": PROMPT},
                            ],
                        }
                    ],
                )
                text = "".join(block.text for block in response.content if block.type == "text")
                pages.append(text.strip())
        except Exception as exc:  # noqa: BLE001
            raise OcrError("The vision engine couldn't read that image.") from exc

        return OcrResult(
            text="\n\n".join(p for p in pages if p), pages=pages, confidence=None, engine=self.name
        )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()
