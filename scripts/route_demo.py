import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.router import TrajectoryState, route
from app.policy_loader import load_policy


def main():
    policy = load_policy()

    print("\n=== Routing decisions along a simulated trajectory ===\n")
    for step in range(0, 12):
        state = TrajectoryState(
            run_id=f"demo-run-{step}",
            current_loop_step=step,
            last_tool_called="read_file" if step % 2 == 0 else "write_file",
            budget_consumed_cents=step * 1.5,
            budget_limit_cents=500.0,
        )
        decision = route(state, policy)
        scores_str = ", ".join(f"{k}:{v:.2f}" for k, v in decision.score_breakdown.items())
        print(
            f"step={step:2d}  "
            f"chose={decision.selected_harness:16s}  "
            f"scores={{{scores_str}}}"
        )

    print("\n=== Budget pressure scenario ===\n")
    state = TrajectoryState(
        run_id="budget-test",
        current_loop_step=5,
        last_tool_called="write_file",
        budget_consumed_cents=490.0,
        budget_limit_cents=500.0,
    )
    decision = route(state, policy)
    print(f"chose={decision.selected_harness}")
    print(f"reason={decision.reason}")


if __name__ == "__main__":
    main()