"""Day 3: URL scope filtering."""

from src.scheduling.url_filter import URLFilter, normalize_host


def test_normalize_host():
    assert normalize_host("WWW.Example.COM") == "example.com"
    assert normalize_host("example.com") == "example.com"
    assert normalize_host(None) == ""


def test_same_domain_only():
    url_filter = URLFilter.for_start_urls(["https://example.com/start"])

    assert url_filter.allowed("https://example.com/page")
    assert url_filter.allowed("https://www.example.com/page")
    assert not url_filter.allowed("https://other.org/page")


def test_any_domain_when_disabled():
    url_filter = URLFilter.for_start_urls(["https://example.com/"], same_domain_only=False)

    assert url_filter.allowed("https://other.org/page")


def test_exclude_patterns():
    url_filter = URLFilter(exclude_patterns=[r"\.pdf$", "/private/"])

    assert not url_filter.allowed("https://example.com/file.pdf")
    assert not url_filter.allowed("https://example.com/private/page")
    assert url_filter.allowed("https://example.com/public")


def test_include_patterns():
    url_filter = URLFilter(include_patterns=[r"/blog/"])

    assert url_filter.allowed("https://example.com/blog/post")
    assert not url_filter.allowed("https://example.com/shop/item")


def test_no_filters_allows_everything():
    assert URLFilter().allowed("https://anything.example/whatever")
