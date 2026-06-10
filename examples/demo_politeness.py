"""Day 4 demo: rate limiting and robots.txt politeness.

Run from the repo root: python -m examples.demo_politeness
"""

import asyncio
import time

from examples.demo_crawl import start_local_site
from src.crawler import AsyncCrawler
from src.logging_setup import setup_logging


async def main() -> None:
    setup_logging("INFO")
    runner, base_url = await start_local_site()

    crawler = AsyncCrawler(
        max_concurrent=5,
        requests_per_second=2.0,  # not more than 2 requests/sec per domain
        min_delay=0.1,
        jitter=0.05,
        respect_robots=True,
        user_agent="PoliteDemoBot/1.0",
        progress_interval=2.0,
    )
    started = time.perf_counter()
    try:
        results = await crawler.crawl([base_url], max_pages=15, max_depth=1)
    finally:
        await crawler.close()
        await runner.cleanup()
    elapsed = time.perf_counter() - started

    limiter = crawler.rate_limiter.get_stats()
    print("\n=== Вежливый обход ===")
    print(f"Обработано:        {len(results)} страниц за {elapsed:.1f} c")
    print(f"Средняя задержка:  {limiter['avg_wait']:.2f} c перед запросом")
    print(f"Суммарно ждали:    {limiter['total_wait']:.1f} c (rate limiting)")
    print(f"Скорость запросов: {limiter['current_rps']:.2f} req/s (лимит: 2.0)")
    print(f"\nЗаблокировано robots.txt: {len(crawler.robots_blocked)}")
    for url in crawler.robots_blocked:
        print(f"  ЗАПРЕЩЁН {url}")


if __name__ == "__main__":
    asyncio.run(main())
