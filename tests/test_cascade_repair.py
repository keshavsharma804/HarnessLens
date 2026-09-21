"""Verify cascade repair runs only from the failure point."""

from app.cascade_repair import CascadeRepair
from app.trajectory_diagnostics import TrajectoryDigest
from app.schema import TraceEvent, EventType


def _digest(salvageable=True, last_step=2, last_tool="analyze"):
    return TrajectoryDigest(
        run_id="r1",
        harness_id="h1",
        total_steps=3,
        failed_at_step=3,
        last_valid_tool=last_tool,
        last_valid_step=last_step,
        divergence_reason="timeout",
        preceding_tools=["read_file", "analyze"],
        cost_so_far_cents=5.0,
        salvageable=salvageable,
    )


def _successful_repairer(digest, harness_id):
    return [TraceEvent(
        run_id=digest.run_id,
        harness_id=harness_id,
        event_index=0,
        turn_index=0,
        loop_step=digest.last_valid_step + 1,
        event_type=EventType.RUN_COMPLETED,
        budget_consumed_cents=2.0,
        last_tool_called="write_file",
    )], True


def _failing_repairer(digest, harness_id):
    return [], False


def test_repair_refuses_unsalvageable():
    repair = CascadeRepair(_successful_repairer)
    result = repair.repair(_digest(salvageable=False))
    assert result.success is False
    assert "not salvageable" in result.reason.lower()


def test_repair_succeeds_and_emits_events():
    repair = CascadeRepair(_successful_repairer)
    result = repair.repair(_digest())
    assert result.success is True
    types = [e.event_type if isinstance(e.event_type, str) else e.event_type.value
             for e in result.repaired_events]
    assert "cascade_repair_started" in types
    assert "cascade_repair_completed" in types


def test_repair_does_not_restart_from_step_zero():
    """Repair should begin at last_valid_step + 1, not at step 0."""
    repair = CascadeRepair(_successful_repairer)
    result = repair.repair(_digest(last_step=2))
    start = next(
        e for e in result.repaired_events
        if (e.event_type if isinstance(e.event_type, str) else e.event_type.value)
        == "cascade_repair_started"
    )
    assert start.loop_step == 3


def test_repair_reports_failure_from_repairer():
    repair = CascadeRepair(_failing_repairer)
    result = repair.repair(_digest())
    assert result.success is False