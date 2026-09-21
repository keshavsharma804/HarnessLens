"""
Tests for the accountability chain.

Verifies contract creation, depth limits, outcome recording, failure
tracing, and snapshotting.
"""

import pytest

from app.accountability_chain import (
    AccountabilityChain,
    DelegationContract,
)


def _chain():
    return AccountabilityChain(max_depth=3)


def test_create_contract_succeeds():
    chain = _chain()
    c = chain.create_contract(
        parent_run_id="r1",
        parent_harness="researchharness",
        sub_harness="easyloops",
        delegated_step=5,
        authority=["read_file", "analyze"],
        boundaries={"max_cost_cents": 50},
    )
    assert c.contract_id.startswith("dc-")
    assert c.depth == 1
    assert c.authority_transferred == ["read_file", "analyze"]


def test_create_contract_rejects_empty_authority():
    chain = _chain()
    with pytest.raises(ValueError, match="at least one authority"):
        chain.create_contract(
            parent_run_id="r1",
            parent_harness="a",
            sub_harness="b",
            delegated_step=1,
            authority=[],
            boundaries={},
        )


def test_create_contract_rejects_deep_nesting():
    chain = _chain()
    with pytest.raises(ValueError, match="exceeds max"):
        chain.create_contract(
            parent_run_id="r1",
            parent_harness="a",
            sub_harness="b",
            delegated_step=1,
            authority=["read_file"],
            boundaries={},
            depth=5,
        )


def test_record_outcome_succeeds():
    chain = _chain()
    c = chain.create_contract(
        "r1", "parent", "sub", 1, ["read_file"], {}
    )
    rec = chain.record_outcome(c.contract_id, "success", "sub", "done")
    assert rec.outcome == "success"
    assert len(chain.records) == 1


def test_record_outcome_rejects_unknown_contract():
    chain = _chain()
    with pytest.raises(ValueError, match="Unknown contract"):
        chain.record_outcome("dc-fake", "success", "x", "y")


def test_record_outcome_rejects_invalid_outcome():
    chain = _chain()
    c = chain.create_contract("r1", "p", "s", 1, ["read_file"], {})
    with pytest.raises(ValueError, match="Invalid outcome"):
        chain.record_outcome(c.contract_id, "maybe", "s", "y")


def test_trace_failure_returns_chain():
    """A failure on a nested contract traces back to parents."""
    chain = _chain()
    parent = chain.create_contract(
        "r1", "root_harness", "mid_harness", 5, ["read_file"], {}, depth=1
    )
    child = chain.create_contract(
        "r1", "mid_harness", "leaf_harness", 7, ["analyze"], {}, depth=2
    )
    chain.record_outcome(parent.contract_id, "success", "mid_harness", "ok")
    chain.record_outcome(child.contract_id, "failure", "leaf_harness", "timeout")

    trace = chain.trace_failure(child.contract_id)
    assert len(trace) >= 1
    assert trace[0].contract.contract_id == child.contract_id
    assert trace[0].outcome == "failure"


def test_contracts_for_run():
    chain = _chain()
    chain.create_contract("runA", "p", "s1", 1, ["read_file"], {}, depth=1)
    chain.create_contract("runA", "p", "s2", 2, ["write_file"], {}, depth=2)
    chain.create_contract("runB", "p", "s3", 1, ["read_file"], {}, depth=1)

    contracts_a = chain.contracts_for_run("runA")
    assert len(contracts_a) == 2
    # Sorted by depth.
    assert contracts_a[0].depth <= contracts_a[1].depth


def test_snapshot_summarizes():
    chain = _chain()
    c1 = chain.create_contract("r1", "p", "s1", 1, ["read_file"], {})
    c2 = chain.create_contract("r1", "p", "s2", 2, ["write_file"], {})
    chain.record_outcome(c1.contract_id, "success", "s1", "ok")
    chain.record_outcome(c2.contract_id, "failure", "s2", "timeout")

    snap = chain.snapshot()
    assert snap["total_contracts"] == 2
    assert snap["total_records"] == 2
    assert snap["by_outcome"]["success"] == 1
    assert snap["by_outcome"]["failure"] == 1