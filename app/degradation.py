"""
Mid-trajectory degradation.

When budget pressure hits mid-run, do not hard-fail. Instead:
1. Compute remaining budget.
2. Pick the cheapest viable harness for the remaining steps.
3. Emit a degradation event so the trace records the switch.

Design rationale:
- Hard budget caps waste the work already done.
- A downgrade preserves trajectory state while capping future cost.
- The policy declares the degradation ladder; the engine follows it.
"""

from dataclasses import dataclass

from app.policy_loader import Policy


@dataclass
class DegradationDecision:
    should_degrade: bool
    reason: str
    from_harness: str
    to_harness: str | None
    remaining_budget_cents: float


def evaluate_degradation(
    current_harness: str,
    budget_consumed_cents: float,
    budget_limit_cents: float,
    policy: Policy,
) -> DegradationDecision:
    """
    Decide whether to switch to a cheaper harness for the remaining steps.

    The trigger is: budget consumed > warning threshold, AND current harness
    is not the cheapest available.
    """
    ac = policy.admission_control
    warning_threshold = ac.get("budget_warning_threshold", 0.8)
    max_cost = ac.get("max_cost_per_run_cents", budget_limit_cents)

    remaining = max_cost - budget_consumed_cents
    ratio = budget_consumed_cents / max_cost if max_cost > 0 else 0.0

    if ratio < warning_threshold:
        return DegradationDecision(
            should_degrade=False,
            reason=f"Budget ratio {ratio:.2f} below threshold {warning_threshold}.",
            from_harness=current_harness,
            to_harness=None,
            remaining_budget_cents=remaining,
        )

    # Find the cheapest harness in the policy.
    cheapest = min(
        policy.harnesses.items(),
        key=lambda kv: kv[1].cost_per_1k_tokens_cents,
    )
    cheapest_id = cheapest[0]

    if cheapest_id == current_harness:
        return DegradationDecision(
            should_degrade=False,
            reason=f"Already on cheapest harness '{current_harness}'.",
            from_harness=current_harness,
            to_harness=None,
            remaining_budget_cents=remaining,
        )

    return DegradationDecision(
        should_degrade=True,
        reason=(
            f"Budget ratio {ratio:.2f} exceeds threshold {warning_threshold}. "
            f"Downgrading '{current_harness}' -> '{cheapest_id}'."
        ),
        from_harness=current_harness,
        to_harness=cheapest_id,
        remaining_budget_cents=remaining,
    )