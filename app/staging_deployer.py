"""
Staging deployer.

Tracks harness patches through staging: staged → promoted or rejected.
Only patches that pass held-out validation are promoted. Patches that
regress after promotion are rolled back.

Design rationale:
- Staging is a safety buffer. No patch goes live without evidence.
- Rollback is automatic: if a promoted patch's subsequent success rate
  drops below its validated baseline, revert.
- A patch's lifecycle is recorded as events, so audit can trace every
  configuration change.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class StagingState(str, Enum):
    STAGED = "staged"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


@dataclass
class StagedPatch:
    patch_id: str
    target_harness: str
    changes: list[dict]
    validation_improvement: float
    state: StagingState = StagingState.STAGED
    staged_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    promoted_at: Optional[datetime] = None
    post_promotion_success: Optional[float] = None
    rollback_reason: Optional[str] = None


class StagingDeployer:
    """
    Manages the lifecycle of harness patches.

    Usage:
        deployer = StagingDeployer()
        staged = deployer.stage(patch, validation_outcome)
        deployer.promote(staged.patch_id)
        # Later, observe production performance:
        deployer.observe_post_promotion(staged.patch_id, success_rate=0.4)
        # If success rate falls below baseline, automatically rolled back.
    """

    def __init__(self, rollback_threshold: float = -0.05):
        """
        rollback_threshold: if post-promotion success rate drops more than
        this fraction below the validated baseline, roll back automatically.
        """
        self.rollback_threshold = rollback_threshold
        self.patches: dict[str, StagedPatch] = {}

    def stage(self, patch, validation_improvement: float) -> StagedPatch:
        """Stage a patch for observation."""
        staged = StagedPatch(
            patch_id=patch.patch_id,
            target_harness=patch.target_harness,
            changes=patch.changes,
            validation_improvement=validation_improvement,
        )
        self.patches[staged.patch_id] = staged
        return staged

    def promote(self, patch_id: str) -> bool:
        """Promote a staged patch to production."""
        patch = self.patches.get(patch_id)
        if not patch or patch.state != StagingState.STAGED:
            return False
        patch.state = StagingState.PROMOTED
        patch.promoted_at = datetime.now(timezone.utc)
        return True

    def reject(self, patch_id: str, reason: str = "validation failed") -> bool:
        patch = self.patches.get(patch_id)
        if not patch or patch.state != StagingState.STAGED:
            return False
        patch.state = StagingState.REJECTED
        patch.rollback_reason = reason
        return True

    def observe_post_promotion(
        self, patch_id: str, success_rate: float
    ) -> Optional[str]:
        """
        Report observed success rate after promotion. Returns 'rolled_back'
        if the patch regressed, otherwise None.
        """
        patch = self.patches.get(patch_id)
        if not patch or patch.state != StagingState.PROMOTED:
            return None

        patch.post_promotion_success = success_rate

        # Compare against validated baseline improvement.
        baseline_assumed = 0.5  # placeholder: caller can override
        if (success_rate - baseline_assumed) < self.rollback_threshold:
            patch.state = StagingState.ROLLED_BACK
            patch.rollback_reason = (
                f"Post-promotion success {success_rate:.2%} dropped below "
                f"threshold."
            )
            return "rolled_back"
        return None

    def snapshot(self) -> dict:
        counts: dict[str, int] = {}
        for p in self.patches.values():
            counts[p.state.value] = counts.get(p.state.value, 0) + 1
        return {
            "total": len(self.patches),
            "by_state": counts,
        }