import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.harness_evolver import HarnessEvolver
from app.held_out_validator import HeldOutValidator
from app.trajectory_diagnostics import TrajectoryDigest


def _digest(run_id, harness_id, failed_at_step, last_valid_tool):
    return TrajectoryDigest(
        run_id=run_id,
        harness_id=harness_id,
        total_steps=failed_at_step,
        failed_at_step=failed_at_step,
        last_valid_tool=last_valid_tool,
        last_valid_step=failed_at_step - 1,
        divergence_reason="timeout",
        preceding_tools=[],
        cost_so_far_cents=1.0,
        salvageable=True,
    )


def _runs(success_rate: float, n: int = 10):
    successes = int(success_rate * n)
    return [{"success": i < successes} for i in range(n)]


def main():
    print("\n=== Scenario 1: Propose patches from failure history ===\n")
    digests = [
        _digest(f"r{i}", "easyloops", failed_at_step=7, last_valid_tool="analyze")
        for i in range(5)
    ]
    evolver = HarnessEvolver(min_evidence=3)
    patches = evolver.analyze(digests)

    for p in patches:
        print(f"  Patch: {p.patch_id}")
        print(f"    target: {p.target_harness}")
        print(f"    rationale: {p.rationale}")
        print(f"    changes: {p.changes}")
        print(f"    evidence count: {len(p.evidence)}")
        print()

    print("\n=== Scenario 2: Validate patches on held-out runs ===\n")
    validator = HeldOutValidator(min_improvement=0.05)

    for p in patches:
        # Simulate baseline = 40% success, patched = 65% success
        outcome = validator.validate(
            p,
            baseline_runs=_runs(0.40),
            patched_runs=_runs(0.65),
        )
        print(f"  {p.patch_id}")
        print(f"    {outcome.detail}")

    print("\n=== Scenario 3: Rejecting a bad patch ===\n")
    bad_patch = patches[0]
    outcome = validator.validate(
        bad_patch,
        baseline_runs=_runs(0.60),
        patched_runs=_runs(0.55),
    )
    print(f"  {bad_patch.patch_id}")
    print(f"    {outcome.detail}")


if __name__ == "__main__":
    main()