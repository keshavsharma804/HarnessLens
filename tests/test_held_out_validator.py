"""
Tests for the held-out validator.

Verifies acceptance criteria, insufficient data handling, and regression
rejection.
"""

from app.harness_evolver import HarnessPatch
from app.held_out_validator import HeldOutValidator


def _patch():
    return HarnessPatch(
        patch_id="hp-test",
        target_harness="h1",
        rationale="test",
        changes=[],
        evidence=[],
        expected_improvement="test",
    )


def _runs(success_rate: float, n: int = 10):
    successes = int(success_rate * n)
    return [{"success": i < successes} for i in range(n)]


def test_validator_accepts_improvement():
    validator = HeldOutValidator(min_improvement=0.05)
    outcome = validator.validate(
        _patch(),
        baseline_runs=_runs(0.4),
        patched_runs=_runs(0.6),
    )
    assert outcome.accepted is True
    assert outcome.improvement >= 0.05


def test_validator_rejects_regression():
    validator = HeldOutValidator(min_improvement=0.05)
    outcome = validator.validate(
        _patch(),
        baseline_runs=_runs(0.6),
        patched_runs=_runs(0.4),
    )
    assert outcome.accepted is False
    assert outcome.improvement < 0


def test_validator_rejects_insufficient_improvement():
    validator = HeldOutValidator(min_improvement=0.10)
    outcome = validator.validate(
        _patch(),
        baseline_runs=_runs(0.50),
        patched_runs=_runs(0.52),
    )
    assert outcome.accepted is False
    assert outcome.improvement < 0.10


def test_validator_rejects_insufficient_data():
    validator = HeldOutValidator(min_runs=5)
    outcome = validator.validate(
        _patch(),
        baseline_runs=_runs(0.4, n=2),
        patched_runs=_runs(0.9, n=2),
    )
    assert outcome.accepted is False
    assert "Insufficient" in outcome.detail


def test_validator_reports_rates_correctly():
    validator = HeldOutValidator(min_improvement=0.05)
    outcome = validator.validate(
        _patch(),
        baseline_runs=_runs(0.30),
        patched_runs=_runs(0.70),
    )
    assert abs(outcome.baseline_success_rate - 0.30) < 0.05
    assert abs(outcome.patched_success_rate - 0.70) < 0.05


def test_validator_accepts_when_improvement_exactly_at_threshold():
    validator = HeldOutValidator(min_improvement=0.10)
    # 3/10 = 0.30 -> 4/10 = 0.40, exactly 0.10 improvement.
    outcome = validator.validate(
        _patch(),
        baseline_runs=_runs(0.30, n=10),
        patched_runs=_runs(0.40, n=10),
    )
    assert outcome.accepted is True