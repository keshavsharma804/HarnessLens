
import uuid
from dataclasses import dataclass, field
from typing import Optional
from app.circuit_breaker import default_registry as default_breaker_registry
from app.schema import RoutingDecision
from app.policy_loader import Policy, load_policy, policy_hash
from app.policy_signer import default_signer

@dataclass
class TrajectoryState:
  

    run_id: str
    current_loop_step: int
    last_tool_called: Optional[str]
    budget_consumed_cents: float
    budget_limit_cents: float
    historical_success: dict = field(default_factory=dict)


def _normalize(value: float, max_value: float) -> float:
    """Convert a raw value to a 0..1 score, where 0 is worst and 1 is best."""
    if max_value <= 0:
        return 1.0
    return max(0.0, 1.0 - (value / max_value))


def _step_affinity(harness_id: str, loop_step: int, policy: Policy) -> float:
    """
    How well does this harness fit this point in the trajectory?

    Early steps: quality matters. Later steps: cost matters.
    """
    affinity_cfg = policy.scoring.step_affinity
    harness_meta = policy.harnesses.get(harness_id)
    if not harness_meta:
        return 0.0

    if loop_step < affinity_cfg.early_phase_max_step:
        if "precision" in harness_meta.strengths:
            return 1.0
        return 0.5

    if loop_step >= affinity_cfg.late_phase_min_step:
        if "cost" in harness_meta.strengths:
            return 1.0
        return 0.5

    return 0.7  # middle phase: neutral


def _score_harness(
    harness_id: str,
    state: TrajectoryState,
    policy: Policy,
) -> dict:
    """Compute a composite score for one candidate harness."""
    meta = policy.harnesses[harness_id]
    w = policy.scoring.weights
    norm = policy.scoring.normalization

    # Historical success (0..1). Default 0.5 when we have no data yet.
    historical = state.historical_success.get(harness_id, 0.5)

    # Cost score (0..1, higher is cheaper)
    cost_score = _normalize(meta.cost_per_1k_tokens_cents, norm.max_cost_cents)

    # Latency score (0..1, higher is faster)
    latency_score = _normalize(meta.typical_latency_ms, norm.max_latency_ms)

    # Step affinity (0..1)
    affinity = _step_affinity(harness_id, state.current_loop_step, policy)

    composite = (
        w.historical_success * historical
        + w.cost * cost_score
        + w.latency * latency_score
        + w.step_affinity * affinity
    )

    return {
        "historical_success": historical,
        "cost": cost_score,
        "latency": latency_score,
        "step_affinity": affinity,
        "composite": composite,
    }


def _check_admission(state: TrajectoryState, policy: Policy) -> Optional[str]:
    """
    Admission control. Returns a rejection reason, or None if allowed.

    Decisions are made BEFORE the call, not audited after.
    """
    ac = policy.admission_control

    if state.budget_consumed_cents >= ac.get("max_cost_per_run_cents", float("inf")):
        return "budget_exhausted"

    if state.current_loop_step >= ac.get("max_loop_steps", float("inf")):
        return "max_loop_steps_exceeded"

    return None


def route(
    state: TrajectoryState,
    policy: Optional[Policy] = None,
) -> RoutingDecision:
    """
    Decide which harness should execute the next step.

    Returns a RoutingDecision that is fully auditable: it records all
    candidate scores and the reason, so the caller can log it.
    """
    policy = policy or load_policy()

    # Step 1: Admission control
    rejection = _check_admission(state, policy)
    if rejection:
        return RoutingDecision(
            decision_id=str(uuid.uuid4())[:8],
            run_id=state.run_id,
            selected_harness="__none__",
            candidate_harnesses=list(policy.harnesses.keys()),
            score_breakdown={},
            reason=f"Rejected by admission control: {rejection}",
            policy_version=policy_hash(policy) + ":" + _policy_signature_for(),
        )

    # Step 2: Score every candidate
        # Step 2: Filter candidates through the circuit breaker.
    all_harnesses = list(policy.harnesses.keys())
    viable = default_breaker_registry.allowed_harnesses(all_harnesses)

    if not viable:
        return RoutingDecision(
            decision_id=str(uuid.uuid4())[:8],
            run_id=state.run_id,
            selected_harness="__none__",
            candidate_harnesses=all_harnesses,
            score_breakdown={},
            reason="All harnesses are circuit-broken (open).",
            policy_version=policy_hash(policy),
        )

    # Step 3: Score every viable candidate.
    scores = {
        harness_id: _score_harness(harness_id, state, policy)
        for harness_id in viable
    }

    # Step 3: Pick the highest composite
    selected = max(scores.keys(), key=lambda h: scores[h]["composite"])

    # Step 4: Build a human-readable reason
    matching_rule = None
    for rule in policy.routing_rules:
        cond = rule.condition
        if "loop_step" in cond and cond["loop_step"] == "< 5":
            if state.current_loop_step < 5 and selected in rule.action.get("prefer_harnesses", []):
                matching_rule = rule.name
                break
        if "last_tool_called" in cond and cond["last_tool_called"] == state.last_tool_called:
            if selected in rule.action.get("prefer_harnesses", []):
                matching_rule = rule.name
                break

    reason = (
        f"Selected '{selected}' at loop_step={state.current_loop_step} "
        f"(last_tool={state.last_tool_called}, "
        f"budget={state.budget_consumed_cents:.2f}c). "
        f"Composite={scores[selected]['composite']:.3f}. "
    )
    if matching_rule:
        reason += f"Matched rule: '{matching_rule}'."

    return RoutingDecision(
        decision_id=str(uuid.uuid4())[:8],
        run_id=state.run_id,
        selected_harness=selected,
        candidate_harnesses=list(scores.keys()),
        score_breakdown={h: s["composite"] for h, s in scores.items()},
        reason=reason,
        policy_version=policy_hash(policy),
    )


def build_state_with_learning(
    run_id: str,
    current_loop_step: int,
    last_tool_called: Optional[str],
    budget_consumed_cents: float,
    budget_limit_cents: float,
) -> TrajectoryState:
    """
    Convenience helper: builds a TrajectoryState with historical success
    rates already loaded from the fleet learning module.

    Callers who want raw control can construct TrajectoryState directly.
    """
    from app.fleet_learning import historical_success_map

    return TrajectoryState(
        run_id=run_id,
        current_loop_step=current_loop_step,
        last_tool_called=last_tool_called,
        budget_consumed_cents=budget_consumed_cents,
        budget_limit_cents=budget_limit_cents,
        historical_success=historical_success_map(),
    )

def _policy_signature_for(path: str = "policies/default.yaml") -> str:
    """Return the signature of the policy file currently in use."""
    return default_signer.sign_file(path)