"""Crawler error hierarchy and classification helpers."""

import asyncio

import aiohttp

RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class CrawlerError(Exception):
    """Base error; keeps the URL and an optional HTTP status."""

    retryable = False

    def __init__(
        self,
        message: str,
        url: str = "",
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.url = url
        self.status = status
        self.retry_after = retry_after  # from the Retry-After header (429/503)


class TransientError(CrawlerError):
    """Temporary failures: timeouts, 429 and 5xx — worth retrying."""

    retryable = True


class PermanentError(CrawlerError):
    """Permanent failures (404, 403, ...) — retrying is pointless."""

    retryable = False


class NetworkError(CrawlerError):
    """Connection-level failures: DNS, refused connections, resets."""

    retryable = True


class ParseError(CrawlerError):
    """Content decoding / HTML parsing failures."""

    retryable = False


def error_from_status(
    url: str, status: int, message: str = "", retry_after: float | None = None
) -> CrawlerError:
    text = message or f"HTTP {status}"
    if status in RETRYABLE_STATUSES:
        return TransientError(text, url=url, status=status, retry_after=retry_after)
    return PermanentError(text, url=url, status=status)


def classify_exception(exc: BaseException, url: str = "") -> CrawlerError:
    """Map third-party/asyncio exceptions onto the crawler error hierarchy."""
    if isinstance(exc, CrawlerError):
        return exc
    if isinstance(exc, aiohttp.ClientResponseError):
        return error_from_status(url, exc.status, exc.message)
    # Checked before ClientError: aiohttp timeout errors subclass both.
    if isinstance(exc, asyncio.TimeoutError):
        return TransientError("timeout", url=url)
    if isinstance(exc, aiohttp.ClientError | OSError):
        return NetworkError(exc.__class__.__name__, url=url)
    if isinstance(exc, UnicodeDecodeError):
        return ParseError("cannot decode response body", url=url)
    return CrawlerError(repr(exc), url=url)
