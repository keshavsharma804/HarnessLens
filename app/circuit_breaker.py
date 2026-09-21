"""
Per-harness circuit breaker.

State machine:
  CLOSED     -> normal operation
  OPEN       -> too many failures; reject calls for cooldown period
  HALF_OPEN  -> cooldown elapsed; allow ONE probe call to test recovery

Design rationale:
- Failure threshold and cooldown are policy-driven, not hardcoded.
- State is per-harness, so one bad harness does not block others.
- The breaker is consulted by the router BEFORE scoring. If a harness is OPEN,
  it is excluded from the candidate pool entirely.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """
    One breaker per harness. Persisted in-process; can be externalized later.
    """

    harness_id: str
    failure_threshold: int = 3
    cooldown_seconds: float = 30.0

    state: BreakerState = BreakerState.CLOSED
    consecutive_failures: int = 0
    opened_at: Optional[float] = None
    half_open_in_flight: bool = False

    def allow_call(self) -> bool:
        """
        Should the router send a request to this harness right now?
        """
        if self.state == BreakerState.CLOSED:
            return True

        if self.state == BreakerState.OPEN:
            # Time to probe?
            if self.opened_at is None:
                return False
            if (time.time() - self.opened_at) >= self.cooldown_seconds:
                self.state = BreakerState.HALF_OPEN
                self.half_open_in_flight = False
                return True
            return False

        if self.state == BreakerState.HALF_OPEN:
            # Only one probe at a time.
            if self.half_open_in_flight:
                return False
            self.half_open_in_flight = True
            return True

        return False

    def record_success(self) -> None:
        """Called when a request to this harness succeeds."""
        self.consecutive_failures = 0
        self.state = BreakerState.CLOSED
        self.opened_at = None
        self.half_open_in_flight = False

    def record_failure(self) -> None:
        """Called when a request to this harness fails."""
        self.consecutive_failures += 1
        self.half_open_in_flight = False

        if self.state == BreakerState.HALF_OPEN:
            # Probe failed; reopen.
            self.state = BreakerState.OPEN
            self.opened_at = time.time()
            return

        if self.consecutive_failures >= self.failure_threshold:
            self.state = BreakerState.OPEN
            self.opened_at = time.time()

    def snapshot(self) -> dict:
        """For observability. Emit this as a metric."""
        return {
            "harness_id": self.harness_id,
            "state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "opened_at": self.opened_at,
        }


class BreakerRegistry:
    """
    Holds one breaker per harness.

    A registry is process-global in this prototype. In production it would
    live in Redis or a sidecar so all control plane replicas share state.
    """

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 30.0):
        self._breakers: dict[str, CircuitBreaker] = {}
        self._default_threshold = failure_threshold
        self._default_cooldown = cooldown_seconds

    def get(self, harness_id: str) -> CircuitBreaker:
        if harness_id not in self._breakers:
            self._breakers[harness_id] = CircuitBreaker(
                harness_id=harness_id,
                failure_threshold=self._default_threshold,
                cooldown_seconds=self._default_cooldown,
            )
        return self._breakers[harness_id]

    def allowed_harnesses(self, harness_ids: list[str]) -> list[str]:
        """Filter a list of harness IDs down to those currently callable."""
        return [h for h in harness_ids if self.get(h).allow_call()]

    def snapshot_all(self) -> list[dict]:
        return [b.snapshot() for b in self._breakers.values()]


# Module-level default registry. Router imports this unless overridden.
default_registry = BreakerRegistry()