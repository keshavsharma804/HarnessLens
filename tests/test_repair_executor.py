"""Tests for the repair executor."""

import tempfile
from pathlib import Path

from app.failure_classifier import FailureSignature, FailureClass
from app.repair_executor import RepairExecutor
from app.repair_library import RepairLibrary
from app.schema import TraceEvent, EventType


RULES = """
version: "1.0.0"
repairs:
  timeout_:
    actions:
      - id: "retry"
        type: "retry_with_backoff"
      - id: "switch"
        type: "switch_harness"
"""


def _lib():
    tmp = Path(tempfile.mkdtemp()) / "repairs.yaml"
    tmp.write_text(RULES)
    return RepairLibrary(str(tmp))


def _template():
    return TraceEvent(
        run_id="r1", harness_id="h1",
        event_index=0, turn_index=0, loop_step=5,
        event_type=EventType.RUN_FAILED,
        budget_consumed_cents=5.0,
        error="timeout",
    )


def _sig():
    return FailureSignature(
        failure_class=FailureClass.TIMEOUT,
        signature_id="timeout_after_analyze",
        detail="step 5 timed out",
        computable=True,
    )


def test_first_handler_succeeds():
    handlers = {
        "retry_with_backoff": lambda a, c: (True, "retried ok"),
        "switch_harness": lambda a, c: (True, "switched"),
    }
    executor = RepairExecutor(_lib(), handlers)
    outcome = executor.repair(_sig(), _template())
    assert outcome.succeeded is True
    assert outcome.action_id == "retry"
    types = [e.event_type if isinstance(e.event_type, str) else e.event_type.value
             for e in outcome.events]
    assert "failure_classified" in types
    assert "repair_attempted" in types
    assert "repair_succeeded" in types


def test_first_fails_second_succeeds():
    handlers = {
        "retry_with_backoff": lambda a, c: (False, "still timed out"),
        "switch_harness": lambda a, c: (True, "switched ok"),
    }
    executor = RepairExecutor(_lib(), handlers)
    outcome = executor.repair(_sig(), _template())
    assert outcome.succeeded is True
    assert outcome.action_id == "switch"


def test_all_handlers_fail():
    handlers = {
        "retry_with_backoff": lambda a, c: (False, "no"),
        "switch_harness": lambda a, c: (False, "no"),
    }
    executor = RepairExecutor(_lib(), handlers)
    outcome = executor.repair(_sig(), _template())
    assert outcome.succeeded is False
    assert outcome.action_id is None


def test_handler_exception_does_not_crash():
    def boom(a, c):
        raise RuntimeError("handler blew up")
    handlers = {
        "retry_with_backoff": boom,
        "switch_harness": lambda a, c: (True, "ok"),
    }
    executor = RepairExecutor(_lib(), handlers)
    outcome = executor.repair(_sig(), _template())
    assert outcome.succeeded is True
    assert outcome.action_id == "switch"


def test_unknown_signature_falls_back():
    handlers = {"escalate": lambda a, c: (True, "escalated")}
    # Library has no _default in this test, so no candidates.
    executor = RepairExecutor(_lib(), handlers)
    sig = FailureSignature(
        failure_class=FailureClass.UNKNOWN,
        signature_id="unknown",
        detail="unknown",
        computable=False,
    )
    outcome = executor.repair(sig, _template())
    assert outcome.attempted is False