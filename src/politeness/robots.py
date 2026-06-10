"""robots.txt fetching, caching and rule checks."""

import asyncio
from collections import defaultdict
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import aiohttp
from loguru import logger


class RobotsParser:
    """Per-domain robots.txt cache with allow/crawl-delay checks.

    A missing or unreachable robots.txt means "everything is allowed".
    """

    def __init__(self, session_factory, user_agent: str = "*") -> None:
        # session_factory: async callable returning an aiohttp.ClientSession.
        self._session_factory = session_factory
        self.user_agent = user_agent
        self._parsers: dict[str, RobotFileParser | None] = {}
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.blocked_count = 0

    @staticmethod
    def _origin(url: str) -> str:
        parts = urlparse(url)
        return f"{parts.scheme}://{parts.netloc}"

    async def ensure_loaded(self, url: str) -> None:
        """Fetch and cache robots.txt of the URL's domain exactly once."""
        origin = self._origin(url)
        if origin in self._parsers:
            return
        async with self._locks[origin]:
            if origin in self._parsers:  # another task fetched it while we waited
                return
            self._parsers[origin] = await self.fetch_robots(origin)

    async def fetch_robots(self, base_url: str) -> RobotFileParser | None:
        robots_url = f"{self._origin(base_url)}/robots.txt"
        session = await self._session_factory()
        try:
            async with session.get(robots_url) as response:
                if response.status != 200:
                    logger.debug("No robots.txt at {} (HTTP {})", robots_url, response.status)
                    return None
                text = await response.text()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.debug("Failed to fetch {}: {}", robots_url, exc.__class__.__name__)
            return None
        parser = RobotFileParser(robots_url)
        parser.parse(text.splitlines())
        logger.info("Loaded robots.txt for {}", self._origin(base_url))
        return parser

    def can_fetch(self, url: str, user_agent: str | None = None) -> bool:
        """Check the cached rules; counts blocked URLs for statistics."""
        parser = self._parsers.get(self._origin(url))
        if parser is None:
            return True
        allowed = parser.can_fetch(user_agent or self.user_agent, url)
        if not allowed:
            self.blocked_count += 1
        return allowed

    def get_crawl_delay(self, url: str, user_agent: str | None = None) -> float | None:
        parser = self._parsers.get(self._origin(url))
        if parser is None:
            return None
        delay = parser.crawl_delay(user_agent or self.user_agent)
        return float(delay) if delay is not None else None
