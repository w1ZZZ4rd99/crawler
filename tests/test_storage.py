"""Day 6: storage backends roundtrip, batching and failure handling."""

import csv
import json

from aiohttp.test_utils import TestServer

from examples.demo_server import create_app
from src.crawler import AsyncCrawler
from src.storage import CompositeStorage, CSVStorage, DataStorage, JSONStorage, SQLiteStorage


def make_page(url: str = "https://example.com/page", **overrides) -> dict:
    page = {
        "url": url,
        "title": "Тестовая страница 🚀",
        "text": 'Текст с "кавычками", запятыми, \n переводами строк',
        "links": ["https://example.com/a", "https://example.com/b"],
        "metadata": {"description": "описание"},
        "crawled_at": "2026-06-10T12:00:00+00:00",
        "status_code": 200,
        "content_type": "text/html",
    }
    page.update(overrides)
    return page


async def test_jsonl_roundtrip(tmp_path):
    path = tmp_path / "out.jsonl"
    async with JSONStorage(path) as storage:
        for i in range(3):
            await storage.save(make_page(f"https://example.com/{i}"))

    records = await JSONStorage(path).read_all()
    assert len(records) == 3
    assert records[0]["title"] == "Тестовая страница 🚀"
    assert records[2]["url"] == "https://example.com/2"


async def test_json_pretty_mode_writes_array(tmp_path):
    path = tmp_path / "out.json"
    async with JSONStorage(path, pretty=True) as storage:
        await storage.save(make_page("https://example.com/1"))
        await storage.save(make_page("https://example.com/2"))

    parsed = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(parsed, list)
    assert [r["url"] for r in parsed] == ["https://example.com/1", "https://example.com/2"]


async def test_csv_handles_special_characters(tmp_path):
    path = tmp_path / "out.csv"
    async with CSVStorage(path) as storage:
        await storage.save(make_page())
        await storage.save(make_page("https://example.com/other", title="второй; ряд"))

    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2
    assert rows[0]["title"] == "Тестовая страница 🚀"
    assert "переводами строк" in rows[0]["text"]
    # Nested values survive as JSON strings.
    assert json.loads(rows[0]["links"]) == ["https://example.com/a", "https://example.com/b"]
    assert rows[1]["title"] == "второй; ряд"


async def test_csv_header_from_first_record(tmp_path):
    path = tmp_path / "out.csv"
    async with CSVStorage(path) as storage:
        await storage.save({"url": "https://x", "title": "t"})

    header = path.read_text(encoding="utf-8").splitlines()[0]
    assert header == "url,title"


async def test_sqlite_roundtrip_and_batching(tmp_path):
    path = tmp_path / "out.db"
    storage = SQLiteStorage(path, batch_size=2)
    for i in range(5):
        await storage.save(make_page(f"https://example.com/{i}"))
    # Two batches are flushed; one row still sits in the buffer.
    assert await storage.count() == 5  # count() flushes the rest
    await storage.close()

    reopened = SQLiteStorage(path)
    assert await reopened.count() == 5
    pages = await reopened.fetch_pages(limit=2)
    assert pages[0]["status_code"] == 200
    await reopened.close()


async def test_sqlite_replaces_same_url(tmp_path):
    path = tmp_path / "out.db"
    async with SQLiteStorage(path, batch_size=1) as storage:
        await storage.save(make_page("https://example.com/p", title="старый"))
        await storage.save(make_page("https://example.com/p", title="новый"))

        assert await storage.count() == 1
        assert (await storage.fetch_pages())[0]["title"] == "новый"


async def test_composite_storage_writes_everywhere(tmp_path):
    json_storage = JSONStorage(tmp_path / "out.jsonl")
    db_storage = SQLiteStorage(tmp_path / "out.db", batch_size=1)
    async with CompositeStorage([json_storage, db_storage]) as storage:
        await storage.save(make_page())
        assert await db_storage.count() == 1

    assert len(await JSONStorage(tmp_path / "out.jsonl").read_all()) == 1


class FailingStorage(DataStorage):
    """Stub that always fails: the crawl must survive it."""

    def __init__(self) -> None:
        self.calls = 0

    async def save(self, data: dict) -> None:
        self.calls += 1
        raise OSError("disk on fire")

    async def close(self) -> None:
        pass


async def test_crawl_survives_storage_failures():
    site = TestServer(create_app(sections=1, items=1))
    await site.start_server()
    failing = FailingStorage()
    try:
        crawler = AsyncCrawler(max_concurrent=3, storage=failing, progress_interval=60)
        async with crawler:
            results = await crawler.crawl([str(site.make_url("/"))], max_pages=10, max_depth=2)

        assert len(results) == 3  # crawl finished despite save errors
        assert failing.calls >= 9  # each save was retried (1 try + 2 retries)
    finally:
        await site.close()


async def test_crawl_saves_processed_pages(tmp_path):
    site = TestServer(create_app(sections=1, items=1))
    await site.start_server()
    path = tmp_path / "crawl.jsonl"
    try:
        crawler = AsyncCrawler(
            max_concurrent=3, storage=JSONStorage(path), progress_interval=60
        )
        async with crawler:
            results = await crawler.crawl([str(site.make_url("/"))], max_pages=10, max_depth=2)
    finally:
        await site.close()

    records = await JSONStorage(path).read_all()
    assert len(records) == len(results) == 3
    sample = records[0]
    assert sample["status_code"] == 200
    assert sample["content_type"] == "text/html"
    assert sample["crawled_at"]  # ISO timestamp is filled in
