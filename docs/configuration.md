# Конфигурация

Конфигурация задаётся YAML- или JSON-файлом (`--config config.yaml`)
и/или флагами CLI. Приоритет: **CLI > файл > значения по умолчанию**.
Пример файла — `config.example.yaml` в корне репозитория.

## Параметры

### Область обхода

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `start_urls` | list[str] | `[]` | стартовые URL |
| `max_pages` | int | `100` | максимум страниц за обход |
| `max_depth` | int | `2` | глубина обхода от стартовых URL |
| `same_domain_only` | bool | `true` | ходить только по доменам стартовых URL |
| `include_patterns` | list[regex] | `[]` | если задано — брать только совпавшие URL |
| `exclude_patterns` | list[regex] | `[]` | пропускать совпавшие URL |
| `use_sitemap` | bool | `false` | дополнить стартовые URL ссылками из sitemap.xml |

### Конкурентность и вежливость

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `max_concurrent` | int | `10` | одновременных запросов всего |
| `per_domain_limit` | int | `3` | одновременных запросов к одному домену |
| `requests_per_second` | float/null | `null` | лимит запросов в секунду на домен |
| `min_delay` | float | `0.0` | минимальная пауза между запросами, с |
| `jitter` | float | `0.0` | случайная добавка к паузе, с |
| `respect_robots` | bool | `true` | соблюдать robots.txt и Crawl-delay |
| `user_agent` | str | `AsyncCrawler/1.0 ...` | заголовок User-Agent |

### Таймауты и повторы

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `timeout_total` | float | `30.0` | общий таймаут запроса, с |
| `max_retries` | int | `3` | повторов для временных ошибок |
| `backoff_factor` | float | `2.0` | множитель экспоненциального backoff |

### Вывод и логирование

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `output` | str/null | `data/results.db` | файл результатов; формат по расширению: `.db`/`.sqlite` (SQLite), `.jsonl`, `.json` (pretty), `.csv` |
| `report_html` | str/null | `null` | HTML-отчёт со статистикой |
| `stats_json` | str/null | `null` | статистика в JSON |
| `log_level` | str | `INFO` | DEBUG / INFO / WARNING / ERROR |
| `log_file` | str/null | `null` | файл логов (ротация 10 MB, хранится 5 архивов) |

## Флаги CLI

```
python crawler.py --urls URL [URL ...]
                  [--config FILE]
                  [--max-pages N] [--max-depth N] [--max-concurrent N]
                  [--rate-limit N] [--respect-robots | --no-respect-robots]
                  [--use-sitemap]
                  [--output FILE] [--report FILE] [--stats-json FILE]
                  [--log-level LEVEL] [--log-file FILE]
```

Примеры:

```bash
# Быстрый обход: результаты в SQLite + HTML-отчёт
python crawler.py --urls https://example.com --max-pages 30 \
    --output data/results.db --report data/report.html

# Всё из конфига, но глубже и в CSV
python crawler.py --config config.yaml --max-depth 3 --output data/results.csv

# Сидирование из sitemap.xml без обхода ссылок
python crawler.py --urls https://example.com --use-sitemap --max-depth 0
```
