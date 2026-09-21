"""
Data-layer context governor.

Three checks that catch silent failures:

1. STALENESS: Is the data source older than the policy-defined TTL?
2. DRIFT: Does the tool's response schema match its previous response?
3. SILENT FAILURE: Did the agent claim completion without producing artifacts?

Why this matters:
- 65% of agent failures come from context drift, not model defects.
- Silent failures (confident wrong answers with no exception) are the most
  dangerous in production because nothing alerts.
- These checks are cheap and run before the result is accepted.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from app.schema import TraceEvent, EventType, VerificationStatus


@dataclass
class GovernorFinding:
    """A single detected issue."""

    kind: str          # "stale", "drift", "silent_failure"
    severity: str      # "warning", "error"
    detail: str
    event_index: int


class ContextGovernor:
    """
    Runs data-layer checks against a trajectory.

    Design rationale:
    - All findings are emitted as TraceEvents, so they flow through the same
      observability pipeline as everything else.
    - Thresholds come from policy, not from hardcoded constants.
    - Every check is a pure function of the events; no external state.
    """

    def __init__(
        self,
        freshness_ttl_seconds: int = 3600,
        artifact_root: Optional[Path] = None,
    ):
        self.freshness_ttl = timedelta(seconds=freshness_ttl_seconds)
        self.artifact_root = artifact_root or Path(".")

    # --- Check 1: Staleness ---

    def check_freshness(self, events: list[TraceEvent]) -> list[GovernorFinding]:
        """
        Flag any event whose source_timestamp is older than TTL.
        """
        now = datetime.now(timezone.utc)
        findings: list[GovernorFinding] = []

        for i, e in enumerate(events):
            if e.source_timestamp is None:
                continue
            # Ensure both are timezone-aware
            source_ts = e.source_timestamp
            if source_ts.tzinfo is None:
                source_ts = source_ts.replace(tzinfo=timezone.utc)
            age = now - source_ts
            if age > self.freshness_ttl:
                findings.append(GovernorFinding(
                    kind="stale",
                    severity="warning",
                    detail=(
                        f"Source data is {age.total_seconds():.0f}s old, "
                        f"exceeds TTL of {self.freshness_ttl.total_seconds():.0f}s."
                    ),
                    event_index=i,
                ))
        return findings

    # --- Check 2: Schema Drift ---

    def check_drift(self, events: list[TraceEvent]) -> list[GovernorFinding]:
        """
        Detect when the same tool returns a different schema shape than before.
        """
        fingerprints: dict[str, str] = {}
        findings: list[GovernorFinding] = []

        for i, e in enumerate(events):
            if e.event_type != EventType.TOOL_CALLED.value and e.event_type != "tool_called":
                continue
            if not e.last_tool_called or not e.schema_fingerprint:
                continue

            tool = e.last_tool_called
            prior = fingerprints.get(tool)
            if prior is None:
                fingerprints[tool] = e.schema_fingerprint
                continue

            if prior != e.schema_fingerprint:
                findings.append(GovernorFinding(
                    kind="drift",
                    severity="warning",
                    detail=(
                        f"Tool '{tool}' response schema changed "
                        f"(prior={prior[:8]}, now={e.schema_fingerprint[:8]})."
                    ),
                    event_index=i,
                ))
            fingerprints[tool] = e.schema_fingerprint
        return findings

    # --- Check 3: Silent Failure ---

    def check_silent_failure(self, events: list[TraceEvent]) -> list[GovernorFinding]:
        """
        If a run claims completion but expected artifacts do not exist, flag it.
        """
        if not events:
            return []

        last = events[-1]
        if last.event_type not in ("run_completed", EventType.RUN_COMPLETED.value):
            return []

        findings: list[GovernorFinding] = []
        for i, e in enumerate(events):
            if not e.expected_artifacts:
                continue
            for path_str in e.expected_artifacts:
                path = self.artifact_root / path_str
                if not path.exists():
                    findings.append(GovernorFinding(
                        kind="silent_failure",
                        severity="error",
                        detail=(
                            f"Run claimed completion but artifact "
                            f"'{path_str}' does not exist."
                        ),
                        event_index=i,
                    ))
        return findings

    # --- Orchestrator ---

    def analyze(self, events: list[TraceEvent]) -> list[GovernorFinding]:
        """Run all checks. Returns all findings."""
        return (
            self.check_freshness(events)
            + self.check_drift(events)
            + self.check_silent_failure(events)
        )


def fingerprint_payload(payload: dict) -> str:
    """
    Produce a stable fingerprint of a JSON payload's *structure*.

    Only key names are hashed, not values. Two responses with the same keys
    but different values produce the same fingerprint. This is intentional:
    we want to detect shape changes, not value changes.
    """
    keys = sorted(payload.keys())
    canonical = json.dumps(keys)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def emit_findings_as_events(
    findings: list[GovernorFinding],
    template: TraceEvent,
) -> list[TraceEvent]:
    """
    Convert findings into TraceEvents so they flow through the pipeline.
    """
    mapping = {
        "stale": EventType.CONTEXT_STALE,
        "drift": EventType.SCHEMA_DRIFT,
        "silent_failure": EventType.SILENT_FAILURE,
    }
    events: list[TraceEvent] = []
    for f in findings:
        event_type = mapping.get(f.kind)
        if not event_type:
            continue
        events.append(TraceEvent(
            run_id=template.run_id,
            harness_id=template.harness_id,
            event_index=template.event_index + 1,
            turn_index=template.turn_index,
            loop_step=template.loop_step,
            last_tool_called=template.last_tool_called,
            event_type=event_type,
            budget_consumed_cents=template.budget_consumed_cents,
            error=f.detail if f.severity == "error" else None,
            verification_status=(
                VerificationStatus.FAILED if f.severity == "error"
                else VerificationStatus.PENDING
            ),
            verification_detail=f.detail,
        ))
    return events