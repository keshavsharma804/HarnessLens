"""
Atomic predicate decomposition for neuro-symbolic verification.

FormalJudge's central discovery: neural reasoning succeeds on atomic
yes-or-no questions but fails at compositional reasoning. So we decompose
verification into atomic predicates, evaluate each independently, then
recompose using formal logic.

This replaces the generic Verifier with something that can catch
deceptive reasoning that passes surface-level checks.

Reference: FormalJudge (ICML 2026) — "LLMs serve as specification compilers
that top-down decompose high-level human intent into atomic, verifiable
constraints, then bottom-up prove compliance."
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PredicateType(str, Enum):
    ARTIFACT_EXISTS = "artifact_exists"
    NO_ERROR_IN_FINAL = "no_error_in_final"
    SCHEMA_MATCHES = "schema_matches"
    TOOL_RESULT_PRESENT = "tool_result_present"
    COST_WITHIN_BUDGET = "cost_within_budget"
    CUSTOM = "custom"


@dataclass
class Predicate:
    name: str
    predicate_type: PredicateType
    params: dict
    description: str


@dataclass
class PredicateResult:
    name: str
    passed: bool
    detail: str


class PredicateDecomposer:
    """
    Breaks a verification request into atomic predicates.

    Predicates come from policies/verification_rules.yaml, keyed by task type.
    Each predicate is evaluated by a deterministic checker or an LLM call
    (for CUSTOM predicates).
    """

    def __init__(self, rules_path: str = "policies/verification_rules.yaml"):
        import yaml
        from pathlib import Path
        raw = yaml.safe_load(Path(rules_path).read_text())
        self.rules = raw.get("verification_rules", {})

    def decompose(self, task_type: str, context: dict) -> list[Predicate]:
        """Return the predicates to check for this task type."""
        rules = self.rules.get(task_type, {}).get("predicates", [])
        return [
            Predicate(
                name=r["name"],
                predicate_type=PredicateType(r["type"]),
                params=r.get("params", {}),
                description=r.get("description", ""),
            )
            for r in rules
        ]

    def evaluate(self, predicate: Predicate, context: dict) -> PredicateResult:
        """
        Evaluate a single atomic predicate.

        Deterministic predicates are checked directly.
        CUSTOM predicates use an injected evaluator (Phase 10b).
        """
        if predicate.predicate_type == PredicateType.ARTIFACT_EXISTS:
            import os
            path = predicate.params.get("path")
            exists = os.path.exists(path) if path else False
            return PredicateResult(
                name=predicate.name,
                passed=exists,
                detail=f"Artifact '{path}' {'exists' if exists else 'missing'}",
            )

        if predicate.predicate_type == PredicateType.NO_ERROR_IN_FINAL:
            error = context.get("final_error")
            passed = error is None
            return PredicateResult(
                name=predicate.name,
                passed=passed,
                detail=f"Final error: {error}" if error else "No error in final event",
            )

        if predicate.predicate_type == PredicateType.COST_WITHIN_BUDGET:
            budget = predicate.params.get("max_cents", float("inf"))
            cost = context.get("cost_cents", 0.0)
            passed = cost <= budget
            return PredicateResult(
                name=predicate.name,
                passed=passed,
                detail=f"Cost {cost:.2f}c vs budget {budget:.2f}c",
            )

        # CUSTOM predicates require an injected evaluator.
        evaluator = context.get("_custom_evaluator")
        if evaluator:
            passed, detail = evaluator(predicate, context)
            return PredicateResult(name=predicate.name, passed=passed, detail=detail)

        return PredicateResult(
            name=predicate.name,
            passed=False,
            detail="No evaluator for custom predicate",
        )