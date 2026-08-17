"""The engine interface every OCR backend implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Sequence

from PIL import Image


class OcrError(Exception):
    """Raised with a message that is safe to show the user directly."""


@dataclass
class OcrResult:
    text: str
    pages: list[str] = field(default_factory=list)
    confidence: float | None = None
    engine: str = "tesseract"

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


class OcrEngine(ABC):
    name: str

    @abstractmethod
    async def healthcheck(self) -> bool: ...

    @abstractmethod
    async def available_langs(self) -> list[str]: ...

    @abstractmethod
    async def recognize(self, images: Sequence[Image.Image], langs: str) -> OcrResult: ...

    async def searchable_pdf(self, images: Sequence[Image.Image], langs: str) -> bytes:
        raise OcrError("Searchable PDF export isn't supported by this engine.")
