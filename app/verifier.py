"""
Independent verifier.

The harness reports success. We do NOT trust it.

Design rationale:
- Harness-Bench documented "execution-alignment failures" where plausible
  reasoning decouples from tool feedback. The harness can report "done"
  while the artifact is wrong.
- The verifier runs a SEPARATE check (schema, artifact presence, tool result
  integrity) and returns its own verdict.
- The verifier's verdict, not the harness's, decides whether the run is marked
  as verified-pass or verified-fail.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class VerificationResult:
    verdict: Verdict
    detail: str
    checks_run: list[str]


class Verifier:
    """
    Base verifier. Extend this per task type.

    The default implementation checks:
    1. The harness produced a non-empty result.
    2. Any artifact paths mentioned in tool_arguments exist.
    3. No error is present in the final event.
    """

    def __init__(self, artifact_root: Optional[Path] = None):
        self.artifact_root = artifact_root or Path(".")

    def verify(self, events: list) -> VerificationResult:
        checks: list[str] = []
        failures: list[str] = []

        # Check 1: Non-empty result.
        checks.append("non_empty_result")
        if not events:
            return VerificationResult(
                verdict=Verdict.FAIL,
                detail="No events to verify.",
                checks_run=checks,
            )

        # Check 2: Final event is not an error.
        checks.append("no_error_in_final_event")
        last = events[-1]
        if last.error:
            failures.append(f"Final event has error: {last.error}")

        # Check 3: Artifact paths mentioned in tool_arguments must exist.
        checks.append("artifacts_exist")
        for e in events:
            if e.event_type == "tool_called" and e.tool_arguments:
                path_str = e.tool_arguments.get("path")
                if path_str:
                    path = Path(path_str)
                    # Only fail if the file SHOULD exist (e.g., write_file).
                    if e.last_tool_called == "write_file" and not path.exists():
                        failures.append(f"Expected artifact missing: {path}")

        if failures:
            return VerificationResult(
                verdict=Verdict.FAIL,
                detail="; ".join(failures),
                checks_run=checks,
            )

        return VerificationResult(
            verdict=Verdict.PASS,
            detail="All checks passed.",
            checks_run=checks,
        )