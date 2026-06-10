"""Day 3: CrawlerQueue priorities, dedup and termination."""

import asyncio

from src.scheduling.crawler_queue import CrawlerQueue


async def test_priority_order():
    queue = CrawlerQueue()
    queue.add_url("http://x/low", priority=0)
    queue.add_url("http://x/high", priority=10)
    queue.add_url("http://x/mid", priority=5)

    served = []
    for _ in range(3):
        url, _ = await queue.get_next()
        served.append(url)
        queue.mark_processed(url)

    assert served == ["http://x/high", "http://x/mid", "http://x/low"]


async def test_duplicate_urls_are_rejected():
    queue = CrawlerQueue()

    assert queue.add_url("http://x/a") is True
    assert queue.add_url("http://x/a") is False

    url, _ = await queue.get_next()
    queue.mark_processed(url)
    assert await queue.get_next() is None


async def test_get_next_returns_none_when_empty_and_idle():
    assert await CrawlerQueue().get_next() is None


async def test_get_next_waits_while_items_in_progress():
    queue = CrawlerQueue()
    queue.add_url("http://x/first")
    first, _ = await queue.get_next()  # now in_progress == 1

    consumer = asyncio.create_task(queue.get_next())
    await asyncio.sleep(0.15)
    assert not consumer.done()  # queue empty, but the producer may add links

    queue.add_url("http://x/second")
    queue.mark_processed(first)
    second, _ = await consumer
    assert second == "http://x/second"
    queue.mark_processed(second)


async def test_depth_is_preserved():
    queue = CrawlerQueue()
    queue.add_url("http://x/deep", depth=4)

    _, depth = await queue.get_next()
    assert depth == 4


async def test_stats():
    queue = CrawlerQueue()
    queue.add_url("http://x/a")
    queue.add_url("http://x/b")
    url, _ = await queue.get_next()
    queue.mark_failed(url, "boom")

    assert queue.get_stats() == {
        "queued": 1,
        "in_progress": 0,
        "processed": 0,
        "failed": 1,
        "seen": 2,
    }
