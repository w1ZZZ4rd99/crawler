"""Day 5: error classification."""

import asyncio

import aiohttp

from src.resilience.errors import (
    CrawlerError,
    NetworkError,
    ParseError,
    PermanentError,
    TransientError,
    classify_exception,
    error_from_status,
)


def test_retryable_statuses_become_transient():
    for status in (429, 500, 502, 503, 504):
        error = error_from_status("http://x/", status)
        assert isinstance(error, TransientError), status
        assert error.retryable


def test_client_error_statuses_become_permanent():
    for status in (400, 401, 403, 404, 410):
        error = error_from_status("http://x/", status)
        assert isinstance(error, PermanentError), status
        assert not error.retryable


def test_retry_after_is_kept():
    error = error_from_status("http://x/", 429, retry_after=7.0)

    assert error.retry_after == 7.0
    assert error.status == 429


def test_classify_timeout():
    assert isinstance(classify_exception(asyncio.TimeoutError(), "http://x/"), TransientError)


def test_classify_network_errors():
    assert isinstance(classify_exception(aiohttp.ClientError(), "http://x/"), NetworkError)
    assert isinstance(classify_exception(ConnectionResetError(), "http://x/"), NetworkError)


def test_classify_decode_error():
    exc = UnicodeDecodeError("utf-8", b"", 0, 1, "bad byte")

    assert isinstance(classify_exception(exc, "http://x/"), ParseError)


def test_classify_passes_crawler_errors_through():
    original = PermanentError("HTTP 404", url="http://x/")

    assert classify_exception(original) is original


def test_unknown_exception_becomes_base_error():
    error = classify_exception(ValueError("odd"), "http://x/")

    assert type(error) is CrawlerError
    assert error.url == "http://x/"
