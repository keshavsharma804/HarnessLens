"""Verify the trajectory digest captures failure structure."""

from app.schema import TraceEvent, EventType
from app.trajectory_diagnostics import generate_digest, digest_to_event


def _event(**kwargs):
    defaults = dict(
        run_id="r1", harness_id="h1", event_index=0, turn_index=0, loop_step=0,
        event_type=EventType.TOOL_CALLED, budget_consumed_cents=0.0,
    )
    defaults.update(kwargs)
    return TraceEvent(**defaults)


def test_digest_of_empty_trajectory():
    d = generate_digest([])
    assert d.salvageable is False
    assert d.divergence_reason == "empty trajectory"


def test_digest_of_failed_run_finds_last_valid_tool():
    events = [
        _event(event_index=0, loop_step=1, last_tool_called="read_file"),
        _event(event_index=1, loop_step=2, last_tool_called="analyze"),
        _event(event_index=2, loop_step=3, event_type=EventType.RUN_FAILED,
               error="timeout"),
    ]
    d = generate_digest(events)
    assert d.salvageable is True
    assert d.last_valid_tool == "analyze"
    assert d.last_valid_step == 2
    assert "timeout" in d.divergence_reason


def test_digest_handles_failure_at_first_step():
    events = [
        _event(event_index=0, event_type=EventType.RUN_FAILED, error="immediate"),
    ]
    d = generate_digest(events)
    assert d.salvageable is False


def test_digest_serializes_to_event():
    events = [
        _event(event_index=0, loop_step=1, last_tool_called="read_file"),
        _event(event_index=1, event_type=EventType.RUN_FAILED, error="boom"),
    ]
    d = generate_digest(events)
    evt = digest_to_event(d, events[-1])
    assert evt.event_type in (EventType.TRAJECTORY_DIGEST, "trajectory_digest")
    assert evt.trajectory_digest["last_valid_tool"] == "read_file"