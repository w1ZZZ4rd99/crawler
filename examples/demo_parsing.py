"""Day 2 demo: fetch pages and extract structured data.

Run from the repo root: python -m examples.demo_parsing
"""

import asyncio

from src.crawler import AsyncCrawler
from src.logging_setup import setup_logging

URLS = [
    "https://example.com",
    "https://www.python.org",
]


def print_summary(page: dict) -> None:
    print(f"\n=== {page['url']} ===")
    print(f"  Заголовок:   {page['title'] or '—'}")
    print(f"  Текст:       {len(page['text'])} символов")
    print(f"  Ссылок:      {len(page['links'])}")
    for link in page["links"][:5]:
        print(f"    - {link}")
    if len(page["links"]) > 5:
        print(f"    ... и ещё {len(page['links']) - 5}")
    print(f"  Картинок:    {len(page['images'])}")
    headings = page["headings"]
    print(
        f"  Заголовки:   h1={len(headings.get('h1', []))}, "
        f"h2={len(headings.get('h2', []))}, h3={len(headings.get('h3', []))}"
    )
    print(f"  Таблиц:      {len(page['tables'])}, списков: {len(page['lists'])}")
    print(f"  Метаданные:  {', '.join(page['metadata']) or '—'}")


async def main() -> None:
    setup_logging("INFO")

    async with AsyncCrawler(max_concurrent=5) as crawler:
        results = await asyncio.gather(*(crawler.fetch_and_parse(url) for url in URLS))

    for page in results:
        if page is not None:
            print_summary(page)


if __name__ == "__main__":
    asyncio.run(main())
