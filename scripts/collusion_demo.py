import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.collusion_detector import CollusionDetector
from app.schema import TraceEvent, EventType


def _event(**kwargs):
    defaults = dict(
        run_id="demo", harness_id="h",
        event_index=0, turn_index=0, loop_step=0,
        event_type=EventType.TOOL_CALLED, budget_consumed_cents=0.0,
    )
    defaults.update(kwargs)
    return TraceEvent(**defaults)


def main():
    detector = CollusionDetector()

    print("\n=== Scenario 1: Honest group ===\n")
    honest = [
        _event(event_index=0, verification_status="passed",
               verification_detail="verified artifact X"),
        _event(event_index=1, event_type=EventType.RUN_COMPLETED),
    ]
    finding = detector.detect({"harness_a": honest, "harness_b": honest})
    print(f"  suspected: {finding.suspected}")
    print(f"  signature: {finding.signature}")
    print(f"  scores: {finding.scores}")

    print("\n=== Scenario 2: Two harnesses with missing artifacts ===\n")
    bad = [
        _event(event_index=0, expected_artifacts=["/not/here.txt"]),
        _event(event_index=1, event_type=EventType.RUN_COMPLETED,
               expected_artifacts=["/not/here.txt"]),
    ]
    finding = detector.detect({"cheater_1": bad, "cheater_2": bad})
    print(f"  suspected: {finding.suspected}")
    print(f"  signature: {finding.signature}")
    print(f"  involved: {finding.involved_harnesses}")
    print(f"  scores: {finding.scores}")
    print(f"  detail: {finding.detail}")

    print("\n=== Scenario 3: Approval cascade ===\n")
    rubber_stamp = [
        _event(event_index=0, verification_status="passed",
               verification_detail=None),
    ]
    finding = detector.detect({"approver_1": rubber_stamp,
                               "approver_2": rubber_stamp})
    print(f"  suspected: {finding.suspected}")
    print(f"  signature: {finding.signature}")
    print(f"  involved: {finding.involved_harnesses}")


if __name__ == "__main__":
    main()