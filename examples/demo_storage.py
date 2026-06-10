"""Day 6 demo: crawl and save results to JSONL, CSV and SQLite at once.

Run from the repo root: python -m examples.demo_storage
"""

import asyncio
import csv
from pathlib import Path

from examples.demo_crawl import start_local_site
from src.crawler import AsyncCrawler
from src.logging_setup import setup_logging
from src.storage import CompositeStorage, CSVStorage, JSONStorage, SQLiteStorage

DATA_DIR = Path("data")


async def main() -> None:
    setup_logging("INFO")
    runner, base_url = await start_local_site()

    json_path = DATA_DIR / "results.jsonl"
    csv_path = DATA_DIR / "results.csv"
    db_path = DATA_DIR / "results.db"
    for path in (json_path, csv_path, db_path):
        path.unlink(missing_ok=True)

    storage = CompositeStorage(
        [JSONStorage(json_path), CSVStorage(csv_path), SQLiteStorage(db_path, batch_size=10)]
    )
    crawler = AsyncCrawler(max_concurrent=10, storage=storage, progress_interval=1.0)
    try:
        results = await crawler.crawl([base_url], max_pages=30, max_depth=2)
    finally:
        await crawler.close()  # also flushes and closes the storage
        await runner.cleanup()

    print(f"\nОбработано страниц: {len(results)}")

    # Read everything back to prove the data is usable.
    json_records = await JSONStorage(json_path).read_all()
    print(f"\nJSONL: {len(json_records)} записей в {json_path}")

    with csv_path.open(encoding="utf-8", newline="") as f:
        csv_rows = list(csv.DictReader(f))
    print(f"CSV:   {len(csv_rows)} строк в {csv_path}")

    db = SQLiteStorage(db_path)
    print(f"SQLite: {await db.count()} строк в {db_path}")
    print("\nПример данных из SQLite:")
    for row in await db.fetch_pages(limit=3):
        print(f"  [{row['status_code']}] {row['url']} — «{row['title']}» @ {row['crawled_at']}")
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
