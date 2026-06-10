"""Retry execution with exponential backoff."""

import asyncio
import random

from loguru import logger

from src.resilience.errors import NetworkError, TransientError


class RetryStrategy:
    """Re-runs a coroutine function on retryable errors with exponential backoff.

    Non-retryable exceptions (e.g. PermanentError) propagate immediately.
    """

    def __init__(
        self,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        base_delay: float = 0.5,
        max_delay: float = 30.0,
        jitter: float = 0.1,
        retry_on: tuple[type[Exception], ...] = (TransientError, NetworkError),
    ) -> None:
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self.retry_on = tuple(retry_on)
        # Statistics
        self.total_retries = 0
        self.successful_retries = 0

    def backoff_delay(self, attempt: int, retry_after: float | None = None) -> float:
        delay = min(self.base_delay * self.backoff_factor**attempt, self.max_delay)
        if retry_after is not None:
            delay = max(delay, retry_after)  # the server knows better (429/503)
        if self.jitter:
            delay += random.uniform(0.0, self.jitter * delay)
        return delay

    async def execute_with_retry(self, func, *args, on_attempt=None, **kwargs):
        """Run func(*args, **kwargs), retrying on the configured errors.

        on_attempt(n) may return extra kwargs for attempt n (e.g. to scale
        timeouts on each retry).
        """
        for attempt in range(self.max_retries + 1):
            extra = on_attempt(attempt) if on_attempt else {}
            try:
                result = await func(*args, **kwargs, **extra)
            except self.retry_on as exc:
                if attempt == self.max_retries:
                    logger.warning("Giving up after {} attempts: {}", attempt + 1, exc)
                    raise
                delay = self.backoff_delay(attempt, getattr(exc, "retry_after", None))
                self.total_retries += 1
                logger.warning(
                    "Attempt {}/{} failed ({}: {}), retrying in {:.2f}s",
                    attempt + 1,
                    self.max_retries + 1,
                    exc.__class__.__name__,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                if attempt > 0:
                    self.successful_retries += 1
                    logger.info("Succeeded on attempt {}", attempt + 1)
                return result

    def get_stats(self) -> dict:
        return {
            "total_retries": self.total_retries,
            "successful_retries": self.successful_retries,
        }
