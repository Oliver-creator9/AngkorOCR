"""SQLite persistence: users, jobs, usage, retention.

WAL mode is on so reads never block on the writer. This is the only module
you need to touch if you outgrow SQLite.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    ui_lang TEXT NOT NULL DEFAULT 'en',
    ocr_langs TEXT NOT NULL,
    engine TEXT NOT NULL,
    output_format TEXT NOT NULL DEFAULT 'auto',
    preprocess INTEGER NOT NULL DEFAULT 1,
    tier TEXT NOT NULL DEFAULT 'free',
    is_blocked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage (
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    pages INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, date)
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    engine TEXT NOT NULL,
    langs TEXT NOT NULL,
    pages INTEGER NOT NULL,
    chars INTEGER NOT NULL,
    confidence REAL,
    duration_ms INTEGER NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    text TEXT,
    file_ids TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id, created_at);
"""


@dataclass
class UserSettings:
    user_id: int
    username: str | None
    first_name: str | None
    ui_lang: str
    ocr_langs: str
    engine: str
    output_format: str
    preprocess: bool
    tier: str
    is_blocked: bool


def _row_to_user(row: aiosqlite.Row) -> UserSettings:
    return UserSettings(
        user_id=row["user_id"],
        username=row["username"],
        first_name=row["first_name"],
        ui_lang=row["ui_lang"],
        ocr_langs=row["ocr_langs"],
        engine=row["engine"],
        output_format=row["output_format"],
        preprocess=bool(row["preprocess"]),
        tier=row["tier"],
        is_blocked=bool(row["is_blocked"]),
    )


class Database:
    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "Database.connect() was not called"
        return self._conn

    # -- users ------------------------------------------------------------

    async def upsert_user(
        self, user_id: int, username: str | None, first_name: str | None,
        default_langs: str, default_engine: str,
    ) -> UserSettings:
        await self.conn.execute(
            """
            INSERT INTO users (user_id, username, first_name, ocr_langs, engine, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username = excluded.username,
                                                first_name = excluded.first_name
            """,
            (user_id, username, first_name, default_langs, default_engine,
             datetime.now(timezone.utc).isoformat()),
        )
        await self.conn.commit()
        cursor = await self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        assert row is not None
        return _row_to_user(row)

    async def get_user(self, user_id: int) -> UserSettings | None:
        cursor = await self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return _row_to_user(row) if row else None

    async def set_langs(self, user_id: int, langs: str) -> None:
        await self.conn.execute("UPDATE users SET ocr_langs = ? WHERE user_id = ?", (langs, user_id))
        await self.conn.commit()

    async def set_engine(self, user_id: int, engine: str) -> None:
        await self.conn.execute("UPDATE users SET engine = ? WHERE user_id = ?", (engine, user_id))
        await self.conn.commit()

    async def set_format(self, user_id: int, fmt: str) -> None:
        await self.conn.execute("UPDATE users SET output_format = ? WHERE user_id = ?", (fmt, user_id))
        await self.conn.commit()

    async def set_preprocess(self, user_id: int, enabled: bool) -> None:
        await self.conn.execute(
            "UPDATE users SET preprocess = ? WHERE user_id = ?", (int(enabled), user_id)
        )
        await self.conn.commit()

    async def block_user(self, user_id: int, blocked: bool = True) -> None:
        await self.conn.execute(
            "UPDATE users SET is_blocked = ? WHERE user_id = ?", (int(blocked), user_id)
        )
        await self.conn.commit()

    async def set_tier(self, user_id: int, tier: str) -> None:
        await self.conn.execute("UPDATE users SET tier = ? WHERE user_id = ?", (tier, user_id))
        await self.conn.commit()

    # -- usage / quota ------------------------------------------------------

    async def pages_used_today(self, user_id: int, date: str) -> int:
        cursor = await self.conn.execute(
            "SELECT pages FROM usage WHERE user_id = ? AND date = ?", (user_id, date)
        )
        row = await cursor.fetchone()
        return row["pages"] if row else 0

    async def add_pages(self, user_id: int, date: str, pages: int) -> None:
        await self.conn.execute(
            """
            INSERT INTO usage (user_id, date, pages) VALUES (?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET pages = pages + excluded.pages
            """,
            (user_id, date, pages),
        )
        await self.conn.commit()

    # -- jobs ------------------------------------------------------------------

    async def record_job(
        self, *, user_id: int, chat_id: int, engine: str, langs: str, pages: int,
        chars: int, confidence: float | None, duration_ms: int, status: str,
        error: str | None, text: str | None, file_ids: str | None = None,
    ) -> int:
        cursor = await self.conn.execute(
            """
            INSERT INTO jobs (user_id, chat_id, engine, langs, pages, chars, confidence,
                               duration_ms, status, error, text, file_ids, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, chat_id, engine, langs, pages, chars, confidence, duration_ms,
             status, error, text, file_ids, datetime.now(timezone.utc).isoformat()),
        )
        await self.conn.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    async def get_job(self, job_id: int, user_id: int) -> aiosqlite.Row | None:
        cursor = await self.conn.execute(
            "SELECT * FROM jobs WHERE id = ? AND user_id = ?", (job_id, user_id)
        )
        return await cursor.fetchone()

    async def search_text(self, user_id: int, query: str, limit: int = 10) -> list[aiosqlite.Row]:
        cursor = await self.conn.execute(
            """
            SELECT * FROM jobs WHERE user_id = ? AND text LIKE ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (user_id, f"%{query}%", limit),
        )
        return list(await cursor.fetchall())

    # -- privacy ------------------------------------------------------------

    async def forget_user(self, user_id: int) -> None:
        await self.conn.execute("DELETE FROM jobs WHERE user_id = ?", (user_id,))
        await self.conn.execute("DELETE FROM usage WHERE user_id = ?", (user_id,))
        await self.conn.commit()

    async def purge_expired_text(self, retention_days: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        cursor = await self.conn.execute(
            "UPDATE jobs SET text = NULL, file_ids = NULL WHERE created_at < ? AND text IS NOT NULL",
            (cutoff,),
        )
        await self.conn.commit()
        return cursor.rowcount

    # -- admin ------------------------------------------------------------------

    async def stats_summary(self) -> dict:
        cursor = await self.conn.execute("SELECT COUNT(*) AS n FROM users")
        total_users = (await cursor.fetchone())["n"]

        cursor = await self.conn.execute(
            "SELECT COUNT(*) AS n FROM jobs WHERE created_at >= ?",
            ((datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),),
        )
        jobs_24h = (await cursor.fetchone())["n"]

        cursor = await self.conn.execute(
            "SELECT AVG(duration_ms) AS avg_ms FROM jobs WHERE created_at >= ? AND status = 'ok'",
            ((datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),),
        )
        avg_ms_24h = (await cursor.fetchone())["avg_ms"] or 0

        return {"total_users": total_users, "jobs_24h": jobs_24h, "avg_ms_24h": round(avg_ms_24h)}
