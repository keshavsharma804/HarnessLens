"""
Tests for the orchestrator entropy monitor.

Verifies Shannon entropy math, trend detection, and failure prediction.
"""

import math

from app.entropy_monitor import EntropyMonitor, EntropySnapshot
from app.degradation_predictor import DegradationPredictor, Prediction


def test_uniform_decisions_produce_max_entropy():
    """Two candidates with equal scores -> entropy = 1.0."""
    m = EntropyMonitor()
    snap = m.record(step=1, decision_scores={"a": 1.0, "b": 1.0}, context_size=0)
    assert abs(snap.task_resolution_component - 1.0) < 1e-6


def test_single_candidate_produces_zero_entropy():
    m = EntropyMonitor()
    snap = m.record(step=1, decision_scores={"a": 1.0}, context_size=0)
    assert snap.task_resolution_component == 0.0


def test_skewed_decisions_produce_low_entropy():
    """One dominant candidate -> entropy near 0."""
    m = EntropyMonitor()
    snap = m.record(
        step=1,
        decision_scores={"a": 0.99, "b": 0.01},
        context_size=0,
    )
    assert snap.task_resolution_component < 0.2


def test_context_load_contributes_to_combined_entropy():
    """Same decisions, more context -> higher combined entropy."""
    m1 = EntropyMonitor()
    m2 = EntropyMonitor()
    s1 = m1.record(1, {"a": 0.5, "b": 0.5}, context_size=0)
    s2 = m2.record(1, {"a": 0.5, "b": 0.5}, context_size=9000)
    assert s2.entropy > s1.entropy


def test_stable_trend_with_flat_entropy():
    m = EntropyMonitor()
    for i in range(5):
        m.record(i, {"a": 0.6, "b": 0.4}, context_size=1000)
    assert m.trend() == "stable"


def test_rising_trend_detected():
    m = EntropyMonitor()
    m.record(0, {"a": 0.99, "b": 0.01}, context_size=100)
    m.record(1, {"a": 0.8, "b": 0.2}, context_size=2000)
    m.record(2, {"a": 0.5, "b": 0.5}, context_size=8000)
    assert m.trend() == "rising"


def test_falling_trend_detected():
    m = EntropyMonitor()
    m.record(0, {"a": 0.5, "b": 0.5}, context_size=8000)
    m.record(1, {"a": 0.8, "b": 0.2}, context_size=2000)
    m.record(2, {"a": 0.99, "b": 0.01}, context_size=100)
    assert m.trend() == "falling"


def test_insufficient_data_returns_no_prediction():
    m = EntropyMonitor()
    assert m.trend() == "insufficient_data"
    assert m.predict_failure_in_steps() == -1


def test_critical_snapshot_triggers_abort():
    m = EntropyMonitor()
    # Force entropy above critical threshold
    m.record(0, {"a": 1.0, "b": 1.0}, context_size=10000)
    predictor = DegradationPredictor(m)
    pred = predictor.predict()
    assert pred.should_intervene is True
    assert pred.intervention_type == "abort"


def test_warning_rising_triggers_compress_context():
    m = EntropyMonitor()
    m.record(0, {"a": 0.9, "b": 0.1}, context_size=500)
    m.record(1, {"a": 0.7, "b": 0.3}, context_size=5000)
    m.record(2, {"a": 0.6, "b": 0.4}, context_size=7000)
    predictor = DegradationPredictor(m)
    pred = predictor.predict()
    # Warning threshold at 0.6; rising -> intervention
    assert pred.should_intervene is True
    assert pred.intervention_type in ("compress_context", "switch_orchestrator", "abort")


def test_stable_orchestrator_no_intervention():
    m = EntropyMonitor()
    for i in range(5):
        m.record(i, {"a": 0.99, "b": 0.01}, context_size=100)
    predictor = DegradationPredictor(m)
    pred = predictor.predict()
    assert pred.should_intervene is False


def test_history_window_is_bounded():
    m = EntropyMonitor(window=5)
    for i in range(20):
        m.record(i, {"a": 0.6, "b": 0.4}, context_size=100)
    assert len(m.history) == 5