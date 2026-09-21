import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.continuous_evolver import ContinuousEvolver
from app.repair_library import RepairLibrary
from app.staging_deployer import StagingDeployer
from app.held_out_validator import HeldOutValidator


def _runs(rate: float, n: int = 10):
    successes = int(rate * n)
    return [{"success": i < successes} for i in range(n)]


def main():
    # Simulate a RepairLibrary with recorded healing outcomes.
    library = RepairLibrary("policies/repair_rules.yaml")
    print("\n=== Seeding repair history ===\n")
    for _ in range(5):
        library.record_attempt("timeout_after_analyze", "retry_with_shorter_context", False)
    for _ in range(5):
        library.record_attempt("timeout_after_analyze", "switch_to_cheaper_harness", True)

    print("  retry_with_shorter_context: 0/5 success")
    print("  switch_to_cheaper_harness:  5/5 success")

    print("\n=== Phase 1: Continuous evolver proposes patches ===\n")
    evolver = ContinuousEvolver(library, target_harness="easyloops")
    patches = evolver.propose_patches()
    if not patches:
        print("  No patches proposed.")
        return

    for p in patches:
        print(f"  Patch: {p.patch_id}")
        print(f"    Rationale: {p.rationale}")
        print(f"    Changes: {p.changes}")
        print(f"    Evidence attempts: {p.evidence_attempts}")
        print(f"    Success rate: {p.success_rate:.2f}")

    print("\n=== Phase 2: Held-out validation ===\n")
    validator = HeldOutValidator(min_improvement=0.05)
    deployer = StagingDeployer()

    for p in patches:
        outcome = validator.validate(
            p,
            baseline_runs=_runs(0.40),
            patched_runs=_runs(0.65),
        )
        print(f"  {p.patch_id}")
        print(f"    {outcome.detail}")

        if outcome.accepted:
            staged = deployer.stage(p, outcome.improvement)
            deployer.promote(staged.patch_id)
            print(f"    Staged and promoted: {staged.patch_id}")
        else:
            print(f"    Rejected")

    print("\n=== Phase 3: Observe post-promotion ===\n")
    for p in patches:
        if p.patch_id in deployer.patches:
            result = deployer.observe_post_promotion(p.patch_id, success_rate=0.55)
            if result == "rolled_back":
                print(f"  {p.patch_id}: auto-rolled back")
            else:
                print(f"  {p.patch_id}: healthy")

    print("\n=== Snapshot ===\n")
    for k, v in deployer.snapshot().items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()