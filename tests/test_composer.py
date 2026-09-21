"""Verify delegation and merging end to end."""

from app.composer import Composer, DelegationRequest
from app.merge_protocol import MergeOutcome
from app.schema import TraceEvent, EventType


def _fake_runner_factory(artifacts: dict[str, str], fail: bool = False):
    def runner(request: DelegationRequest):
        if fail:
            raise RuntimeError("sub-harness crashed")
        events = [
            TraceEvent(
                run_id=request.parent_run_id,
                harness_id=request.sub_harness,
                event_index=0,
                turn_index=0,
                loop_step=request.delegated_step,
                event_type=EventType.RUN_COMPLETED,
                budget_consumed_cents=1.0,
                parent_run_id=request.parent_run_id,
            )
        ]
        return events, artifacts
    return runner


def test_delegation_success_additive():
    composer = Composer(_fake_runner_factory({"new.txt": "content"}))
    req = DelegationRequest(
        parent_run_id="parent-1",
        delegated_step=5,
        parent_harness="researchharness",
        sub_harness="easyloops",
        task_description="subtask",
        parent_artifacts={},
    )
    result = composer.delegate(req)
    assert result.success is True
    assert result.merge.outcome == MergeOutcome.ADDITIVE


def test_delegation_conflict_flagged():
    from app.merge_protocol import fingerprint_artifacts
    parent_artifacts = fingerprint_artifacts({"a.txt": "v1"})
    composer = Composer(_fake_runner_factory({"a.txt": "v2"}))
    req = DelegationRequest(
        parent_run_id="parent-1",
        delegated_step=5,
        parent_harness="researchharness",
        sub_harness="easyloops",
        task_description="subtask",
        parent_artifacts=parent_artifacts,
    )
    result = composer.delegate(req)
    assert result.success is False
    assert result.merge.outcome == MergeOutcome.CONFLICTING


def test_delegation_emits_delegation_and_merge_events():
    composer = Composer(_fake_runner_factory({"new.txt": "content"}))
    req = DelegationRequest(
        parent_run_id="parent-1",
        delegated_step=5,
        parent_harness="researchharness",
        sub_harness="easyloops",
        task_description="subtask",
        parent_artifacts={},
    )
    result = composer.delegate(req)
    types = [e.event_type for e in result.events]
    assert "subtask_delegated" in [t if isinstance(t, str) else t.value for t in types]
    assert "subtask_merged" in [t if isinstance(t, str) else t.value for t in types]


def test_delegation_handles_sub_harness_failure():
    composer = Composer(_fake_runner_factory({}, fail=True))
    req = DelegationRequest(
        parent_run_id="parent-1",
        delegated_step=5,
        parent_harness="researchharness",
        sub_harness="easyloops",
        task_description="subtask",
        parent_artifacts={},
    )
    result = composer.delegate(req)
    assert result.success is False
    assert result.merge is None