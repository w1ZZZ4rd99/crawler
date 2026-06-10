"""Day 4: RateLimiter spacing, per-domain isolation and stats."""

import asyncio
import time

from src.politeness.rate_limiter import RateLimiter

# Timing assertions use a tolerance to avoid flakiness on slow machines.
TOLERANCE = 0.85


async def test_single_domain_requests_are_spaced():
    limiter = RateLimiter(requests_per_second=5.0)  # 0.2s interval

    start = time.monotonic()
    for _ in range(3):
        await limiter.acquire("example.com")
    elapsed = time.monotonic() - start

    assert elapsed >= 0.4 * TOLERANCE  # 2 intervals after the first request


async def test_domains_do_not_block_each_other():
    limiter = RateLimiter(requests_per_second=2.0)  # 0.5s interval

    start = time.monotonic()
    await asyncio.gather(*(limiter.acquire(f"domain{i}.com") for i in range(4)))
    elapsed = time.monotonic() - start

    assert elapsed < 0.3  # the first slot of every domain is free


async def test_global_mode_spaces_all_domains():
    limiter = RateLimiter(requests_per_second=5.0, per_domain=False)

    start = time.monotonic()
    await asyncio.gather(*(limiter.acquire(f"d{i}.com") for i in range(3)))
    elapsed = time.monotonic() - start

    assert elapsed >= 0.4 * TOLERANCE


async def test_min_delay_applies():
    limiter = RateLimiter(requests_per_second=100.0, min_delay=0.2)

    start = time.monotonic()
    await limiter.acquire("x")
    await limiter.acquire("x")
    elapsed = time.monotonic() - start

    assert elapsed >= 0.2 * TOLERANCE


async def test_override_interval_extends_spacing():
    limiter = RateLimiter(requests_per_second=100.0)

    start = time.monotonic()
    await limiter.acquire("x", override_interval=0.3)
    await limiter.acquire("x")
    elapsed = time.monotonic() - start

    assert elapsed >= 0.3 * TOLERANCE


async def test_disabled_rate_does_not_wait():
    limiter = RateLimiter(requests_per_second=None)

    start = time.monotonic()
    await asyncio.gather(*(limiter.acquire("x") for _ in range(10)))
    elapsed = time.monotonic() - start

    assert elapsed < 0.1


async def test_penalize_delays_next_request():
    limiter = RateLimiter(requests_per_second=None)
    limiter.penalize("x", 0.3)

    start = time.monotonic()
    await limiter.acquire("x")
    elapsed = time.monotonic() - start

    assert elapsed >= 0.3 * TOLERANCE


async def test_stats_are_tracked():
    limiter = RateLimiter(requests_per_second=10.0)
    for _ in range(3):
        await limiter.acquire("x")

    stats = limiter.get_stats()
    assert stats["acquired"] == 3
    assert stats["total_wait"] >= 0.0
    assert stats["current_rps"] > 0.0
