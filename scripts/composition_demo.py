import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.composer import Composer, DelegationRequest
from app.merge_protocol import fingerprint_artifacts
from app.schema import TraceEvent, EventType


def fake_sub_harness(request: DelegationRequest):
    """Simulate a sub-harness that produces one new artifact."""
    events = [TraceEvent(
        run_id=request.parent_run_id,
        harness_id=request.sub_harness,
        event_index=0, turn_index=0, loop_step=request.delegated_step,
        event_type=EventType.RUN_COMPLETED,
        budget_consumed_cents=2.0,
        parent_run_id=request.parent_run_id,
    )]
    return events, {"analysis.json": "some analysis result"}


def main():
    print("\n=== Scenario 1: Clean delegation ===\n")
    parent_artifacts = fingerprint_artifacts({"input.txt": "original"})
    composer = Composer(fake_sub_harness)

    req = DelegationRequest(
        parent_run_id="parent-abc",
        delegated_step=5,
        parent_harness="researchharness",
        sub_harness="easyloops",
        task_description="analyze input",
        parent_artifacts=parent_artifacts,
    )
    result = composer.delegate(req)
    print(f"  Subtask run: {result.subtask_run_id}")
    print(f"  Success: {result.success}")
    print(f"  Merge outcome: {result.merge.outcome.value}")
    print(f"  Added: {result.merge.added}")

    print("\n=== Scenario 2: Conflicting delegation ===\n")

    def conflicting_runner(request):
        return [], {"input.txt": "modified by subtask"}

    composer2 = Composer(conflicting_runner)
    req2 = DelegationRequest(
        parent_run_id="parent-xyz",
        delegated_step=5,
        parent_harness="researchharness",
        sub_harness="easyloops",
        task_description="modify input",
        parent_artifacts=parent_artifacts,
    )
    result2 = composer2.delegate(req2)
    print(f"  Success: {result2.success}")
    print(f"  Merge outcome: {result2.merge.outcome.value}")
    print(f"  Conflicts: {result2.merge.conflicts}")
    print(f"  Detail: {result2.merge.detail}")


if __name__ == "__main__":
    main()