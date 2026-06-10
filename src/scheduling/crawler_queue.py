"""Priority URL queue with deduplication and processing state."""

import asyncio
import itertools

IDLE_POLL_INTERVAL = 0.05


class CrawlerQueue:
    """Async priority queue of (url, depth) items; higher priority is served first.

    A URL can be enqueued only once for the queue's lifetime. The queue is
    self-terminating: get_next() returns None once it is empty and no item
    is being processed, so workers can simply exit.
    """

    def __init__(self) -> None:
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._counter = itertools.count()  # tie-breaker for equal priorities
        self._seen: set[str] = set()
        self.in_progress = 0
        self.processed_count = 0
        self.failed: dict[str, str] = {}

    def add_url(self, url: str, priority: int = 0, depth: int = 0) -> bool:
        """Enqueue a URL once; return False for duplicates."""
        if url in self._seen:
            return False
        self._seen.add(url)
        # PriorityQueue pops the smallest tuple, so the priority is negated.
        self._queue.put_nowait((-priority, next(self._counter), url, depth))
        return True

    async def get_next(self) -> tuple[str, int] | None:
        """Return the next (url, depth), or None when the crawl is finished.

        Blocks while the queue is empty but other items are still in
        progress — they may produce new links.
        """
        while True:
            try:
                _, _, url, depth = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                if self.in_progress == 0:
                    return None
                await asyncio.sleep(IDLE_POLL_INTERVAL)
                continue
            self.in_progress += 1
            return url, depth

    def mark_processed(self, url: str) -> None:
        self.in_progress -= 1
        self.processed_count += 1

    def mark_failed(self, url: str, error: str) -> None:
        self.in_progress -= 1
        self.failed[url] = error

    def get_stats(self) -> dict:
        return {
            "queued": self._queue.qsize(),
            "in_progress": self.in_progress,
            "processed": self.processed_count,
            "failed": len(self.failed),
            "seen": len(self._seen),
        }
