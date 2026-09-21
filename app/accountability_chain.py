"""
Accountability chain for recursive delegation.

Every delegation is a contract: parent delegates step N to a sub-harness,
transferring authority but retaining accountability. When a delegated step
fails, the chain identifies who is responsible and why.

Implements DeepMind's "Intelligent AI Delegation" framework elements:
- Task allocation
- Transfer of authority
- Responsibility assignment
- Accountability tracking
- Role and boundary specifications
- Trust calibration

Design rationale:
- Contracts are immutable after creation.
- Depth limit prevents unbounded recursive chains.
- Failure tracing walks the parent chain to root cause.
- Every contract has a UUID so audit can reference it directly.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class DelegationContract:
    """A single authority-transfer contract between two harnesses."""

    contract_id: str
    parent_run_id: str
    parent_harness: str
    sub_harness: str
    delegated_step: int
    authority_transferred: list[str]  # tool names the sub-harness may call
    boundaries: dict                    # e.g., {"max_cost_cents": 50, "max_steps": 5}
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    depth: int = 1                      # 1 = top-level delegation


@dataclass
class AccountabilityRecord:
    contract: DelegationContract
    outcome: str                        # "success" | "failure" | "violation"
    responsible_party: str              # harness_id that owns the outcome
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AccountabilityChain:
    """
    Manages delegation contracts and their outcomes.

    Usage:
        chain = AccountabilityChain(max_depth=3)
        contract = chain.create_contract(...)
        # ... run sub-harness ...
        chain.record_outcome(contract.contract_id, "failure", "easyloops", "timeout")
        trace = chain.trace_failure(contract.contract_id)
    """

    def __init__(self, max_depth: int = 3):
        self.max_depth = max_depth
        self.contracts: dict[str, DelegationContract] = {}
        self.records: list[AccountabilityRecord] = []

    def create_contract(
        self,
        parent_run_id: str,
        parent_harness: str,
        sub_harness: str,
        delegated_step: int,
        authority: list[str],
        boundaries: dict,
        depth: int = 1,
    ) -> DelegationContract:
        """Create and register a delegation contract."""
        if depth > self.max_depth:
            raise ValueError(
                f"Delegation depth {depth} exceeds max {self.max_depth}. "
                f"Prevents quadratic chain validation cost."
            )
        if not authority:
            raise ValueError("Delegation must transfer at least one authority.")

        contract = DelegationContract(
            contract_id=f"dc-{uuid.uuid4().hex[:8]}",
            parent_run_id=parent_run_id,
            parent_harness=parent_harness,
            sub_harness=sub_harness,
            delegated_step=delegated_step,
            authority_transferred=list(authority),
            boundaries=dict(boundaries),
            depth=depth,
        )
        self.contracts[contract.contract_id] = contract
        return contract

    def record_outcome(
        self,
        contract_id: str,
        outcome: str,
        responsible_party: str,
        reason: str,
    ) -> AccountabilityRecord:
        """Record a contract's outcome. Raises if contract unknown."""
        contract = self.contracts.get(contract_id)
        if not contract:
            raise ValueError(f"Unknown contract: {contract_id}")

        if outcome not in ("success", "failure", "violation"):
            raise ValueError(f"Invalid outcome: {outcome}")

        record = AccountabilityRecord(
            contract=contract,
            outcome=outcome,
            responsible_party=responsible_party,
            reason=reason,
        )
        self.records.append(record)
        return record

    def trace_failure(self, contract_id: str) -> list[AccountabilityRecord]:
        """
        Walk the chain from a failing contract back through its parents.

        Returns records in order from the failing contract outward.
        """
        chain: list[AccountabilityRecord] = []
        current_id = contract_id
        seen: set[str] = set()

        while current_id and current_id not in seen:
            seen.add(current_id)
            contract = self.contracts.get(current_id)
            if not contract:
                break

            # Find the outcome record for this contract.
            record = next(
                (r for r in self.records if r.contract.contract_id == current_id),
                None,
            )
            if record:
                chain.append(record)

            # Find the parent contract in the same run.
            parent = next(
                (
                    c for c in self.contracts.values()
                    if c.parent_run_id == contract.parent_run_id
                    and c.contract_id != contract.contract_id
                    and c.depth < contract.depth
                ),
                None,
            )
            current_id = parent.contract_id if parent else None

        return chain

    def contracts_for_run(self, run_id: str) -> list[DelegationContract]:
        """All contracts belonging to a run, sorted by depth."""
        return sorted(
            [c for c in self.contracts.values() if c.parent_run_id == run_id],
            key=lambda c: c.depth,
        )

    def snapshot(self) -> dict:
        """Summary for observability."""
        return {
            "total_contracts": len(self.contracts),
            "total_records": len(self.records),
            "by_outcome": {
                outcome: sum(1 for r in self.records if r.outcome == outcome)
                for outcome in ("success", "failure", "violation")
            },
        }