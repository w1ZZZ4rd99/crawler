"""Local demo site used by demos and tests.

Layout: / -> /section/{s} -> /section/{s}/item/{i} (depth 2), plus one
external link, a robots-disallowed /private/ area and failure endpoints
(/flaky, /error/500, /hang) for retry demos.
Standalone: python -m examples.demo_server
"""

import asyncio
from collections import defaultdict

from aiohttp import web

HITS_KEY = web.AppKey("hits", dict)

PAGE = """<html>
<head><title>{title}</title><meta name="description" content="{title}"></head>
<body>
<h1>{title}</h1>
<p>Generated demo page for crawler runs.</p>
{links}
</body></html>"""

EXTERNAL_LINK = "https://external.invalid/offsite"
PRIVATE_LINK = "/private/secret"


def _render(title: str, links: list[str]) -> str:
    anchors = "\n".join(f'<a href="{href}">{href}</a>' for href in links)
    return PAGE.format(title=title, links=anchors)


@web.middleware
async def _count_hits(request: web.Request, handler):
    request.app[HITS_KEY][request.path] += 1
    return await handler(request)


def create_app(
    sections: int = 3,
    items: int = 4,
    delay: float = 0.0,
    robots_crawl_delay: int | None = None,
) -> web.Application:
    async def maybe_delay() -> None:
        if delay:
            await asyncio.sleep(delay)

    async def robots_txt(request: web.Request) -> web.Response:
        lines = ["User-agent: *", "Disallow: /private/"]
        if robots_crawl_delay is not None:
            lines.append(f"Crawl-delay: {robots_crawl_delay}")
        return web.Response(text="\n".join(lines) + "\n")

    async def private_page(request: web.Request) -> web.Response:
        return web.Response(text=_render("Private page", ["/"]), content_type="text/html")

    async def index(request: web.Request) -> web.Response:
        await maybe_delay()
        links = [f"/section/{s}" for s in range(sections)] + [PRIVATE_LINK, EXTERNAL_LINK]
        return web.Response(text=_render("Demo site index", links), content_type="text/html")

    async def section(request: web.Request) -> web.Response:
        await maybe_delay()
        s = request.match_info["s"]
        links = [f"/section/{s}/item/{i}" for i in range(items)] + ["/"]
        return web.Response(text=_render(f"Section {s}", links), content_type="text/html")

    async def item(request: web.Request) -> web.Response:
        await maybe_delay()
        s, i = request.match_info["s"], request.match_info["i"]
        links = [f"/section/{s}", "/"]
        return web.Response(text=_render(f"Item {s}-{i}", links), content_type="text/html")

    async def flaky(request: web.Request) -> web.Response:
        # The first two hits fail with 503, then the page recovers.
        if request.app[HITS_KEY][request.path] <= 2:
            return web.Response(status=503, text="temporarily unavailable")
        return web.Response(text=_render("Flaky page", ["/"]), content_type="text/html")

    async def always_error(request: web.Request) -> web.Response:
        return web.Response(status=int(request.match_info["code"]), text="server error")

    async def hang(request: web.Request) -> web.Response:
        await asyncio.sleep(60)
        return web.Response(text="finally awake")

    app = web.Application(middlewares=[_count_hits])
    app[HITS_KEY] = defaultdict(int)
    app.router.add_get("/", index)
    app.router.add_get("/robots.txt", robots_txt)
    app.router.add_get("/private/{name}", private_page)
    app.router.add_get("/section/{s}", section)
    app.router.add_get("/section/{s}/item/{i}", item)
    app.router.add_get("/flaky", flaky)
    app.router.add_get("/error/{code}", always_error)
    app.router.add_get("/hang", hang)
    return app


def main() -> None:
    web.run_app(create_app(delay=0.05), host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
