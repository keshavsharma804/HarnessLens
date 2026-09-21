"""
Tests for the per-harness deception probe.

Verifies each signal contributes to the score independently and that
honest harnesses score near zero.
"""

from app.deception_probe import DeceptionProbe
from app.schema import TraceEvent, EventType


def _event(**kwargs):
    defaults = dict(
        run_id="r1",
        harness_id="h1",
        event_index=0,
        turn_index=0,
        loop_step=0,
        event_type=EventType.TOOL_CALLED,
        budget_consumed_cents=0.0,
    )
    defaults.update(kwargs)
    return TraceEvent(**defaults)


def test_honest_harness_scores_zero():
    events = [
        _event(event_index=0, verification_status="passed",
               verification_detail="checked artifact"),
        _event(event_index=1, event_type=EventType.RUN_COMPLETED),
    ]
    probe = DeceptionProbe()
    result = probe.score_harness("h1", events)
    assert result.score == 0.0
    assert result.signals == []


def test_missing_artifact_raises_score():
    events = [
        _event(event_index=0, expected_artifacts=["/definitely/not/here.txt"]),
    ]
    probe = DeceptionProbe()
    result = probe.score_harness("h1", events)
    assert result.score > 0.0
    assert any("missing" in s.lower() for s in result.signals)


def test_silent_failure_detected():
    events = [
        _event(event_index=0, expected_artifacts=["/not/here.txt"]),
        _event(event_index=1, event_type=EventType.RUN_COMPLETED,
               expected_artifacts=["/not/here.txt"]),
    ]
    probe = DeceptionProbe()
    result = probe.score_harness("h1", events)
    assert result.score > 0.0
    assert any("completion claimed" in s.lower() for s in result.signals)


def test_evidence_free_approval_flagged():
    events = [
        _event(event_index=0, verification_status="passed",
               verification_detail=None),
    ]
    probe = DeceptionProbe()
    result = probe.score_harness("h1", events)
    assert any("rubber-stamp" in s.lower() for s in result.signals)


def test_score_is_bounded_at_one():
    events = [
        _event(event_index=0, expected_artifacts=["/not/here.txt"],
               verification_status="passed", verification_detail=None),
        _event(event_index=1, event_type=EventType.RUN_COMPLETED,
               expected_artifacts=["/not/here.txt"]),
    ]
    probe = DeceptionProbe()
    result = probe.score_harness("h1", events)
    assert result.score <= 1.0