"""Settings, language, quota, search — everything that isn't the OCR job itself."""

from __future__ import annotations

from datetime import date

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..config import Settings
from ..db import Database, UserSettings
from ..ocr.pipeline import OcrService
from ..texts import t

router = Router(name="commands")


def today() -> str:
    return date.today().isoformat()


def daily_limit(user: UserSettings, settings: Settings) -> int:
    return settings.premium_daily_pages if user.tier == "premium" else settings.free_daily_pages


@router.message(Command("start"))
async def cmd_start(message: Message, user: UserSettings) -> None:
    await message.answer(t("start", user.ui_lang))


@router.message(Command("help"))
async def cmd_help(message: Message, user: UserSettings) -> None:
    await message.answer(t("help", user.ui_lang))


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, user: UserSettings) -> None:
    await message.answer(t("cancelled", user.ui_lang))


@router.message(Command("lang"))
async def cmd_lang(
    message: Message, command: CommandObject, user: UserSettings, db: Database, ocr: OcrService
) -> None:
    args = (command.args or "").strip()
    if not args:
        installed = ", ".join(ocr.installed_langs) or "—"
        await message.answer(t("lang_current", user.ui_lang, langs=user.ocr_langs, installed=installed))
        return

    ok, missing = ocr.validate_langs(args)
    if not ok:
        await message.answer(t("lang_invalid", user.ui_lang, missing=", ".join(missing)))
        return

    await db.set_langs(user.user_id, args)
    await message.answer(t("lang_set", user.ui_lang, langs=args))


@router.message(Command("engine"))
async def cmd_engine(
    message: Message, command: CommandObject, user: UserSettings, db: Database, ocr: OcrService
) -> None:
    args = (command.args or "").strip().lower()
    if not args:
        await message.answer(t("engine_current", user.ui_lang, engine=user.engine))
        return

    if args not in ocr.engine_names:
        await message.answer(t("engine_unavailable", user.ui_lang))
        return

    await db.set_engine(user.user_id, args)
    await message.answer(t("engine_set", user.ui_lang, engine=args))


@router.message(Command("settings"))
async def cmd_settings(message: Message, user: UserSettings) -> None:
    await message.answer(
        t("settings_summary", user.ui_lang, langs=user.ocr_langs, engine=user.engine, tier=user.tier)
    )


@router.message(Command("quota"))
async def cmd_quota(message: Message, user: UserSettings, db: Database, settings: Settings) -> None:
    used = await db.pages_used_today(user.user_id, today())
    await message.answer(t("quota_status", user.ui_lang, used=used, limit=daily_limit(user, settings)))


@router.message(Command("privacy"))
async def cmd_privacy(message: Message, user: UserSettings, settings: Settings) -> None:
    await message.answer(t("privacy_notice", user.ui_lang, days=settings.history_retention_days))


@router.message(Command("forgetme"))
async def cmd_forgetme(message: Message, user: UserSettings, db: Database) -> None:
    await db.forget_user(user.user_id)
    await message.answer(t("forgetme_done", user.ui_lang))


@router.message(Command("search"))
async def cmd_search(
    message: Message, command: CommandObject, user: UserSettings, db: Database
) -> None:
    query = (command.args or "").strip()
    if not query:
        await message.answer(t("search_usage", user.ui_lang))
        return

    rows = await db.search_text(user.user_id, query)
    if not rows:
        await message.answer(t("search_no_results", user.ui_lang, query=query))
        return

    lines = [t("search_results_header", user.ui_lang, count=len(rows))]
    for row in rows:
        snippet = (row["text"] or "")[:200]
        lines.append(
            t(
                "search_result_item", user.ui_lang,
                date=row["created_at"][:10], chars=row["chars"], snippet=snippet,
            )
        )
    await message.answer("\n\n".join(lines))
