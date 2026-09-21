"""Tests for the continuous evolver."""

import tempfile
from pathlib import Path

from app.continuous_evolver import ContinuousEvolver
from app.repair_library import RepairLibrary


RULES = """
version: "1.0.0"
repairs:
  timeout_:
    actions:
      - id: "retry"
        type: "retry_with_backoff"
      - id: "switch"
        type: "switch_harness"
  silent_failure_:
    actions:
      - id: "rerun"
        type: "rerun_with_verifier"
"""


def _lib():
    tmp = Path(tempfile.mkdtemp()) / "repairs.yaml"
    tmp.write_text(RULES)
    return RepairLibrary(str(tmp))


def test_no_patches_without_enough_evidence():
    lib = _lib()
    lib.record_attempt("timeout_x", "switch", True)
    lib.record_attempt("timeout_x", "switch", True)
    evolver = ContinuousEvolver(lib)
    # MIN_ATTEMPTS = 3; only 2 attempts recorded.
    assert evolver.propose_patches() == []


def test_patch_proposed_when_success_rate_high():
    lib = _lib()
    for _ in range(4):
        lib.record_attempt("timeout_x", "switch", True)
    evolver = ContinuousEvolver(lib)
    patches = evolver.propose_patches()
    assert len(patches) == 1
    assert patches[0].success_rate == 1.0
    assert patches[0].evidence_attempts == 4
    assert patches[0].changes[0]["field"] == "fallback_harness"


def test_no_patch_when_success_rate_low():
    lib = _lib()
    for _ in range(5):
        lib.record_attempt("timeout_x", "retry", False)
    lib.record_attempt("timeout_x", "switch", False)
    evolver = ContinuousEvolver(lib)
    # Best action success rate is 0.0, below 0.6 threshold.
    assert evolver.propose_patches() == []


def test_escalate_actions_are_skipped():
    lib = _lib()
    # Override the YAML: use an escalate action.
    rules = """
version: "1.0.0"
repairs:
  timeout_:
    actions:
      - id: "esc"
        type: "escalate"
"""
    tmp = Path(tempfile.mkdtemp()) / "r.yaml"
    tmp.write_text(rules)
    lib2 = RepairLibrary(str(tmp))
    for _ in range(5):
        lib2.record_attempt("timeout_x", "esc", True)
    evolver = ContinuousEvolver(lib2)
    # escalate has no config field mapping, so no patch is proposed.
    assert evolver.propose_patches() == []


def test_multiple_signatures_produce_multiple_patches():
    lib = _lib()
    for _ in range(4):
        lib.record_attempt("timeout_x", "switch", True)
        lib.record_attempt("silent_failure_y", "rerun", True)
    evolver = ContinuousEvolver(lib)
    patches = evolver.propose_patches()
    assert len(patches) == 2