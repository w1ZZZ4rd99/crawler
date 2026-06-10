"""Command line interface for the crawler."""

import argparse
import asyncio

from src.advanced_crawler import AdvancedCrawler
from src.config import CrawlerConfig
from src.logging_setup import setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crawler",
        description="Асинхронный веб-краулер: обход сайтов, парсинг и сохранение данных",
    )
    parser.add_argument("--urls", nargs="+", help="стартовые URL")
    parser.add_argument("--config", help="конфигурационный файл (YAML или JSON)")
    parser.add_argument("--max-pages", type=int, help="максимум страниц")
    parser.add_argument("--max-depth", type=int, help="максимальная глубина обхода")
    parser.add_argument("--max-concurrent", type=int, help="одновременных запросов")
    parser.add_argument("--rate-limit", type=float, help="запросов в секунду на домен")
    parser.add_argument(
        "--respect-robots",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="соблюдать robots.txt (по умолчанию: да)",
    )
    parser.add_argument(
        "--use-sitemap", action="store_true", default=None, help="брать URL из sitemap.xml"
    )
    parser.add_argument("--output", help="файл результатов (.jsonl/.json/.csv/.db)")
    parser.add_argument("--report", help="сохранить HTML-отчёт со статистикой")
    parser.add_argument("--stats-json", help="сохранить статистику в JSON")
    parser.add_argument("--log-level", help="уровень логирования (DEBUG/INFO/...)")
    parser.add_argument("--log-file", help="файл логов (с ротацией)")
    return parser


def config_from_args(args: argparse.Namespace) -> CrawlerConfig:
    config = CrawlerConfig.from_file(args.config) if args.config else CrawlerConfig()
    config.apply_cli_args(args)
    return config


async def run(config: CrawlerConfig) -> int:
    crawler = AdvancedCrawler(config)
    try:
        await crawler.crawl()
    finally:
        await crawler.close()

    stats = crawler.stats
    print("\n=== Краулинг завершён ===")
    print(f"Обработано: {stats.total_pages} страниц за {stats.duration} c")
    print(f"Успешно:    {stats.successful}")
    print(f"Ошибок:     {stats.failed}")
    print(f"Скорость:   {stats.pages_per_second} страниц/с")
    if config.output:
        print(f"Результаты: {config.output}")
    if config.stats_json:
        print(f"Статистика: {crawler.export_to_json(config.stats_json)}")
    if config.report_html:
        print(f"HTML-отчёт: {crawler.export_to_html_report(config.report_html)}")
    return 0 if stats.successful > 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = config_from_args(args)
    if not config.start_urls:
        parser.error("укажите стартовые URL: --urls ... или --config файл со start_urls")
    setup_logging(config.log_level, config.log_file)
    return asyncio.run(run(config))
