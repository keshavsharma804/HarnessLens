"""
Mock harness adapter. Emits TraceEvents matching the schema.
Used in Phase 0 to prove the contract without external dependencies.
"""

import uuid
from datetime import datetime
from app.schema import TraceEvent, EventType


class DummyHarness:
    """Simulates a harness that does a simple task: call a tool, return a result."""

    def __init__(self, harness_id: str = "dummy", cost_per_step_cents: float = 0.5):
        self.harness_id = harness_id
        self.cost_per_step = cost_per_step_cents

    def run(self, task: str) -> list[TraceEvent]:
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
            budget_consumed_cents=0.0,
        ))

        # Simulate 3 loop steps
        for step in range(1, 4):
            cumulative_cost += self.cost_per_step
            tool = "read_file" if step == 1 else "write_file"

            events.append(TraceEvent(
                run_id=run_id,
                harness_id=self.harness_id,
                event_index=step,
                turn_index=step,
                loop_step=step,
                last_tool_called=tool,
                event_type=EventType.TOOL_CALLED,
                cost_cents=self.cost_per_step,
                budget_consumed_cents=cumulative_cost,
                tool_arguments={"path": f"/tmp/step_{step}.txt"},
            ))

        events.append(TraceEvent(
            run_id=run_id,
            harness_id=self.harness_id,
            event_index=99,
            turn_index=3,
            loop_step=3,
            last_tool_called="write_file",
            event_type=EventType.RUN_COMPLETED,
            budget_consumed_cents=cumulative_cost,
        ))

        return events