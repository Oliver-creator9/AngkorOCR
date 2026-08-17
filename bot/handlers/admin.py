"""Admin commands plus the global error handler."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import ErrorEvent, Message

from ..db import Database, UserSettings
from ..texts import t

log = logging.getLogger(__name__)
router = Router(name="admin")


async def _require_admin(message: Message, is_admin: bool, user: UserSettings) -> bool:
    if not is_admin:
        await message.answer(t("admin_only", user.ui_lang))
        return False
    return True


@router.message(Command("stats"))
async def cmd_stats(message: Message, user: UserSettings, db: Database, is_admin: bool = False) -> None:
    if not await _require_admin(message, is_admin, user):
        return
    stats = await db.stats_summary()
    await message.answer(
        t(
            "stats_summary", user.ui_lang,
            users=stats["total_users"], jobs=stats["jobs_24h"], avg_ms=stats["avg_ms_24h"],
        )
    )


@router.message(Command("block"))
async def cmd_block(
    message: Message, command: CommandObject, user: UserSettings, db: Database, is_admin: bool = False
) -> None:
    if not await _require_admin(message, is_admin, user):
        return
    target = (command.args or "").strip()
    if not target.isdigit():
        await message.answer(t("admin_usage", user.ui_lang))
        return
    await db.block_user(int(target), True)
    await message.answer(t("block_done", user.ui_lang, id=target))


@router.message(Command("unblock"))
async def cmd_unblock(
    message: Message, command: CommandObject, user: UserSettings, db: Database, is_admin: bool = False
) -> None:
    if not await _require_admin(message, is_admin, user):
        return
    target = (command.args or "").strip()
    if not target.isdigit():
        await message.answer(t("admin_usage", user.ui_lang))
        return
    await db.block_user(int(target), False)
    await message.answer(t("unblock_done", user.ui_lang, id=target))


@router.message(Command("grant"))
async def cmd_grant(
    message: Message, command: CommandObject, user: UserSettings, db: Database, is_admin: bool = False
) -> None:
    if not await _require_admin(message, is_admin, user):
        return
    parts = (command.args or "").split()
    if len(parts) != 2 or not parts[0].isdigit() or parts[1] not in {"free", "premium"}:
        await message.answer(t("admin_usage", user.ui_lang))
        return
    target_id, tier = parts
    await db.set_tier(int(target_id), tier)
    await message.answer(t("grant_done", user.ui_lang, id=target_id, tier=tier))


async def on_error(event: ErrorEvent) -> None:
    log.exception("unhandled update error", exc_info=event.exception)
    update = event.update
    message = update.message or (update.callback_query.message if update.callback_query else None)
    if isinstance(message, Message):
        await message.answer(t("error", "en"))
