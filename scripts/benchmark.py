"""Performance benchmark: sequential vs concurrent crawling + memory usage.

Run from the repo root: python -m scripts.benchmark
"""

import asyncio
import time
import tracemalloc

from aiohttp import web

from examples.demo_server import create_app
from src.crawler import AsyncCrawler
from src.logging_setup import setup_logging
from src.resilience.retry import RetryStrategy

# sections=22, items=22 -> 1 + 22 + 484 = 507 pages available.
SITE_SECTIONS = 22
SITE_ITEMS = 22
PAGE_DELAY = 0.005

SCENARIOS = [
    ("Последовательно (1)", 1, 100),
    ("Асинхронно (10)", 10, 100),
    ("Асинхронно (20)", 20, 100),
    ("Асинхронно (20), 500 страниц", 20, 500),
]


async def start_site() -> tuple[web.AppRunner, str]:
    app = create_app(sections=SITE_SECTIONS, items=SITE_ITEMS, delay=PAGE_DELAY)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    return runner, f"http://127.0.0.1:{port}/"


async def run_scenario(base_url: str, concurrency: int, max_pages: int) -> dict:
    crawler = AsyncCrawler(
        max_concurrent=concurrency,
        per_domain_limit=concurrency,
        max_depth=3,
        retry_strategy=RetryStrategy(max_retries=1, base_delay=0.1),
        progress_interval=600,
    )
    tracemalloc.start()
    started = time.perf_counter()
    try:
        results = await crawler.crawl([base_url], max_pages=max_pages)
    finally:
        await crawler.close()
    elapsed = time.perf_counter() - started
    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "pages": len(results),
        "time": elapsed,
        "rate": len(results) / elapsed if elapsed else 0.0,
        "peak_mb": peak_memory / 1024 / 1024,
    }


async def main() -> None:
    setup_logging("WARNING")  # keep the table readable
    runner, base_url = await start_site()
    try:
        print(f"Демо-сайт: {base_url} (до {1 + SITE_SECTIONS * (1 + SITE_ITEMS)} страниц)\n")
        header = f"{'Сценарий':35} {'Страниц':>8} {'Время, c':>10} {'Стр/с':>8} {'Память, МБ':>11}"
        print(header)
        print("-" * len(header))
        baseline: float | None = None
        for title, concurrency, max_pages in SCENARIOS:
            result = await run_scenario(base_url, concurrency, max_pages)
            speedup = ""
            if concurrency == 1 and max_pages == 100:
                baseline = result["time"]
            elif baseline and max_pages == 100:
                speedup = f"  (x{baseline / result['time']:.1f} к последовательному)"
            print(
                f"{title:35} {result['pages']:>8} {result['time']:>10.2f} "
                f"{result['rate']:>8.1f} {result['peak_mb']:>11.2f}{speedup}"
            )
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
