import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.accountability_chain import AccountabilityChain
from app.delegation_validator import DelegationValidator


def main():
    chain = AccountabilityChain(max_depth=3)

    print("\n=== Scenario 1: Clean nested delegation ===\n")
    parent = chain.create_contract(
        parent_run_id="run-001",
        parent_harness="researchharness",
        sub_harness="easyloops",
        delegated_step=5,
        authority=["read_file", "analyze"],
        boundaries={"max_cost_cents": 50, "max_steps": 5},
    )
    print(f"  Created parent contract: {parent.contract_id}")
    print(f"    parent: {parent.parent_harness} -> sub: {parent.sub_harness}")
    print(f"    authority: {parent.authority_transferred}")
    print(f"    depth: {parent.depth}")

    child = chain.create_contract(
        parent_run_id="run-001",
        parent_harness="easyloops",
        sub_harness="dummy_harness",
        delegated_step=7,
        authority=["write_file"],
        boundaries={"max_cost_cents": 20},
        depth=2,
    )
    print(f"\n  Created child contract: {child.contract_id}")
    print(f"    depth: {child.depth}")

    chain.record_outcome(parent.contract_id, "success", "easyloops", "completed")
    chain.record_outcome(child.contract_id, "failure", "dummy_harness", "timeout")

    print("\n  Tracing failure from child contract...")
    trace = chain.trace_failure(child.contract_id)
    for i, record in enumerate(trace):
        print(
            f"    [{i}] {record.contract.contract_id} "
            f"({record.contract.parent_harness} -> {record.contract.sub_harness}) "
            f"outcome={record.outcome} responsible={record.responsible_party}"
        )

    print("\n=== Scenario 2: Delegation validator ===\n")
    validator = DelegationValidator()

    # Case A: Authorized action.
    result = validator.validate(parent, {"requested_action": "read_file"})
    print(f"  read_file on parent contract: valid={result.valid}")

    # Case B: Unauthorized action.
    result = validator.validate(parent, {"requested_action": "run_command"})
    print(f"  run_command on parent contract: valid={result.valid}")
    for v in result.violations:
        print(f"    violation: {v}")

    print("\n=== Scenario 3: Depth limit enforcement ===\n")
    try:
        chain.create_contract(
            parent_run_id="run-001",
            parent_harness="dummy_harness",
            sub_harness="rogue",
            delegated_step=9,
            authority=["read_file"],
            boundaries={},
            depth=5,
        )
    except ValueError as e:
        print(f"  Correctly rejected: {e}")

    print("\n=== Snapshot ===\n")
    snap = chain.snapshot()
    for k, v in snap.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()