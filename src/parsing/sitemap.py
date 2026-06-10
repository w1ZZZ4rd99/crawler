"""sitemap.xml fetching and parsing (plain and index sitemaps)."""

import xml.etree.ElementTree as ET

from loguru import logger

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
MAX_INDEX_DEPTH = 3


class SitemapParser:
    """Extracts page URLs from sitemap.xml, recursing into sitemap indexes."""

    def __init__(self, fetch_text) -> None:
        # fetch_text: async callable(url) -> str | None, e.g. AsyncCrawler.fetch_url.
        self._fetch_text = fetch_text

    async def fetch_sitemap(self, sitemap_url: str, _depth: int = 0) -> list[str]:
        """Return all page URLs listed in the sitemap (or [] on any problem)."""
        body = await self._fetch_text(sitemap_url)
        if not body:
            return []
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            logger.warning("Invalid sitemap XML at {}: {}", sitemap_url, exc)
            return []

        locs = self._extract_locs(root)
        if root.tag in (f"{SITEMAP_NS}sitemapindex", "sitemapindex"):
            if _depth >= MAX_INDEX_DEPTH:
                logger.warning("Sitemap index nested too deep at {}", sitemap_url)
                return []
            urls: list[str] = []
            for child in locs:
                urls.extend(await self.fetch_sitemap(child, _depth + 1))
            return self._unique(urls)
        logger.info("Sitemap {}: {} urls", sitemap_url, len(locs))
        return self._unique(locs)

    @staticmethod
    def _extract_locs(root: ET.Element) -> list[str]:
        locs = [el.text.strip() for el in root.iter(f"{SITEMAP_NS}loc") if el.text]
        if not locs:  # tolerate sitemaps written without the namespace
            locs = [el.text.strip() for el in root.iter("loc") if el.text]
        return locs

    @staticmethod
    def _unique(urls: list[str]) -> list[str]:
        seen: set[str] = set()
        result = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                result.append(url)
        return result
