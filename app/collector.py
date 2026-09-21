"""
SQLite-backed sink for TraceEvents.

Why SQLite:
- Zero-ops. No server to run. Ships with Python.
- Good enough for thousands of runs.
- Easy to demonstrate: query it from the dashboard, dump to Parquet later.

Design decision: we store raw events AND a rollup table.
- Raw events → debugging and replay.
- Rollup (HarnessRunSummary) → fleet-level queries (Phase 4 learning).
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Iterable
from app.schema import TraceEvent, HarnessRunSummary


DB_PATH = Path("data/traces.db")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    harness_id TEXT NOT NULL,
    event_index INTEGER NOT NULL,
    turn_index INTEGER NOT NULL,
    loop_step INTEGER NOT NULL,
    last_tool_called TEXT,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    latency_ms INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_cents REAL,
    budget_consumed_cents REAL NOT NULL,
    verification_status TEXT NOT NULL,
    error TEXT,
    raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id);
CREATE INDEX IF NOT EXISTS idx_events_harness ON events(harness_id);
CREATE INDEX IF NOT EXISTS idx_events_loop_step ON events(harness_id, loop_step);

CREATE TABLE IF NOT EXISTS run_summaries (
    run_id TEXT PRIMARY KEY,
    harness_id TEXT NOT NULL,
    total_steps INTEGER NOT NULL,
    total_cost_cents REAL NOT NULL,
    total_latency_ms INTEGER NOT NULL,
    final_status TEXT NOT NULL,
    verification_passed INTEGER NOT NULL,
    failure_reason TEXT
);
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_SCHEMA)
    return conn


def insert_events(events: Iterable[TraceEvent]) -> int:
    """Insert events. Returns number of rows written."""
    conn = _connect()
    count = 0
    with conn:
        for e in events:
            conn.execute(
                """
                INSERT INTO events (
                    run_id, harness_id, event_index, turn_index, loop_step,
                    last_tool_called, event_type, timestamp, latency_ms,
                    input_tokens, output_tokens, cost_cents,
                    budget_consumed_cents, verification_status, error, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    e.run_id, e.harness_id, e.event_index, e.turn_index,
                    e.loop_step, e.last_tool_called, e.event_type,
                    e.timestamp.isoformat(), e.latency_ms,
                    e.input_tokens, e.output_tokens, e.cost_cents,
                    e.budget_consumed_cents, e.verification_status,
                    e.error, json.dumps(e.model_dump(mode="json")),
                ),
            )
            count += 1
    conn.close()
    return count


def rollup_run(events: list[TraceEvent]) -> HarnessRunSummary:
    if not events:
        raise ValueError("Cannot roll up empty run")

    first = events[0]
    last = events[-1]

    total_cost = max((e.budget_consumed_cents or 0.0) for e in events)
    total_latency = sum(e.latency_ms or 0 for e in events)

    explicit_failed = any(e.verification_status == "failed" for e in events)
    explicit_passed = any(e.verification_status == "passed" for e in events)

    if explicit_failed:
        verification_passed = False
    elif explicit_passed:
        verification_passed = True
    else:
        verification_passed = True  # no verifier ran; trust harness's own success

    last_type = last.event_type if isinstance(last.event_type, str) else last.event_type.value
    if last_type == "run_completed":
        final_status = "success" if verification_passed else "failed"
    elif last_type == "run_failed":
        final_status = "failed"
    else:
        final_status = "incomplete"

    return HarnessRunSummary(
        run_id=first.run_id,
        harness_id=first.harness_id,
        total_steps=len([e for e in events if e.event_type == "tool_called"]),
        total_cost_cents=total_cost,
        total_latency_ms=total_latency,
        final_status=final_status,
        verification_passed=verification_passed,
        failure_reason=last.error,
    )

def insert_run_summary(summary: HarnessRunSummary) -> None:
    conn = _connect()
    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO run_summaries (
                run_id, harness_id, total_steps, total_cost_cents,
                total_latency_ms, final_status, verification_passed, failure_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary.run_id, summary.harness_id, summary.total_steps,
                summary.total_cost_cents, summary.total_latency_ms,
                summary.final_status, int(summary.verification_passed),
                summary.failure_reason,
            ),
        )
    conn.close()


def query_recent_runs(limit: int = 20) -> list[dict]:
    """For the dashboard. Returns recent run summaries as dicts."""
    conn = _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM run_summaries ORDER BY rowid DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]