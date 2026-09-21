"""Verify the merge protocol classifies outcomes correctly."""

from app.merge_protocol import (
    MergeOutcome,
    fingerprint_artifacts,
    merge,
)


def test_clean_merge_no_changes():
    parent = fingerprint_artifacts({"a.txt": "hello"})
    subtask = {}
    result = merge(parent, subtask)
    assert result.outcome == MergeOutcome.CLEAN


def test_additive_merge_new_file():
    parent = fingerprint_artifacts({"a.txt": "hello"})
    subtask = fingerprint_artifacts({"b.txt": "new"})
    result = merge(parent, subtask)
    assert result.outcome == MergeOutcome.ADDITIVE
    assert "b.txt" in result.added


def test_conflicting_merge_same_path_different_content():
    parent = fingerprint_artifacts({"a.txt": "hello"})
    subtask = fingerprint_artifacts({"a.txt": "different"})
    result = merge(parent, subtask)
    assert result.outcome == MergeOutcome.CONFLICTING
    assert "a.txt" in result.conflicts


def test_same_path_same_content_no_conflict():
    parent = fingerprint_artifacts({"a.txt": "hello"})
    subtask = fingerprint_artifacts({"a.txt": "hello"})
    result = merge(parent, subtask)
    assert result.outcome == MergeOutcome.CLEAN
    assert result.conflicts == []