"""
Recursive harness composition.

Delegate a single loop step to a sub-harness, then merge the result back
into the parent trajectory.

Design rationale:
- Delegation is triggered by policy (latency, budget, or explicit step markers).
- The parent trajectory is paused at the delegated step; the sub-harness runs
  with a bounded budget and its own circuit breaker.
- Results are merged using the merge protocol. Conflicts emit a MERGE_CONFLICT
  event and are routed to the verifier for human review.
- This turns the control plane from a selector into a composer.
"""

import uuid
from dataclasses import dataclass, field
from typing import Optional

from app.merge_protocol import (
    MergeOutcome,
    MergeResult,
    fingerprint_artifacts,
    merge,
)
from app.schema import TraceEvent, EventType


@dataclass
class DelegationRequest:
    """A single step to delegate from the parent to a sub-harness."""

    parent_run_id: str
    delegated_step: int
    parent_harness: str
    sub_harness: str
    task_description: str
    parent_artifacts: dict[str, str] = field(default_factory=dict)
    budget_cents: float = 50.0


@dataclass
class DelegationResult:
    subtask_run_id: str
    events: list[TraceEvent]
    merge: Optional[MergeResult]
    success: bool


class Composer:
    """
    Executes delegations and merges results.

    The Composer does not know how to run harnesses. It calls a `runner`
    callable that is injected by the caller. This keeps the Composer pure
    and testable without real harnesses.
    """

    def __init__(self, runner):
        """
        runner: callable(request: DelegationRequest) -> tuple[events, artifacts]
        """
        self.runner = runner

    def delegate(self, request: DelegationRequest) -> DelegationResult:
        subtask_run_id = f"sub-{uuid.uuid4().hex[:8]}"

        # --- Emit delegation event on the parent trajectory ---
        delegation_event = TraceEvent(
            run_id=request.parent_run_id,
            harness_id=request.parent_harness,
            event_index=request.delegated_step,
            turn_index=request.delegated_step,
            loop_step=request.delegated_step,
            last_tool_called=None,
            event_type=EventType.SUBTASK_DELEGATED,
            budget_consumed_cents=0.0,
            parent_run_id=request.parent_run_id,
            delegated_step=request.delegated_step,
            metadata={
                "sub_harness": request.sub_harness,
                "subtask_run_id": subtask_run_id,
                "task": request.task_description,
            },
        )

        # --- Run the sub-harness ---
        try:
            sub_events, sub_artifacts = self.runner(request)
            success = True
        except Exception as e:
            # Sub-harness failed entirely. Return failure without merging.
            return DelegationResult(
                subtask_run_id=subtask_run_id,
                events=[delegation_event],
                merge=None,
                success=False,
            )

        # --- Merge subtask artifacts into parent state ---
        sub_versions = fingerprint_artifacts(sub_artifacts)
        merge_result = merge(request.parent_artifacts, sub_versions)

        # --- Emit merge event ---
        merge_event_type = (
            EventType.MERGE_CONFLICT
            if merge_result.outcome == MergeOutcome.CONFLICTING
            else EventType.SUBTASK_MERGED
        )
        merge_event = TraceEvent(
            run_id=request.parent_run_id,
            harness_id=request.parent_harness,
            event_index=request.delegated_step + 1,
            turn_index=request.delegated_step + 1,
            loop_step=request.delegated_step + 1,
            last_tool_called=None,
            event_type=merge_event_type,
            budget_consumed_cents=0.0,
            parent_run_id=request.parent_run_id,
            delegated_step=request.delegated_step,
            artifact_versions=sub_versions,
            verification_detail=merge_result.detail,
            error=merge_result.detail if merge_result.outcome == MergeOutcome.CONFLICTING else None,
        )

        return DelegationResult(
            subtask_run_id=subtask_run_id,
            events=[delegation_event] + sub_events + [merge_event],
            merge=merge_result,
            success=(merge_result.outcome != MergeOutcome.CONFLICTING),
        )