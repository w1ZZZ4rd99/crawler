"""CSV storage with automatic header detection."""

import asyncio
import csv
import io
import json
from pathlib import Path

import aiofiles

from src.storage.base import DataStorage


class CSVStorage(DataStorage):
    """Writes one row per page; the header comes from the first record's keys.

    Nested values (lists/dicts) are serialized as JSON strings; the csv
    module takes care of quoting commas, quotes and newlines.
    """

    def __init__(self, path: str | Path, encoding: str = "utf-8", delimiter: str = ",") -> None:
        self.path = Path(path)
        self.encoding = encoding
        self.delimiter = delimiter
        self._lock = asyncio.Lock()
        self._file = None
        self._fields: list[str] | None = None

    @staticmethod
    def _flatten(value):
        if isinstance(value, dict | list):
            return json.dumps(value, ensure_ascii=False)
        return "" if value is None else value

    def _format_row(self, row: list) -> str:
        buffer = io.StringIO()
        csv.writer(buffer, delimiter=self.delimiter).writerow(row)
        return buffer.getvalue()

    async def save(self, data: dict) -> None:
        async with self._lock:
            if self._file is None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._file = await aiofiles.open(
                    self.path, "w", encoding=self.encoding, newline=""
                )
                self._fields = list(data.keys())
                await self._file.write(self._format_row(self._fields))
            row = [self._flatten(data.get(field)) for field in self._fields]
            await self._file.write(self._format_row(row))

    async def close(self) -> None:
        if self._file is not None:
            await self._file.close()
            self._file = None
