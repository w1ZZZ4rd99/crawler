# Асинхронный веб-краулер

Веб-краулер для парсинга сайтов на Python (asyncio + aiohttp): параллельный
обход страниц, извлечение данных из HTML, соблюдение правил вежливости,
устойчивость к ошибкам и сохранение результатов в файлы и базу данных.

## Возможности

- параллельная загрузка страниц с ограничением конкурентности (глобально и по доменам)
- парсинг HTML: ссылки, текст, метаданные, картинки, заголовки, таблицы, списки
- обход сайта: очередь с приоритетами, ограничение глубины и числа страниц,
  фильтрация URL, прогресс с процентами и ETA в реальном времени
- правила вежливости: rate limiting по доменам, robots.txt, Crawl-delay,
  настраиваемый User-Agent
- устойчивость: классификация ошибок, повторы с экспоненциальным backoff,
  circuit breaker по доменам
- сохранение: JSON Lines, JSON, CSV, SQLite — в одно или несколько хранилищ сразу
- sitemap.xml (включая sitemap index) как источник стартовых URL
- статистика и отчёты: JSON и автономный HTML-отчёт
- конфигурация через YAML/JSON + CLI, логирование в файл с ротацией, Docker

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Быстрый старт (CLI)

```bash
# результаты — в SQLite (data/results.db) + HTML-отчёт
python crawler.py --urls https://example.com --max-pages 30 \
    --output data/results.db --report data/report.html

# посмотреть сохранённое
sqlite3 data/results.db 'SELECT url, title, status_code FROM pages LIMIT 5;'

# или всё через конфиг (пример: config.example.yaml)
cp config.example.yaml config.yaml
python crawler.py --config config.yaml
```

Формат результата определяется расширением `--output`:
`.db`/`.sqlite` (SQLite, по умолчанию), `.jsonl` (построчно),
`.json` (форматированный массив), `.csv`.
Все параметры — в [docs/configuration.md](docs/configuration.md).

## Запуск в Docker

```bash
docker compose up --build
```

Поднимает локальный демо-сайт и краулер, который его обходит; результаты
появляются в `./data`: база SQLite `results.db`, `report.html`, `stats.json`,
логи — в `./logs`. Отдельный сервис для базы не нужен: SQLite — встраиваемая
БД без серверного процесса, краулер пишет в файл через aiosqlite.

## Использование как библиотеки

```python
import asyncio

from src.advanced_crawler import AdvancedCrawler

async def main():
    crawler = AdvancedCrawler.from_config("config.yaml")
    await crawler.crawl()

    stats = crawler.get_stats()
    print(f"Обработано: {stats['total_pages']} страниц")
    print(f"Успешно: {stats['successful']}, ошибок: {stats['failed']}")

    crawler.export_to_html_report("data/report.html")
    await crawler.close()

asyncio.run(main())
```

Низкоуровневый API (`AsyncCrawler`: `fetch_url`, `fetch_urls`,
`fetch_and_parse`, `crawl`) — см. [docs/architecture.md](docs/architecture.md).

## Демо по дням

```bash
python -m examples.demo_fetch       # день 1: параллельная загрузка vs последовательная
python -m examples.demo_parsing     # день 2: извлечение данных из HTML
python -m examples.demo_crawl       # день 3: обход сайта с прогрессом
python -m examples.demo_politeness  # день 4: rate limiting и robots.txt
python -m examples.demo_retries     # день 5: повторы и отчёт об ошибках
python -m examples.demo_storage     # день 6: JSONL + CSV + SQLite
python -m scripts.benchmark         # день 7: производительность и память
```

Демо работают против локального демо-сайта (`examples/demo_server.py`) —
интернет не нужен.

## Тесты и линт

```bash
pytest -q
ruff check src tests examples scripts
```

Тесты (100+) не ходят во внешнюю сеть: все сценарии — против локальных
aiohttp-серверов, включая флаки-страницы, robots.txt и sitemap.

## Структура проекта

```
├── crawler.py             # точка входа CLI
├── config.example.yaml    # пример конфигурации
├── Dockerfile / docker-compose.yml
├── src/
│   ├── crawler.py         # AsyncCrawler — ядро краулера
│   ├── advanced_crawler.py# AdvancedCrawler — конфиг + статистика + sitemap
│   ├── cli.py             # argparse-интерфейс
│   ├── config.py          # CrawlerConfig (YAML/JSON + CLI)
│   ├── stats.py           # CrawlerStats + JSON/HTML отчёты
│   ├── models.py          # PageData, FetchResult
│   ├── logging_setup.py   # loguru: консоль + файл с ротацией
│   ├── parsing/           # html_parser.py, sitemap.py
│   ├── scheduling/        # crawler_queue.py, semaphores.py, url_filter.py
│   ├── politeness/        # rate_limiter.py, robots.py
│   ├── resilience/        # errors.py, retry.py, circuit_breaker.py
│   └── storage/           # base.py, json/csv/sqlite_storage.py
├── examples/              # демо-скрипты + локальный демо-сайт
├── scripts/benchmark.py   # замер производительности
├── tests/                 # pytest + pytest-asyncio, локальные серверы
└── docs/                  # architecture.md, configuration.md
```

Подробное описание архитектуры и потока данных — в
[docs/architecture.md](docs/architecture.md).

## Прогресс по дням

### День 1 — базовый асинхронный HTTP-клиент ✅

- `AsyncCrawler`: `fetch_url`, `fetch_urls`, `close`, поддержка `async with`
- `aiohttp.ClientSession` с таймаутами (total / connect / sock_read)
  и пулом соединений (`TCPConnector`)
- ограничение конкурентности через `asyncio.Semaphore`
- обработка ошибок: HTTP-статусы, таймауты, сетевые ошибки — без падения
- логирование старта/успеха/ошибок каждого запроса (loguru)
- демо: 8 URL параллельно и последовательно, замер ускорения

### День 2 — парсинг HTML и извлечение данных ✅

- `HTMLParser`: `parse_html` (в отдельном потоке через `asyncio.to_thread`),
  `extract_links`, `extract_text`, `extract_metadata`
- извлечение картинок (src/alt), заголовков h1–h3, таблиц и списков
- относительные ссылки конвертируются в абсолютные (`urljoin`),
  отбрасываются fragment/`mailto:`/`javascript:`, дедупликация
- модель `PageData` (`src/models.py`)
- `AsyncCrawler.fetch_and_parse(url)` — загрузка + парсинг одним вызовом
- ошибки парсинга не роняют программу: частичный результат + warning в логе

### День 3 — управление конкурентностью и очередями ✅

- `CrawlerQueue`: приоритетная очередь URL, дедупликация, самозавершение
  (`get_next()` возвращает `None`, когда очередь пуста и всё обработано)
- `SemaphoreManager`: глобальный лимит + лимит одновременных запросов к домену
- `URLFilter`: только тот же домен (`same_domain_only`), include/exclude паттерны
- `AsyncCrawler.crawl(start_urls, max_pages, max_depth, ...)`: пул воркеров,
  автодобавление найденных ссылок, контроль глубины, состояние
  `visited_urls` / `processed_urls` / `failed_urls`
- прогресс в реальном времени: обработано / в очереди / активно / ошибок / страниц-в-сек
- локальный демо-сайт (`examples/demo_server.py`) для офлайн-демо и тестов

### День 4 — rate limiting и правила вежливости ✅

- `RateLimiter`: лимит запросов в секунду на домен или глобально,
  `min_delay`, случайный `jitter`, `penalize()` для штрафных задержек
- `RobotsParser`: загрузка robots.txt (одна на домен, кэш + lock),
  `can_fetch`, `get_crawl_delay`; недоступный robots.txt = «всё разрешено»
- интеграция: лимит применяется перед каждым запросом (`fetch_url`),
  Crawl-delay из robots.txt усиливает лимит, запрещённые URL пропускаются
  и учитываются отдельно (`robots_blocked`), настраиваемый User-Agent
- мониторинг: текущий req/s, средняя задержка, количество блокировок

### День 5 — обработка ошибок и автоматические повторы ✅

- иерархия ошибок: `TransientError` (таймауты, 429/5xx), `PermanentError`
  (404/403/...), `NetworkError` (DNS, connection refused), `ParseError`
- `RetryStrategy.execute_with_retry`: экспоненциальный backoff с jitter,
  уважение `Retry-After` (429), повторы только для retryable-ошибок,
  увеличение таймаутов на каждой попытке
- `CircuitBreaker`: после N подряд ошибок домен временно отключается
  (closed → open → half-open), пробный запрос после паузы
- `fetch_url` теперь работает поверх `_request_page`, который бросает
  классифицированные ошибки; публичное поведение прежнее (None при ошибке)
- статистика: ошибки по типам, число повторов, успешные повторы;
  отчёт об ошибках в `data/error_report.json` (демо)

### День 6 — сохранение данных ✅

- абстрактный `DataStorage` (save / save_many / close, `async with`)
- `JSONStorage`: JSON Lines построчно (большие объёмы) или форматированный
  JSON-массив (`pretty=True`); `CSVStorage`: заголовки из первой записи,
  вложенные структуры как JSON-строки, экранирование через модуль `csv`;
  `SQLiteStorage`: aiosqlite, batch-вставки `executemany`, `INSERT OR REPLACE`
  по уникальному URL, индекс по `crawled_at`
- `CompositeStorage` — запись в несколько хранилищ одновременно
- единый формат записи: url, title, text, links, metadata, crawled_at,
  status_code, content_type (`PageData`)
- интеграция: `AsyncCrawler(storage=...)` сохраняет каждую обработанную
  страницу; ошибки записи ретраятся и логируются, краул не падает

### День 7 — продвинутые возможности и интеграция ✅

- `SitemapParser`: обычные sitemap и sitemap index (рекурсивно, с лимитом
  глубины), обнаружение sitemap через robots.txt, `use_sitemap` сидирует очередь
- `CrawlerStats`: успешные/неудачные, скорость, распределение статус-кодов,
  топ доменов, ошибки по типам, повторы; экспорт в JSON и автономный HTML-отчёт
- `CrawlerConfig`: YAML/JSON конфиг + переопределение флагами CLI
- CLI (`python crawler.py --urls ... --max-pages ... --output ...`)
- `AdvancedCrawler` — фасад, собирающий все компоненты
- логирование в файл с ротацией и сжатием (loguru)
- прогресс: проценты, ETA, скорость, активные задачи
- Docker + docker-compose (демо-сайт + краулер из коробки)
- `scripts/benchmark.py`: последовательный против асинхронного режим,
  100/500 страниц, пиковая память (tracemalloc)
