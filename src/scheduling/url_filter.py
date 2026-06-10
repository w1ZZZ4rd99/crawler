"""URL scope filtering: domain restriction and include/exclude patterns."""

import re
from urllib.parse import urlparse


def normalize_host(host: str | None) -> str:
    """Lowercase the host and strip a leading "www." for comparison."""
    host = (host or "").lower()
    return host[4:] if host.startswith("www.") else host


class URLFilter:
    """Decides whether a discovered link is in scope for the crawl."""

    def __init__(
        self,
        allowed_domains: set[str] | None = None,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> None:
        self.allowed_domains = {normalize_host(d) for d in (allowed_domains or set())}
        self._include = [re.compile(p) for p in (include_patterns or [])]
        self._exclude = [re.compile(p) for p in (exclude_patterns or [])]

    @classmethod
    def for_start_urls(
        cls,
        start_urls: list[str],
        same_domain_only: bool = True,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> "URLFilter":
        domains = None
        if same_domain_only:
            domains = {urlparse(url).hostname or "" for url in start_urls}
        return cls(domains, include_patterns, exclude_patterns)

    def allowed(self, url: str) -> bool:
        if self.allowed_domains:
            if normalize_host(urlparse(url).hostname) not in self.allowed_domains:
                return False
        if any(pattern.search(url) for pattern in self._exclude):
            return False
        if self._include and not any(pattern.search(url) for pattern in self._include):
            return False
        return True
