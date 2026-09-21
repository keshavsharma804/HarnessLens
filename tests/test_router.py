"""Verify the router makes correct decisions under different conditions."""

from app.router import TrajectoryState, route
from app.policy_loader import load_policy


def _state(**kwargs):
    defaults = dict(
        run_id="test-run",
        current_loop_step=1,
        last_tool_called=None,
        budget_consumed_cents=0.0,
        budget_limit_cents=500.0,
        historical_success={},
    )
    defaults.update(kwargs)
    return TrajectoryState(**defaults)


def test_early_step_prefers_precision_harness():
    """At loop_step=1, the router should pick the capable harness."""
    policy = load_policy()
    decision = route(_state(current_loop_step=1), policy)
    assert decision.selected_harness == "researchharness", decision.reason


def test_late_step_prefers_cheap_harness():
    """At loop_step=10, cost should dominate and pick the cheap harness."""
    policy = load_policy()
    decision = route(_state(current_loop_step=10), policy)
    assert decision.selected_harness == "easyloops", decision.reason


def test_budget_exhaustion_blocks_routing():
    """Admission control must reject when budget is exhausted."""
    policy = load_policy()
    state = _state(budget_consumed_cents=9999.0)
    decision = route(state, policy)
    assert decision.selected_harness == "__none__"
    assert "budget" in decision.reason.lower()


def test_decision_is_auditable():
    """Every decision carries a policy hash, reason, and score breakdown."""
    policy = load_policy()
    decision = route(_state(), policy)
    assert decision.policy_version
    assert decision.reason
    assert decision.score_breakdown
    assert all(isinstance(v, float) for v in decision.score_breakdown.values())


def test_historical_success_influences_choice():
    """If we know a harness fails often, the router should avoid it."""
    policy = load_policy()
    state = _state(
        current_loop_step=1,
        historical_success={"researchharness": 0.0, "easyloops": 1.0},
    )
    decision = route(state, policy)
    assert decision.selected_harness == "easyloops", decision.reason