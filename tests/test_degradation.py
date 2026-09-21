"""Verify mid-trajectory degradation logic."""

from app.degradation import evaluate_degradation
from app.policy_loader import load_policy


def test_no_degradation_below_threshold():
    policy = load_policy()
    decision = evaluate_degradation(
        current_harness="researchharness",
        budget_consumed_cents=100.0,  # well below 500c limit
        budget_limit_cents=500.0,
        policy=policy,
    )
    assert decision.should_degrade is False


def test_degradation_above_threshold():
    policy = load_policy()
    decision = evaluate_degradation(
        current_harness="researchharness",
        budget_consumed_cents=450.0,  # 90% of 500c
        budget_limit_cents=500.0,
        policy=policy,
    )
    assert decision.should_degrade is True
    assert decision.to_harness == "easyloops"
    assert "Downgrading" in decision.reason


def test_no_degradation_when_already_cheapest():
    policy = load_policy()
    decision = evaluate_degradation(
        current_harness="easyloops",
        budget_consumed_cents=450.0,
        budget_limit_cents=500.0,
        policy=policy,
    )
    assert decision.should_degrade is False