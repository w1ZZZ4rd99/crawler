"""Abstract storage interface for crawled pages."""

from abc import ABC, abstractmethod


class DataStorage(ABC):
    """Asynchronous sink for crawled page records."""

    @abstractmethod
    async def save(self, data: dict) -> None:
        """Persist one page record."""

    async def save_many(self, items: list[dict]) -> None:
        for item in items:
            await self.save(item)

    @abstractmethod
    async def close(self) -> None:
        """Flush buffers and release resources."""

    async def __aenter__(self) -> "DataStorage":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()
