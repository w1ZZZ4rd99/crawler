"""Day 3: crawl() over the local demo site."""

import pytest
from aiohttp.test_utils import TestServer

from examples.demo_server import EXTERNAL_LINK, create_app
from src.crawler import AsyncCrawler
from src.resilience.retry import RetryStrategy

# create_app(sections=2, items=2): 1 index + 2 sections + 4 items = 7 pages.
SITE_PAGES = 7


@pytest.fixture
async def site():
    server = TestServer(create_app(sections=2, items=2))
    await server.start_server()
    yield server
    await server.close()


def make_crawler(**kwargs) -> AsyncCrawler:
    kwargs.setdefault("max_concurrent", 5)
    kwargs.setdefault("progress_interval", 60)  # keep test logs quiet
    return AsyncCrawler(**kwargs)


async def test_crawl_visits_whole_site_without_duplicates(site):
    async with make_crawler() as crawler:
        results = await crawler.crawl([str(site.make_url("/"))], max_pages=50, max_depth=3)

    assert len(results) == SITE_PAGES
    assert len(crawler.visited_urls) == SITE_PAGES
    assert crawler.failed_urls == {}
    # The external link is filtered out by same_domain_only=True.
    assert EXTERNAL_LINK not in crawler.visited_urls


async def test_crawl_respects_max_depth(site):
    async with make_crawler() as crawler:
        results = await crawler.crawl([str(site.make_url("/"))], max_pages=50, max_depth=1)

    # Depth 0 is the index, depth 1 the sections; items are depth 2.
    assert len(results) == 3
    assert not any("/item/" in url for url in results)


async def test_crawl_respects_max_pages(site):
    async with make_crawler(max_concurrent=2) as crawler:
        await crawler.crawl([str(site.make_url("/"))], max_pages=3, max_depth=3)

    assert len(crawler.visited_urls) == 3


async def test_crawl_exclude_patterns(site):
    async with make_crawler() as crawler:
        results = await crawler.crawl(
            [str(site.make_url("/"))],
            max_pages=50,
            max_depth=3,
            exclude_patterns=[r"/section/1"],
        )

    # Section 1 and its two items are skipped: 7 - 3 = 4.
    assert len(results) == 4
    assert not any("/section/1" in url for url in results)


async def test_crawl_follows_external_links_when_allowed(site):
    # No retries: the external host is unreachable, retrying only slows the test.
    async with make_crawler(retry_strategy=RetryStrategy(max_retries=0)) as crawler:
        await crawler.crawl(
            [str(site.make_url("/"))], max_pages=50, max_depth=1, same_domain_only=False
        )

    # The unreachable external link was attempted and recorded as failed.
    assert EXTERNAL_LINK in crawler.failed_urls
