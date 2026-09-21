"""Loads and validates policy YAML. Prevents malformed policies from reaching the router."""

import yaml
from pathlib import Path
from pydantic import BaseModel, ValidationError
from typing import List, Dict, Any, Optional


class RoutingRule(BaseModel):
    name: str
    condition: Dict[str, Any]
    action: Dict[str, Any]


class HarnessMeta(BaseModel):
    display_name: str
    cost_per_1k_tokens_cents: float
    typical_latency_ms: int
    strengths: List[str]
    weaknesses: List[str]

class ScoringWeights(BaseModel):
    historical_success: float
    cost: float
    latency: float
    step_affinity: float


class ScoringNormalization(BaseModel):
    max_cost_cents: float
    max_latency_ms: int


class StepAffinity(BaseModel):
    early_phase_max_step: int
    late_phase_min_step: int


class Scoring(BaseModel):
    weights: ScoringWeights
    normalization: ScoringNormalization
    step_affinity: StepAffinity


class Policy(BaseModel):
    version: str
    policy_name: str
    admission_control: Dict[str, Any]
    routing_rules: List[RoutingRule]
    harnesses: Dict[str, HarnessMeta]
    scoring: Scoring

def load_policy(path: str = "policies/default.yaml") -> Policy:
    """Load and validate a policy file. Raises ValidationError on malformed input."""
    raw = yaml.safe_load(Path(path).read_text())
    return Policy(**raw)


def policy_hash(policy: Policy) -> str:
    """Deterministic hash for audit. Every RoutingDecision references this."""
    import hashlib
    import json
    canonical = json.dumps(policy.model_dump(), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]