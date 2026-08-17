"""Tests for the pieces that break silently in production.

Run with: pytest -q
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from aiogram.types import Chat, Message, PhotoSize
from PIL import Image, ImageDraw, ImageFont

from bot.config import Settings
from bot.db import Database
from bot.export import chunk_message, escape, fits_inline, to_docx, to_txt
from bot.middlewares import AlbumMiddleware, ThrottleMiddleware
from bot.ocr.pipeline import OcrService
from bot.texts import STRINGS, t


# --- export ------------------------------------------------------------------


def test_chunking_never_exceeds_limit_or_splits_words() -> None:
    text = " ".join(f"word{i}" for i in range(4000))
    chunks = chunk_message(text, limit=1000)
    assert all(len(c) <= 1000 for c in chunks)
    assert "".join(c.replace(" ", "") for c in chunks) == text.replace(" ", "")


def test_short_text_is_one_chunk() -> None:
    assert chunk_message("hello") == ["hello"]


def test_html_is_escaped_before_display() -> None:
    assert "<script>" not in escape("<script>alert(1)</script>")


def test_fits_inline_accounts_for_entity_expansion() -> None:
    # 3000 ampersands become 15000 characters once escaped.
    assert not fits_inline("&" * 3000)


def test_txt_has_bom_for_windows() -> None:
    assert to_txt("សួស្តី").startswith(b"\xef\xbb\xbf")


def test_docx_is_a_zip_container() -> None:
    assert to_docx("hello\n\nworld").startswith(b"PK")


# --- middlewares -------------------------------------------------------------


def test_throttle_enforces_capacity() -> None:
    throttle = ThrottleMiddleware(per_minute=5)
    assert sum(throttle._allow(1) for _ in range(10)) == 5
    assert throttle._allow(2) is True  # a different user is unaffected


def _photo_message(message_id: int, group: str | None) -> Message:
    return Message(
        message_id=message_id,
        date=datetime.now(),
        chat=Chat(id=1, type="private"),
        media_group_id=group,
        photo=[
            PhotoSize(
                file_id=f"f{message_id}", file_unique_id=f"u{message_id}",
                width=100, height=100, file_size=1000,
            )
        ],
    )


@pytest.mark.asyncio
async def test_album_collapses_to_one_handler_call() -> None:
    seen: list[int] = []

    async def handler(_event, data):
        seen.append(len(data.get("album", [])))

    middleware = AlbumMiddleware(latency=0.15)
    messages = [_photo_message(i, "group-1") for i in range(5, 0, -1)]
    await asyncio.gather(*(middleware(handler, m, {}) for m in messages))
    assert seen == [5]


@pytest.mark.asyncio
async def test_non_album_passes_through() -> None:
    seen: list[int] = []

    async def handler(_event, data):
        seen.append(len(data.get("album", [])))

    middleware = AlbumMiddleware(latency=0.05)
    await middleware(handler, _photo_message(1, None), {})
    assert seen == [0]


# --- i18n --------------------------------------------------------------------


def test_every_language_defines_every_key() -> None:
    base = set(STRINGS["en"])
    for lang, table in STRINGS.items():
        assert not base - set(table), f"{lang} is missing keys"


def test_unknown_language_falls_back_to_english() -> None:
    assert t("cancelled", "xx") == STRINGS["en"]["cancelled"]


# --- database ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_quota_accumulates_per_day(tmp_path) -> None:
    db = Database(str(tmp_path / "t.sqlite3"))
    await db.connect()
    await db.upsert_user(7, "u", "U", "eng", "tesseract")
    await db.add_pages(7, "2026-08-12", 3)
    await db.add_pages(7, "2026-08-12", 2)
    assert await db.pages_used_today(7, "2026-08-12") == 5
    assert await db.pages_used_today(7, "2026-08-13") == 0
    await db.close()


@pytest.mark.asyncio
async def test_forgetme_removes_everything(tmp_path) -> None:
    db = Database(str(tmp_path / "t.sqlite3"))
    await db.connect()
    await db.upsert_user(8, "u", "U", "eng", "tesseract")
    await db.record_job(
        user_id=8, chat_id=1, engine="tesseract", langs="eng", pages=1, chars=5,
        confidence=None, duration_ms=1, status="ok", error=None, text="secret",
    )
    await db.add_pages(8, "2026-08-12", 1)
    await db.forget_user(8)
    assert await db.search_text(8, "secret") == []
    assert await db.pages_used_today(8, "2026-08-12") == 0
    await db.close()


# --- OCR round trip ----------------------------------------------------------


def _rendered_page(text: str, angle: float = 0.0) -> Image.Image:
    img = Image.new("RGB", (900, 220), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
    except OSError:  # pragma: no cover
        font = ImageFont.load_default()
    draw.text((40, 80), text, fill="black", font=font)
    return img.rotate(angle, expand=True, fillcolor="white") if angle else img


@pytest.mark.asyncio
async def test_recognises_clean_text() -> None:
    settings = Settings(bot_token="1:test")  # type: ignore[call-arg]
    service = OcrService(settings)
    result, duration = await service.run(
        [_rendered_page("INVOICE 2026")], engine_name="tesseract",
        langs="eng", preprocess=True,
    )
    assert "INVOICE" in result.text.upper()
    assert duration > 0
    assert result.confidence and result.confidence > 50


@pytest.mark.asyncio
async def test_deskews_rotated_input() -> None:
    settings = Settings(bot_token="1:test")  # type: ignore[call-arg]
    service = OcrService(settings)
    result, _ = await service.run(
        [_rendered_page("TOTAL DUE", angle=-3.0)], engine_name="tesseract",
        langs="eng", preprocess=True,
    )
    assert "TOTAL" in result.text.upper()


@pytest.mark.asyncio
async def test_blank_page_reports_empty() -> None:
    settings = Settings(bot_token="1:test")  # type: ignore[call-arg]
    service = OcrService(settings)
    result, _ = await service.run(
        [Image.new("RGB", (600, 400), "white")], engine_name="tesseract",
        langs="eng", preprocess=True,
    )
    assert result.is_empty


def test_corrupt_bytes_raise_user_safe_error() -> None:
    from bot.ocr.base import OcrError

    with pytest.raises(OcrError):
        OcrService.decode_image(b"not an image at all")
