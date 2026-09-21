"""
Trajectory diagnostics.

When a run fails, produce a structured digest instead of dumping the whole
trace. The digest is the input to cascade repair.

Design rationale:
- Full trace replay is expensive and mostly irrelevant — the failure is
  usually localized to a small window of steps.
- The digest captures: where the failure started, what the last valid tool
  call was, and what the divergence looked like.
- Digest is a dict, not prose, so it can be programmatically consumed.
"""

from dataclasses import dataclass, field
from typing import Optional

from app.schema import TraceEvent, EventType


@dataclass
class TrajectoryDigest:
    """Structured summary of a failed trajectory."""

    run_id: str
    harness_id: str
    total_steps: int
    failed_at_step: int
    last_valid_tool: Optional[str]
    last_valid_step: int
    divergence_reason: str
    preceding_tools: list[str] = field(default_factory=list)
    cost_so_far_cents: float = 0.0
    salvageable: bool = True


def _is_tool_call(event: TraceEvent) -> bool:
    value = event.event_type if isinstance(event.event_type, str) else event.event_type.value
    return value == "tool_called"


def _is_failure(event: TraceEvent) -> bool:
    value = event.event_type if isinstance(event.event_type, str) else event.event_type.value
    return value in ("run_failed", "silent_failure", "merge_conflict", "action_denied")


def generate_digest(events: list[TraceEvent]) -> TrajectoryDigest:
    """
    Produce a digest from a completed (failed) trajectory.

    Precondition: the last event should be a failure. Callers who call this
    on a successful run will get a digest with divergence_reason="no failure".
    """
    if not events:
        return TrajectoryDigest(
            run_id="unknown",
            harness_id="unknown",
            total_steps=0,
            failed_at_step=0,
            last_valid_tool=None,
            last_valid_step=0,
            divergence_reason="empty trajectory",
            salvageable=False,
        )

    run_id = events[0].run_id
    harness_id = events[0].harness_id

    # Find the first failure event.
    failed_at = -1
    divergence = "no failure"
    for i, e in enumerate(events):
        if _is_failure(e):
            failed_at = i
            divergence = e.error or e.verification_detail or "unspecified failure"
            break

    # Find the last valid tool call before the failure.
    last_tool: Optional[str] = None
    last_step = 0
    preceding: list[str] = []
    for e in events[:failed_at if failed_at >= 0 else len(events)]:
        if _is_tool_call(e):
            last_tool = e.last_tool_called
            last_step = e.loop_step
            if e.last_tool_called:
                preceding.append(e.last_tool_called)

    # Cost so far.
    cost = max((e.budget_consumed_cents or 0.0) for e in events)

    # Salvageable if we got at least one valid tool call in before failing.
    salvageable = last_tool is not None and last_step > 0

    return TrajectoryDigest(
        run_id=run_id,
        harness_id=harness_id,
        total_steps=len(events),
        failed_at_step=last_step + 1 if failed_at >= 0 else last_step,
        last_valid_tool=last_tool,
        last_valid_step=last_step,
        divergence_reason=divergence,
        preceding_tools=preceding,
        cost_so_far_cents=cost,
        salvageable=salvageable,
    )


def digest_to_event(digest: TrajectoryDigest, template: TraceEvent) -> TraceEvent:
    """Convert a digest into a TraceEvent for persistence."""
    return TraceEvent(
        run_id=template.run_id,
        harness_id=template.harness_id,
        event_index=template.event_index + 1,
        turn_index=template.turn_index,
        loop_step=template.loop_step,
        last_tool_called=template.last_tool_called,
        event_type=EventType.TRAJECTORY_DIGEST,
        budget_consumed_cents=template.budget_consumed_cents,
        trajectory_digest={
            "failed_at_step": digest.failed_at_step,
            "last_valid_tool": digest.last_valid_tool,
            "last_valid_step": digest.last_valid_step,
            "divergence_reason": digest.divergence_reason,
            "salvageable": digest.salvageable,
        },
        verification_detail=digest.divergence_reason,
    )