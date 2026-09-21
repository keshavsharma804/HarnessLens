"""Phase 0 acceptance test: schema validates, policy loads, dummy emits valid events."""

import pytest
from app.schema import TraceEvent, EventType, VerificationStatus
from app.policy_loader import load_policy, policy_hash
from adapters.dummy_adapter import DummyHarness


def test_trace_event_minimal():
    """Every event must have run_id, harness_id, event_index, turn_index, loop_step."""
    event = TraceEvent(
        run_id="test-run",
        harness_id="test-harness",
        event_index=0,
        turn_index=0,
        loop_step=0,
        event_type=EventType.RUN_STARTED,
    )
    assert event.run_id == "test-run"
    assert event.verification_status == VerificationStatus.PENDING


def test_dummy_harness_emits_valid_events():
    """The dummy adapter must produce events the schema accepts."""
    harness = DummyHarness()
    events = harness.run("test task")

    assert len(events) == 5  # 1 start + 3 steps + 1 end
    assert events[0].event_type == EventType.RUN_STARTED
    assert events[-1].event_type == EventType.RUN_COMPLETED

    # Loop step is the routing signal — verify it's populated
    assert events[1].loop_step == 1
    assert events[1].last_tool_called == "read_file"
    assert events[1].budget_consumed_cents == 0.5

    # Verify cumulative budget tracking
    assert events[-1].budget_consumed_cents == 1.5


def test_policy_loads_and_hashes():
    """Policy loads without error and produces a stable hash for audit."""
    policy = load_policy("policies/default.yaml")
    assert policy.policy_name == "default-cost-aware"
    assert len(policy.routing_rules) == 3

    hash1 = policy_hash(policy)
    hash2 = policy_hash(policy)
    assert hash1 == hash2  # Deterministic


def test_routing_rules_reference_valid_harnesses():
    """Every harness mentioned in routing rules must exist in the registry."""
    policy = load_policy("policies/default.yaml")
    registered = set(policy.harnesses.keys())

    for rule in policy.routing_rules:
        for h in rule.action.get("prefer_harnesses", []):
            assert h in registered, f"Rule '{rule.name}' references unknown harness '{h}'"
        for h in rule.action.get("fallback_harnesses", []):
            assert h in registered, f"Rule '{rule.name}' references unknown fallback '{h}'"