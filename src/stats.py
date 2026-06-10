"""Aggregated crawl statistics with JSON and HTML report exports."""

import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

HTML_STYLE = """
body { font-family: sans-serif; margin: 2em auto; max-width: 60em; color: #222; }
h1 { border-bottom: 2px solid #4a78c2; padding-bottom: .3em; }
table { border-collapse: collapse; margin: 1em 0; min-width: 28em; }
th, td { border: 1px solid #ccc; padding: .4em .8em; text-align: left; }
th { background: #eef3fb; }
.bar { background: #4a78c2; height: 1em; display: inline-block; }
.fail { color: #b3362c; }
"""


class CrawlerStats:
    """Summary of one crawl run, built from the crawler's final state."""

    def __init__(self) -> None:
        self.total_pages = 0
        self.successful = 0
        self.failed = 0
        self.robots_blocked = 0
        self.duration = 0.0
        self.pages_per_second = 0.0
        self.total_text_length = 0
        self.status_codes: Counter = Counter()
        self.domains: Counter = Counter()
        self.error_types: Counter = Counter()
        self.retries = {"total_retries": 0, "successful_retries": 0}
        self.failed_urls: dict[str, str] = {}

    @classmethod
    def from_crawler(cls, crawler, duration: float) -> "CrawlerStats":
        stats = cls()
        stats.successful = len(crawler.processed_urls)
        stats.failed = len(crawler.failed_urls)
        stats.total_pages = stats.successful + stats.failed
        stats.robots_blocked = len(crawler.robots_blocked)
        stats.duration = round(duration, 2)
        if duration > 0:
            stats.pages_per_second = round(stats.total_pages / duration, 2)
        for url, page in crawler.processed_urls.items():
            if page.get("status_code"):
                stats.status_codes[page["status_code"]] += 1
            stats.domains[urlparse(url).hostname or "?"] += 1
            stats.total_text_length += len(page.get("text", ""))
        stats.error_types = Counter(crawler.error_stats)
        stats.retries = crawler.retry_strategy.get_stats()
        stats.failed_urls = dict(crawler.failed_urls)
        return stats

    def top_domains(self, limit: int = 10) -> list[tuple[str, int]]:
        return self.domains.most_common(limit)

    def to_dict(self) -> dict:
        return {
            "total_pages": self.total_pages,
            "successful": self.successful,
            "failed": self.failed,
            "robots_blocked": self.robots_blocked,
            "duration_seconds": self.duration,
            "pages_per_second": self.pages_per_second,
            "total_text_length": self.total_text_length,
            "status_codes": dict(self.status_codes),
            "top_domains": dict(self.top_domains()),
            "error_types": dict(self.error_types),
            "retries": self.retries,
            "failed_urls": self.failed_urls,
        }

    def export_to_json(self, filename: str | Path) -> Path:
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path

    def export_to_html_report(self, filename: str | Path) -> Path:
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self._render_html(), encoding="utf-8")
        return path

    def _render_html(self) -> str:
        summary_rows = "".join(
            f"<tr><th>{name}</th><td>{value}</td></tr>"
            for name, value in [
                ("Всего страниц", self.total_pages),
                ("Успешно", self.successful),
                ("Ошибок", self.failed),
                ("Заблокировано robots.txt", self.robots_blocked),
                ("Время работы, c", self.duration),
                ("Скорость, страниц/с", self.pages_per_second),
                ("Повторов (успешных)",
                 f"{self.retries['total_retries']} ({self.retries['successful_retries']})"),
            ]
        )

        max_count = max(self.status_codes.values(), default=1)
        status_rows = "".join(
            f"<tr><td>{code}</td><td>{count}</td>"
            f'<td><span class="bar" style="width:{count / max_count * 200:.0f}px"></span></td></tr>'
            for code, count in sorted(self.status_codes.items())
        )

        domain_rows = "".join(
            f"<tr><td>{domain}</td><td>{count}</td></tr>"
            for domain, count in self.top_domains()
        )

        error_rows = "".join(
            f"<tr><td>{name}</td><td>{count}</td></tr>"
            for name, count in self.error_types.most_common()
        ) or "<tr><td colspan=2>нет</td></tr>"

        failed_items = "".join(
            f'<li><span class="fail">{error}</span> — {url}</li>'
            for url, error in list(self.failed_urls.items())[:50]
        ) or "<li>нет</li>"

        return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><title>Отчёт краулера</title>
<style>{HTML_STYLE}</style></head>
<body>
<h1>Отчёт о работе краулера</h1>
<h2>Сводка</h2><table>{summary_rows}</table>
<h2>Распределение по статус-кодам</h2>
<table><tr><th>Код</th><th>Страниц</th><th></th></tr>{status_rows}</table>
<h2>Топ доменов</h2>
<table><tr><th>Домен</th><th>Страниц</th></tr>{domain_rows}</table>
<h2>Ошибки по типам</h2>
<table><tr><th>Тип</th><th>Количество</th></tr>{error_rows}</table>
<h2>Неудачные URL (до 50)</h2><ul>{failed_items}</ul>
</body></html>"""
