"""Day 1 demo: concurrent vs sequential page downloads.

Run from the repo root: python -m examples.demo_fetch
"""

import asyncio
import time

from src.crawler import AsyncCrawler
from src.logging_setup import setup_logging

URLS = [
    "https://example.com",
    "https://example.org",
    "https://www.python.org",
    "https://www.wikipedia.org",
    "https://httpbin.org/delay/1",
    "https://httpbin.org/delay/2",
    "https://httpbin.org/status/404",
    "https://nonexistent-domain-for-demo.invalid",
]


async def fetch_sequentially(crawler: AsyncCrawler, urls: list[str]) -> dict[str, str]:
    results: dict[str, str] = {}
    for url in urls:
        text = await crawler.fetch_url(url)
        if text is not None:
            results[url] = text
    return results


async def main() -> None:
    setup_logging("INFO")

    async with AsyncCrawler(max_concurrent=5) as crawler:
        start = time.perf_counter()
        parallel_results = await crawler.fetch_urls(URLS)
        parallel_time = time.perf_counter() - start

        start = time.perf_counter()
        sequential_results = await fetch_sequentially(crawler, URLS)
        sequential_time = time.perf_counter() - start

    print("\n=== Статус загрузки ===")
    for url in URLS:
        if url in parallel_results:
            print(f"  OK   {url} ({len(parallel_results[url])} символов)")
        else:
            print(f"  FAIL {url}")

    print(f"\nПараллельно:     {parallel_time:.2f} c ({len(parallel_results)} успешных)")
    print(f"Последовательно: {sequential_time:.2f} c ({len(sequential_results)} успешных)")
    if parallel_time > 0:
        print(f"Ускорение: x{sequential_time / parallel_time:.1f}")


if __name__ == "__main__":
    asyncio.run(main())
