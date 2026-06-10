# Архитектура краулера

## Карта модулей

```
src/
├── crawler.py            AsyncCrawler — ядро: HTTP-клиент + цикл обхода
├── advanced_crawler.py   AdvancedCrawler — фасад: конфиг, sitemap, статистика
├── cli.py                argparse-интерфейс (python crawler.py ...)
├── config.py             CrawlerConfig: YAML/JSON + переопределение из CLI
├── stats.py              CrawlerStats: агрегация, JSON/HTML отчёты
├── models.py             PageData, FetchResult
├── logging_setup.py      loguru: консоль + файл с ротацией
├── parsing/
│   ├── html_parser.py    HTMLParser: ссылки, текст, метаданные, таблицы...
│   └── sitemap.py        SitemapParser: urlset + sitemapindex рекурсивно
├── scheduling/
│   ├── crawler_queue.py  приоритетная очередь URL с дедупликацией
│   ├── semaphores.py     SemaphoreManager: глобальный + по-доменный лимиты
│   └── url_filter.py     URLFilter: домен, include/exclude паттерны
├── politeness/
│   ├── rate_limiter.py   RateLimiter: интервалы между запросами по доменам
│   └── robots.py         RobotsParser: кэш robots.txt, can_fetch, Crawl-delay
├── resilience/
│   ├── errors.py         Transient/Permanent/Network/ParseError + классификация
│   ├── retry.py          RetryStrategy: экспоненциальный backoff
│   └── circuit_breaker.py CircuitBreaker: closed → open → half-open
└── storage/
    ├── base.py           DataStorage (ABC)
    ├── json_storage.py   JSON Lines / pretty JSON
    ├── csv_storage.py    CSV с автозаголовками
    └── sqlite_storage.py SQLite c batch-вставками
```

## Поток данных при обходе

```
start_urls (+ sitemap.xml)
      │
      ▼
CrawlerQueue (приоритеты, дедупликация, глубина)
      │  get_next()
      ▼
worker × max_concurrent      ← воркеры — обычные asyncio-задачи
      │
      ├─ robots.txt: можно ли? ──нет──► robots_blocked
      ├─ CircuitBreaker: домен жив? ──нет──► failed (CircuitOpenError)
      ├─ SemaphoreManager (глобальный + по-доменный слоты)
      ├─ RateLimiter.acquire(domain)  ← + Crawl-delay из robots.txt
      ├─ HTTP GET (aiohttp, пул соединений, таймауты)
      │      └─ ошибки → классификация → RetryStrategy (backoff)
      ├─ HTMLParser.parse_html (в отдельном потоке: asyncio.to_thread)
      ├─ DataStorage.save (ретраи записи, ошибки не фатальны)
      └─ новые ссылки → URLFilter → CrawlerQueue (depth + 1)
```

## Ключевые решения

- **Самозавершающаяся очередь.** `CrawlerQueue.get_next()` возвращает `None`,
  когда очередь пуста и ни один элемент не в обработке. Воркеры просто
  выходят из цикла — не нужны ни sentinel-значения, ни отмена задач.
- **Единая точка вежливости.** Rate limiter вызывается внутри
  `_request_page`, поэтому лимиты соблюдают и `crawl()`, и прямые вызовы
  `fetch_url` / `fetch_urls`.
- **Ошибки — это типы.** `_request_page` бросает классифицированную ошибку
  (`TransientError`, `PermanentError`, ...). RetryStrategy повторяет только
  retryable-типы; публичный `fetch_url` оставляет старый контракт
  («None при ошибке»).
- **Парсинг не блокирует event loop.** BeautifulSoup — CPU-bound, поэтому
  выполняется в `asyncio.to_thread`.
- **Хранилище не может уронить обход.** Запись каждой страницы обёрнута
  в короткий retry; финальная неудача — это лог, а не исключение.

## Эволюция по дням

| День | Что добавлено |
|---|---|
| 1 | AsyncCrawler: fetch_url / fetch_urls, таймауты, пул соединений |
| 2 | HTMLParser, PageData, fetch_and_parse |
| 3 | CrawlerQueue, SemaphoreManager, URLFilter, crawl() |
| 4 | RateLimiter, RobotsParser, User-Agent |
| 5 | классификация ошибок, RetryStrategy, CircuitBreaker |
| 6 | DataStorage: JSONL / CSV / SQLite / Composite |
| 7 | SitemapParser, CrawlerStats, конфиг, CLI, Docker |
