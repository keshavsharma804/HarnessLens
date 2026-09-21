"""
Repair library: maps failure signatures to repair actions.

Each signature has one or more candidate actions ordered by preference.
The executor tries them in order and records which worked.

Design rationale:
- Repairs are declarative, not code. A team can add a repair by editing
  YAML and opening a PR.
- Success rates are tracked per (signature, action). The library exposes
  a "best action" query for use during execution.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class RepairAction:
    action_id: str
    action_type: str              # "retry_with_backoff" | "switch_harness" | ...
    params: dict = field(default_factory=dict)


@dataclass
class RepairAttemptRecord:
    signature_id: str
    action_id: str
    succeeded: bool


class RepairLibrary:
    """
    Loads repair rules from YAML, tracks success rates.
    """

    def __init__(self, rules_path: str = "policies/repair_rules.yaml"):
        self.rules_path = Path(rules_path)
        self._rules = self._load()
        self._records: list[RepairAttemptRecord] = []

    def _load(self) -> dict:
        if not self.rules_path.exists():
            return {}
        raw = yaml.safe_load(self.rules_path.read_text())
        return raw.get("repairs", {})

    def candidates_for(self, signature_id: str) -> list[RepairAction]:
        """Return candidate actions for a signature, ordered by preference."""
        # Exact match first.
        if signature_id in self._rules:
            return self._parse_actions(self._rules[signature_id])
        # Prefix match, e.g. "timeout_after_analyze" -> "timeout_*".
        prefix = signature_id.split("_")[0] + "_"
        for key, rules in self._rules.items():
            if key.startswith(prefix) or key == prefix.rstrip("_"):
                return self._parse_actions(rules)
        # Fallback.
        if "_default" in self._rules:
            return self._parse_actions(self._rules["_default"])
        return []

    def _parse_actions(self, rules: dict) -> list[RepairAction]:
        actions = []
        for i, a in enumerate(rules.get("actions", [])):
            actions.append(RepairAction(
                action_id=a.get("id", f"action-{i}"),
                action_type=a["type"],
                params=a.get("params", {}),
            ))
        return actions

    def record_attempt(self, signature_id: str, action_id: str, succeeded: bool) -> None:
        self._records.append(RepairAttemptRecord(
            signature_id=signature_id,
            action_id=action_id,
            succeeded=succeeded,
        ))

    def success_rate(self, signature_id: str, action_id: str) -> float:
        relevant = [
            r for r in self._records
            if r.signature_id == signature_id and r.action_id == action_id
        ]
        if not relevant:
            return 0.0
        return sum(1 for r in relevant if r.succeeded) / len(relevant)

    def best_action(self, signature_id: str) -> RepairAction | None:
        """Return the action with the highest observed success rate."""
        candidates = self.candidates_for(signature_id)
        if not candidates:
            return None
        # If no data, return first candidate (declared preference).
        if not self._records:
            return candidates[0]
        scored = sorted(
            candidates,
            key=lambda a: self.success_rate(signature_id, a.action_id),
            reverse=True,
        )
        return scored[0]