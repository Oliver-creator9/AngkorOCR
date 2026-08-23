"""The part that actually does the job: media in, text out."""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Sequence

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.types import Message
from PIL import Image

from ..config import Settings
from ..db import Database, UserSettings
from ..export import chunk_message, escape
from ..ocr.base import OcrError, OcrResult
from ..ocr.pipeline import OcrService
from ..ocr.qrcode import decode_qr_codes
from ..texts import t
from .commands import daily_limit, today

log = logging.getLogger(__name__)
router = Router(name="ocr")

IMAGE_MIME_PREFIX = "image/"
PDF_MIME = "application/pdf"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic"}


# --- input collection --------------------------------------------------------


def _photo_sources(messages: Sequence[Message]) -> list[tuple[str, int]]:
    """Largest available size of each photo: (file_id, size_bytes)."""
    out = []
    for msg in messages:
        if msg.photo:
            best = msg.photo[-1]
            out.append((best.file_id, best.file_size or 0))
    return out


def _is_supported_document(msg: Message) -> bool:
    doc = msg.document
    if doc is None:
        return False
    mime = (doc.mime_type or "").lower()
    if mime.startswith(IMAGE_MIME_PREFIX) or mime == PDF_MIME:
        return True
    name = (doc.file_name or "").lower()
    return any(name.endswith(ext) for ext in IMAGE_EXTS) or name.endswith(".pdf")


async def _download(bot: Bot, file_id: str) -> bytes:
    buf = io.BytesIO()
    await bot.download(file_id, destination=buf)
    return buf.getvalue()


# --- delivery ----------------------------------------------------------------

async def _deliver(message: Message, result: OcrResult) -> None:
    """Just the text, chunked to fit Telegram's per-message cap. Plain text —
    no <pre> block, so there's no tap-to-copy affordance, just a normal message."""
    for chunk in chunk_message(result.text):
        await message.reply(escape(chunk))


# --- main handlers -----------------------------------------------------------


async def _process(
    message: Message,
    messages: Sequence[Message],
    *,
    bot: Bot,
    user: UserSettings,
    db: Database,
    ocr: OcrService,
    settings: Settings,
) -> None:
    sources = _photo_sources(messages)
    is_pdf = False

    if not sources:
        doc = message.document
        if doc is None:
            return
        mime = (doc.mime_type or "").lower()
        is_pdf = mime == PDF_MIME or (doc.file_name or "").lower().endswith(".pdf")
        sources = [(doc.file_id, doc.file_size or 0)]

    # Size gate before we spend bandwidth.
    oversized = next((s for _, s in sources if s > settings.max_file_bytes), None)
    if oversized:
        await message.reply(
            t("too_big", user.ui_lang, size=round(oversized / 1024 / 1024, 1),
              limit=settings.max_file_mb)
        )
        return

    used = await db.pages_used_today(user.user_id, today())
    limit = daily_limit(user, settings)
    if used >= limit:
        await message.reply(t("quota_exceeded", user.ui_lang, limit=limit))
        return

    page_word = f" {len(sources)} pages" if len(sources) > 1 else ""
    status = await message.reply(t("processing", user.ui_lang, pages=page_word))
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

    images: list[Image.Image] = []
    try:
        for file_id, _ in sources:
            raw = await _download(bot, file_id)
            if is_pdf:
                images.extend(ocr.pdf_to_images(raw, settings.max_pdf_pages))
            else:
                images.append(ocr.decode_image(raw))

        if not images:
            await status.edit_text(t("unsupported", user.ui_lang))
            return

        remaining = limit - used
        if len(images) > remaining:
            images = images[:remaining]
            await message.reply(
                f"Only the first {remaining} page(s) fit in today's quota."
            )

        result, duration_ms = await ocr.run(
            images,
            engine_name=user.engine,
            langs=user.ocr_langs,
            preprocess=user.preprocess,
        )

        qr_codes: list[str] = []
        for image in images:
            qr_codes.extend(await asyncio.to_thread(decode_qr_codes, image))
        if qr_codes:
            qr_block = "\n".join(dict.fromkeys(qr_codes))
            result.text = f"{qr_block}\n\n{result.text}".strip() if result.text.strip() else qr_block

        if result.is_empty:
            await status.edit_text(t("no_text", user.ui_lang))
            await db.record_job(
                user_id=user.user_id, chat_id=message.chat.id, engine=user.engine,
                langs=user.ocr_langs, pages=len(images), chars=0, confidence=None,
                duration_ms=duration_ms, status="ok", error="empty", text=None,
            )
            return

        job_id = await db.record_job(
            user_id=user.user_id,
            chat_id=message.chat.id,
            engine=result.engine,
            langs=user.ocr_langs,
            pages=len(images),
            chars=result.char_count,
            confidence=result.confidence,
            duration_ms=duration_ms,
            status="ok",
            error=None,
            text=result.text if settings.store_text_history else None,
            file_ids=",".join(f for f, _ in sources),
        )
        await db.add_pages(user.user_id, today(), len(images))

        await status.delete()
        await _deliver(message, result)

        log.info(
            "ocr ok",
            extra={"user_id": user.user_id, "job_id": job_id,
                   "engine": result.engine, "duration_ms": duration_ms},
        )

    except OcrError as exc:
        await status.edit_text(str(exc))
        await db.record_job(
            user_id=user.user_id, chat_id=message.chat.id, engine=user.engine,
            langs=user.ocr_langs, pages=len(sources), chars=0, confidence=None,
            duration_ms=0, status="failed", error=str(exc), text=None,
        )
    except Exception:  # noqa: BLE001
        log.exception("ocr crashed", extra={"user_id": user.user_id})
        await status.edit_text(t("error", user.ui_lang))
        await db.record_job(
            user_id=user.user_id, chat_id=message.chat.id, engine=user.engine,
            langs=user.ocr_langs, pages=len(sources), chars=0, confidence=None,
            duration_ms=0, status="failed", error="internal", text=None,
        )
    finally:
        for img in images:
            try:
                img.close()
            except Exception:  # noqa: BLE001
                pass


@router.message(F.photo)
async def on_photo(
    message: Message, bot: Bot, user: UserSettings, db: Database,
    ocr: OcrService, settings: Settings, album: list[Message] | None = None,
) -> None:
    await _process(message, album or [message], bot=bot, user=user, db=db,
                   ocr=ocr, settings=settings)


@router.message(F.document)
async def on_document(
    message: Message, bot: Bot, user: UserSettings, db: Database,
    ocr: OcrService, settings: Settings, album: list[Message] | None = None,
) -> None:
    batch = [m for m in (album or [message]) if _is_supported_document(m)]
    if not batch:
        await message.reply(t("unsupported", user.ui_lang))
        return
    await _process(batch[0], batch, bot=bot, user=user, db=db, ocr=ocr, settings=settings)


# --- fallback ----------------------------------------------------------------


@router.message(F.text & ~F.text.startswith("/"))
async def on_text(message: Message, user: UserSettings) -> None:
    await message.reply(t("start", user.ui_lang))


@router.message(F.video | F.audio | F.voice | F.sticker | F.video_note)
async def on_unsupported(message: Message, user: UserSettings) -> None:
    await message.reply(t("unsupported", user.ui_lang))
