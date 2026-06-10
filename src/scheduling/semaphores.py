"""Global and per-domain concurrency limits."""

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager


class SemaphoreManager:
    """Caps total concurrency and the number of concurrent requests per domain."""

    def __init__(self, global_limit: int = 10, per_domain_limit: int = 3) -> None:
        self._global = asyncio.Semaphore(global_limit)
        self._per_domain: dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(per_domain_limit)
        )
        self.active_total = 0
        self.active_by_domain: dict[str, int] = defaultdict(int)

    @asynccontextmanager
    async def limit(self, domain: str):
        """Hold one global slot and one slot of the domain for the duration."""
        async with self._global, self._per_domain[domain]:
            self.active_total += 1
            self.active_by_domain[domain] += 1
            try:
                yield
            finally:
                self.active_total -= 1
                self.active_by_domain[domain] -= 1
