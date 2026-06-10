"""Crawler configuration: dataclass, YAML/JSON loading, CLI overrides."""

import json
from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml
from loguru import logger

# (CLI argument name, config field name) pairs for overrides.
CLI_OVERRIDES = [
    ("urls", "start_urls"),
    ("max_pages", "max_pages"),
    ("max_depth", "max_depth"),
    ("max_concurrent", "max_concurrent"),
    ("rate_limit", "requests_per_second"),
    ("respect_robots", "respect_robots"),
    ("use_sitemap", "use_sitemap"),
    ("output", "output"),
    ("report", "report_html"),
    ("stats_json", "stats_json"),
    ("log_level", "log_level"),
    ("log_file", "log_file"),
]


@dataclass
class CrawlerConfig:
    """All crawler knobs; defaults match a polite small crawl."""

    # Crawl scope
    start_urls: list[str] = field(default_factory=list)
    max_pages: int = 100
    max_depth: int = 2
    same_domain_only: bool = True
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    use_sitemap: bool = False
    # Concurrency and politeness
    max_concurrent: int = 10
    per_domain_limit: int = 3
    requests_per_second: float | None = None
    min_delay: float = 0.0
    jitter: float = 0.0
    respect_robots: bool = True
    user_agent: str = "AsyncCrawler/1.0 (educational project)"
    # Timeouts and retries
    timeout_total: float = 30.0
    max_retries: int = 3
    backoff_factor: float = 2.0
    # Output (the storage backend is picked by extension; SQLite by default)
    output: str | None = "data/results.db"
    report_html: str | None = None
    stats_json: str | None = None
    # Logging
    log_level: str = "INFO"
    log_file: str | None = None

    @classmethod
    def from_file(cls, path: str | Path) -> "CrawlerConfig":
        """Load YAML (.yaml/.yml) or JSON config."""
        path = Path(path)
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() in {".yaml", ".yml"}:
            raw = yaml.safe_load(text)
        else:
            raw = json.loads(text)
        return cls.from_dict(raw or {})

    @classmethod
    def from_dict(cls, raw: dict) -> "CrawlerConfig":
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(raw) - known)
        if unknown:
            logger.warning("Unknown config keys ignored: {}", unknown)
        return cls(**{key: value for key, value in raw.items() if key in known})

    def apply_cli_args(self, args) -> None:
        """CLI flags beat config-file values, but only when explicitly given."""
        for arg_name, field_name in CLI_OVERRIDES:
            value = getattr(args, arg_name, None)
            if value is not None:
                setattr(self, field_name, value)
