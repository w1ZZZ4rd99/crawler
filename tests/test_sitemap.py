"""Day 7: sitemap parsing (plain, index, broken)."""

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from src.crawler import AsyncCrawler
from src.parsing.sitemap import SitemapParser

NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'


def urlset(*urls: str) -> str:
    entries = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return f'<?xml version="1.0"?><urlset {NS}>{entries}</urlset>'


@pytest.fixture
async def sitemap_server():
    app = web.Application()

    def add_xml(path: str, body_factory):
        async def handler(request: web.Request) -> web.Response:
            return web.Response(text=body_factory(request), content_type="application/xml")

        app.router.add_get(path, handler)

    def base(request) -> str:
        return f"http://{request.host}"

    add_xml("/sitemap.xml", lambda r: urlset(f"{base(r)}/a", f"{base(r)}/b", f"{base(r)}/c"))
    add_xml(
        "/sitemap_index.xml",
        lambda r: (
            f'<?xml version="1.0"?><sitemapindex {NS}>'
            f"<sitemap><loc>{base(r)}/sitemap.xml</loc></sitemap>"
            f"<sitemap><loc>{base(r)}/extra.xml</loc></sitemap>"
            "</sitemapindex>"
        ),
    )
    add_xml("/extra.xml", lambda r: urlset(f"{base(r)}/c", f"{base(r)}/d"))
    add_xml("/no_namespace.xml", lambda r: "<urlset><url><loc>http://x/page</loc></url></urlset>")
    add_xml("/broken.xml", lambda r: "<urlset><url>not closed")

    server = TestServer(app)
    await server.start_server()
    yield server
    await server.close()


@pytest.fixture
async def parser(sitemap_server):
    async with AsyncCrawler(respect_robots=False, progress_interval=60) as crawler:
        yield SitemapParser(crawler.fetch_url)


async def test_plain_sitemap(sitemap_server, parser):
    urls = await parser.fetch_sitemap(str(sitemap_server.make_url("/sitemap.xml")))

    assert len(urls) == 3
    assert urls[0].endswith("/a")


async def test_sitemap_index_recursion_and_dedup(sitemap_server, parser):
    urls = await parser.fetch_sitemap(str(sitemap_server.make_url("/sitemap_index.xml")))

    # a, b, c from the first child; c (dup) and d from the second.
    assert len(urls) == 4
    assert [u.rsplit("/", 1)[1] for u in urls] == ["a", "b", "c", "d"]


async def test_sitemap_without_namespace(sitemap_server, parser):
    urls = await parser.fetch_sitemap(str(sitemap_server.make_url("/no_namespace.xml")))

    assert urls == ["http://x/page"]


async def test_broken_sitemap_returns_empty(sitemap_server, parser):
    assert await parser.fetch_sitemap(str(sitemap_server.make_url("/broken.xml"))) == []


async def test_missing_sitemap_returns_empty(sitemap_server, parser):
    assert await parser.fetch_sitemap(str(sitemap_server.make_url("/nope.xml"))) == []
