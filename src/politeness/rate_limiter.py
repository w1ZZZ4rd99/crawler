"""Per-domain and global request rate limiting."""

import asyncio
import random
import time
from collections import defaultdict, deque

GLOBAL_KEY = "*"


class RateLimiter:
    """Spaces out requests: at most requests_per_second per domain (or globally).

    Each acquire() reserves the next free time slot of its key and sleeps
    until that slot, so concurrent callers line up one interval apart.
    """

    def __init__(
        self,
        requests_per_second: float | None = 1.0,
        per_domain: bool = True,
        min_delay: float = 0.0,
        jitter: float = 0.0,
    ) -> None:
        self.interval = 1.0 / requests_per_second if requests_per_second else 0.0
        self.per_domain = per_domain
        self.min_delay = min_delay
        self.jitter = jitter
        self._next_slot: dict[str, float] = defaultdict(float)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        # Monitoring counters.
        self.acquired_count = 0
        self.total_waited = 0.0
        self._recent: deque[float] = deque(maxlen=50)

    def _key(self, domain: str | None) -> str:
        return (domain or GLOBAL_KEY) if self.per_domain else GLOBAL_KEY

    async def acquire(
        self, domain: str | None = None, override_interval: float | None = None
    ) -> float:
        """Wait for the next free slot of the domain; return the waited time."""
        key = self._key(domain)
        interval = max(self.interval, self.min_delay, override_interval or 0.0)
        if self.jitter:
            interval += random.uniform(0.0, self.jitter)
        async with self._locks[key]:
            now = time.monotonic()
            slot = max(self._next_slot[key], now)
            self._next_slot[key] = slot + interval
        wait = max(slot - now, 0.0)
        if wait > 0:
            await asyncio.sleep(wait)
        self.acquired_count += 1
        self.total_waited += wait
        self._recent.append(time.monotonic())
        return wait

    def penalize(self, domain: str | None, delay: float) -> None:
        """Push the domain's next slot into the future (used after errors)."""
        key = self._key(domain)
        self._next_slot[key] = max(self._next_slot[key], time.monotonic() + delay)

    def current_rate(self) -> float:
        """Requests per second over the recent window."""
        if len(self._recent) < 2:
            return 0.0
        span = self._recent[-1] - self._recent[0]
        return (len(self._recent) - 1) / span if span > 0 else 0.0

    def get_stats(self) -> dict:
        avg = self.total_waited / self.acquired_count if self.acquired_count else 0.0
        return {
            "acquired": self.acquired_count,
            "total_wait": round(self.total_waited, 3),
            "avg_wait": round(avg, 3),
            "current_rps": round(self.current_rate(), 2),
        }
