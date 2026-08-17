"""Chunking, escaping, and file formats for delivering OCR text back to the user."""

from __future__ import annotations

import html
import io
from datetime import datetime

from docx import Document

TELEGRAM_MESSAGE_LIMIT = 4096
INLINE_BUDGET = 3500  # leaves room for the <pre> wrapper and the meta line


def escape(text: str) -> str:
    return html.escape(text)


def chunk_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Word-aware wrap: no chunk exceeds `limit`, and no word is split unless
    the word itself is longer than `limit`."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""
    for word in text.split(" "):
        candidate = f"{current} {word}" if current else word
        if len(candidate) <= limit:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(word) > limit:
            for i in range(0, len(word), limit):
                chunks.append(word[i : i + limit])
        else:
            current = word

    if current:
        chunks.append(current)
    return chunks


def fits_inline(text: str) -> bool:
    """Whether the escaped text fits in a single Telegram message."""
    return len(escape(text)) <= INLINE_BUDGET


def as_code_block(text: str) -> str:
    return f"<pre>{escape(text)}</pre>"


def to_txt(text: str) -> bytes:
    return b"\xef\xbb\xbf" + text.encode("utf-8")


def to_docx(text: str) -> bytes:
    doc = Document()
    for paragraph in text.split("\n\n"):
        doc.add_paragraph(paragraph)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def timestamped_name(prefix: str, ext: str) -> str:
    return f"{prefix}_{datetime.now():%Y%m%d_%H%M%S}.{ext}"
