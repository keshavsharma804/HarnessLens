"""
Test 4: Does routing improve outcomes?

Compares two strategies on the same real tasks:
- Baseline: always use gpt-5 (most capable, most expensive)
- Routed:   use the fleet-learning router to pick the cheapest
            viable config from historical success rates

Proves: routing matches baseline outcomes at lower cost.

Usage:
    python -m scripts.run_routing_test
"""

import sys
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.openhands_adapter import OpenHandsAdapter


FIXTURE = Path("local_tests/fixture_01").resolve()
N_TASKS = 5

# Candidates with real observed success rates from Test 1
# (all three produced correct fixes on this fixture)
CANDIDATES = [
    {"model": "gpt-5",       "cost_per_task_cents": 3.85, "success_rate": 1.0},
    {"model": "gpt-5-mini",  "cost_per_task_cents": 0.60, "success_rate": 1.0},
    {"model": "gpt-5-nano",  "cost_per_task_cents": 0.16, "success_rate": 1.0},
]


def prepare_workspace() -> Path:
    workspace = Path(tempfile.mkdtemp(prefix="routing_"))
    for name in ("buggy.py", "test_buggy.py", "INSTRUCTIONS.md"):
        shutil.copy(FIXTURE / name, workspace / name)
    subprocess.run(["git", "init"], cwd=workspace, capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=workspace, capture_output=True, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t.com", "-c", "user.name=t",
         "commit", "-m", "initial"],
        cwd=workspace, capture_output=True, check=True,
    )
    return workspace


def run_one(model: str, tag: str) -> dict:
    workspace = prepare_workspace()
    adapter = OpenHandsAdapter(
        model=model,
        harness_id=f"{model}-{tag}",
        workspace_dir=str(workspace),
    )
    task_text = (FIXTURE / "INSTRUCTIONS.md").read_text()

    start = time.time()
    try:
        events, patch = adapter.run(task_text, tag)
        error = None
    except Exception as e:
        events, patch = [], ""
        error = f"{type(e).__name__}: {e}"
    duration = time.time() - start

    if error is None:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "test_buggy.py", "-q"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=60,
        )
        passed = result.returncode == 0
    else:
        passed = False

    cost_cents = max((e.budget_consumed_cents or 0.0) for e in events) if events else 0.0

    return {
        "model": model,
        "passed": passed,
        "cost_cents": cost_cents,
        "duration": duration,
        "error": error,
    }


def pick_routed_model() -> str:
    """
    The router's decision: pick the cheapest candidate with success_rate >= 0.9.
    This is the same logic as Phase 4's fleet learning, applied to real data.
    """
    viable = [c for c in CANDIDATES if c["success_rate"] >= 0.9]
    if not viable:
        return CANDIDATES[0]["model"]  # fallback: most capable
    return min(viable, key=lambda c: c["cost_per_task_cents"])["model"]


def main():
    print(f"\n=== Test 4: Routing vs Baseline ===")
    print(f"    Tasks: {N_TASKS}")
    print(f"    Candidates: {[c['model'] for c in CANDIDATES]}\n")

    routed_model = pick_routed_model()
    print(f"  Router decision (cheapest viable): {routed_model}")
    print(f"  Baseline (always most capable):    gpt-5\n")

    # --- Baseline ---
    print("--- Strategy A: Baseline (gpt-5) ---\n")
    baseline_results = []
    for i in range(N_TASKS):
        r = run_one("gpt-5", f"baseline-{i}")
        baseline_results.append(r)
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  Task {i+1}: {r['duration']:.1f}s  {status}  ${r['cost_cents']/100:.4f}")

    # --- Routed ---
    print(f"\n--- Strategy B: Routed ({routed_model}) ---\n")
    routed_results = []
    for i in range(N_TASKS):
        r = run_one(routed_model, f"routed-{i}")
        routed_results.append(r)
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  Task {i+1}: {r['duration']:.1f}s  {status}  ${r['cost_cents']/100:.4f}")

    # --- Summary ---
    b_passes = sum(1 for r in baseline_results if r["passed"])
    r_passes = sum(1 for r in routed_results if r["passed"])
    b_cost = sum(r["cost_cents"] for r in baseline_results)
    r_cost = sum(r["cost_cents"] for r in routed_results)
    b_avg_time = sum(r["duration"] for r in baseline_results) / len(baseline_results)
    r_avg_time = sum(r["duration"] for r in routed_results) / len(routed_results)

    print("\n" + "=" * 60)
    print("ROUTING COMPARISON")
    print("=" * 60)
    print(f"{'Strategy':<20} {'Pass':<10} {'Total Cost':<15} {'Avg Time':<10}")
    print("-" * 60)
    print(f"{'Baseline (gpt-5)':<20} {b_passes}/{N_TASKS:<8} "
          f"${b_cost/100:<14.4f} {b_avg_time:.1f}s")
    print(f"{'Routed (' + routed_model + ')':<20} {r_passes}/{N_TASKS:<8} "
          f"${r_cost/100:<14.4f} {r_avg_time:.1f}s")

    if b_passes == r_passes and b_passes > 0:
        savings = (1 - r_cost / b_cost) * 100
        print(f"\n✅ Same pass rate ({b_passes}/{N_TASKS}) at "
              f"{savings:.1f}% lower cost.")
        print(f"   Baseline cost per success: ${b_cost/100/max(b_passes,1):.4f}")
        print(f"   Routed cost per success:   ${r_cost/100/max(r_passes,1):.4f}")
    elif r_passes < b_passes:
        print(f"\n⚠️  Routed lost {b_passes - r_passes} task(s). "
              f"Router picked a model that could not handle the workload.")
    else:
        print(f"\n⚠️  Both strategies failed the same tasks.")


if __name__ == "__main__":
    main()