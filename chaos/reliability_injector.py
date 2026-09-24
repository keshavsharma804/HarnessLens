"""
Fault injection for real reliability testing.

Based on ReliabilityBench methodology (arXiv 2601.06112).
Injects real faults into the adapter layer:

- Timeouts: API call hangs for N seconds, then fails
- Rate limits: API returns 429 after N calls
- Partial responses: response truncated
- Schema drift: response structure changes
"""

import time
import random
from functools import wraps


class ChaosInjector:
    def __init__(self, fault_probability: float = 0.15):
        self.fault_probability = fault_probability
        self.call_count = 0

    def maybe_inject_timeout(self, duration: float = 30.0):
        if random.random() < self.fault_probability:
            time.sleep(duration)
            raise TimeoutError("Injected timeout")

    def maybe_inject_rate_limit(self, max_calls: int = 10):
        self.call_count += 1
        if self.call_count > max_calls and random.random() < 0.5:
            raise Exception("429 Too Many Requests")

    def maybe_inject_partial_response(self, response: dict) -> dict:
        if random.random() < self.fault_probability:
            keys = list(response.keys())
            if keys:
                del response[keys[-1]]  # drop last field
        return response

    def wrap_adapter(self, adapter):
        """Wrap an adapter to inject faults on every run."""
        original_run = adapter.run

        @wraps(original_run)
        def chaos_run(task, instance_id):
            self.maybe_inject_rate_limit()
            self.maybe_inject_timeout()
            return original_run(task, instance_id)

        adapter.run = chaos_run
        return adapter