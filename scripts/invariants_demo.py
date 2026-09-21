import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.invariant_checker import InvariantChecker
from app.schema import TraceEvent, EventType


def _event(**kwargs):
    defaults = dict(
        run_id="demo", harness_id="researchharness",
        event_index=0, turn_index=0, loop_step=0,
        event_type=EventType.TOOL_CALLED, budget_consumed_cents=0.0,
    )
    defaults.update(kwargs)
    return TraceEvent(**defaults)


def main():
    print("\n=== Scenario 1: Clean run ===\n")
    clean = [
        _event(event_index=0, action_verdict="allowed"),
        _event(event_index=1, loop_step=1, budget_consumed_cents=10.0),
        _event(event_index=2, loop_step=2, budget_consumed_cents=20.0,
               event_type=EventType.RUN_COMPLETED),
    ]
    checker = InvariantChecker(
        max_budget_cents=500.0,
        max_loop_steps=40,
        allowed_harnesses=["researchharness", "easyloops"],
    )
    violations = checker.check(clean)
    print(f"  Violations: {len(violations)}")

    print("\n=== Scenario 2: Multiple invariant violations ===\n")
    dirty = [
        _event(event_index=0, action_verdict="denied"),
        _event(event_index=1, loop_step=1),  # tool call after deny: INV-1
        _event(event_index=2, loop_step=100,
               budget_consumed_cents=999.0),  # INV-2, INV-3
        _event(event_index=3, harness_id="rogue"),  # INV-4
    ]
    violations = checker.check(dirty)
    for v in violations:
        print(f"  [{v.invariant_name}] event={v.event_index}: {v.detail}")

    print(f"\n  Total violations: {len(violations)}")

    print("\n=== Scenario 3: Violation events ===\n")
    emitted = checker.emit_violations(dirty, violations)
    for e in emitted:
        print(f"  {e.event_type}: {e.error}")


if __name__ == "__main__":
    main()