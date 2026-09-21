"""
Benchmark: compare cost-per-success with and without the control plane.

Method:
- Run N synthetic tasks against two harnesses.
- Baseline: always use researchharness (naive default).
- Control-plane: use the router with learning enabled.
- Report: total cost, success count, cost per success.

This is a synthetic benchmark. Numbers reflect the simulation, not real
providers. But the methodology is the same one you would use in production.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import random
import tempfile
import uuid

from app import collector
from app.schema import HarnessRunSummary
from app.router import TrajectoryState, route
from app.policy_loader import load_policy
from app.fleet_learning import historical_success_map


def _simulate_run(harness_id: str, task_id: str) -> HarnessRunSummary:
    """
    Simulate a single agent run.

    Success probability depends on harness (from the demo we already know
    researchharness is unreliable and easyloops is reliable).
    """
    if harness_id == "researchharness":
        success = random.random() < 0.20
        cost = 6.0
    else:  # easyloops
        success = random.random() < 0.80
        cost = 1.5

    return HarnessRunSummary(
        run_id=f"{harness_id}-{task_id}",
        harness_id=harness_id,
        total_steps=3,
        total_cost_cents=cost,
        total_latency_ms=2600 if harness_id == "researchharness" else 300,
        final_status="success" if success else "failed",
        verification_passed=success,
        failure_reason=None if success else "simulated failure",
    )


def _seed_history(n_per_harness: int = 20) -> None:
    """Pre-populate the DB so fleet learning has something to work with."""
    for i in range(n_per_harness):
        collector.insert_run_summary(
            _simulate_run("researchharness", f"seed-{i}")
        )
        collector.insert_run_summary(
            _simulate_run("easyloops", f"seed-{i}")
        )


def _run_baseline(n_tasks: int = 100) -> dict:
    """Naive baseline: always route to researchharness."""
    total_cost = 0.0
    successes = 0
    for i in range(n_tasks):
        s = _simulate_run("researchharness", f"baseline-{i}")
        total_cost += s.total_cost_cents
        successes += 1 if s.final_status == "success" else 0
    return {
        "total_cost_cents": total_cost,
        "successes": successes,
        "tasks": n_tasks,
        "cost_per_success": total_cost / max(successes, 1),
    }


def _run_with_control_plane(n_tasks: int = 100) -> dict:
    """Route each task using the control plane with fleet learning."""
    policy = load_policy()
    rates = historical_success_map()

    total_cost = 0.0
    successes = 0
    picks: dict[str, int] = {}

    for i in range(n_tasks):
        state = TrajectoryState(
            run_id=f"cp-{i}",
            current_loop_step=1,     # early step: router would normally prefer research
            last_tool_called="read_file",
            budget_consumed_cents=0.0,
            budget_limit_cents=500.0,
            historical_success=rates,
        )
        decision = route(state, policy)
        picks[decision.selected_harness] = picks.get(decision.selected_harness, 0) + 1

        s = _simulate_run(decision.selected_harness, f"cp-{i}")
        total_cost += s.total_cost_cents
        successes += 1 if s.final_status == "success" else 0

    return {
        "total_cost_cents": total_cost,
        "successes": successes,
        "tasks": n_tasks,
        "cost_per_success": total_cost / max(successes, 1),
        "picks": picks,
    }


def main():
    random.seed(42)

    tmpdir = tempfile.mkdtemp()
    collector.DB_PATH = Path(tmpdir) / "bench.db"

    print("\n=== Seeding historical data ===\n")
    _seed_history(20)
    print("  Seeded 20 runs per harness.")

    print("\n=== Baseline (always researchharness) ===\n")
    baseline = _run_baseline(100)
    print(f"  Tasks: {baseline['tasks']}")
    print(f"  Successes: {baseline['successes']}")
    print(f"  Total cost: {baseline['total_cost_cents']:.1f} cents")
    print(f"  Cost per success: {baseline['cost_per_success']:.2f} cents")

    print("\n=== With control plane ===\n")
    cp = _run_with_control_plane(100)
    print(f"  Tasks: {cp['tasks']}")
    print(f"  Successes: {cp['successes']}")
    print(f"  Total cost: {cp['total_cost_cents']:.1f} cents")
    print(f"  Cost per success: {cp['cost_per_success']:.2f} cents")
    print(f"  Harness picks: {cp['picks']}")

    print("\n=== Improvement ===\n")
    improvement = (
        (baseline["cost_per_success"] - cp["cost_per_success"])
        / baseline["cost_per_success"] * 100
    )
    success_delta = cp["successes"] - baseline["successes"]
    print(f"  Cost-per-success reduction: {improvement:.1f}%")
    print(f"  Additional successes: {success_delta}")


if __name__ == "__main__":
    main()