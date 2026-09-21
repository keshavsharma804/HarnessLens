"""
Automatic harness evolution from failure trajectories.

Reads a batch of TrajectoryDigest objects, identifies recurring failure
patterns, and proposes harness configuration patches.

This is a simplified, deterministic version of Harness-R1. The full paper
uses RL to train a 9B harness engineer. We use pattern detection over
digests. The architecture is the same: read failures, propose patch,
validate on held-out runs, deploy if improvement.

Reference: Harness-R1 (2026) — "post-trains a dedicated harness engineer
that reads failed trajectories and writes reusable runtime patches."
"""

import uuid
from collections import Counter
from dataclasses import dataclass, field

from app.trajectory_diagnostics import TrajectoryDigest


@dataclass
class HarnessPatch:
    patch_id: str
    target_harness: str
    rationale: str
    changes: list[dict] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    expected_improvement: str = ""


class HarnessEvolver:
    """
    Proposes harness patches from failure patterns.

    Two patterns are detected:
    1. Step clustering: failures cluster around the same step index.
    2. Tool clustering: failures follow the same last-valid tool.
    """

    def __init__(self, min_evidence: int = 3):
        self.min_evidence = min_evidence

    def analyze(self, digests: list[TrajectoryDigest]) -> list[HarnessPatch]:
        """Find recurring patterns and propose patches."""
        by_harness: dict[str, list[TrajectoryDigest]] = {}
        for d in digests:
            by_harness.setdefault(d.harness_id, []).append(d)

        patches: list[HarnessPatch] = []
        for harness_id, group in by_harness.items():
            patches.extend(self._step_clustering(harness_id, group))
            patches.extend(self._tool_clustering(harness_id, group))
        return patches

    def _step_clustering(
        self, harness_id: str, group: list[TrajectoryDigest]
    ) -> list[HarnessPatch]:
        counts = Counter(d.failed_at_step for d in group)
        if not counts:
            return []
        step, count = counts.most_common(1)[0]
        if count < self.min_evidence:
            return []
        evidence = [d.run_id for d in group if d.failed_at_step == step]
        return [HarnessPatch(
            patch_id=f"hp-{harness_id}-step-{step}-{uuid.uuid4().hex[:6]}",
            target_harness=harness_id,
            rationale=(
                f"{count} failures cluster at step {step}. "
                f"Likely a harness policy issue at that point."
            ),
            changes=[{
                "field": "retry_policy",
                "from": "no_retry",
                "to": f"retry_at_step_{step}",
            }],
            evidence=evidence,
            expected_improvement=f"Reduce failures at step {step}.",
        )]

    def _tool_clustering(
        self, harness_id: str, group: list[TrajectoryDigest]
    ) -> list[HarnessPatch]:
        counts = Counter(
            d.last_valid_tool for d in group if d.last_valid_tool
        )
        if not counts:
            return []
        tool, count = counts.most_common(1)[0]
        if count < self.min_evidence:
            return []
        evidence = [d.run_id for d in group if d.last_valid_tool == tool]
        return [HarnessPatch(
            patch_id=f"hp-{harness_id}-tool-{tool}-{uuid.uuid4().hex[:6]}",
            target_harness=harness_id,
            rationale=(
                f"{count} failures follow tool '{tool}'. "
                f"Likely a missing verification checkpoint after that tool."
            ),
            changes=[{
                "field": "verification_policy",
                "from": "post_run",
                "to": f"after_{tool}",
            }],
            evidence=evidence,
            expected_improvement=f"Add verification after '{tool}'.",
        )]