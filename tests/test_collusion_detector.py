"""
Tests for group-level collusion detection.

Verifies each signature fires correctly and honest groups stay clean.
"""

from app.collusion_detector import CollusionDetector
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


def test_clean_group_no_collusion():
    clean = [
        _event(event_index=0, verification_status="passed",
               verification_detail="checked X"),
        _event(event_index=1, event_type=EventType.RUN_COMPLETED),
    ]
    detector = CollusionDetector()
    finding = detector.detect({"harness_a": clean, "harness_b": clean})
    assert finding.suspected is False
    assert finding.signature == "none"


def test_correlated_deception_two_harnesses():
    """Two harnesses with missing artifacts -> correlated_deception."""
    bad = [
        _event(event_index=0, expected_artifacts=["/not/here.txt"]),
        _event(event_index=1, event_type=EventType.RUN_COMPLETED,
               expected_artifacts=["/not/here.txt"]),
    ]
    detector = CollusionDetector()
    finding = detector.detect({"a": bad, "b": bad})
    assert finding.suspected is True
    assert finding.signature == "correlated_deception"
    assert len(finding.involved_harnesses) >= 2


def test_single_critical_harness():
    """One harness with very high deception score."""
    critical = [
        _event(event_index=0, expected_artifacts=["/not/here.txt"],
               verification_status="passed", verification_detail=None),
        _event(event_index=1, event_type=EventType.RUN_COMPLETED,
               expected_artifacts=["/not/here.txt"]),
        _event(event_index=2, expected_artifacts=["/also/not/here.txt"]),
    ]
    clean = [
        _event(event_index=0, verification_status="passed",
               verification_detail="ok"),
    ]
    detector = CollusionDetector()
    finding = detector.detect({"bad": critical, "good": clean})
    assert finding.suspected is True
    assert finding.signature in ("single_harness_critical", "correlated_deception", "approval_cascade")


def test_approval_cascade_detected():
    """Two harnesses both rubber-stamping -> approval_cascade."""
    rubber_stamp = [
        _event(event_index=0, verification_status="passed",
               verification_detail=None),
    ]
    detector = CollusionDetector()
    finding = detector.detect({"a": rubber_stamp, "b": rubber_stamp})
    assert finding.suspected is True
    assert finding.signature in ("approval_cascade", "correlated_deception")


def test_finding_includes_scores_map():
    detector = CollusionDetector()
    finding = detector.detect({
        "h1": [_event(verification_status="passed", verification_detail="ok")],
        "h2": [_event(verification_status="passed", verification_detail="ok")],
    })
    assert "h1" in finding.scores
    assert "h2" in finding.scores


def test_empty_group_is_not_collusion():
    detector = CollusionDetector()
    finding = detector.detect({})
    assert finding.suspected is False


def test_high_score_harness_not_flagged_alone_under_elevated():
    """A single harness just above elevated but below critical -> clean."""
    moderate = [
        _event(event_index=0, expected_artifacts=["/not/here.txt"]),
    ]
    clean = [
        _event(event_index=0, verification_status="passed",
               verification_detail="ok"),
    ]
    detector = CollusionDetector(elevated_threshold=0.5, critical_threshold=0.9)
    finding = detector.detect({"moderate": moderate, "clean": clean})
    assert finding.suspected is False