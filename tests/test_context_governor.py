"""Verify data-layer governance detects stale, drift, and silent failures."""

from datetime import datetime, timezone, timedelta
from pathlib import Path

from app.context_governor import (
    ContextGovernor,
    fingerprint_payload,
    emit_findings_as_events,
)
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


def test_stale_context_detected():
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    events = [_event(source_timestamp=old)]
    findings = ContextGovernor(freshness_ttl_seconds=3600).check_freshness(events)
    assert len(findings) == 1
    assert findings[0].kind == "stale"


def test_fresh_context_not_flagged():
    fresh = datetime.now(timezone.utc) - timedelta(minutes=5)
    events = [_event(source_timestamp=fresh)]
    findings = ContextGovernor(freshness_ttl_seconds=3600).check_freshness(events)
    assert findings == []


def test_schema_drift_detected():
    events = [
        _event(event_index=0, last_tool_called="read_file", schema_fingerprint="aaa"),
        _event(event_index=1, last_tool_called="read_file", schema_fingerprint="bbb"),
    ]
    findings = ContextGovernor().check_drift(events)
    assert len(findings) == 1
    assert findings[0].kind == "drift"


def test_schema_stable_not_flagged():
    events = [
        _event(event_index=0, last_tool_called="read_file", schema_fingerprint="aaa"),
        _event(event_index=1, last_tool_called="read_file", schema_fingerprint="aaa"),
    ]
    findings = ContextGovernor().check_drift(events)
    assert findings == []


def test_silent_failure_detected():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        missing = "does_not_exist.txt"
        events = [
            _event(event_index=0, expected_artifacts=[missing]),
            _event(event_index=1, event_type=EventType.RUN_COMPLETED),
        ]
        findings = ContextGovernor(artifact_root=Path(tmp)).check_silent_failure(events)
        assert len(findings) == 1
        assert findings[0].kind == "silent_failure"
        assert findings[0].severity == "error"


def test_artifact_exists_no_failure():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        real_file = Path(tmp) / "output.txt"
        real_file.write_text("content")
        events = [
            _event(event_index=0, expected_artifacts=["output.txt"]),
            _event(event_index=1, event_type=EventType.RUN_COMPLETED),
        ]
        findings = ContextGovernor(artifact_root=Path(tmp)).check_silent_failure(events)
        assert findings == []

        
def test_fingerprint_is_stable_and_ignores_values():
    f1 = fingerprint_payload({"a": 1, "b": 2})
    f2 = fingerprint_payload({"a": 999, "b": "different"})
    assert f1 == f2  # Same keys -> same fingerprint


def test_findings_converted_to_events():
    events = [_event(source_timestamp=datetime.now(timezone.utc) - timedelta(hours=2))]
    findings = ContextGovernor(freshness_ttl_seconds=60).check_freshness(events)
    emitted = emit_findings_as_events(findings, events[0])
    assert len(emitted) == 1
    assert emitted[0].event_type == EventType.CONTEXT_STALE