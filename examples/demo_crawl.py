"""Day 3 demo: crawl a site with depth/pages limits and live progress.

Run from the repo root: python -m examples.demo_crawl
By default an in-process demo site is crawled; pass --url for a real one.
"""

import argparse
import asyncio
import time

from aiohttp import web

from examples.demo_server import create_app
from src.crawler import AsyncCrawler
from src.logging_setup import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl demo")
    parser.add_argument("--url", help="стартовый URL (по умолчанию — локальный демо-сайт)")
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--max-depth", type=int, default=2)
    return parser.parse_args()


async def start_local_site() -> tuple[web.AppRunner, str]:
    runner = web.AppRunner(create_app(sections=4, items=5, delay=0.15))
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    return runner, f"http://127.0.0.1:{port}/"


async def main() -> None:
    setup_logging("INFO")
    args = parse_args()

    runner = None
    base_url = args.url
    if base_url is None:
        runner, base_url = await start_local_site()

    crawler = AsyncCrawler(max_concurrent=10, max_depth=args.max_depth, progress_interval=0.5)
    started = time.perf_counter()
    try:
        results = await crawler.crawl([base_url], max_pages=args.max_pages)
    finally:
        await crawler.close()
        if runner is not None:
            await runner.cleanup()
    elapsed = time.perf_counter() - started

    print("\n=== Итоги обхода ===")
    print(f"Обработано: {len(results)} страниц за {elapsed:.1f} c")
    print(f"Ошибок:     {len(crawler.failed_urls)}")
    print(f"Посещено:   {len(crawler.visited_urls)} уникальных URL")
    if elapsed > 0:
        print(f"Скорость:   {len(results) / elapsed:.1f} страниц/сек")
    print("\nПримеры страниц:")
    for url, page in list(results.items())[:5]:
        print(f"  {url} — «{page['title']}», ссылок: {len(page['links'])}")


if __name__ == "__main__":
    asyncio.run(main())
