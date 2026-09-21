"""
Tests for the harness evolver.

Verifies step-clustering and tool-clustering detection, evidence thresholds,
and per-harness patch generation.
"""

from app.harness_evolver import HarnessEvolver
from app.trajectory_diagnostics import TrajectoryDigest


def _digest(run_id, harness_id, failed_at_step=5, last_valid_tool="read_file"):
    return TrajectoryDigest(
        run_id=run_id,
        harness_id=harness_id,
        total_steps=failed_at_step,
        failed_at_step=failed_at_step,
        last_valid_tool=last_valid_tool,
        last_valid_step=failed_at_step - 1,
        divergence_reason="timeout",
        preceding_tools=[],
        cost_so_far_cents=1.0,
        salvageable=True,
    )


def test_step_clustering_produces_patch():
    digests = [
        _digest(f"r{i}", "h1", failed_at_step=7, last_valid_tool=f"tool{i}")
        for i in range(5)
    ]
    evolver = HarnessEvolver(min_evidence=3)
    patches = evolver.analyze(digests)
    step_patches = [p for p in patches if "step-7" in p.patch_id]
    assert len(step_patches) == 1
    assert step_patches[0].target_harness == "h1"
    assert "7 failures" not in step_patches[0].rationale  # exactly 5 in test
    assert "5 failures" in step_patches[0].rationale


def test_step_clustering_below_threshold_produces_no_patch():
    digests = [
        _digest(f"r{i}", "h1", failed_at_step=i, last_valid_tool="read")
        for i in range(3)
    ]
    evolver = HarnessEvolver(min_evidence=3)
    patches = evolver.analyze(digests)
    step_patches = [p for p in patches if "step-" in p.patch_id]
    assert len(step_patches) == 0


def test_tool_clustering_produces_patch():
    digests = [
        _digest(f"r{i}", "h1", failed_at_step=3 + i, last_valid_tool="analyze")
        for i in range(4)
    ]
    evolver = HarnessEvolver(min_evidence=3)
    patches = evolver.analyze(digests)
    tool_patches = [p for p in patches if "tool-analyze" in p.patch_id]
    assert len(tool_patches) == 1
    assert "after_analyze" in str(tool_patches[0].changes)


def test_multiple_harnesses_produce_separate_patches():
    digests = (
        [_digest(f"a{i}", "h1", failed_at_step=7, last_valid_tool="x") for i in range(4)]
        + [_digest(f"b{i}", "h2", failed_at_step=3, last_valid_tool="y") for i in range(4)]
    )
    evolver = HarnessEvolver(min_evidence=3)
    patches = evolver.analyze(digests)
    harnesses = {p.target_harness for p in patches}
    assert "h1" in harnesses
    assert "h2" in harnesses


def test_evidence_listed_in_patch():
    digests = [
        _digest(f"r{i}", "h1", failed_at_step=7, last_valid_tool="read")
        for i in range(5)
    ]
    evolver = HarnessEvolver(min_evidence=3)
    patches = evolver.analyze(digests)
    step_patch = next(p for p in patches if "step-7" in p.patch_id)
    assert len(step_patch.evidence) == 5


def test_empty_digest_list_produces_no_patches():
    evolver = HarnessEvolver()
    assert evolver.analyze([]) == []