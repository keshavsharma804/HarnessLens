"""Tests for the repair library."""

import tempfile
from pathlib import Path

from app.repair_library import RepairLibrary


RULES = """
version: "1.0.0"
repairs:
  timeout_:
    actions:
      - id: "retry"
        type: "retry_with_backoff"
        params: {max_retries: 2}
      - id: "switch"
        type: "switch_harness"
  _default:
    actions:
      - id: "escalate"
        type: "escalate"
"""


def _lib():
    tmp = Path(tempfile.mkdtemp()) / "repairs.yaml"
    tmp.write_text(RULES)
    return RepairLibrary(str(tmp))


def test_candidates_exact_prefix_match():
    lib = _lib()
    actions = lib.candidates_for("timeout_after_analyze")
    assert len(actions) == 2
    assert actions[0].action_id == "retry"


def test_candidates_fallback_to_default():
    lib = _lib()
    actions = lib.candidates_for("totally_unknown")
    assert len(actions) == 1
    assert actions[0].action_id == "escalate"


def test_record_attempt_and_success_rate():
    lib = _lib()
    lib.record_attempt("timeout_after_x", "retry", True)
    lib.record_attempt("timeout_after_x", "retry", True)
    lib.record_attempt("timeout_after_x", "retry", False)
    rate = lib.success_rate("timeout_after_x", "retry")
    assert abs(rate - 2/3) < 1e-6


def test_best_action_picks_highest_rate():
    lib = _lib()
    lib.record_attempt("timeout_after_x", "retry", False)
    lib.record_attempt("timeout_after_x", "switch", True)
    best = lib.best_action("timeout_after_x")
    assert best.action_id == "switch"