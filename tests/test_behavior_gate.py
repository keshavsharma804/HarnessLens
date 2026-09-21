"""Verify the behavior gate denies, flags, and allows correctly."""

import tempfile
from pathlib import Path

from app.behavior_gate import BehaviorGate, Verdict


RULES = """
version: "1.0.0"
rules:
  - name: "deny-writes-on-risky-tasks"
    action: deny
    when: {tool_name: "write_file", risk_level: "high"}
    reason: "High-risk writes forbidden."
  - name: "deny-shell-on-prod"
    action: deny
    when: {tool_name: "run_command", target_environment: "production"}
    reason: "Prod shell forbidden."
  - name: "flag-env-reads"
    action: flag
    when: {tool_name: "read_file", path_glob: "**/.env"}
    reason: "Log .env reads."
  - name: "default-allow"
    action: allow
    when: {}
    reason: "Default."
"""


def _gate():
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(RULES)
        path = Path(f.name)
    return BehaviorGate(path)


def test_gate_denies_high_risk_write():
    gate = _gate()
    d = gate.evaluate({"tool_name": "write_file", "risk_level": "high"})
    assert d.verdict == Verdict.DENIED
    assert d.rule_name == "deny-writes-on-risky-tasks"


def test_gate_denies_prod_shell():
    gate = _gate()
    d = gate.evaluate({"tool_name": "run_command", "target_environment": "production"})
    assert d.verdict == Verdict.DENIED


def test_gate_flags_env_read():
    gate = _gate()
    d = gate.evaluate({"tool_name": "read_file", "path": "/app/.env"})
    assert d.verdict == Verdict.FLAGGED


def test_gate_allows_normal_read():
    gate = _gate()
    d = gate.evaluate({"tool_name": "read_file", "path": "/app/readme.md"})
    assert d.verdict == Verdict.ALLOWED


def test_first_matching_rule_wins():
    """Deny should win over the default allow."""
    gate = _gate()
    d = gate.evaluate({"tool_name": "write_file", "risk_level": "high"})
    assert d.verdict == Verdict.DENIED