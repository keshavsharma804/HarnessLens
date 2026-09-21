"""
Demonstrate fleet learning changing the router's decisions.

The scenario:
1. Populate the DB with runs where researchharness FAILS often and easyloops
   SUCCEEDS often.
2. Compute historical success rates.
3. Route a request at loop_step=1 with those rates applied.
4. Compare to routing WITHOUT learning (neutral prior).

Expected result: without learning, researchharness wins at loop_step=1.
With learning, the successful easyloops overtakes it because its observed
success rate is high.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tempfile
from app import collector
from app.schema import HarnessRunSummary
from app.router import TrajectoryState, route
from app.policy_loader import load_policy
from app.fleet_learning import historical_success_map


def _summary(run_id, harness_id, status):
    return HarnessRunSummary(
        run_id=run_id,
        harness_id=harness_id,
        total_steps=3,
        total_cost_cents=1.5,
        total_latency_ms=200,
        final_status=status,
        verification_passed=(status == "success"),
        failure_reason=None if status == "success" else "harness failure",
    )


def main():
    policy = load_policy()

    # Use an isolated DB for the demo.
    tmpdir = tempfile.mkdtemp()
    collector.DB_PATH = Path(tmpdir) / "demo.db"

    # Populate: researchharness fails 8/10 times, easyloops succeeds 8/10 times.
    print("\n=== Populating historical data ===\n")
    for i in range(10):
        collector.insert_run_summary(
            _summary(f"r-{i}", "researchharness",
                     "success" if i < 2 else "failed")
        )
        collector.insert_run_summary(
            _summary(f"e-{i}", "easyloops",
                     "success" if i < 8 else "failed")
        )
    print("  researchharness: 2/10 success (20%)")
    print("  easyloops:       8/10 success (80%)")

    rates = historical_success_map()
    print(f"\n  Learned rates: {rates}")

    # ---- Route WITHOUT learning ----
    print("\n=== Route at loop_step=1 WITHOUT learning ===\n")
    state_neutral = TrajectoryState(
        run_id="neutral",
        current_loop_step=1,
        last_tool_called="read_file",
        budget_consumed_cents=10.0,
        budget_limit_cents=500.0,
        historical_success={},   # neutral prior
    )
    d1 = route(state_neutral, policy)
    print(f"  chose: {d1.selected_harness}")
    print(f"  scores: {d1.score_breakdown}")

    # ---- Route WITH learning ----
    print("\n=== Route at loop_step=1 WITH learning ===\n")
    state_learned = TrajectoryState(
        run_id="learned",
        current_loop_step=1,
        last_tool_called="read_file",
        budget_consumed_cents=10.0,
        budget_limit_cents=500.0,
        historical_success=rates,
    )
    d2 = route(state_learned, policy)
    print(f"  chose: {d2.selected_harness}")
    print(f"  scores: {d2.score_breakdown}")

    print("\n=== Interpretation ===\n")
    if d1.selected_harness != d2.selected_harness:
        print(
            f"  Learning changed the decision: "
            f"{d1.selected_harness} -> {d2.selected_harness}."
        )
    else:
        print(
            "  Learning did not change the decision on this scenario "
            "(bounded adjustment). See tests for edge cases."
        )


if __name__ == "__main__":
    main()