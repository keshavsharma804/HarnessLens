"""Verify the independent verifier catches what the harness hides."""

from app.verifier import Verifier, Verdict
from app.schema import TraceEvent, EventType


def _event(**kwargs):
    defaults = dict(
        run_id="r1", harness_id="h1", event_index=0, turn_index=0, loop_step=0,
        event_type=EventType.RUN_COMPLETED, budget_consumed_cents=0.0,
    )
    defaults.update(kwargs)
    return TraceEvent(**defaults)


def test_verifier_passes_clean_run():
    events = [_event(event_type=EventType.RUN_COMPLETED)]
    result = Verifier().verify(events)
    assert result.verdict == Verdict.PASS


def test_verifier_fails_on_error():
    events = [_event(event_type=EventType.RUN_FAILED, error="something broke")]
    result = Verifier().verify(events)
    assert result.verdict == Verdict.FAIL
    assert "error" in result.detail.lower()


def test_verifier_fails_on_empty_events():
    result = Verifier().verify([])
    assert result.verdict == Verdict.FAIL