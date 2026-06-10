"""Local demo site used by demos and tests.

Layout: / -> /section/{s} -> /section/{s}/item/{i} (depth 2), plus one
external link on the index page. Standalone: python -m examples.demo_server
"""

import asyncio

from aiohttp import web

PAGE = """<html>
<head><title>{title}</title><meta name="description" content="{title}"></head>
<body>
<h1>{title}</h1>
<p>Generated demo page for crawler runs.</p>
{links}
</body></html>"""

EXTERNAL_LINK = "https://external.invalid/offsite"


def _render(title: str, links: list[str]) -> str:
    anchors = "\n".join(f'<a href="{href}">{href}</a>' for href in links)
    return PAGE.format(title=title, links=anchors)


def create_app(sections: int = 3, items: int = 4, delay: float = 0.0) -> web.Application:
    async def maybe_delay() -> None:
        if delay:
            await asyncio.sleep(delay)

    async def index(request: web.Request) -> web.Response:
        await maybe_delay()
        links = [f"/section/{s}" for s in range(sections)] + [EXTERNAL_LINK]
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

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/section/{s}", section)
    app.router.add_get("/section/{s}/item/{i}", item)
    return app


def main() -> None:
    web.run_app(create_app(delay=0.05), host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
