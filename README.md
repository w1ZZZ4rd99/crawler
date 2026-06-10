# Асинхронный веб-краулер

Веб-краулер для парсинга сайтов на Python (asyncio + aiohttp).

## Возможности (по мере разработки)

- параллельная загрузка страниц с ограничением конкурентности (день 1)
- парсинг HTML: ссылки, текст, метаданные, картинки, заголовки, таблицы, списки (день 2)
- обход сайта: очередь с приоритетами, ограничение глубины и числа страниц,
  фильтрация URL, прогресс в реальном времени (день 3)
- правила вежливости: rate limiting по доменам, robots.txt, Crawl-delay,
  настраиваемый User-Agent (день 4)
- устойчивость: классификация ошибок, автоматические повторы с экспоненциальным
  backoff, circuit breaker по доменам (день 5)
- асинхронное сохранение результатов: JSON Lines, CSV, SQLite,
  несколько хранилищ одновременно (день 6)

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Запуск демо

```bash
# День 1: параллельная против последовательной загрузки
python -m examples.demo_fetch

# День 2: загрузка и извлечение структурированных данных
python -m examples.demo_parsing

# День 3: обход локального демо-сайта с прогрессом
python -m examples.demo_crawl
# или обход реального сайта:
python -m examples.demo_crawl --url https://example.com --max-pages 10

# День 4: rate limiting и соблюдение robots.txt
python -m examples.demo_politeness

# День 5: повторы при ошибках и отчёт об ошибках
python -m examples.demo_retries

# День 6: сохранение в JSONL + CSV + SQLite и чтение назад
python -m examples.demo_storage
```

## Тесты и линт

```bash
pytest -q
ruff check src tests examples
```

Тесты не ходят во внешнюю сеть: используется локальный aiohttp-сервер
(`tests/conftest.py`).

## Структура проекта

```
├── src/
│   ├── crawler.py         # AsyncCrawler — ядро краулера
│   ├── models.py          # PageData — модель данных страницы
│   ├── logging_setup.py   # настройка loguru
│   ├── parsing/
│   │   └── html_parser.py # HTMLParser — извлечение данных из HTML
│   ├── politeness/
│   │   ├── rate_limiter.py # ограничение частоты запросов
│   │   └── robots.py       # загрузка и проверка robots.txt
│   ├── resilience/
│   │   ├── errors.py          # иерархия и классификация ошибок
│   │   ├── retry.py           # повторы с экспоненциальным backoff
│   │   └── circuit_breaker.py # отключение «больных» доменов
│   ├── storage/
│   │   ├── base.py            # DataStorage — абстрактный интерфейс
│   │   ├── json_storage.py    # JSON Lines / форматированный JSON
│   │   ├── csv_storage.py     # CSV с автоопределением заголовков
│   │   └── sqlite_storage.py  # SQLite с batch-вставками (aiosqlite)
│   └── scheduling/
│       ├── crawler_queue.py # очередь URL с приоритетами и дедупликацией
│       ├── semaphores.py    # глобальный и по-доменный лимиты конкурентности
│       └── url_filter.py    # фильтрация URL (домен, include/exclude)
├── examples/
│   ├── demo_server.py     # локальный демо-сайт (robots.txt, /private)
│   ├── demo_fetch.py      # демо дня 1
│   ├── demo_parsing.py    # демо дня 2
│   ├── demo_crawl.py      # демо дня 3
│   ├── demo_politeness.py # демо дня 4
│   ├── demo_retries.py    # демо дня 5
│   └── demo_storage.py    # демо дня 6
├── tests/
│   ├── conftest.py        # локальный тестовый HTTP-сервер
│   ├── test_crawler.py
│   ├── test_html_parser.py
│   ├── test_queue.py
│   ├── test_url_filter.py
│   ├── test_crawl.py
│   ├── test_rate_limiter.py
│   ├── test_robots.py
│   ├── test_errors.py
│   ├── test_retry.py
│   ├── test_circuit_breaker.py
│   └── test_storage.py
├── requirements.txt
├── pytest.ini
└── ruff.toml
```

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
