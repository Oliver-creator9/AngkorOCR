"""Composition root — wiring, webhook/polling, lifecycle."""

from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

from .config import Settings
from .db import Database
from .handlers import admin, commands
from .handlers import ocr as ocr_handlers
from .middlewares import AlbumMiddleware, ThrottleMiddleware, UserContextMiddleware
from .ocr.pipeline import OcrService

log = logging.getLogger(__name__)


def _build_dispatcher(settings: Settings, db: Database, ocr: OcrService) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp["db"] = db
    dp["ocr"] = ocr
    dp["settings"] = settings

    user_mw = UserContextMiddleware(db, settings)
    dp.message.middleware(user_mw)
    dp.message.middleware(ThrottleMiddleware(settings.burst_per_minute))
    dp.message.middleware(AlbumMiddleware())
    dp.callback_query.middleware(user_mw)

    dp.include_router(commands.router)
    dp.include_router(ocr_handlers.router)
    dp.include_router(admin.router)

    dp.errors.register(admin.on_error)
    return dp


async def _purge_loop(db: Database, retention_days: int) -> None:
    while True:
        await asyncio.sleep(3600)
        try:
            purged = await db.purge_expired_text(retention_days)
            if purged:
                log.info("purged expired text", extra={"rows": purged})
        except Exception:  # noqa: BLE001
            log.exception("retention purge failed")


async def _run_webhook(bot: Bot, dp: Dispatcher, settings: Settings) -> None:
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

    webhook_path = "/webhook"
    await bot.set_webhook(
        f"{settings.webhook_base}{webhook_path}", secret_token=settings.webhook_secret or None
    )

    app = web.Application()
    SimpleRequestHandler(
        dispatcher=dp, bot=bot, secret_token=settings.webhook_secret or None
    ).register(app, path=webhook_path)
    setup_application(app, dp, bot=bot)

    async def health(_request: web.Request) -> web.Response:
        return web.Response(text="ok")

    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.webhook_port)
    await site.start()
    log.info("webhook listening on :%s%s", settings.webhook_port, webhook_path)

    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


async def main() -> None:
    log_kwargs = {"level": logging.INFO}
    logging.basicConfig(**log_kwargs)

    settings = Settings()  # type: ignore[call-arg]
    os.makedirs("data", exist_ok=True)

    db = Database("data/bot.sqlite3")
    await db.connect()

    ocr = OcrService(settings)
    await ocr.startup()

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = _build_dispatcher(settings, db, ocr)
    purge_task = asyncio.create_task(_purge_loop(db, settings.history_retention_days))

    try:
        if settings.webhook_base:
            await _run_webhook(bot, dp, settings)
        else:
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot)
    finally:
        purge_task.cancel()
        await ocr.shutdown()
        await db.close()
        await bot.session.close()
