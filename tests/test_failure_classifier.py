"""Tests for the failure classifier."""

from app.failure_classifier import FailureClassifier, FailureClass
from app.trajectory_diagnostics import TrajectoryDigest


def _digest(reason, last_tool="analyze", preceding=None):
    return TrajectoryDigest(
        run_id="r1",
        harness_id="h1",
        total_steps=5,
        failed_at_step=5,
        last_valid_tool=last_tool,
        last_valid_step=4,
        divergence_reason=reason,
        preceding_tools=preceding or ["read_file", "analyze"],
        cost_so_far_cents=1.0,
        salvageable=True,
    )


def test_classify_timeout():
    sig = FailureClassifier().classify(_digest("step 5 timed out"))
    assert sig.failure_class == FailureClass.TIMEOUT
    assert sig.signature_id == "timeout_after_analyze"
    assert sig.computable is True


def test_classify_silent_failure():
    sig = FailureClassifier().classify(_digest("expected artifact missing"))
    assert sig.failure_class == FailureClass.SILENT_FAILURE


def test_classify_tool_error():
    sig = FailureClassifier().classify(_digest("tool returned error"))
    assert sig.failure_class == FailureClass.TOOL_ERROR


def test_classify_stale_context():
    sig = FailureClassifier().classify(_digest("source is stale"))
    assert sig.failure_class == FailureClass.CONTEXT_STALE


def test_classify_merge_conflict():
    sig = FailureClassifier().classify(_digest("merge conflict on a.txt"))
    assert sig.failure_class == FailureClass.MERGE_CONFLICT


def test_classify_loop_wins_over_reason():
    # Even if reason says timeout, if the tool repeated 4 times -> loop.
    sig = FailureClassifier().classify(_digest(
        "timeout", last_tool="read_file",
        preceding=["read_file", "read_file", "read_file", "read_file"],
    ))
    assert sig.failure_class == FailureClass.LOOP_DETECTED


def test_classify_unknown():
    sig = FailureClassifier().classify(_digest("something weird"))
    assert sig.failure_class == FailureClass.UNKNOWN
    assert sig.computable is False