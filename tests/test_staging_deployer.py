"""Tests for the staging deployer."""

from app.continuous_evolver import EvolvedPatch
from app.staging_deployer import StagingDeployer, StagingState


import uuid

def _patch():
    return EvolvedPatch(
        patch_id=f"ep-test-{uuid.uuid4().hex[:6]}",
        target_harness="easyloops",
        rationale="test",
        changes=[{"field": "retry_policy", "from": "default", "to": "retry_with_backoff"}],
        evidence_signatures=["timeout_x"],
        evidence_attempts=5,
        success_rate=0.8,
    )


def test_stage_creates_patch():
    d = StagingDeployer()
    staged = d.stage(_patch(), validation_improvement=0.15)
    assert staged.state == StagingState.STAGED
    assert staged.validation_improvement == 0.15


def test_promote_moves_to_promoted():
    d = StagingDeployer()
    staged = d.stage(_patch(), 0.15)
    assert d.promote(staged.patch_id) is True
    assert d.patches[staged.patch_id].state == StagingState.PROMOTED


def test_reject_moves_to_rejected():
    d = StagingDeployer()
    staged = d.stage(_patch(), 0.15)
    assert d.reject(staged.patch_id, "insufficient evidence") is True
    assert d.patches[staged.patch_id].state == StagingState.REJECTED


def test_cannot_promote_already_promoted():
    d = StagingDeployer()
    staged = d.stage(_patch(), 0.15)
    d.promote(staged.patch_id)
    # Second promote returns False.
    assert d.promote(staged.patch_id) is False


def test_auto_rollback_when_post_promotion_regresses():
    d = StagingDeployer(rollback_threshold=-0.05)
    staged = d.stage(_patch(), 0.15)
    d.promote(staged.patch_id)
    result = d.observe_post_promotion(staged.patch_id, success_rate=0.30)
    assert result == "rolled_back"
    assert d.patches[staged.patch_id].state == StagingState.ROLLED_BACK


def test_no_rollback_when_post_promotion_healthy():
    d = StagingDeployer(rollback_threshold=-0.05)
    staged = d.stage(_patch(), 0.15)
    d.promote(staged.patch_id)
    result = d.observe_post_promotion(staged.patch_id, success_rate=0.55)
    assert result is None
    assert d.patches[staged.patch_id].state == StagingState.PROMOTED


def test_snapshot_summarizes():
    d = StagingDeployer()
    p1 = d.stage(_patch(), 0.15)
    p2 = d.stage(_patch(), 0.20)
    d.promote(p1.patch_id)
    d.reject(p2.patch_id)
    snap = d.snapshot()
    assert snap["total"] == 2
    assert snap["by_state"]["promoted"] == 1
    assert snap["by_state"]["rejected"] == 1