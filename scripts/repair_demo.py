import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schema import TraceEvent, EventType
from app.trajectory_diagnostics import generate_digest
from app.cascade_repair import CascadeRepair


def _event(**kwargs):
    defaults = dict(
        run_id="demo", harness_id="easyloops",
        event_index=0, turn_index=0, loop_step=0,
        event_type=EventType.TOOL_CALLED, budget_consumed_cents=0.0,
    )
    defaults.update(kwargs)
    return TraceEvent(**defaults)


def successful_repairer(digest, harness_id):
    return [TraceEvent(
        run_id=digest.run_id,
        harness_id=harness_id,
        event_index=0, turn_index=0,
        loop_step=digest.last_valid_step + 1,
        event_type=EventType.RUN_COMPLETED,
        budget_consumed_cents=3.0,
        last_tool_called="write_file",
    )], True


def main():
    print("\n=== Scenario: Long trajectory fails at step 7 of 10 ===\n")
    events = []
    for step in range(1, 7):
        events.append(_event(
            event_index=step,
            loop_step=step,
            last_tool_called=["read_file", "analyze", "search"][step % 3],
            budget_consumed_cents=step * 1.5,
        ))
    events.append(_event(
        event_index=7,
        loop_step=7,
        event_type=EventType.RUN_FAILED,
        error="step 7 timed out after 30s",
        budget_consumed_cents=10.5,
    ))

    print(f"  Total cost spent on first 6 steps: 10.5c")
    print(f"  Naive retry would cost: ~15c more")

    digest = generate_digest(events)
    print(f"\n  Digest:")
    print(f"    failed at step: {digest.failed_at_step}")
    print(f"    last valid tool: {digest.last_valid_tool}")
    print(f"    last valid step: {digest.last_valid_step}")
    print(f"    reason: {digest.divergence_reason}")
    print(f"    salvageable: {digest.salvageable}")

    repair = CascadeRepair(successful_repairer, strong_harness_id="researchharness")
    result = repair.repair(digest)

    print(f"\n  Repair:")
    print(f"    success: {result.success}")
    print(f"    steps repaired: {result.steps_repaired}")
    print(f"    cost of repair: {result.cost_cents}c")
    print(f"    total cost (partial + repair): {digest.cost_so_far_cents + result.cost_cents}c")
    print(f"\n  Savings vs full retry: {15.0 - result.cost_cents:.1f}c")


if __name__ == "__main__":
    main()