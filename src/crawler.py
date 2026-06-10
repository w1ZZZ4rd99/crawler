"""Core asynchronous HTTP client and crawling engine built on aiohttp."""

import asyncio
import contextlib
import time
from collections import Counter
from urllib.parse import urlparse

import aiohttp
from loguru import logger

from src.parsing.html_parser import HTMLParser
from src.politeness.rate_limiter import RateLimiter
from src.politeness.robots import RobotsParser
from src.resilience.circuit_breaker import CircuitBreaker, CircuitOpenError
from src.resilience.errors import CrawlerError, classify_exception, error_from_status
from src.resilience.retry import RetryStrategy
from src.scheduling.crawler_queue import CrawlerQueue
from src.scheduling.semaphores import SemaphoreManager
from src.scheduling.url_filter import URLFilter, normalize_host

DEFAULT_USER_AGENT = "AsyncCrawler/1.0 (educational project)"


class AsyncCrawler:
    """Downloads web pages concurrently with a configurable concurrency limit."""

    def __init__(
        self,
        max_concurrent: int = 10,
        max_depth: int = 2,
        per_domain_limit: int = 3,
        timeout_total: float = 30.0,
        timeout_connect: float = 10.0,
        timeout_read: float = 10.0,
        progress_interval: float = 2.0,
        parser: HTMLParser | None = None,
        requests_per_second: float | None = None,
        per_domain_rate: bool = True,
        min_delay: float = 0.0,
        jitter: float = 0.0,
        respect_robots: bool = True,
        user_agent: str = DEFAULT_USER_AGENT,
        retry_strategy: RetryStrategy | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self.max_concurrent = max_concurrent
        self.max_depth = max_depth
        self.progress_interval = progress_interval
        self.user_agent = user_agent
        self.respect_robots = respect_robots
        self.parser = parser or HTMLParser()
        self.semaphores = SemaphoreManager(max_concurrent, per_domain_limit)
        self.rate_limiter = RateLimiter(requests_per_second, per_domain_rate, min_delay, jitter)
        self.robots = RobotsParser(self._get_session, user_agent)
        self.retry_strategy = retry_strategy or RetryStrategy()
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self._timeout = aiohttp.ClientTimeout(
            total=timeout_total, connect=timeout_connect, sock_read=timeout_read
        )
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._session: aiohttp.ClientSession | None = None
        # Crawl state, reset on every crawl() call.
        self.visited_urls: set[str] = set()
        self.processed_urls: dict[str, dict] = {}
        self.failed_urls: dict[str, str] = {}
        self.robots_blocked: list[str] = []
        self.error_stats: Counter = Counter()

    async def _get_session(self) -> aiohttp.ClientSession:
        # Lazy init: ClientSession must be created inside a running event loop.
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=self.max_concurrent)
            self._session = aiohttp.ClientSession(
                timeout=self._timeout,
                connector=connector,
                headers={"User-Agent": self.user_agent},
            )
        return self._session

    def _scaled_timeout(self, scale: float) -> aiohttp.ClientTimeout | None:
        # Retries pass scale > 1 to give slow servers progressively more time.
        if scale == 1.0:
            return None
        return aiohttp.ClientTimeout(
            total=(self._timeout.total or 0) * scale or None,
            connect=self._timeout.connect,
            sock_read=(self._timeout.sock_read or 0) * scale or None,
        )

    async def _request_page(self, url: str, timeout_scale: float = 1.0) -> str:
        """Download a page or raise a classified CrawlerError.

        Every request first waits for a rate-limiter slot of its domain
        (the Crawl-delay from robots.txt is respected when cached).
        """
        session = await self._get_session()
        domain = normalize_host(urlparse(url).hostname)
        crawl_delay = self.robots.get_crawl_delay(url) if self.respect_robots else None
        waited = await self.rate_limiter.acquire(domain, override_interval=crawl_delay)
        if waited > 0:
            logger.debug("Rate limit: waited {:.2f}s before {}", waited, url)
        start = time.perf_counter()
        logger.debug("Fetching {}", url)
        try:
            async with self._semaphore:
                kwargs = {}
                timeout = self._scaled_timeout(timeout_scale)
                if timeout is not None:
                    kwargs["timeout"] = timeout
                async with session.get(url, **kwargs) as response:
                    if response.status >= 400:
                        retry_after = response.headers.get("Retry-After")
                        raise error_from_status(
                            url,
                            response.status,
                            retry_after=float(retry_after) if retry_after else None,
                        )
                    text = await response.text()
        except CrawlerError:
            raise
        except Exception as exc:
            raise classify_exception(exc, url) from exc
        elapsed = time.perf_counter() - start
        logger.info("Fetched {} ({} chars in {:.2f}s)", url, len(text), elapsed)
        return text

    async def fetch_url(self, url: str) -> str | None:
        """Download a single page; return its text or None on any error."""
        try:
            return await self._request_page(url)
        except CrawlerError as exc:
            logger.warning("{} for {}: {}", exc.__class__.__name__, url, exc)
            return None

    async def fetch_urls(self, urls: list[str]) -> dict[str, str]:
        """Download many pages concurrently; return {url: text} for successful ones."""
        results = await asyncio.gather(*(self.fetch_url(url) for url in urls))
        fetched = {url: text for url, text in zip(urls, results) if text is not None}
        logger.info("Fetched {}/{} urls", len(fetched), len(urls))
        return fetched

    async def fetch_and_parse(self, url: str) -> dict | None:
        """Download a page and return structured data extracted from its HTML."""
        html = await self.fetch_url(url)
        if html is None:
            return None
        return await self.parser.parse_html(html, url)

    async def crawl(
        self,
        start_urls: list[str],
        max_pages: int = 100,
        max_depth: int | None = None,
        same_domain_only: bool = True,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> dict[str, dict]:
        """Breadth-style site crawl driven by a priority queue of URLs.

        Discovered links pass the URL filter and are queued with depth + 1
        until max_pages or max_depth is reached. Returns {url: page_data}.
        """
        depth_limit = self.max_depth if max_depth is None else max_depth
        url_filter = URLFilter.for_start_urls(
            start_urls, same_domain_only, include_patterns, exclude_patterns
        )
        queue = CrawlerQueue()
        for url in start_urls:
            queue.add_url(url, depth=0)

        self.visited_urls = set()
        self.processed_urls = {}
        self.failed_urls = {}
        self.robots_blocked = []
        self.error_stats = Counter()
        pages_taken = 0
        started = time.perf_counter()

        async def fetch_page(url: str, domain: str) -> dict:
            """One crawl attempt chain: circuit check -> fetch with retries -> parse."""
            if not self.circuit_breaker.allow(domain):
                raise CircuitOpenError(f"circuit open for {domain}", url=url)
            async with self.semaphores.limit(domain):
                html = await self.retry_strategy.execute_with_retry(
                    self._request_page,
                    url,
                    # Give the server more time on every retry.
                    on_attempt=lambda n: {"timeout_scale": 1.0 + 0.5 * n},
                )
            self.circuit_breaker.record_success(domain)
            return await self.parser.parse_html(html, url)

        async def worker() -> None:
            nonlocal pages_taken
            while True:
                item = await queue.get_next()
                if item is None:
                    return
                url, depth = item
                if pages_taken >= max_pages:
                    # Budget exhausted: drain the queue so workers can exit.
                    queue.mark_processed(url)
                    continue
                pages_taken += 1
                if self.respect_robots:
                    await self.robots.ensure_loaded(url)
                    if not self.robots.can_fetch(url):
                        logger.info("Blocked by robots.txt: {}", url)
                        self.robots_blocked.append(url)
                        queue.mark_processed(url)
                        continue
                self.visited_urls.add(url)
                domain = normalize_host(urlparse(url).hostname)
                page = None
                error = "unknown error"
                try:
                    page = await fetch_page(url, domain)
                except CircuitOpenError as exc:
                    error = f"{exc.__class__.__name__}: {exc}"
                    self.error_stats[exc.__class__.__name__] += 1
                except CrawlerError as exc:
                    error = f"{exc.__class__.__name__}: {exc}"
                    self.error_stats[exc.__class__.__name__] += 1
                    if exc.retryable:
                        self.circuit_breaker.record_failure(domain)
                except Exception as exc:  # a worker must survive anything
                    logger.exception("Unexpected error for {}", url)
                    error = repr(exc)
                    self.error_stats["UnexpectedError"] += 1
                if page is None:
                    logger.warning("Failed: {} ({})", url, error)
                    self.failed_urls[url] = error
                    queue.mark_failed(url, error)
                    continue
                if "error" in page:
                    self.error_stats["ParseError"] += 1
                self.processed_urls[url] = page
                if depth < depth_limit:
                    for link in page["links"]:
                        if url_filter.allowed(link):
                            queue.add_url(link, depth=depth + 1)
                queue.mark_processed(url)

        async def report_progress() -> None:
            while True:
                await asyncio.sleep(self.progress_interval)
                stats = queue.get_stats()
                elapsed = time.perf_counter() - started
                rate = stats["processed"] / elapsed if elapsed > 0 else 0.0
                limiter = self.rate_limiter.get_stats()
                logger.info(
                    "Progress: {} processed, {} queued, {} active, {} failed, "
                    "{:.1f} pages/s, {:.2f} req/s, avg delay {:.2f}s, {} blocked",
                    stats["processed"],
                    stats["queued"],
                    stats["in_progress"],
                    stats["failed"],
                    rate,
                    limiter["current_rps"],
                    limiter["avg_wait"],
                    len(self.robots_blocked),
                )

        progress_task = asyncio.create_task(report_progress())
        try:
            await asyncio.gather(*(worker() for _ in range(self.max_concurrent)))
        finally:
            progress_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await progress_task

        elapsed = time.perf_counter() - started
        retry_stats = self.retry_strategy.get_stats()
        logger.info(
            "Crawl finished: {} processed, {} failed, {} visited, {} robots-blocked, "
            "{} retries ({} successful) in {:.1f}s",
            len(self.processed_urls),
            len(self.failed_urls),
            len(self.visited_urls),
            len(self.robots_blocked),
            retry_stats["total_retries"],
            retry_stats["successful_retries"],
            elapsed,
        )
        if self.error_stats:
            logger.info("Errors by type: {}", dict(self.error_stats))
        return dict(self.processed_urls)

    async def close(self) -> None:
        """Release the HTTP session and its connection pool."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def __aenter__(self) -> "AsyncCrawler":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()
