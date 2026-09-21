"""Verify fleet learning computes correct stats and bounded adjustments."""

import tempfile
from pathlib import Path

from app import collector, fleet_learning
from app.schema import HarnessRunSummary


def _summary(run_id, harness_id, status, cost=1.0, latency=100):
    return HarnessRunSummary(
        run_id=run_id,
        harness_id=harness_id,
        total_steps=3,
        total_cost_cents=cost,
        total_latency_ms=latency,
        final_status=status,
        verification_passed=(status == "success"),
        failure_reason=None if status == "success" else "test failure",
    )


def _setup_temp_db(monkeypatch):
    tmpdir = tempfile.mkdtemp()
    monkeypatch.setattr(collector, "DB_PATH", Path(tmpdir) / "test.db")


def test_stats_empty_db(monkeypatch):
    _setup_temp_db(monkeypatch)
    stats = fleet_learning.compute_harness_stats()
    assert stats == {}


def test_stats_single_harness(monkeypatch):
    _setup_temp_db(monkeypatch)
    for i in range(5):
        status = "success" if i < 3 else "failed"
        collector.insert_run_summary(_summary(f"r{i}", "h1", status))

    stats = fleet_learning.compute_harness_stats()
    assert "h1" in stats
    assert stats["h1"].total_runs == 5
    assert stats["h1"].successful_runs == 3
    assert abs(stats["h1"].success_rate - 0.6) < 1e-6


def test_historical_success_bounded(monkeypatch):
    """
    Even a harness with 0% success rate should not go below
    0.5 - MAX_ADJUSTMENT in the adjusted map.
    """
    _setup_temp_db(monkeypatch)
    for i in range(10):
        collector.insert_run_summary(_summary(f"r{i}", "bad", "failed"))

    rates = fleet_learning.historical_success_map()
    assert "bad" in rates
    assert rates["bad"] >= 0.5 - fleet_learning.MAX_ADJUSTMENT


def test_historical_success_cold_start(monkeypatch):
    """
    With fewer than MIN_RUNS_FOR_CONFIDENCE, the rate should stay near neutral.
    """
    _setup_temp_db(monkeypatch)
    collector.insert_run_summary(_summary("r1", "new", "failed"))

    rates = fleet_learning.historical_success_map()
    # Only 1 run: confidence is 1/3. Blended rate should be 0.5*(2/3) + 0*(1/3) = 0.333.
    # Bounded, so >= 0.5 - MAX_ADJUSTMENT (0.20).
    assert rates["new"] >= 0.5 - fleet_learning.MAX_ADJUSTMENT