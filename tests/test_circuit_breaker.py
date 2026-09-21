"""Verify circuit breaker trips, rejects, and recovers."""

import time
from app.circuit_breaker import CircuitBreaker, BreakerState, BreakerRegistry


def test_breaker_starts_closed():
    cb = CircuitBreaker("h1")
    assert cb.state == BreakerState.CLOSED
    assert cb.allow_call() is True


def test_breaker_opens_after_threshold():
    cb = CircuitBreaker("h1", failure_threshold=3, cooldown_seconds=10.0)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == BreakerState.CLOSED
    cb.record_failure()  # third failure
    assert cb.state == BreakerState.OPEN
    assert cb.allow_call() is False


def test_breaker_recovers_after_cooldown():
    cb = CircuitBreaker("h1", failure_threshold=1, cooldown_seconds=0.1)
    cb.record_failure()
    assert cb.state == BreakerState.OPEN

    time.sleep(0.2)
    assert cb.allow_call() is True
    assert cb.state == BreakerState.HALF_OPEN

    cb.record_success()
    assert cb.state == BreakerState.CLOSED


def test_registry_filters_open_breakers():
    reg = BreakerRegistry(failure_threshold=1, cooldown_seconds=60.0)
    reg.get("h1").record_failure()
    allowed = reg.allowed_harnesses(["h1", "h2"])
    assert allowed == ["h2"]