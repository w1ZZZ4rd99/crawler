"""Day 5: circuit breaker transitions and crawl integration."""

import asyncio

from aiohttp import web
from aiohttp.test_utils import TestServer

from src.crawler import AsyncCrawler
from src.resilience.circuit_breaker import (
    STATE_CLOSED,
    STATE_HALF_OPEN,
    STATE_OPEN,
    CircuitBreaker,
)
from src.resilience.retry import RetryStrategy

DOMAIN = "example.com"


def test_opens_after_consecutive_failures():
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)

    for _ in range(2):
        breaker.record_failure(DOMAIN)
    assert breaker.state(DOMAIN) == STATE_CLOSED
    assert breaker.allow(DOMAIN)

    breaker.record_failure(DOMAIN)
    assert breaker.state(DOMAIN) == STATE_OPEN
    assert not breaker.allow(DOMAIN)


def test_success_resets_failure_count():
    breaker = CircuitBreaker(failure_threshold=2)

    breaker.record_failure(DOMAIN)
    breaker.record_success(DOMAIN)
    breaker.record_failure(DOMAIN)

    assert breaker.state(DOMAIN) == STATE_CLOSED


async def test_half_open_after_cooldown_and_recovery():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.15)

    breaker.record_failure(DOMAIN)
    assert breaker.state(DOMAIN) == STATE_OPEN

    await asyncio.sleep(0.2)
    assert breaker.state(DOMAIN) == STATE_HALF_OPEN
    assert breaker.allow(DOMAIN)  # one probe request is allowed

    breaker.record_success(DOMAIN)
    assert breaker.state(DOMAIN) == STATE_CLOSED


async def test_failed_probe_reopens_circuit():
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.15)

    breaker.record_failure(DOMAIN)
    await asyncio.sleep(0.2)
    assert breaker.state(DOMAIN) == STATE_HALF_OPEN

    breaker.record_failure(DOMAIN)
    assert breaker.state(DOMAIN) == STATE_OPEN


async def test_crawl_fails_fast_once_circuit_opens():
    hits = {"errors": 0}

    async def index(request: web.Request) -> web.Response:
        links = "".join(f'<a href="/broken/{i}">{i}</a>' for i in range(6))
        return web.Response(
            text=f"<html><body>{links}</body></html>", content_type="text/html"
        )

    async def broken(request: web.Request) -> web.Response:
        hits["errors"] += 1
        return web.Response(status=500)

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/broken/{i}", broken)
    server = TestServer(app)
    await server.start_server()
    try:
        crawler = AsyncCrawler(
            max_concurrent=1,  # serialize workers for a deterministic order
            retry_strategy=RetryStrategy(max_retries=0),
            circuit_breaker=CircuitBreaker(failure_threshold=2, recovery_timeout=60),
            progress_interval=60,
        )
        async with crawler:
            await crawler.crawl([str(server.make_url("/"))], max_pages=20, max_depth=1)

        # Only the first two pages hit the server; the rest failed fast.
        assert hits["errors"] == 2
        assert crawler.error_stats["CircuitOpenError"] == 4
        assert sum(1 for e in crawler.failed_urls.values() if "CircuitOpenError" in e) == 4
    finally:
        await server.close()
