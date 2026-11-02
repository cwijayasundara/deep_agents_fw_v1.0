"""Retry with real exponential backoff + jitter, and a circuit breaker.

Schema-independent: used by the Decisions client, usable for any flaky upstream.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable


class Unavailable(RuntimeError):
    """Upstream is unusable right now (breaker open or retries exhausted)."""


def backoff_delay(attempt: int, base: float, cap: float, rng: random.Random) -> float:
    """Full-jitter exponential backoff: uniform(0, min(cap, base * 2**attempt))."""
    return rng.uniform(0, min(cap, base * (2**attempt)))


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = failure_threshold
        self._reset = reset_timeout
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None
        self._probing = False

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if self._clock() - self._opened_at >= self._reset:
            return "half_open"
        return "open"

    def allow(self) -> bool:
        s = self.state
        if s == "closed":
            return True
        if s == "half_open" and not self._probing:
            self._probing = True  # exactly one probe at a time
            return True
        return False

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None
        self._probing = False

    def record_failure(self) -> None:
        self._probing = False
        self._failures += 1
        if self._opened_at is not None or self._failures >= self._threshold:
            self._opened_at = self._clock()


_SHARED: dict[str, CircuitBreaker] = {}


def shared_breaker(name: str) -> CircuitBreaker:
    """The process-wide breaker for upstream `name`, so state survives rebuilding clients."""
    if name not in _SHARED:
        _SHARED[name] = CircuitBreaker()
    return _SHARED[name]


def reset_shared_breakers() -> None:
    """Forget every shared breaker (tests)."""
    _SHARED.clear()


async def call_with_retry[T](
    fn: Callable[[], Awaitable[T]],
    *,
    breaker: CircuitBreaker,
    retry_on: tuple[type[BaseException], ...],
    attempts: int = 3,
    base: float = 0.5,
    cap: float = 8.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    rng: random.Random | None = None,
) -> T:
    rng = rng or random.Random()
    last: BaseException | None = None
    for attempt in range(attempts):
        if not breaker.allow():
            raise Unavailable("circuit breaker open") from last
        try:
            result = await fn()
        except retry_on as e:
            breaker.record_failure()
            last = e
            if attempt < attempts - 1:
                await sleep(backoff_delay(attempt, base, cap, rng))
        else:
            breaker.record_success()
            return result
    raise Unavailable(f"retries exhausted after {attempts} attempts") from last
