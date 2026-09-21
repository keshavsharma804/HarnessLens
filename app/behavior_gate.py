"""
Runtime behavior gate.

Evaluates declarative rules against an incoming tool call BEFORE the harness
executes it. Returns a verdict: allowed, denied, or flagged.

Design rationale:
- Rules live in YAML, not code. Security review can diff them.
- Evaluation is deterministic. No LLM. No prompt injection risk.
- The gate runs on the control plane, not inside the harness. Agents cannot
  bypass it by manipulating their own prompts.
- Verdicts are recorded on the trace so audit can prove what was blocked.
"""

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml


class Verdict:
    ALLOWED = "allow"
    DENIED = "deny"
    FLAGGED = "flag"


@dataclass
class GateDecision:
    verdict: str
    rule_name: str
    reason: str


class BehaviorGate:
    def __init__(self, rules_path: str | Path = "policies/behavior_rules.yaml"):
        self.rules_path = Path(rules_path)
        self.rules = self._load_rules()

    def _load_rules(self) -> list[dict]:
        raw = yaml.safe_load(self.rules_path.read_text())
        return raw.get("rules", [])

    def _matches(self, when: dict, context: dict) -> bool:
        """Check if all `when` conditions match the given context."""
        for key, expected in when.items():
            # Glob match: key ends with `_glob`, look up the base key in context.
            if key.endswith("_glob"):
                target_key = key[:-5]  # strip "_glob"
                target_value = context.get(target_key, "")
                if not fnmatch.fnmatch(str(target_value), expected):
                    return False
                continue

            # Exact match.
            actual = context.get(key)
            if actual != expected:
                return False
        return True

    def evaluate(self, context: dict) -> GateDecision:
        """
        Evaluate rules in order. First match wins.
        `context` should contain tool_name, risk_level, target_environment,
        path, etc., depending on the rule conditions.
        """
        for rule in self.rules:
            when = rule.get("when", {})
            if self._matches(when, context):
                return GateDecision(
                    verdict=rule["action"],
                    rule_name=rule["name"],
                    reason=rule.get("reason", ""),
                )
        # No rule matched. Default deny? No — default allow with warning.
        return GateDecision(
            verdict=Verdict.FLAGGED,
            rule_name="no-match",
            reason="No rule matched; flagged for review.",
        )


default_gate = BehaviorGate()