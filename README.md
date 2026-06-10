# Асинхронный веб-краулер

Веб-краулер для парсинга сайтов на Python (asyncio + aiohttp).

## Возможности (по мере разработки)

- параллельная загрузка страниц с ограничением конкурентности (день 1)

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
│   └── logging_setup.py   # настройка loguru
├── examples/
│   └── demo_fetch.py      # демо дня 1
├── tests/
│   ├── conftest.py        # локальный тестовый HTTP-сервер
│   └── test_crawler.py
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
