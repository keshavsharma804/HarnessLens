"""
Merge protocol for recursive composition.

When a sub-harness produces results, those results must be merged back into
the parent trajectory. This module detects conflicts — cases where the parent
state and subtask state disagree about the same artifact.

Design rationale:
- Conflicts are detected by comparing artifact version hashes.
- Three outcomes: CLEAN (no overlap), ADDITIVE (subtask only adds new artifacts),
  CONFLICTING (both modified the same artifact differently).
- Conflict resolution policy is declared in YAML, not hardcoded.
"""

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class MergeOutcome(str, Enum):
    CLEAN = "clean"
    ADDITIVE = "additive"
    CONFLICTING = "conflicting"


@dataclass
class MergeResult:
    outcome: MergeOutcome
    conflicts: list[str]           # paths that conflicted
    added: list[str]               # paths added by subtask
    unchanged: list[str]           # paths the subtask did not touch
    detail: str


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def fingerprint_artifacts(artifacts: dict[str, str]) -> dict[str, str]:
    """
    Given a {path: content} map, return {path: version_hash}.
    """
    return {path: _hash_content(content) for path, content in artifacts.items()}


def merge(
    parent_versions: dict[str, str],
    subtask_versions: dict[str, str],
) -> MergeResult:
    """
    Merge a subtask's artifact versions into the parent trajectory.

    Logic:
    - A path in both with same hash -> unchanged (no conflict).
    - A path only in subtask -> added.
    - A path in both with different hash -> conflict.
    """
    parent_paths = set(parent_versions.keys())
    subtask_paths = set(subtask_versions.keys())

    shared = parent_paths & subtask_paths
    added = list(subtask_paths - parent_paths)
    unchanged = list(parent_paths - subtask_paths)

    conflicts = [
        p for p in shared
        if parent_versions[p] != subtask_versions[p]
    ]

    if conflicts:
        outcome = MergeOutcome.CONFLICTING
        detail = f"Conflicts in {len(conflicts)} artifact(s): {conflicts}"
    elif added:
        outcome = MergeOutcome.ADDITIVE
        detail = f"Subtask added {len(added)} artifact(s) without conflict."
    else:
        outcome = MergeOutcome.CLEAN
        detail = "No artifacts changed or added."

    return MergeResult(
        outcome=outcome,
        conflicts=conflicts,
        added=added,
        unchanged=unchanged,
        detail=detail,
    )