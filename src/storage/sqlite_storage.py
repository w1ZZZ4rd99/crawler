"""SQLite storage with batched inserts (aiosqlite)."""

import asyncio
import json
from pathlib import Path

import aiosqlite

from src.storage.base import DataStorage

SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    text TEXT,
    links TEXT,
    metadata TEXT,
    crawled_at TEXT,
    status_code INTEGER,
    content_type TEXT
);
CREATE INDEX IF NOT EXISTS idx_pages_crawled_at ON pages (crawled_at);
"""

INSERT_SQL = """
INSERT OR REPLACE INTO pages
    (url, title, text, links, metadata, crawled_at, status_code, content_type)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""


class SQLiteStorage(DataStorage):
    """Buffers rows and flushes them with executemany for throughput."""

    def __init__(self, path: str | Path, batch_size: int = 50) -> None:
        self.path = Path(path)
        self.batch_size = batch_size
        self._db: aiosqlite.Connection | None = None
        self._buffer: list[tuple] = []
        self._lock = asyncio.Lock()

    async def init_db(self) -> None:
        if self._db is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(self.path)
            await self._db.executescript(SCHEMA)
            await self._db.commit()

    @staticmethod
    def _to_row(data: dict) -> tuple:
        return (
            data.get("url"),
            data.get("title"),
            data.get("text"),
            json.dumps(data.get("links", []), ensure_ascii=False),
            json.dumps(data.get("metadata", {}), ensure_ascii=False),
            data.get("crawled_at"),
            data.get("status_code"),
            data.get("content_type"),
        )

    async def save(self, data: dict) -> None:
        await self.init_db()
        async with self._lock:
            self._buffer.append(self._to_row(data))
            if len(self._buffer) >= self.batch_size:
                await self._flush_locked()

    async def _flush_locked(self) -> None:
        if self._buffer:
            await self._db.executemany(INSERT_SQL, self._buffer)
            await self._db.commit()
            self._buffer.clear()

    async def flush(self) -> None:
        async with self._lock:
            await self._flush_locked()

    async def count(self) -> int:
        await self.init_db()
        await self.flush()
        async with self._db.execute("SELECT COUNT(*) FROM pages") as cursor:
            (total,) = await cursor.fetchone()
        return total

    async def fetch_pages(self, limit: int = 5) -> list[dict]:
        """Helper for demos/tests: read several saved rows back."""
        await self.init_db()
        await self.flush()
        query = "SELECT url, title, status_code, crawled_at FROM pages LIMIT ?"
        async with self._db.execute(query, (limit,)) as cursor:
            rows = await cursor.fetchall()
        return [
            {"url": r[0], "title": r[1], "status_code": r[2], "crawled_at": r[3]} for r in rows
        ]

    async def close(self) -> None:
        if self._db is not None:
            await self.flush()
            await self._db.close()
            self._db = None
