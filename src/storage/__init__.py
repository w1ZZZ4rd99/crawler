"""Asynchronous storage backends for crawled data."""

from src.storage.base import DataStorage
from src.storage.csv_storage import CSVStorage
from src.storage.json_storage import JSONStorage
from src.storage.sqlite_storage import SQLiteStorage


class CompositeStorage(DataStorage):
    """Fans every record out to several storages at once."""

    def __init__(self, storages: list[DataStorage]) -> None:
        self.storages = list(storages)

    async def save(self, data: dict) -> None:
        for storage in self.storages:
            await storage.save(data)

    async def close(self) -> None:
        for storage in self.storages:
            await storage.close()


__all__ = ["CSVStorage", "CompositeStorage", "DataStorage", "JSONStorage", "SQLiteStorage"]
