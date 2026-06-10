"""Day 5: RetryStrategy behaviour and crawler integration."""

import time

import pytest
from aiohttp.test_utils import TestServer

from examples.demo_server import HITS_KEY, create_app
from src.crawler import AsyncCrawler
from src.resilience.errors import PermanentError, TransientError
from src.resilience.retry import RetryStrategy


def fast_strategy(**kwargs) -> RetryStrategy:
    kwargs.setdefault("max_retries", 3)
    kwargs.setdefault("base_delay", 0.02)
    kwargs.setdefault("jitter", 0.0)
    return RetryStrategy(**kwargs)


class Flaky:
    """Coroutine stub failing a given number of times before succeeding."""

    def __init__(self, failures: int, exc_factory=TransientError):
        self.failures = failures
        self.exc_factory = exc_factory
        self.calls = 0

    async def __call__(self, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.exc_factory(f"failure {self.calls}")
        return "ok"


async def test_retries_until_success():
    strategy = fast_strategy()
    flaky = Flaky(failures=2)

    assert await strategy.execute_with_retry(flaky) == "ok"
    assert flaky.calls == 3
    assert strategy.total_retries == 2
    assert strategy.successful_retries == 1


async def test_permanent_error_is_not_retried():
    strategy = fast_strategy()
    flaky = Flaky(failures=5, exc_factory=PermanentError)

    with pytest.raises(PermanentError):
        await strategy.execute_with_retry(flaky)
    assert flaky.calls == 1


async def test_gives_up_after_max_retries():
    strategy = fast_strategy(max_retries=2)
    flaky = Flaky(failures=10)

    with pytest.raises(TransientError):
        await strategy.execute_with_retry(flaky)
    assert flaky.calls == 3  # initial attempt + 2 retries


async def test_exponential_backoff_delays():
    strategy = fast_strategy(max_retries=2, base_delay=0.1, backoff_factor=2.0)
    flaky = Flaky(failures=2)

    start = time.monotonic()
    await strategy.execute_with_retry(flaky)
    elapsed = time.monotonic() - start

    # Delays: 0.1 then 0.2 -> at least ~0.3s in total.
    assert elapsed >= 0.25


async def test_retry_after_overrides_short_backoff():
    strategy = fast_strategy(max_retries=1, base_delay=0.01)
    flaky = Flaky(failures=1, exc_factory=lambda msg: TransientError(msg, retry_after=0.3))

    start = time.monotonic()
    await strategy.execute_with_retry(flaky)
    elapsed = time.monotonic() - start

    assert elapsed >= 0.25


async def test_on_attempt_kwargs_are_injected():
    strategy = fast_strategy(max_retries=2)
    seen: list[float] = []

    async def func(scale: float = 0.0):
        seen.append(scale)
        if len(seen) < 3:
            raise TransientError("again")
        return "done"

    await strategy.execute_with_retry(func, on_attempt=lambda n: {"scale": 1.0 + n})

    assert seen == [1.0, 2.0, 3.0]


@pytest.fixture
async def flaky_site():
    server = TestServer(create_app(sections=1, items=1))
    await server.start_server()
    yield server
    await server.close()


async def test_crawler_retries_503_until_success(flaky_site):
    crawler = AsyncCrawler(
        max_concurrent=2, retry_strategy=fast_strategy(), progress_interval=60
    )
    async with crawler:
        results = await crawler.crawl(
            [str(flaky_site.make_url("/flaky"))], max_pages=5, max_depth=0
        )

    flaky_url = str(flaky_site.make_url("/flaky"))
    assert flaky_url in results
    assert flaky_site.app[HITS_KEY]["/flaky"] == 3  # 2 failures + 1 success


async def test_crawler_does_not_retry_404(flaky_site):
    crawler = AsyncCrawler(
        max_concurrent=2, retry_strategy=fast_strategy(), progress_interval=60
    )
    async with crawler:
        await crawler.crawl([str(flaky_site.make_url("/no-route"))], max_pages=5, max_depth=0)

    assert flaky_site.app[HITS_KEY]["/no-route"] == 1
    failed = crawler.failed_urls[str(flaky_site.make_url("/no-route"))]
    assert "PermanentError" in failed
    assert crawler.error_stats["PermanentError"] == 1


async def test_crawler_retries_timeouts(flaky_site):
    crawler = AsyncCrawler(
        max_concurrent=2,
        timeout_total=0.3,
        retry_strategy=fast_strategy(max_retries=1),
        progress_interval=60,
    )
    async with crawler:
        await crawler.crawl([str(flaky_site.make_url("/hang"))], max_pages=5, max_depth=0)

    assert flaky_site.app[HITS_KEY]["/hang"] == 2  # original attempt + 1 retry
    failed = crawler.failed_urls[str(flaky_site.make_url("/hang"))]
    assert "TransientError" in failed
