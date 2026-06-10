"""HTML parsing and structured data extraction (BeautifulSoup + lxml)."""

import asyncio
from urllib.parse import urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup
from loguru import logger

from src.models import PageData

ALLOWED_SCHEMES = {"http", "https"}
SKIP_HREF_PREFIXES = ("javascript:", "mailto:", "tel:", "#")


class HTMLParser:
    """Extracts links, text, metadata and common page elements from HTML."""

    def __init__(self, parser: str = "lxml") -> None:
        self.parser = parser

    async def parse_html(self, html: str, url: str) -> dict:
        """Parse a page and return extracted fields as a dict.

        Parsing runs in a worker thread (CPU-bound) and never raises:
        on failure a partial result with an "error" key is returned.
        """
        try:
            page = await asyncio.to_thread(self._parse, html, url)
            return page.to_dict()
        except Exception as exc:
            logger.warning("Parse error for {}: {}", url, exc)
            partial = PageData(url=url).to_dict()
            partial["error"] = str(exc)
            return partial

    def _parse(self, html: str, url: str) -> PageData:
        soup = BeautifulSoup(html or "", self.parser)
        # Script/style bodies would pollute the extracted text.
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        return PageData(
            url=url,
            title=title,
            text=self.extract_text(soup),
            links=self.extract_links(soup, url),
            metadata=self.extract_metadata(soup),
            images=self.extract_images(soup, url),
            headings=self.extract_headings(soup),
            tables=self.extract_tables(soup),
            lists=self.extract_lists(soup),
        )

    def extract_links(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """Collect unique absolute http(s) links, preserving document order."""
        links: list[str] = []
        seen: set[str] = set()
        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()
            if not href or href.lower().startswith(SKIP_HREF_PREFIXES):
                continue
            absolute, _ = urldefrag(urljoin(base_url, href))
            if urlparse(absolute).scheme not in ALLOWED_SCHEMES:
                continue
            if absolute not in seen:
                seen.add(absolute)
                links.append(absolute)
        return links

    def extract_text(self, soup: BeautifulSoup, selector: str | None = None) -> str:
        node = soup.select_one(selector) if selector else (soup.body or soup)
        if node is None:
            return ""
        return " ".join(node.get_text(separator=" ", strip=True).split())

    def extract_metadata(self, soup: BeautifulSoup) -> dict:
        """Collect title, description/keywords/author, og:* tags, lang and canonical."""
        metadata: dict = {}
        if soup.title and soup.title.string:
            metadata["title"] = soup.title.string.strip()
        for meta in soup.find_all("meta"):
            name = (meta.get("name") or meta.get("property") or "").lower()
            content = meta.get("content")
            if not content:
                continue
            if name in {"description", "keywords", "author"} or name.startswith("og:"):
                metadata[name] = content.strip()
        html_tag = soup.find("html")
        if html_tag and html_tag.get("lang"):
            metadata["lang"] = html_tag["lang"]
        canonical = soup.find("link", rel="canonical")
        if canonical and canonical.get("href"):
            metadata["canonical"] = canonical["href"]
        return metadata

    def extract_images(self, soup: BeautifulSoup, base_url: str) -> list[dict]:
        images = []
        for img in soup.find_all("img", src=True):
            src = img["src"].strip()
            if not src or src.startswith("data:"):
                continue
            images.append({"src": urljoin(base_url, src), "alt": img.get("alt", "")})
        return images

    def extract_headings(self, soup: BeautifulSoup) -> dict:
        return {
            level: [h.get_text(" ", strip=True) for h in soup.find_all(level)]
            for level in ("h1", "h2", "h3")
        }

    def extract_tables(self, soup: BeautifulSoup) -> list:
        """Each table becomes a list of rows, each row a list of cell texts."""
        tables = []
        for table in soup.find_all("table"):
            rows = []
            for tr in table.find_all("tr"):
                cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
                if cells:
                    rows.append(cells)
            if rows:
                tables.append(rows)
        return tables

    def extract_lists(self, soup: BeautifulSoup) -> list:
        """Each ul/ol becomes {"type": ..., "items": [...]} (direct items only)."""
        lists = []
        for tag in soup.find_all(["ul", "ol"]):
            items = [li.get_text(" ", strip=True) for li in tag.find_all("li", recursive=False)]
            if items:
                lists.append({"type": tag.name, "items": items})
        return lists
