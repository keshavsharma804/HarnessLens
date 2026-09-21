"""
Unified Trace Schema for the Harness Control Plane.

This schema defines the contract between harness adapters and the control plane.
Every adapter MUST emit events matching this schema. The router reads this schema
to make loop-step-aware routing decisions.

Design decisions:
- Flat event structure (not nested) for easy storage in SQLite/Parquet.
- `loop_step` is the primary routing signal, not prompt text (per BitRouter).
- `harness_id` allows cross-harness comparison of the same task.
- `budget_consumed_cents` enables runtime admission control.
"""

from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class EventType(str, Enum):
    RUN_STARTED = "run_started"
    STEP_STARTED = "step_started"
    TOOL_CALLED = "tool_called"
    TOOL_RESULT = "tool_result"
    VERIFICATION_CHECKED = "verification_checked"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    BUDGET_WARNING = "budget_warning"
    # --- Phase 6 additions ---
    CONTEXT_STALE = "context_stale"
    SCHEMA_DRIFT = "schema_drift"
    SILENT_FAILURE = "silent_failure"
    ACTION_DENIED = "action_denied"
    POLICY_TAMPERED = "policy_tampered"
    SUBTASK_DELEGATED = "subtask_delegated"
    SUBTASK_MERGED = "subtask_merged"
    MERGE_CONFLICT = "merge_conflict"
    TRAJECTORY_DIGEST = "trajectory_digest"
    CASCADE_REPAIR_STARTED = "cascade_repair_started"
    CASCADE_REPAIR_COMPLETED = "cascade_repair_completed"
    PREDICATE_EVALUATED = "predicate_evaluated"
    VERIFICATION_PROOF_GENERATED = "verification_proof_generated"
    ENTROPY_SNAPSHOT = "entropy_snapshot"
    ORCHESTRATOR_DEGRADATION_PREDICTED = "orchestrator_degradation_predicted"
    INVARIANT_VIOLATION = "invariant_violation"
    DECEPTION_SCORED = "deception_scored"
    COLLUSION_SUSPECTED = "collusion_suspected"
    DELEGATION_CONTRACT_VIOLATED = "delegation_contract_violated"
    HARNESS_PATCH_PROPOSED = "harness_patch_proposed"
    HARNESS_PATCH_VALIDATED = "harness_patch_validated"

    FAILURE_CLASSIFIED = "failure_classified"
    REPAIR_ATTEMPTED = "repair_attempted"
    REPAIR_SUCCEEDED = "repair_succeeded"
    REPAIR_FAILED = "repair_failed"
    MEMORY_RETRIEVED = "memory_retrieved"
    MEMORY_WRITTEN = "memory_written"
    MEMORY_PRUNED = "memory_pruned"
    MEMORY_FITNESS_UPDATED = "memory_fitness_updated"

    PATCH_STAGED = "patch_staged"
    PATCH_PROMOTED = "patch_promoted"
    PATCH_REJECTED_BY_STAGING = "patch_rejected_by_staging"
    


class VerificationStatus(str, Enum):
    """Result of the independent verifier (Phase 3)."""
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TraceEvent(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    """
    A single event in the unified trace stream.

    This is the atomic unit the control plane operates on.
    Adapters emit these; the router consumes them.
    """

    # --- Identity (who, what, where) ---
    run_id: str = Field(..., description="Unique ID for the entire agent run")
    harness_id: str = Field(..., description="Which harness produced this (e.g., 'researchharness', 'easyloops')")
    event_index: int = Field(..., description="Monotonic index within this run")
    turn_index: int = Field(..., description="Which turn of the agent loop")

    # --- THE ROUTING SIGNAL ---
    loop_step: int = Field(
        ...,
        description="Position in trajectory. Primary routing signal per BitRouter."
    )
    last_tool_called: Optional[str] = Field(
        None,
        description="The tool called in the PREVIOUS turn. Keyed for loop-step routing."
    )

    # --- Timing & Cost ---
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    latency_ms: Optional[int] = Field(None, description="Duration of this step in ms")
    input_tokens: Optional[int] = Field(None, description="Prompt tokens for this step")
    output_tokens: Optional[int] = Field(None, description="Completion tokens for this step")
    cost_cents: Optional[float] = Field(None, description="USD cost in cents for this step")
    budget_consumed_cents: float = Field(
        default=0.0,
        description="Cumulative spend for this run so far. Enables admission control."
    )

    # --- Event-specific payload ---
    event_type: EventType
    tool_arguments: Optional[Dict[str, Any]] = Field(None, description="Args passed to the tool")
    tool_result_summary: Optional[str] = Field(
        None,
        description="Truncated result for debugging. Full results stored separately."
    )
    error: Optional[str] = Field(None, description="Error message if the step failed")

    # --- Verification (Phase 3) ---
    verification_status: VerificationStatus = Field(default=VerificationStatus.PENDING)
    verification_detail: Optional[str] = Field(None, description="Why verification passed/failed")

        # --- Data-layer governance (Phase 6) ---
    source_timestamp: Optional[datetime] = Field(
        None,
        description="When the data source was last verified. Used for TTL checks."
    )
    schema_fingerprint: Optional[str] = Field(
        None,
        description="Hash of the JSON structure returned by a tool. Used for drift detection."
    )
    expected_artifacts: Optional[list[str]] = Field(
        None,
        description="Paths this step claims to produce. Used for silent failure detection."
    )

        # --- Policy-as-contract (Phase 7) ---
    policy_signature: Optional[str] = Field(
        None,
        description="HMAC signature of the policy file used for this decision."
    )
    action_verdict: Optional[str] = Field(
        None,
        description="Behavior gate verdict: 'allowed', 'denied', 'flagged'."
    )

    # --- Extensibility ---
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Harness-specific extras. Never routed on; for debugging only."
    )

        # --- Recursive composition (Phase 8) ---
    parent_run_id: Optional[str] = Field(
        None,
        description="If this event is from a delegated subtask, the parent run."
    )
    delegated_step: Optional[int] = Field(
        None,
        description="The loop_step in the parent trajectory this subtask replaces."
    )
    artifact_versions: Optional[dict] = Field(
        None,
        description="Map of artifact path -> version hash at the moment of merge."
    )

        # --- Trajectory diagnostics (Phase 9) ---
    trajectory_digest: Optional[dict] = Field(
        None,
        description="Structured summary of a failed run. Used for cascade repair."
    )

    predicate_results: Optional[dict] = Field(
        None,
        description="Map of predicate_name -> bool. Atomic verification results."
    )
    verification_proof: Optional[str] = Field(
        None,
        description="Human-readable proof of the final verdict."
    )
        # --- Entropy monitoring (Phase 11) ---
    entropy_snapshot: Optional[dict] = Field(
        None,
        description="Orchestrator health snapshot: entropy, trend, prediction."
    )

        # --- Formal invariants (Phase 12) ---
    invariant_violation: Optional[dict] = Field(
        None,
        description="Named invariant that was violated, with detail."
    )
        # --- Collusion detection (Phase 13) ---
    deception_score: Optional[float] = Field(
        None,
        description="Per-harness deception score (0.0 honest to 1.0 deceptive)."
    )
        # --- Accountability chain (Phase 14) ---
    delegation_contract: Optional[dict] = Field(
        None,
        description="Contract metadata when this event is part of a delegation."
    )
        # --- Harness evolution (Phase 15) ---
    harness_patch: Optional[dict] = Field(
        None,
        description="Proposed or validated harness patch metadata."
    )

        # --- Self-healing (Phase 16) ---
    failure_signature: Optional[str] = Field(
        None,
        description="Classified failure type, e.g. 'timeout_after_analyze'."
    )
    repair_action: Optional[str] = Field(
        None,
        description="Repair action applied, e.g. 'retry_with_backoff'."
    )

        # --- Self-improving (Phase 17) ---
    staging_status: Optional[str] = Field(
        None,
        description="Staging state: 'staged', 'promoted', 'rejected', 'rolled_back'."
    )

        # --- Evolving memory (Phase 18) ---
    memory_lessons: Optional[list[str]] = Field(
        None,
        description="Lessons retrieved for this step, injected as constraints."
    )

    


class HarnessRunSummary(BaseModel):
    """Rollup of a completed run. Used by the fleet learning layer (Phase 4)."""

    run_id: str
    harness_id: str
    total_steps: int
    total_cost_cents: float
    total_latency_ms: int
    final_status: str  # "success" | "failed" | "budget_exhausted" | "cycle_detected"
    verification_passed: bool
    failure_reason: Optional[str] = None


class RoutingDecision(BaseModel):
    """
    The output of the router (Phase 2). Recorded for audit.

    This model is intentionally separate from TraceEvent because routing
    decisions are MADE, not OBSERVED. Keeping them separate allows the
    control plane to log "what I chose" vs. "what actually happened."
    """

    decision_id: str
    run_id: str
    selected_harness: str
    candidate_harnesses: List[str]
    score_breakdown: Dict[str, float]  # harness_id -> score
    reason: str  # Human-readable: "loop_step > 5, prefer cheap"
    policy_version: str  # Hash of the policy YAML used