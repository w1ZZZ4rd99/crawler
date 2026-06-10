"""Per-domain circuit breaker: fail fast when a domain keeps erroring."""

import time
from collections import defaultdict

from loguru import logger

from src.resilience.errors import TransientError

STATE_CLOSED = "closed"
STATE_OPEN = "open"
STATE_HALF_OPEN = "half_open"


class CircuitOpenError(TransientError):
    """Raised instead of a request while the domain's circuit is open."""


class CircuitBreaker:
    """Opens after N consecutive failures; lets one probe through after a cooldown."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failures: dict[str, int] = defaultdict(int)
        self._opened_at: dict[str, float] = {}

    def state(self, domain: str) -> str:
        if domain not in self._opened_at:
            return STATE_CLOSED
        if time.monotonic() - self._opened_at[domain] >= self.recovery_timeout:
            return STATE_HALF_OPEN
        return STATE_OPEN

    def allow(self, domain: str) -> bool:
        """False while the circuit is open (and the cooldown has not passed)."""
        return self.state(domain) != STATE_OPEN

    def record_success(self, domain: str) -> None:
        self._failures[domain] = 0
        if self._opened_at.pop(domain, None) is not None:
            logger.info("Circuit closed again for {}", domain)

    def record_failure(self, domain: str) -> None:
        if self.state(domain) == STATE_HALF_OPEN:
            # The probe failed: re-open for another cooldown.
            self._opened_at[domain] = time.monotonic()
            return
        self._failures[domain] += 1
        if self._failures[domain] >= self.failure_threshold and domain not in self._opened_at:
            self._opened_at[domain] = time.monotonic()
            logger.warning(
                "Circuit OPEN for {} after {} consecutive failures",
                domain,
                self._failures[domain],
            )
