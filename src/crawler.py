"""Core asynchronous HTTP client and crawling engine built on aiohttp."""

import asyncio
import contextlib
import time
from urllib.parse import urlparse

import aiohttp
from loguru import logger

from src.parsing.html_parser import HTMLParser
from src.scheduling.crawler_queue import CrawlerQueue
from src.scheduling.semaphores import SemaphoreManager
from src.scheduling.url_filter import URLFilter, normalize_host


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
    ) -> None:
        self.max_concurrent = max_concurrent
        self.max_depth = max_depth
        self.progress_interval = progress_interval
        self.parser = parser or HTMLParser()
        self.semaphores = SemaphoreManager(max_concurrent, per_domain_limit)
        self._timeout = aiohttp.ClientTimeout(
            total=timeout_total, connect=timeout_connect, sock_read=timeout_read
        )
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._session: aiohttp.ClientSession | None = None
        # Crawl state, reset on every crawl() call.
        self.visited_urls: set[str] = set()
        self.processed_urls: dict[str, dict] = {}
        self.failed_urls: dict[str, str] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        # Lazy init: ClientSession must be created inside a running event loop.
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=self.max_concurrent)
            self._session = aiohttp.ClientSession(timeout=self._timeout, connector=connector)
        return self._session

    async def fetch_url(self, url: str) -> str | None:
        """Download a single page; return its text or None on any error."""
        session = await self._get_session()
        start = time.perf_counter()
        logger.debug("Fetching {}", url)
        try:
            async with self._semaphore:
                async with session.get(url) as response:
                    response.raise_for_status()
                    text = await response.text()
        except aiohttp.ClientResponseError as exc:
            logger.warning("HTTP {} for {}", exc.status, url)
        except asyncio.TimeoutError:
            logger.warning("Timeout for {}", url)
        except aiohttp.ClientError as exc:
            logger.warning("Network error for {}: {}", url, exc.__class__.__name__)
        except UnicodeDecodeError:
            logger.warning("Cannot decode response body for {}", url)
        else:
            elapsed = time.perf_counter() - start
            logger.info("Fetched {} ({} chars in {:.2f}s)", url, len(text), elapsed)
            return text
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
        pages_taken = 0
        started = time.perf_counter()

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
                self.visited_urls.add(url)
                error = "fetch or parse failed"
                try:
                    domain = normalize_host(urlparse(url).hostname)
                    async with self.semaphores.limit(domain):
                        page = await self.fetch_and_parse(url)
                except Exception as exc:  # a worker must survive anything
                    logger.exception("Unexpected error for {}", url)
                    page = None
                    error = repr(exc)
                if page is None:
                    self.failed_urls[url] = error
                    queue.mark_failed(url, error)
                    continue
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
                logger.info(
                    "Progress: {} processed, {} queued, {} active, {} failed, {:.1f} pages/s",
                    stats["processed"],
                    stats["queued"],
                    stats["in_progress"],
                    stats["failed"],
                    rate,
                )

        progress_task = asyncio.create_task(report_progress())
        try:
            await asyncio.gather(*(worker() for _ in range(self.max_concurrent)))
        finally:
            progress_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await progress_task

        elapsed = time.perf_counter() - started
        logger.info(
            "Crawl finished: {} processed, {} failed, {} visited in {:.1f}s",
            len(self.processed_urls),
            len(self.failed_urls),
            len(self.visited_urls),
            elapsed,
        )
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
