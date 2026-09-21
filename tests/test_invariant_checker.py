"""
Tests for the runtime invariant checker.

Each test targets one invariant from spec/invariants.md. Together these
tests and the TLA+ spec cover both design-time and runtime verification.
"""

from app.invariant_checker import InvariantChecker
from app.schema import TraceEvent, EventType


def _event(**kwargs):
    defaults = dict(
        run_id="r1",
        harness_id="h1",
        event_index=0,
        turn_index=0,
        loop_step=0,
        event_type=EventType.TOOL_CALLED,
        budget_consumed_cents=0.0,
    )
    defaults.update(kwargs)
    return TraceEvent(**defaults)


# --- INV-1: NoDeniedActionExecutes ---

def test_denied_action_followed_by_tool_call_is_violation():
    events = [
        _event(event_index=0, action_verdict="denied"),
        _event(event_index=1),  # tool_called after deny
    ]
    checker = InvariantChecker()
    violations = checker.check(events)
    assert any(v.invariant_name == "NoDeniedActionExecutes" for v in violations)


def test_denied_action_with_no_subsequent_tool_call_is_clean():
    events = [
        _event(event_index=0, action_verdict="denied"),
        _event(event_index=1, event_type=EventType.RUN_COMPLETED),
    ]
    checker = InvariantChecker()
    violations = checker.check(events)
    assert not any(v.invariant_name == "NoDeniedActionExecutes" for v in violations)


def test_allowed_action_then_tool_call_is_clean():
    events = [
        _event(event_index=0, action_verdict="allowed"),
        _event(event_index=1),
    ]
    checker = InvariantChecker()
    violations = checker.check(events)
    assert violations == []


# --- INV-2: BudgetNeverExceeds ---

def test_budget_overflow_is_violation():
    events = [
        _event(event_index=0, budget_consumed_cents=600.0),
    ]
    checker = InvariantChecker(max_budget_cents=500.0)
    violations = checker.check(events)
    assert any(v.invariant_name == "BudgetNeverExceeds" for v in violations)


def test_budget_at_ceiling_is_clean():
    events = [
        _event(event_index=0, budget_consumed_cents=500.0),
    ]
    checker = InvariantChecker(max_budget_cents=500.0)
    violations = checker.check(events)
    assert violations == []


# --- INV-3: LoopStepBounded ---

def test_loop_step_overflow_is_violation():
    events = [_event(event_index=0, loop_step=100)]
    checker = InvariantChecker(max_loop_steps=40)
    violations = checker.check(events)
    assert any(v.invariant_name == "LoopStepBounded" for v in violations)


def test_loop_step_within_bounds_is_clean():
    events = [_event(event_index=0, loop_step=30)]
    checker = InvariantChecker(max_loop_steps=40)
    violations = checker.check(events)
    assert violations == []


# --- INV-4: SelectionInHarnessSet ---

def test_unknown_harness_is_violation():
    events = [_event(event_index=0, harness_id="rogue")]
    checker = InvariantChecker(allowed_harnesses=["researchharness", "easyloops"])
    violations = checker.check(events)
    assert any(v.invariant_name == "SelectionInHarnessSet" for v in violations)


def test_known_harness_is_clean():
    events = [_event(event_index=0, harness_id="easyloops")]
    checker = InvariantChecker(allowed_harnesses=["researchharness", "easyloops"])
    violations = checker.check(events)
    assert violations == []


def test_harness_set_check_skipped_when_not_configured():
    events = [_event(event_index=0, harness_id="anything")]
    checker = InvariantChecker()  # allowed_harnesses=None
    violations = checker.check(events)
    assert violations == []


# --- Emission ---

def test_violations_emit_as_events():
    events = [_event(event_index=0, budget_consumed_cents=999.0)]
    checker = InvariantChecker(max_budget_cents=500.0)
    emitted = checker.emit_violations(events)
    assert len(emitted) == 1
    assert emitted[0].invariant_violation["invariant_name"] == "BudgetNeverExceeds"
    assert emitted[0].error is not None


def test_no_violations_emits_nothing():
    events = [_event(event_index=0, budget_consumed_cents=10.0)]
    checker = InvariantChecker(max_budget_cents=500.0)
    emitted = checker.emit_violations(events)
    assert emitted == []


def test_multiple_violations_all_reported():
    events = [
        _event(event_index=0, budget_consumed_cents=999.0, loop_step=100),
    ]
    checker = InvariantChecker(max_budget_cents=500.0, max_loop_steps=40)
    violations = checker.check(events)
    names = {v.invariant_name for v in violations}
    assert "BudgetNeverExceeds" in names
    assert "LoopStepBounded" in names