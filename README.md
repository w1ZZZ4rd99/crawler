# Асинхронный веб-краулер

Веб-краулер для парсинга сайтов на Python (asyncio + aiohttp).

## Возможности (по мере разработки)

- параллельная загрузка страниц с ограничением конкурентности (день 1)
- парсинг HTML: ссылки, текст, метаданные, картинки, заголовки, таблицы, списки (день 2)

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
│   └── parsing/
│       └── html_parser.py # HTMLParser — извлечение данных из HTML
├── examples/
│   ├── demo_fetch.py      # демо дня 1
│   └── demo_parsing.py    # демо дня 2
├── tests/
│   ├── conftest.py        # локальный тестовый HTTP-сервер
│   ├── test_crawler.py
│   └── test_html_parser.py
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
