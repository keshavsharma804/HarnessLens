"""
Second harness adapter. Simulates a "capable but expensive" harness.

Design contrast with DummyHarness:
- Higher cost per step
- Higher latency per step
- Extra verification step at the end
- Sometimes fails on the final step (to exercise circuit breaker later)
"""

import uuid
import time
import random
from datetime import datetime, timezone
from app.schema import TraceEvent, EventType, VerificationStatus


class SlowHarness:
    """Simulates a high-quality, high-cost harness."""

    def __init__(
        self,
        harness_id: str = "slowharness",
        cost_per_step_cents: float = 2.0,
        latency_ms: int = 800,
        fail_rate: float = 0.2,
    ):
        self.harness_id = harness_id
        self.cost_per_step = cost_per_step_cents
        self.latency_ms = latency_ms
        self.fail_rate = fail_rate

    def run(self, task: str, steps: int = 3) -> list[TraceEvent]:
        run_id = str(uuid.uuid4())[:8]
        events: list[TraceEvent] = []
        cumulative_cost = 0.0

        events.append(TraceEvent(
            run_id=run_id,
            harness_id=self.harness_id,
            event_index=0,
            turn_index=0,
            loop_step=0,
            last_tool_called=None,
            event_type=EventType.RUN_STARTED,
            latency_ms=0,
            budget_consumed_cents=0.0,
        ))

        for step in range(1, steps + 1):
            cumulative_cost += self.cost_per_step
            tool = ["read_file", "analyze_code", "write_file", "run_tests"][step % 4]

            events.append(TraceEvent(
                run_id=run_id,
                harness_id=self.harness_id,
                event_index=step,
                turn_index=step,
                loop_step=step,
                last_tool_called=tool,
                event_type=EventType.TOOL_CALLED,
                latency_ms=self.latency_ms,
                cost_cents=self.cost_per_step,
                budget_consumed_cents=cumulative_cost,
                tool_arguments={"path": f"/tmp/slow_{step}.txt"},
            ))

        # Simulate verification step (this is what makes it "capable")
        verification_passed = random.random() > self.fail_rate
        events.append(TraceEvent(
            run_id=run_id,
            harness_id=self.harness_id,
            event_index=steps + 1,
            turn_index=steps,
            loop_step=steps,
            last_tool_called=events[-1].last_tool_called,
            event_type=EventType.VERIFICATION_CHECKED,
            latency_ms=200,
            budget_consumed_cents=cumulative_cost,
            verification_status=(
                VerificationStatus.PASSED if verification_passed
                else VerificationStatus.FAILED
            ),
            verification_detail="Independent check on final artifact",
        ))

        final_type = EventType.RUN_COMPLETED if verification_passed else EventType.RUN_FAILED
        events.append(TraceEvent(
            run_id=run_id,
            harness_id=self.harness_id,
            event_index=steps + 2,
            turn_index=steps,
            loop_step=steps,
            last_tool_called=events[-1].last_tool_called,
            event_type=final_type,
            budget_consumed_cents=cumulative_cost,
            error=None if verification_passed else "Verification failed on final artifact",
        ))

        return events