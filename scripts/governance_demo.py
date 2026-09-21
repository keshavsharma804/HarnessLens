import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timezone, timedelta
import tempfile

from app.context_governor import ContextGovernor, fingerprint_payload
from app.schema import TraceEvent, EventType


def _event(**kwargs):
    defaults = dict(
        run_id="demo", harness_id="demo-harness",
        event_index=0, turn_index=0, loop_step=0,
        event_type=EventType.TOOL_CALLED, budget_consumed_cents=0.0,
    )
    defaults.update(kwargs)
    return TraceEvent(**defaults)


def main():
    print("\n=== Scenario 1: Stale context ===\n")
    old_ts = datetime.now(timezone.utc) - timedelta(hours=3)
    events = [_event(source_timestamp=old_ts)]
    findings = ContextGovernor(freshness_ttl_seconds=3600).analyze(events)
    for f in findings:
        print(f"  [{f.severity}] {f.kind}: {f.detail}")

    print("\n=== Scenario 2: Schema drift ===\n")
    events = [
        _event(event_index=0, last_tool_called="get_user",
               schema_fingerprint=fingerprint_payload({"id": 1, "name": "x"})),
        _event(event_index=1, last_tool_called="get_user",
               schema_fingerprint=fingerprint_payload({"id": 1, "name": "x", "email": "y"})),
    ]
    findings = ContextGovernor().analyze(events)
    for f in findings:
        print(f"  [{f.severity}] {f.kind}: {f.detail}")

    print("\n=== Scenario 3: Silent failure ===\n")
    with tempfile.TemporaryDirectory() as tmp:
        events = [
            _event(event_index=0, expected_artifacts=["output.json"]),
            _event(event_index=1, event_type=EventType.RUN_COMPLETED),
        ]
        findings = ContextGovernor(artifact_root=Path(tmp)).analyze(events)
        for f in findings:
            print(f"  [{f.severity}] {f.kind}: {f.detail}")


if __name__ == "__main__":
    main()