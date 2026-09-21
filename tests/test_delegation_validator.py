"""
Tests for the delegation validator.

Verifies that authority boundaries are enforced and behavior gate rules
override the contract.
"""

from app.accountability_chain import AccountabilityChain
from app.delegation_validator import DelegationValidator


class _MockGate:
    """Minimal stub matching BehaviorGate's interface."""

    def __init__(self, verdict: str, rule: str = "test-rule", reason: str = "test"):
        self._verdict = verdict
        self._rule = rule
        self._reason = reason

    def evaluate(self, context):
        class D:
            pass
        d = D()
        d.verdict = self._verdict
        d.rule_name = self._rule
        d.reason = self._reason
        return d


def _make_contract(authority=None):
    chain = AccountabilityChain()
    return chain.create_contract(
        parent_run_id="r1",
        parent_harness="researchharness",
        sub_harness="easyloops",
        delegated_step=5,
        authority=authority or ["read_file"],
        boundaries={"max_cost_cents": 50},
    )


def test_validator_allows_authorized_action():
    contract = _make_contract(authority=["read_file"])
    v = DelegationValidator()
    result = v.validate(contract, {"requested_action": "read_file"})
    assert result.valid is True
    assert result.violations == []


def test_validator_rejects_unauthorized_action():
    contract = _make_contract(authority=["read_file"])
    v = DelegationValidator()
    result = v.validate(contract, {"requested_action": "write_file"})
    assert result.valid is False
    assert any("not in transferred authority" in violation
               for violation in result.violations)


def test_validator_passes_when_no_action_requested():
    contract = _make_contract()
    v = DelegationValidator()
    result = v.validate(contract, {})
    assert result.valid is True


def test_validator_honors_behavior_gate_denial():
    contract = _make_contract(authority=["write_file"])
    gate = _MockGate(verdict="deny", rule="deny-writes", reason="high risk")
    v = DelegationValidator(behavior_gate=gate)
    result = v.validate(contract, {"requested_action": "write_file"})
    assert result.valid is False
    assert any("Behavior gate denied" in violation
               for violation in result.violations)


def test_validator_honors_behavior_gate_allow():
    contract = _make_contract(authority=["read_file"])
    gate = _MockGate(verdict="allow")
    v = DelegationValidator(behavior_gate=gate)
    result = v.validate(contract, {"requested_action": "read_file"})
    assert result.valid is True