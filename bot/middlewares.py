"""Cross-cutting concerns applied to every update."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any, Awaitable, Callable, DefaultDict

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, User

from .config import Settings
from .db import Database
from .texts import t

log = logging.getLogger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class UserContextMiddleware(BaseMiddleware):
    """Loads (or creates) the user row and puts it in handler data as `user`."""

    def __init__(self, db: Database, settings: Settings) -> None:
        self._db = db
        self._settings = settings

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user: User | None = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        user = await self._db.upsert_user(
            tg_user.id,
            tg_user.username,
            tg_user.first_name,
            self._settings.default_langs,
            self._settings.default_engine,
        )
        if user.is_blocked:
            log.info("dropped update from blocked user", extra={"user_id": tg_user.id})
            return None

        data["user"] = user
        data["is_admin"] = tg_user.id in self._settings.admins
        return await handler(event, data)


class ThrottleMiddleware(BaseMiddleware):
    """Token bucket per user. Protects the worker pool from a single spammer."""

    def __init__(self, per_minute: int) -> None:
        self._capacity = float(per_minute)
        self._rate = per_minute / 60.0
        self._tokens: DefaultDict[int, float] = defaultdict(lambda: float(per_minute))
        self._last: DefaultDict[int, float] = defaultdict(time.monotonic)
        self._warned: dict[int, float] = {}

    def _allow(self, user_id: int) -> bool:
        now = time.monotonic()
        elapsed = now - self._last[user_id]
        self._last[user_id] = now
        self._tokens[user_id] = min(
            self._capacity, self._tokens[user_id] + elapsed * self._rate
        )
        if self._tokens[user_id] < 1.0:
            return False
        self._tokens[user_id] -= 1.0
        return True

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user: User | None = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        if self._allow(tg_user.id):
            return await handler(event, data)

        # Warn at most once every 20s so we don't amplify the flood.
        now = time.monotonic()
        if isinstance(event, Message) and now - self._warned.get(tg_user.id, 0) > 20:
            self._warned[tg_user.id] = now
            user = data.get("user")
            lang = getattr(user, "ui_lang", "en")
            await event.answer(t("rate_limited", lang))
        return None


class AlbumMiddleware(BaseMiddleware):
    """Batches Telegram media groups into a single handler call.

    Telegram delivers an album as N separate updates with a shared media_group_id.
    Without this, sending 10 pages of a book fires 10 independent OCR jobs and the
    user gets 10 disordered replies instead of one document.
    """

    def __init__(self, latency: float = 1.2, max_items: int = 20) -> None:
        self._latency = latency
        self._max = max_items
        self._albums: DefaultDict[str, list[Message]] = defaultdict(list)
        self._locks: DefaultDict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if not isinstance(event, Message) or event.media_group_id is None:
            return await handler(event, data)

        group_id = event.media_group_id
        async with self._locks[group_id]:
            self._albums[group_id].append(event)
            is_first = len(self._albums[group_id]) == 1

        if not is_first:
            return None  # a sibling update is already waiting to flush the batch

        await asyncio.sleep(self._latency)
        async with self._locks[group_id]:
            batch = self._albums.pop(group_id, [])
            self._locks.pop(group_id, None)

        batch.sort(key=lambda m: m.message_id)
        data["album"] = batch[: self._max]
        return await handler(batch[0], data)
