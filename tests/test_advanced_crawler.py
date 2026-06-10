"""Day 7: AdvancedCrawler end-to-end over the local demo site."""

import pytest
from aiohttp.test_utils import TestServer

from examples.demo_server import create_app
from src.advanced_crawler import AdvancedCrawler, storage_for_path
from src.config import CrawlerConfig
from src.storage import CSVStorage, JSONStorage, SQLiteStorage


@pytest.fixture
async def site():
    server = TestServer(create_app(sections=2, items=2))
    await server.start_server()
    yield server
    await server.close()


def test_storage_for_path_picks_backend_by_extension(tmp_path):
    assert isinstance(storage_for_path(str(tmp_path / "r.jsonl")), JSONStorage)
    assert isinstance(storage_for_path(str(tmp_path / "r.csv")), CSVStorage)
    assert isinstance(storage_for_path(str(tmp_path / "r.db")), SQLiteStorage)
    pretty = storage_for_path(str(tmp_path / "r.json"))
    assert isinstance(pretty, JSONStorage)
    assert pretty.pretty is True


async def test_end_to_end_crawl_with_reports(site, tmp_path):
    config = CrawlerConfig(
        start_urls=[str(site.make_url("/"))],
        max_pages=20,
        max_depth=3,
        max_concurrent=5,
        output=str(tmp_path / "results.jsonl"),
        report_html=str(tmp_path / "report.html"),
        stats_json=str(tmp_path / "stats.json"),
    )
    crawler = AdvancedCrawler(config)
    try:
        results = await crawler.crawl()
    finally:
        await crawler.close()

    assert len(results) == 7
    stats = crawler.get_stats()
    assert stats["successful"] == 7
    assert stats["status_codes"][200] == 7

    # Storage, HTML report and JSON stats are all written and readable.
    records = await JSONStorage(tmp_path / "results.jsonl").read_all()
    assert len(records) == 7
    html = crawler.export_to_html_report(config.report_html).read_text(encoding="utf-8")
    assert "Отчёт" in html
    assert crawler.export_to_json(config.stats_json).exists()


async def test_sitemap_seeding(site, tmp_path):
    # max_depth=0: only seeded URLs are fetched, no link following.
    config = CrawlerConfig(
        start_urls=[str(site.make_url("/"))],
        use_sitemap=True,
        max_pages=20,
        max_depth=0,
        output=None,
    )
    crawler = AdvancedCrawler(config)
    try:
        results = await crawler.crawl()
    finally:
        await crawler.close()

    # Index page + two /section/{s} urls advertised by sitemap.xml
    # (discovered through the Sitemap line in robots.txt).
    assert len(results) == 3
    assert any(url.endswith("/section/0") for url in results)
    assert any(url.endswith("/section/1") for url in results)


async def test_from_config_file(site, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
start_urls:
  - {site.make_url("/")}
max_pages: 3
max_depth: 1
output: null
""",
        encoding="utf-8",
    )
    crawler = AdvancedCrawler.from_config(config_path)
    try:
        results = await crawler.crawl()
    finally:
        await crawler.close()

    assert len(results) == 3
    assert crawler.config.max_pages == 3
