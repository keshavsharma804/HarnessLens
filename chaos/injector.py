"""
Chaos injector for real fault testing.

Wraps a real adapter and injects failures at controlled points.
The failures are real exceptions raised in the real code path.
The circuit breaker that responds to them is real.

Based on ReliabilityBench methodology (arXiv 2601.06112):
inject timeouts, rate limits, and partial responses, then measure
whether the system's resilience mechanisms respond correctly.
"""

from functools import wraps


class ChaosInjector:
    """
    Wraps a callable to inject failures on specified call counts.

    Usage:
        injector = ChaosInjector(fail_on_calls={1, 2, 3})
        wrapped = injector.wrap(real_adapter.run)
        events, patch = wrapped(task, instance_id)  # raises on calls 1, 2, 3
    """

    def __init__(self, fail_on_calls: set = None, fault_type: str = "timeout"):
        self.fail_on_calls = fail_on_calls or set()
        self.fault_type = fault_type
        self.call_count = 0
        self.faults_injected = 0
        self.calls_succeeded = 0

    def wrap(self, func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            self.call_count += 1
            if self.call_count in self.fail_on_calls:
                self.faults_injected += 1
                if self.fault_type == "timeout":
                    raise TimeoutError(
                        f"Injected timeout on call {self.call_count}"
                    )
                elif self.fault_type == "rate_limit":
                    raise Exception(
                        f"Injected 429 rate limit on call {self.call_count}"
                    )
                elif self.fault_type == "network":
                    raise ConnectionError(
                        f"Injected network partition on call {self.call_count}"
                    )
            self.calls_succeeded += 1
            return func(*args, **kwargs)
        return wrapped

    def snapshot(self) -> dict:
        return {
            "total_calls": self.call_count,
            "faults_injected": self.faults_injected,
            "calls_succeeded": self.calls_succeeded,
        }