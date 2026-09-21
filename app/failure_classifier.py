"""
Failure classification for self-healing.

Reads a TrajectoryDigest and outputs a FailureSignature. The signature
maps to a repair action in the RepairLibrary.

Taxonomy grounded in AutoAgent (June 2026):
- Computable failures: fixable with deterministic code
- Ceiling failures: require escalation

We implement the computable side and flag the rest.
"""

from dataclasses import dataclass
from enum import Enum

from app.trajectory_diagnostics import TrajectoryDigest


class FailureClass(str, Enum):
    TIMEOUT = "timeout"
    SILENT_FAILURE = "silent_failure"
    TOOL_ERROR = "tool_error"
    LOOP_DETECTED = "loop_detected"
    CONTEXT_STALE = "context_stale"
    MERGE_CONFLICT = "merge_conflict"
    UNKNOWN = "unknown"


@dataclass
class FailureSignature:
    failure_class: FailureClass
    signature_id: str           # machine-readable, e.g. "timeout_after_analyze"
    detail: str
    computable: bool             # true if a deterministic repair likely exists


class FailureClassifier:
    """
    Classifies a failure digest into a signature.

    Heuristics (in priority order):
    1. If divergence_reason mentions "timeout" -> TIMEOUT
    2. If reason mentions "artifact" or "missing" -> SILENT_FAILURE
    3. If reason mentions "tool" and "error" -> TOOL_ERROR
    4. If same tool repeats > 3 times -> LOOP_DETECTED
    5. If reason mentions "stale" or "ttl" -> CONTEXT_STALE
    6. If reason mentions "conflict" -> MERGE_CONFLICT
    7. Otherwise UNKNOWN
    """

    LOOP_REPEAT_THRESHOLD = 3

    def classify(self, digest: TrajectoryDigest) -> FailureSignature:
        reason = (digest.divergence_reason or "").lower()
        last_tool = digest.last_valid_tool or "unknown"

        # Priority 1: Loop detection (independent of reason text).
        if self._is_loop(digest):
            return FailureSignature(
                failure_class=FailureClass.LOOP_DETECTED,
                signature_id=f"loop_after_{last_tool}",
                detail=(
                    f"Tool '{last_tool}' repeated "
                    f"{self._count_repeats(digest)} times."
                ),
                computable=True,
            )

        # Priority 2-6: reason-based.
        if "timeout" in reason or "timed out" in reason:
            return FailureSignature(
                failure_class=FailureClass.TIMEOUT,
                signature_id=f"timeout_after_{last_tool}",
                detail=digest.divergence_reason,
                computable=True,
            )

        if "artifact" in reason or "missing" in reason:
            return FailureSignature(
                failure_class=FailureClass.SILENT_FAILURE,
                signature_id=f"silent_failure_after_{last_tool}",
                detail=digest.divergence_reason,
                computable=True,
            )

        if "tool" in reason and "error" in reason:
            return FailureSignature(
                failure_class=FailureClass.TOOL_ERROR,
                signature_id=f"tool_error_on_{last_tool}",
                detail=digest.divergence_reason,
                computable=True,
            )

        if "stale" in reason or "ttl" in reason:
            return FailureSignature(
                failure_class=FailureClass.CONTEXT_STALE,
                signature_id=f"stale_context_before_{last_tool}",
                detail=digest.divergence_reason,
                computable=True,
            )

        if "conflict" in reason:
            return FailureSignature(
                failure_class=FailureClass.MERGE_CONFLICT,
                signature_id=f"merge_conflict_at_{last_tool}",
                detail=digest.divergence_reason,
                computable=True,
            )

        return FailureSignature(
            failure_class=FailureClass.UNKNOWN,
            signature_id="unknown",
            detail=digest.divergence_reason or "no reason provided",
            computable=False,
        )

    def _is_loop(self, digest: TrajectoryDigest) -> bool:
        return self._count_repeats(digest) >= self.LOOP_REPEAT_THRESHOLD

    def _count_repeats(self, digest: TrajectoryDigest) -> int:
        if not digest.preceding_tools:
            return 0
        last = digest.preceding_tools[-1]
        return sum(1 for t in digest.preceding_tools if t == last)