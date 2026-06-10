"""Day 7: statistics aggregation and report exports."""

import json

import pytest
from aiohttp.test_utils import TestServer

from examples.demo_server import create_app
from src.crawler import AsyncCrawler
from src.resilience.retry import RetryStrategy
from src.stats import CrawlerStats


@pytest.fixture
async def site():
    server = TestServer(create_app(sections=2, items=2))
    await server.start_server()
    yield server
    await server.close()


@pytest.fixture
async def crawled(site):
    crawler = AsyncCrawler(
        max_concurrent=5,
        retry_strategy=RetryStrategy(max_retries=0),
        progress_interval=60,
    )
    async with crawler:
        start = [str(site.make_url("/")), str(site.make_url("/missing"))]
        await crawler.crawl(start, max_pages=50, max_depth=3)
    return CrawlerStats.from_crawler(crawler, duration=2.0)


async def test_stats_aggregation(crawled):
    stats = crawled

    assert stats.successful == 7  # the whole demo site
    assert stats.failed == 1  # /missing -> 404
    assert stats.total_pages == 8
    assert stats.robots_blocked == 1  # /private/secret
    assert stats.status_codes[200] == 7
    assert stats.pages_per_second == 4.0  # 8 pages / 2 s
    assert stats.total_text_length > 0
    assert stats.error_types["PermanentError"] == 1
    assert stats.top_domains()[0][1] == 7  # all pages from one host


async def test_stats_to_dict_and_json_export(crawled, tmp_path):
    stats_dict = crawled.to_dict()
    assert stats_dict["successful"] == 7
    assert stats_dict["status_codes"][200] == 7

    path = crawled.export_to_json(tmp_path / "stats.json")
    parsed = json.loads(path.read_text(encoding="utf-8"))
    assert parsed["total_pages"] == 8
    assert parsed["retries"] == {"total_retries": 0, "successful_retries": 0}


async def test_html_report_contains_key_numbers(crawled, tmp_path):
    path = crawled.export_to_html_report(tmp_path / "report.html")
    html = path.read_text(encoding="utf-8")

    assert "<html" in html
    assert "Отчёт о работе краулера" in html
    assert "<td>7</td>" in html  # successful pages
    assert "PermanentError" in html
    assert "127.0.0.1" in html  # top domain
