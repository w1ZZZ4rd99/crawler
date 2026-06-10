"""JSON storage: JSON Lines stream or a pretty-printed array."""

import asyncio
import json
from pathlib import Path

import aiofiles

from src.storage.base import DataStorage


class JSONStorage(DataStorage):
    """Default mode appends one JSON object per line (handles large crawls).

    pretty=True buffers records and writes a formatted JSON array on close —
    convenient for small result sets.
    """

    def __init__(self, path: str | Path, pretty: bool = False) -> None:
        self.path = Path(path)
        self.pretty = pretty
        self._lock = asyncio.Lock()
        self._file = None
        self._buffer: list[dict] = []

    async def save(self, data: dict) -> None:
        if self.pretty:
            async with self._lock:
                self._buffer.append(data)
            return
        line = json.dumps(data, ensure_ascii=False) + "\n"
        async with self._lock:
            if self._file is None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._file = await aiofiles.open(self.path, "a", encoding="utf-8")
            await self._file.write(line)

    async def close(self) -> None:
        if self.pretty and self._buffer:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(self.path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(self._buffer, ensure_ascii=False, indent=2))
            self._buffer = []
        if self._file is not None:
            await self._file.close()
            self._file = None

    async def read_all(self) -> list[dict]:
        """Helper for demos/tests: load every record back."""
        if not self.path.exists():
            return []
        async with aiofiles.open(self.path, encoding="utf-8") as f:
            content = await f.read()
        content = content.strip()
        if not content:
            return []
        if content.startswith("["):  # pretty mode wrote a JSON array
            return json.loads(content)
        return [json.loads(line) for line in content.splitlines() if line.strip()]
