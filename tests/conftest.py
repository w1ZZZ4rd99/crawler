"""Shared fixtures: a local aiohttp test server, no external network in tests."""

import asyncio
from collections import defaultdict

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from src.crawler import AsyncCrawler

STATS_KEY = web.AppKey("stats", dict)


@web.middleware
async def _track_requests(request: web.Request, handler):
    # Per-path hit counters and peak concurrency, used in assertions.
    stats = request.app[STATS_KEY]
    stats["hits"][request.path] += 1
    stats["active"] += 1
    stats["max_active"] = max(stats["max_active"], stats["active"])
    try:
        return await handler(request)
    finally:
        stats["active"] -= 1


def create_test_app() -> web.Application:
    async def ok(request: web.Request) -> web.Response:
        return web.Response(
            text="<html><body>ok page</body></html>", content_type="text/html"
        )

    async def slow(request: web.Request) -> web.Response:
        await asyncio.sleep(float(request.query.get("d", "0.5")))
        return web.Response(text="slow page")

    async def echo_user_agent(request: web.Request) -> web.Response:
        return web.Response(text=request.headers.get("User-Agent", ""))

    async def html_page(request: web.Request) -> web.Response:
        body = (
            "<html><head><title>Test page</title>"
            '<meta name="description" content="demo page"></head>'
            '<body><h1>Hello</h1><a href="/ok">ok</a>'
            '<a href="relative/path">rel</a></body></html>'
        )
        return web.Response(text=body, content_type="text/html")

    app = web.Application(middlewares=[_track_requests])
    app[STATS_KEY] = {"hits": defaultdict(int), "active": 0, "max_active": 0}
    app.router.add_get("/ok", ok)
    app.router.add_get("/slow", slow)
    app.router.add_get("/html", html_page)
    app.router.add_get("/echo-ua", echo_user_agent)
    return app


@pytest.fixture
async def server():
    test_server = TestServer(create_test_app())
    await test_server.start_server()
    yield test_server
    await test_server.close()


@pytest.fixture
async def crawler():
    async with AsyncCrawler(max_concurrent=5) as instance:
        yield instance
