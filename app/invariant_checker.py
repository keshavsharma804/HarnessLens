"""
Runtime invariant monitor.

Checks control-plane invariants against every event in a trajectory.
Violations emit INVARIANT_VIOLATION events and can trigger hard stops.

This is the runtime half of the TLA+ specification in spec/control_plane.tla.
The spec proves invariants hold at design time; this checker verifies they
hold at runtime against real event streams.
"""

from dataclasses import dataclass
from typing import Optional

from app.schema import TraceEvent, EventType


@dataclass
class InvariantViolation:
    invariant_name: str
    detail: str
    event_index: int


def _event_type_str(e: TraceEvent) -> str:
    """Normalize event_type across Pydantic enum/str cases."""
    return e.event_type if isinstance(e.event_type, str) else e.event_type.value


class InvariantChecker:
    """
    Verifies INV-1 through INV-4 from spec/invariants.md against a list
    of TraceEvents.

    Usage:
        checker = InvariantChecker(max_budget_cents=500.0, max_loop_steps=40)
        violations = checker.check(events)
        if violations:
            violation_events = checker.emit_violations(events)
    """

    def __init__(
        self,
        max_budget_cents: float = 500.0,
        max_loop_steps: int = 40,
        allowed_harnesses: Optional[list[str]] = None,
    ):
        self.max_budget = max_budget_cents
        self.max_loop_steps = max_loop_steps
        self.allowed_harnesses = allowed_harnesses

    def check(self, events: list[TraceEvent]) -> list[InvariantViolation]:
        """Run all invariant checks against a trajectory."""
        violations: list[InvariantViolation] = []
        violations.extend(self._check_denied_action(events))
        violations.extend(self._check_budget(events))
        violations.extend(self._check_loop_step(events))
        violations.extend(self._check_harness_set(events))
        return violations

    def _check_denied_action(self, events: list[TraceEvent]) -> list[InvariantViolation]:
        """
        INV-1: After a tool call with action_verdict='denied', no further
        tool_called events may appear in the same run.
        """
        violations: list[InvariantViolation] = []
        for i, e in enumerate(events):
            verdict = getattr(e, "action_verdict", None)
            if verdict != "denied":
                continue

            subsequent_tool_calls = [
                ev for ev in events[i + 1:]
                if _event_type_str(ev) == "tool_called"
            ]
            if subsequent_tool_calls:
                violations.append(InvariantViolation(
                    invariant_name="NoDeniedActionExecutes",
                    detail=(
                        f"Denied action at event index {i} was followed by "
                        f"{len(subsequent_tool_calls)} tool call(s)."
                    ),
                    event_index=i,
                ))
        return violations

    def _check_budget(self, events: list[TraceEvent]) -> list[InvariantViolation]:
        """INV-2: budget_consumed_cents never exceeds the ceiling."""
        violations: list[InvariantViolation] = []
        for i, e in enumerate(events):
            if e.budget_consumed_cents > self.max_budget:
                violations.append(InvariantViolation(
                    invariant_name="BudgetNeverExceeds",
                    detail=(
                        f"Budget {e.budget_consumed_cents:.2f}c exceeds "
                        f"max {self.max_budget:.2f}c at event index {i}."
                    ),
                    event_index=i,
                ))
        return violations

    def _check_loop_step(self, events: list[TraceEvent]) -> list[InvariantViolation]:
        """INV-3: loop_step never exceeds max_loop_steps."""
        violations: list[InvariantViolation] = []
        for i, e in enumerate(events):
            if e.loop_step > self.max_loop_steps:
                violations.append(InvariantViolation(
                    invariant_name="LoopStepBounded",
                    detail=(
                        f"Loop step {e.loop_step} exceeds max "
                        f"{self.max_loop_steps} at event index {i}."
                    ),
                    event_index=i,
                ))
        return violations

    def _check_harness_set(self, events: list[TraceEvent]) -> list[InvariantViolation]:
        """INV-4: every event's harness_id is in the allowed set."""
        if self.allowed_harnesses is None:
            return []
        allowed = set(self.allowed_harnesses)
        violations: list[InvariantViolation] = []
        for i, e in enumerate(events):
            if e.harness_id not in allowed:
                violations.append(InvariantViolation(
                    invariant_name="SelectionInHarnessSet",
                    detail=(
                        f"Harness '{e.harness_id}' at event index {i} is not "
                        f"in the allowed set: {sorted(allowed)}"
                    ),
                    event_index=i,
                ))
        return violations

    def emit_violations(
        self,
        events: list[TraceEvent],
        violations: Optional[list[InvariantViolation]] = None,
    ) -> list[TraceEvent]:
        """Convert violations into TraceEvents for persistence."""
        if not events:
            return []
        violations = violations if violations is not None else self.check(events)
        if not violations:
            return []

        template = events[-1]
        emitted: list[TraceEvent] = []
        for idx, v in enumerate(violations):
            emitted.append(TraceEvent(
                run_id=template.run_id,
                harness_id=template.harness_id,
                event_index=template.event_index + 1 + idx,
                turn_index=template.turn_index,
                loop_step=template.loop_step,
                last_tool_called=template.last_tool_called,
                event_type=EventType.INVARIANT_VIOLATION,
                budget_consumed_cents=template.budget_consumed_cents,
                error=f"{v.invariant_name}: {v.detail}",
                verification_detail=v.detail,
                invariant_violation={
                    "invariant_name": v.invariant_name,
                    "detail": v.detail,
                    "event_index": v.event_index,
                },
            ))
        return emitted