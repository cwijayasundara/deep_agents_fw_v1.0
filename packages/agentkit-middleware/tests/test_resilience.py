import random

import pytest
from agentkit_middleware import CircuitBreaker, Unavailable, backoff_delay, call_with_retry


class Clock:
    t = 0.0

    def __call__(self) -> float:
        return self.t


def test_backoff_grows_exponentially_and_caps():
    class Max(random.Random):
        def uniform(self, a, b):
            return b

    r = Max()
    assert [backoff_delay(i, 0.5, 4.0, r) for i in range(5)] == [0.5, 1.0, 2.0, 4.0, 4.0]


def test_backoff_is_jittered():
    r = random.Random(1)
    assert len({backoff_delay(3, 0.5, 8.0, r) for _ in range(10)}) > 1


def test_breaker_transitions():
    clk = Clock()
    b = CircuitBreaker(failure_threshold=2, reset_timeout=10, clock=clk)
    assert b.state == "closed"
    b.record_failure()
    assert b.state == "closed"
    b.record_failure()
    assert b.state == "open" and not b.allow()
    clk.t = 10
    assert b.state == "half_open"
    assert b.allow() and not b.allow()  # single probe
    b.record_failure()
    assert b.state == "open"  # failed probe reopens
    clk.t = 20
    assert b.allow()
    b.record_success()
    assert b.state == "closed"


async def test_retry_sleeps_with_backoff_then_succeeds():
    sleeps: list[float] = []
    calls = 0

    async def fn():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionError
        return "ok"

    async def sleep(s):
        sleeps.append(s)

    out = await call_with_retry(
        fn, breaker=CircuitBreaker(), retry_on=(ConnectionError,), sleep=sleep, base=1, cap=8
    )
    assert out == "ok" and calls == 3 and len(sleeps) == 2
    assert sleeps[0] <= 1 and sleeps[1] <= 2


async def test_retry_exhausted_raises_unavailable():
    async def fn():
        raise ConnectionError

    async def sleep(s):
        pass

    with pytest.raises(Unavailable):
        await call_with_retry(
            fn, breaker=CircuitBreaker(10), retry_on=(ConnectionError,), sleep=sleep, attempts=2
        )


async def test_open_breaker_short_circuits_without_calling():
    b = CircuitBreaker(failure_threshold=1, reset_timeout=100, clock=Clock())
    b.record_failure()
    called = False

    async def fn():
        nonlocal called
        called = True

    with pytest.raises(Unavailable):
        await call_with_retry(fn, breaker=b, retry_on=(ConnectionError,))
    assert not called


async def test_non_retryable_error_propagates():
    async def fn():
        raise KeyError("x")

    with pytest.raises(KeyError):
        await call_with_retry(fn, breaker=CircuitBreaker(), retry_on=(ConnectionError,))
