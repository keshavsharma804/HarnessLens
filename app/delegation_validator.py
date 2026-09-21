"""
Validates delegation contracts before execution.

The validator enforces the delegation's boundaries: a sub-harness cannot
perform an action that was not in its authority list, and behavior gate
rules override everything.

This is the "terminal architectural grounding" the Homunculus Protocol
argues is required to resolve the Validator's Paradox. Contract boundaries
are enforced structurally, not by trusting the chain.
"""

from dataclasses import dataclass, field

from app.accountability_chain import DelegationContract


@dataclass
class ValidationResult:
    valid: bool
    violations: list[str] = field(default_factory=list)


class DelegationValidator:
    """
    Validates a delegation contract against a requested action.

    Checks:
    1. Requested action is within the transferred authority set.
    2. Depth does not exceed the chain's max.
    3. Behavior gate (if injected) does not deny the action.
    """

    def __init__(self, behavior_gate=None):
        self.gate = behavior_gate

    def validate(self, contract: DelegationContract, context: dict) -> ValidationResult:
        violations: list[str] = []

        requested_action = context.get("requested_action")

        # Check 1: Requested action within transferred authority.
        if requested_action and requested_action not in contract.authority_transferred:
            violations.append(
                f"Action '{requested_action}' not in transferred authority "
                f"{contract.authority_transferred}."
            )

        # Check 2: Depth limit (defense in depth; chain already enforces).
        if contract.depth > 3:
            violations.append(
                f"Delegation depth {contract.depth} exceeds limit (3)."
            )

        # Check 3: Behavior gate override.
        if self.gate and requested_action:
            decision = self.gate.evaluate(context)
            if decision.verdict == "deny":
                violations.append(
                    f"Behavior gate denied action: {decision.reason} "
                    f"(rule: {decision.rule_name})."
                )

        return ValidationResult(valid=len(violations) == 0, violations=violations)