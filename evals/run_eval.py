"""
Statistical eval harness.

Runs N fixtures across M strategies, records rollouts, computes
Wilson confidence intervals, and reports a comparison table.

Usage:
    python -m evals.run_eval --strategies baseline routed --tasks 10
"""

import sys
import shutil
import subprocess
import tempfile
import time
import json
import math
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.openhands_adapter import OpenHandsAdapter


FIXTURES = Path("evals/fixtures").resolve()
ROLLOUTS = Path("evals/rollouts").resolve()
ROLLOUTS.mkdir(parents=True, exist_ok=True)


# Strategy definitions
STRATEGIES = {
    "baseline": {"model": "gpt-5", "cost_cents": 3.85},
    "routed":   {"model": "gpt-5-nano", "cost_cents": 0.16},
    "mid":      {"model": "gpt-5-mini", "cost_cents": 0.60},
}


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Compute the Wilson score interval for a binomial proportion."""
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denom = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    lo = max(0.0, (centre - margin) / denom)
    hi = min(1.0, (centre + margin) / denom)
    return lo, hi


def prepare_fixture(fixture_dir: Path) -> Path:
    """Copy a fixture into a fresh workspace."""
    workspace = Path(tempfile.mkdtemp(prefix=f"eval_{fixture_dir.name}_"))
    for f in fixture_dir.iterdir():
        if f.is_file():
            shutil.copy(f, workspace / f.name)
    subprocess.run(["git", "init"], cwd=workspace, capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=workspace, capture_output=True, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t.com", "-c", "user.name=t",
         "commit", "-m", "initial"],
        cwd=workspace, capture_output=True, check=True,
    )
    return workspace


def run_task(fixture_dir: Path, strategy_name: str, run_id: int) -> dict:
    """Run one task under one strategy. Returns rollout dict."""
    strategy = STRATEGIES[strategy_name]
    workspace = prepare_fixture(fixture_dir)

    adapter = OpenHandsAdapter(
        model=strategy["model"],
        harness_id=f"{strategy_name}-{run_id}",
        workspace_dir=str(workspace),
    )

    instructions = (fixture_dir / "INSTRUCTIONS.md").read_text()
    test_file = next(fixture_dir.glob("test_*.py")).name

    start = time.time()
    try:
        events, patch = adapter.run(instructions, f"{fixture_dir.name}-{run_id}")
        error = None
    except Exception as e:
        events, patch = [], ""
        error = f"{type(e).__name__}: {e}"
    duration = time.time() - start

    # Grade
    passed = False
    if error is None:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", test_file, "-q"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=60,
        )
        passed = result.returncode == 0

    cost_cents = max((e.budget_consumed_cents or 0.0) for e in events) if events else 0.0
    input_tokens = sum(e.input_tokens or 0 for e in events)
    output_tokens = sum(e.output_tokens or 0 for e in events)

    rollout = {
        "fixture": fixture_dir.name,
        "strategy": strategy_name,
        "model": strategy["model"],
        "run_id": run_id,
        "passed": passed,
        "cost_cents": cost_cents,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "duration_seconds": duration,
        "patch_length": len(patch),
        "error": error,
    }

    # Save rollout JSON
    out_file = ROLLOUTS / f"{strategy_name}_{fixture_dir.name}_{run_id}.json"
    out_file.write_text(json.dumps(rollout, indent=2))
    return rollout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategies", nargs="+", default=["baseline", "routed"])
    parser.add_argument("--tasks", type=int, default=10)
    args = parser.parse_args()

    fixtures = sorted([f for f in FIXTURES.iterdir() if f.is_dir()])[:args.tasks]
    print(f"\n=== Eval: {len(fixtures)} fixtures, {len(args.strategies)} strategies ===")
    print(f"    Total runs: {len(fixtures) * len(args.strategies)}\n")

    results = {s: [] for s in args.strategies}

    for strategy in args.strategies:
        print(f"\n--- Strategy: {strategy} ({STRATEGIES[strategy]['model']}) ---\n")
        for i, fixture in enumerate(fixtures):
            r = run_task(fixture, strategy, i)
            results[strategy].append(r)
            status = "PASS" if r["passed"] else "FAIL"
            print(f"  [{i+1}/{len(fixtures)}] {fixture.name:<20} {status}  "
                  f"${r['cost_cents']/100:.4f}  {r['duration_seconds']:.0f}s")

    # --- Summary with confidence intervals ---
    print("\n" + "=" * 70)
    print("SUMMARY WITH CONFIDENCE INTERVALS")
    print("=" * 70)
    print(f"{'Strategy':<12} {'Pass':<10} {'95% CI':<20} {'Cost':<12} {'Cost/Success':<15}")
    print("-" * 70)

    for strategy in args.strategies:
        rs = results[strategy]
        passes = sum(1 for r in rs if r["passed"])
        total = len(rs)
        lo, hi = wilson_interval(passes, total)
        total_cost = sum(r["cost_cents"] for r in rs)
        cost_per_success = total_cost / max(passes, 1)
        print(
            f"{strategy:<12} "
            f"{passes}/{total:<8} "
            f"({lo:.2f}, {hi:.2f}){'':<8} "
            f"${total_cost/100:<11.4f} "
            f"${cost_per_success/100:<14.4f}"
        )

    # Save summary
    summary = {
        "strategies": args.strategies,
        "fixtures_count": len(fixtures),
        "results": {
            s: {
                "passes": sum(1 for r in results[s] if r["passed"]),
                "total": len(results[s]),
                "cost_cents": sum(r["cost_cents"] for r in results[s]),
                "raw": results[s],
            }
            for s in args.strategies
        },
    }
    (Path("evals") / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nSummary saved: evals/summary.json")
    print(f"Rollouts saved: evals/rollouts/")


if __name__ == "__main__":
    main()