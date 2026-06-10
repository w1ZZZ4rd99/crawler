"""High-level crawler assembling all components around a CrawlerConfig."""

import time
from pathlib import Path
from urllib.parse import urlparse

from loguru import logger

from src.config import CrawlerConfig
from src.crawler import AsyncCrawler
from src.parsing.sitemap import SitemapParser
from src.resilience.retry import RetryStrategy
from src.stats import CrawlerStats
from src.storage import CSVStorage, DataStorage, JSONStorage, SQLiteStorage


def storage_for_path(path: str) -> DataStorage:
    """Pick a storage backend by the output file extension."""
    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        return CSVStorage(path)
    if suffix in {".db", ".sqlite", ".sqlite3"}:
        return SQLiteStorage(path)
    if suffix == ".json":
        return JSONStorage(path, pretty=True)
    return JSONStorage(path)  # .jsonl and anything else -> JSON Lines


class AdvancedCrawler:
    """Facade over AsyncCrawler: config, sitemap seeding, stats and reports."""

    def __init__(self, config: CrawlerConfig) -> None:
        self.config = config
        self.stats: CrawlerStats | None = None
        self.crawler = AsyncCrawler(
            max_concurrent=config.max_concurrent,
            max_depth=config.max_depth,
            per_domain_limit=config.per_domain_limit,
            timeout_total=config.timeout_total,
            requests_per_second=config.requests_per_second,
            min_delay=config.min_delay,
            jitter=config.jitter,
            respect_robots=config.respect_robots,
            user_agent=config.user_agent,
            retry_strategy=RetryStrategy(
                max_retries=config.max_retries, backoff_factor=config.backoff_factor
            ),
            storage=storage_for_path(config.output) if config.output else None,
        )
        self.sitemaps = SitemapParser(self.crawler.fetch_url)

    @classmethod
    def from_config(cls, path: str | Path) -> "AdvancedCrawler":
        return cls(CrawlerConfig.from_file(path))

    async def _seed_urls(self) -> list[str]:
        """Start URLs, optionally extended with URLs discovered in sitemaps."""
        urls = list(self.config.start_urls)
        if not self.config.use_sitemap:
            return urls
        discovered: list[str] = []
        for url in self.config.start_urls:
            parts = urlparse(url)
            origin = f"{parts.scheme}://{parts.netloc}"
            candidates: list[str] = []
            if self.config.respect_robots:
                await self.crawler.robots.ensure_loaded(url)
                candidates = self.crawler.robots.get_sitemaps(url)
            if not candidates:
                candidates = [f"{origin}/sitemap.xml"]
            for sitemap_url in candidates:
                discovered.extend(await self.sitemaps.fetch_sitemap(sitemap_url))
        logger.info("Sitemap discovery added {} urls", len(discovered))
        return urls + discovered  # the queue deduplicates

    async def crawl(self) -> dict[str, dict]:
        started = time.perf_counter()
        start_urls = await self._seed_urls()
        results = await self.crawler.crawl(
            start_urls,
            max_pages=self.config.max_pages,
            max_depth=self.config.max_depth,
            same_domain_only=self.config.same_domain_only,
            include_patterns=self.config.include_patterns or None,
            exclude_patterns=self.config.exclude_patterns or None,
        )
        self.stats = CrawlerStats.from_crawler(self.crawler, time.perf_counter() - started)
        return results

    def get_stats(self) -> dict:
        return self.stats.to_dict() if self.stats else {}

    def export_to_json(self, filename: str | Path) -> Path:
        return self.stats.export_to_json(filename)

    def export_to_html_report(self, filename: str | Path) -> Path:
        return self.stats.export_to_html_report(filename)

    async def close(self) -> None:
        await self.crawler.close()
