"""
Cascade repair.

Given a digest of a failed run, repair ONLY the failed step using a
stronger harness. Do not re-run the whole trajectory.

Design rationale:
- Full retries waste budget on steps that already succeeded.
- Local repair assumes the failure is localized (which digests usually
  confirm — the last valid tool is the branch point).
- The repaired step produces new events that are appended to the parent
  trajectory, not a fresh run.
"""

from dataclasses import dataclass
from typing import Callable, Optional

from app.schema import TraceEvent, EventType
from app.trajectory_diagnostics import TrajectoryDigest


@dataclass
class RepairResult:
    success: bool
    repaired_events: list[TraceEvent]
    steps_repaired: int
    cost_cents: float
    reason: str


class CascadeRepair:
    """
    Executes a cascade repair against a digest.

    The repairer is injected so tests do not need a real harness.

    repairer: callable(digest, strong_harness_id) -> tuple[events, success]
    """

    def __init__(
        self,
        repairer: Callable,
        strong_harness_id: str = "researchharness",
    ):
        self.repairer = repairer
        self.strong_harness_id = strong_harness_id

    def repair(self, digest: TrajectoryDigest) -> RepairResult:
        # --- Refuse to repair if the trajectory is unsalvageable ---
        if not digest.salvageable:
            return RepairResult(
                success=False,
                repaired_events=[],
                steps_repaired=0,
                cost_cents=0.0,
                reason="Trajectory not salvageable: no valid step to resume from.",
            )

        # --- Emit start event ---
        start_event = TraceEvent(
            run_id=digest.run_id,
            harness_id=self.strong_harness_id,
            event_index=digest.total_steps,
            turn_index=digest.last_valid_step,
            loop_step=digest.last_valid_step + 1,
            last_tool_called=digest.last_valid_tool,
            event_type=EventType.CASCADE_REPAIR_STARTED,
            budget_consumed_cents=digest.cost_so_far_cents,
            verification_detail=(
                f"Repairing from step {digest.last_valid_step + 1} "
                f"because: {digest.divergence_reason}"
            ),
        )

        # --- Invoke the injected repairer ---
        try:
            repaired_events, success = self.repairer(digest, self.strong_harness_id)
        except Exception as e:
            return RepairResult(
                success=False,
                repaired_events=[start_event],
                steps_repaired=0,
                cost_cents=0.0,
                reason=f"Repairer raised: {e}",
            )

        # --- Emit completion event ---
        completion_event = TraceEvent(
            run_id=digest.run_id,
            harness_id=self.strong_harness_id,
            event_index=digest.total_steps + 1,
            turn_index=digest.last_valid_step + 1,
            loop_step=digest.last_valid_step + 1,
            last_tool_called=digest.last_valid_tool,
            event_type=EventType.CASCADE_REPAIR_COMPLETED,
            budget_consumed_cents=digest.cost_so_far_cents,
            verification_detail=(
                "Repair succeeded." if success else "Repair failed."
            ),
        )

        cost = sum(e.budget_consumed_cents or 0.0 for e in repaired_events)

        return RepairResult(
            success=success,
            repaired_events=[start_event] + repaired_events + [completion_event],
            steps_repaired=len(repaired_events),
            cost_cents=cost,
            reason="Repaired locally." if success else "Local repair failed.",
        )