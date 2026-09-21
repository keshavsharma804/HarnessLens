import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.circuit_breaker import default_registry
from app.degradation import evaluate_degradation
from app.router import TrajectoryState, route
from app.policy_loader import load_policy


def main():
    policy = load_policy()

    print("\n=== Scenario 1: Circuit breaker trips ===\n")
    cb = default_registry.get("researchharness")
    for i in range(3):
        cb.record_failure()
        print(f"  Failure {i+1}: state={cb.state.value}")
    print(f"  allow_call() = {cb.allow_call()}")

    # Now route a request; it should NOT pick researchharness.
    state = TrajectoryState(
        run_id="demo-1",
        current_loop_step=1,   # would normally prefer researchharness
        last_tool_called="read_file",
        budget_consumed_cents=10.0,
        budget_limit_cents=500.0,
    )
    decision = route(state, policy)
    print(f"  Router chose: {decision.selected_harness} (researchharness is broken)")
    print(f"  Reason: {decision.reason}")

    print("\n=== Scenario 2: Mid-trajectory degradation ===\n")
    state = TrajectoryState(
        run_id="demo-2",
        current_loop_step=7,
        last_tool_called="write_file",
        budget_consumed_cents=430.0,   # 86% of 500
        budget_limit_cents=500.0,
    )
    deg = evaluate_degradation(
        current_harness="researchharness",
        budget_consumed_cents=state.budget_consumed_cents,
        budget_limit_cents=state.budget_limit_cents,
        policy=policy,
    )
    print(f"  Should degrade? {deg.should_degrade}")
    print(f"  From: {deg.from_harness}")
    print(f"  To:   {deg.to_harness}")
    print(f"  Reason: {deg.reason}")

    # Reset breaker for future runs
    default_registry.get("researchharness").record_success()


if __name__ == "__main__":
    main()