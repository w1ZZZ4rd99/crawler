"""Day 5 demo: error classification, automatic retries and error report.

Run from the repo root: python -m examples.demo_retries
"""

import asyncio
import json
from pathlib import Path

from examples.demo_crawl import start_local_site
from src.crawler import AsyncCrawler
from src.logging_setup import setup_logging
from src.resilience.retry import RetryStrategy

REPORT_PATH = Path("data/error_report.json")


async def main() -> None:
    setup_logging("INFO")
    runner, base_url = await start_local_site()

    crawler = AsyncCrawler(
        max_concurrent=4,
        timeout_total=2.0,
        retry_strategy=RetryStrategy(max_retries=3, backoff_factor=2.0, base_delay=0.3),
        progress_interval=5.0,
    )
    # max_depth=0: only the listed URLs, no link following.
    targets = [
        base_url,
        f"{base_url}flaky",
        f"{base_url}error/500",
        f"{base_url}missing-page",
        f"{base_url}hang",
    ]
    try:
        results = await crawler.crawl(targets, max_pages=10, max_depth=0)
    finally:
        await crawler.close()
        await runner.cleanup()

    print("\n=== Результаты по URL ===")
    for url in targets:
        if url in results:
            print(f"  OK     {url}")
        elif url in crawler.failed_urls:
            print(f"  FAIL   {url} — {crawler.failed_urls[url]}")

    retry_stats = crawler.retry_strategy.get_stats()
    print("\n=== Статистика ===")
    print(f"Ошибки по типам:   {dict(crawler.error_stats)}")
    print(f"Всего повторов:    {retry_stats['total_retries']}")
    print(f"Успешных повторов: {retry_stats['successful_retries']}")

    REPORT_PATH.parent.mkdir(exist_ok=True)
    report = {
        "failed_urls": crawler.failed_urls,
        "error_stats": dict(crawler.error_stats),
        "retries": retry_stats,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nОтчёт об ошибках сохранён в {REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
