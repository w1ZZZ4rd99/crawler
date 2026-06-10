"""Day 4: robots.txt parsing, caching and crawl integration."""

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from examples.demo_server import PRIVATE_LINK, create_app
from src.crawler import AsyncCrawler

ROBOTS_BODY = """User-agent: *
Disallow: /private/
Crawl-delay: 2

User-agent: BannedBot
Disallow: /
"""


@pytest.fixture
async def robots_server():
    hits = {"robots": 0}

    async def robots_txt(request: web.Request) -> web.Response:
        hits["robots"] += 1
        return web.Response(text=ROBOTS_BODY)

    async def page(request: web.Request) -> web.Response:
        return web.Response(text="<html><body>page</body></html>", content_type="text/html")

    app = web.Application()
    app.router.add_get("/robots.txt", robots_txt)
    app.router.add_get("/public", page)
    app.router.add_get("/private/{name}", page)
    server = TestServer(app)
    await server.start_server()
    server.hits = hits
    yield server
    await server.close()


@pytest.fixture
async def crawler():
    async with AsyncCrawler(max_concurrent=5, progress_interval=60) as instance:
        yield instance


async def test_disallowed_path_is_blocked(robots_server, crawler):
    base = str(robots_server.make_url("/"))
    await crawler.robots.ensure_loaded(base)

    assert crawler.robots.can_fetch(str(robots_server.make_url("/public")))
    assert not crawler.robots.can_fetch(str(robots_server.make_url("/private/x")))
    assert crawler.robots.blocked_count == 1


async def test_crawl_delay_is_read(robots_server, crawler):
    base = str(robots_server.make_url("/"))
    await crawler.robots.ensure_loaded(base)

    assert crawler.robots.get_crawl_delay(base) == 2.0


async def test_user_agent_specific_rules(robots_server):
    async with AsyncCrawler(user_agent="BannedBot", progress_interval=60) as crawler:
        base = str(robots_server.make_url("/"))
        await crawler.robots.ensure_loaded(base)

        assert not crawler.robots.can_fetch(str(robots_server.make_url("/public")))


async def test_missing_robots_allows_everything(server, crawler):
    # The day-1 test server has no /robots.txt at all.
    base = str(server.make_url("/"))
    await crawler.robots.ensure_loaded(base)

    assert crawler.robots.can_fetch(str(server.make_url("/ok")))
    assert crawler.robots.get_crawl_delay(base) is None


async def test_robots_is_fetched_once_per_domain(robots_server, crawler):
    base = str(robots_server.make_url("/"))
    await crawler.robots.ensure_loaded(base)
    await crawler.robots.ensure_loaded(str(robots_server.make_url("/public")))

    assert robots_server.hits["robots"] == 1


async def test_custom_user_agent_header_is_sent(server):
    async with AsyncCrawler(user_agent="MyBot/1.0", progress_interval=60) as crawler:
        body = await crawler.fetch_url(str(server.make_url("/echo-ua")))

    assert body == "MyBot/1.0"


async def test_crawl_skips_robots_disallowed_pages():
    site = TestServer(create_app(sections=2, items=2))
    await site.start_server()
    try:
        async with AsyncCrawler(max_concurrent=5, progress_interval=60) as crawler:
            results = await crawler.crawl([str(site.make_url("/"))], max_pages=50, max_depth=3)

        private_url = str(site.make_url(PRIVATE_LINK))
        assert private_url in crawler.robots_blocked
        assert private_url not in results
        assert private_url not in crawler.visited_urls
        assert private_url not in crawler.failed_urls
    finally:
        await site.close()


async def test_crawl_fetches_disallowed_pages_when_robots_ignored():
    site = TestServer(create_app(sections=2, items=2))
    await site.start_server()
    try:
        async with AsyncCrawler(
            max_concurrent=5, respect_robots=False, progress_interval=60
        ) as crawler:
            results = await crawler.crawl([str(site.make_url("/"))], max_pages=50, max_depth=3)

        assert str(site.make_url(PRIVATE_LINK)) in results
        assert crawler.robots_blocked == []
    finally:
        await site.close()
