"""Day 1: AsyncCrawler basic fetching, error handling and concurrency."""

import time

from src.crawler import AsyncCrawler
from tests.conftest import STATS_KEY


async def test_fetch_valid_url(server, crawler):
    text = await crawler.fetch_url(str(server.make_url("/ok")))

    assert text is not None
    assert "ok page" in text


async def test_fetch_404_returns_none(server, crawler):
    assert await crawler.fetch_url(str(server.make_url("/no-such-page"))) is None


async def test_fetch_unreachable_host_returns_none(crawler):
    # Port 1 is never listening: connection refused.
    assert await crawler.fetch_url("http://127.0.0.1:1/") is None


async def test_fetch_timeout_returns_none(server):
    async with AsyncCrawler(max_concurrent=2, timeout_total=0.3) as crawler:
        assert await crawler.fetch_url(str(server.make_url("/slow")) + "?d=2") is None


async def test_fetch_urls_returns_only_successes(server, crawler):
    ok_url = str(server.make_url("/ok"))
    results = await crawler.fetch_urls([ok_url, str(server.make_url("/missing"))])

    assert set(results) == {ok_url}


async def test_parallel_faster_than_sequential(server):
    urls = [str(server.make_url("/slow")) + f"?d=0.3&i={i}" for i in range(4)]
    async with AsyncCrawler(max_concurrent=4) as crawler:
        start = time.perf_counter()
        parallel = await crawler.fetch_urls(urls)
        parallel_time = time.perf_counter() - start

        start = time.perf_counter()
        for url in urls:
            await crawler.fetch_url(url)
        sequential_time = time.perf_counter() - start

    assert len(parallel) == 4
    # 4 concurrent 0.3s responses take ~0.3s vs ~1.2s sequentially.
    assert parallel_time < sequential_time * 0.7


async def test_concurrency_limit_is_respected(server):
    urls = [str(server.make_url("/slow")) + f"?d=0.2&i={i}" for i in range(6)]
    async with AsyncCrawler(max_concurrent=2) as crawler:
        await crawler.fetch_urls(urls)

    assert server.app[STATS_KEY]["max_active"] <= 2
