"""Day 7: configuration loading and CLI overrides."""

import json

from src.cli import build_parser, config_from_args
from src.config import CrawlerConfig

YAML_BODY = """
start_urls:
  - https://example.com
max_pages: 25
requests_per_second: 1.5
respect_robots: false
exclude_patterns:
  - '\\.pdf$'
output: out/results.csv
"""


def test_defaults():
    config = CrawlerConfig()

    assert config.max_pages == 100
    assert config.respect_robots is True
    assert config.start_urls == []


def test_from_yaml(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(YAML_BODY, encoding="utf-8")

    config = CrawlerConfig.from_file(path)

    assert config.start_urls == ["https://example.com"]
    assert config.max_pages == 25
    assert config.requests_per_second == 1.5
    assert config.respect_robots is False
    assert config.exclude_patterns == [r"\.pdf$"]
    assert config.output == "out/results.csv"


def test_from_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"max_depth": 5, "user_agent": "X/1.0"}), encoding="utf-8")

    config = CrawlerConfig.from_file(path)

    assert config.max_depth == 5
    assert config.user_agent == "X/1.0"


def test_unknown_keys_are_ignored():
    config = CrawlerConfig.from_dict({"max_pages": 7, "definitely_not_a_key": 1})

    assert config.max_pages == 7
    assert not hasattr(config, "definitely_not_a_key")


def test_cli_overrides_config_file(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(YAML_BODY, encoding="utf-8")

    args = build_parser().parse_args(
        ["--config", str(path), "--max-pages", "5", "--rate-limit", "9", "--urls", "https://x"]
    )
    config = config_from_args(args)

    assert config.max_pages == 5  # CLI beats the file
    assert config.requests_per_second == 9.0
    assert config.start_urls == ["https://x"]
    assert config.respect_robots is False  # file value survives: flag not passed


def test_boolean_optional_action():
    parser = build_parser()

    assert parser.parse_args([]).respect_robots is None
    assert parser.parse_args(["--respect-robots"]).respect_robots is True
    assert parser.parse_args(["--no-respect-robots"]).respect_robots is False


def test_cli_defaults_do_not_override():
    config = CrawlerConfig(max_pages=42)
    config.apply_cli_args(build_parser().parse_args([]))

    assert config.max_pages == 42
