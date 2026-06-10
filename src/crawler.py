"""Core asynchronous HTTP client built on aiohttp."""

import asyncio
import time

import aiohttp
from loguru import logger

from src.parsing.html_parser import HTMLParser


class AsyncCrawler:
    """Downloads web pages concurrently with a configurable concurrency limit."""

    def __init__(
        self,
        max_concurrent: int = 10,
        timeout_total: float = 30.0,
        timeout_connect: float = 10.0,
        timeout_read: float = 10.0,
        parser: HTMLParser | None = None,
    ) -> None:
        self.max_concurrent = max_concurrent
        self.parser = parser or HTMLParser()
        self._timeout = aiohttp.ClientTimeout(
            total=timeout_total, connect=timeout_connect, sock_read=timeout_read
        )
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._session: aiohttp.ClientSession | None = None

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

    async def close(self) -> None:
        """Release the HTTP session and its connection pool."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def __aenter__(self) -> "AsyncCrawler":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()
