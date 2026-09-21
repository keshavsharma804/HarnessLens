"""
Continuous harness evolution.

Turns repair success rates into harness patches. Unlike Phase 15 (which
reads digests for failure patterns), Phase 17 reads the RepairLibrary's
recorded outcomes to propose configuration changes grounded in evidence
of what actually fixed what.

Design rationale:
- A repair action with 100% success rate is a strong signal that the
  harness should be configured that way by default.
- A repair action with 0% success rate is a signal that the harness
  has a systematic weakness, but the current repair strategy does not
  address it.
- Bounded: only patches with sufficient evidence (min_attempts) are proposed.
- Aligned with HSI (Aug 2026): the evolver proposes; held-out validation decides.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from app.failure_classifier import FailureSignature
from app.repair_library import RepairLibrary


# Mapping from repair action type to the harness config field it suggests changing.
ACTION_TO_CONFIG_FIELD = {
    "retry_with_backoff": "retry_policy",
    "switch_harness": "fallback_harness",
    "inject_context": "context_strategy",
    "rerun_with_verifier": "verification_policy",
    "escalate": None,  # escalations cannot be "baked in"
}


@dataclass
class EvolvedPatch:
    patch_id: str
    target_harness: str
    rationale: str
    changes: list[dict] = field(default_factory=list)
    evidence_signatures: list[str] = field(default_factory=list)
    evidence_attempts: int = 0
    success_rate: float = 0.0


class ContinuousEvolver:
    """
    Proposes harness patches from repair success statistics.

    For each signature in the RepairLibrary, examines the best-performing
    action. If its success rate exceeds a threshold and it has enough
    attempts, proposes a patch that bakes the winning strategy into the
    harness configuration.
    """

    MIN_ATTEMPTS = 3
    MIN_SUCCESS_RATE = 0.6

    def __init__(self, library: RepairLibrary, target_harness: str = "easyloops"):
        self.library = library
        self.target_harness = target_harness

    def propose_patches(self) -> list[EvolvedPatch]:
        """Examine all signatures with recorded attempts and propose patches."""
        # Group records by signature.
        by_sig: dict[str, list] = defaultdict(list)
        for r in self.library._records:
            by_sig[r.signature_id].append(r)

        patches: list[EvolvedPatch] = []
        for sig_id, records in by_sig.items():
            if len(records) < self.MIN_ATTEMPTS:
                continue

            # Find the best action for this signature.
            best = self.library.best_action(sig_id)
            if not best:
                continue

            rate = self.library.success_rate(sig_id, best.action_id)
            if rate < self.MIN_SUCCESS_RATE:
                continue

            # Skip escalations — cannot be baked into config.
            config_field = ACTION_TO_CONFIG_FIELD.get(best.action_type)
            if not config_field:
                continue

            patch = EvolvedPatch(
                patch_id=f"ep-{self.target_harness}-{sig_id}-{uuid.uuid4().hex[:6]}",
                target_harness=self.target_harness,
                rationale=(
                    f"Repair '{best.action_id}' succeeded {rate:.0%} of "
                    f"{len(records)} attempts on signature '{sig_id}'. "
                    f"Baking this strategy into harness configuration."
                ),
                changes=[{
                    "field": config_field,
                    "from": "default",
                    "to": best.action_type,
                }],
                evidence_signatures=[sig_id],
                evidence_attempts=len(records),
                success_rate=rate,
            )
            patches.append(patch)

        return patches