"""
Held-out validation for harness patches.

A patch is only accepted if it improves on held-out runs. This prevents
overfitting to the failures that motivated the patch.

This is the structural answer to the Validator's Paradox: the patch's
own claim of improvement is not trusted. The held-out runs decide.

Reference: HarnessCompass (2026) — "Iterative refinement with held-out
validation is what pushes Pass@1 from 54% to 66%."
"""

from dataclasses import dataclass

from app.harness_evolver import HarnessPatch


@dataclass
class ValidationOutcome:
    patch_id: str
    accepted: bool
    baseline_success_rate: float
    patched_success_rate: float
    improvement: float
    detail: str


class HeldOutValidator:
    def __init__(
        self,
        min_improvement: float = 0.05,
        min_runs: int = 3,
    ):
        self.min_improvement = min_improvement
        self.min_runs = min_runs

    def validate(
        self,
        patch: HarnessPatch,
        baseline_runs: list[dict],
        patched_runs: list[dict],
    ) -> ValidationOutcome:
        """
        baseline_runs and patched_runs are lists of dicts each with a
        "success" boolean key.

        The patch is accepted only if:
        - Both run sets have at least min_runs entries.
        - patched success rate exceeds baseline by at least min_improvement.
        """
        if len(baseline_runs) < self.min_runs or len(patched_runs) < self.min_runs:
            return ValidationOutcome(
                patch_id=patch.patch_id,
                accepted=False,
                baseline_success_rate=0.0,
                patched_success_rate=0.0,
                improvement=0.0,
                detail=(
                    f"Insufficient held-out data: "
                    f"baseline={len(baseline_runs)}, patched={len(patched_runs)} "
                    f"(need >= {self.min_runs} each)."
                ),
            )

        baseline_rate = sum(1 for r in baseline_runs if r["success"]) / len(baseline_runs)
        patched_rate = sum(1 for r in patched_runs if r["success"]) / len(patched_runs)
        improvement = patched_rate - baseline_rate

        accepted = improvement >= self.min_improvement

        return ValidationOutcome(
            patch_id=patch.patch_id,
            accepted=accepted,
            baseline_success_rate=baseline_rate,
            patched_success_rate=patched_rate,
            improvement=improvement,
            detail=(
                f"Baseline {baseline_rate:.2%} -> Patched {patched_rate:.2%} "
                f"(improvement {improvement:+.2%}). "
                f"{'ACCEPTED' if accepted else 'REJECTED'}."
            ),
        )