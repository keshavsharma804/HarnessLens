"""
Fleet learning.

Reads historical run summaries from SQLite and computes per-harness success
rates. These rates are fed into the router's scoring so that a harness which
has been failing on similar work is automatically de-prioritized.

Design rationale:
- We do NOT retrain any model. We adjust routing weights from observed outcomes.
- The learning is bounded: it can only shift scores by a fixed maximum.
- Cold start: with fewer than N runs, we return a neutral 0.5 prior.
- This is the "capability-matching flywheel" that Agentic Routing describes
  as an open problem — we implement a bounded version here.
"""

from dataclasses import dataclass
from typing import Optional

from app import collector


# How many runs before we trust the observed rate over the neutral prior.
MIN_RUNS_FOR_CONFIDENCE = 3

# The maximum amount learning can shift a harness's score.
# Prevents one bad batch from permanently blacklisting a harness.
MAX_ADJUSTMENT = 0.30


@dataclass
class HarnessStats:
    harness_id: str
    total_runs: int
    successful_runs: int
    success_rate: float
    avg_cost_cents: float
    avg_latency_ms: float
    confidence: float  # 0..1; based on sample size


def compute_harness_stats(harness_id: Optional[str] = None) -> dict[str, HarnessStats]:
    """
    Compute stats for one or all harnesses.

    If harness_id is None, returns stats for all harnesses seen in the DB.
    """
    conn = collector._connect()
    conn.row_factory = None  # tuples

    if harness_id:
        rows = conn.execute(
            """
            SELECT harness_id,
                   COUNT(*) AS total,
                   SUM(CASE WHEN final_status='success' THEN 1 ELSE 0 END) AS successes,
                   AVG(total_cost_cents) AS avg_cost,
                   AVG(total_latency_ms) AS avg_latency
            FROM run_summaries
            WHERE harness_id = ?
            GROUP BY harness_id
            """,
            (harness_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT harness_id,
                   COUNT(*) AS total,
                   SUM(CASE WHEN final_status='success' THEN 1 ELSE 0 END) AS successes,
                   AVG(total_cost_cents) AS avg_cost,
                   AVG(total_latency_ms) AS avg_latency
            FROM run_summaries
            GROUP BY harness_id
            """
        ).fetchall()

    conn.close()

    result: dict[str, HarnessStats] = {}
    for row in rows:
        hid, total, successes, avg_cost, avg_latency = row
        total = total or 0
        successes = successes or 0
        rate = (successes / total) if total > 0 else 0.5
        confidence = min(1.0, total / MIN_RUNS_FOR_CONFIDENCE)
        result[hid] = HarnessStats(
            harness_id=hid,
            total_runs=total,
            successful_runs=successes,
            success_rate=rate,
            avg_cost_cents=float(avg_cost or 0.0),
            avg_latency_ms=float(avg_latency or 0.0),
            confidence=confidence,
        )
    return result


def historical_success_map() -> dict[str, float]:
    """
    Produce a harness_id -> success_rate map for the router.

    Blends observed rate with a neutral 0.5 prior, weighted by confidence.
    Bounds the total adjustment so learning cannot swing decisions wildly.

    Cold start: harnesses with no runs get 0.5 (neutral).
    """
    stats = compute_harness_stats()
    result: dict[str, float] = {}

    for hid, s in stats.items():
        neutral = 0.5
        # Blend prior with observed, weighted by confidence.
        blended = neutral * (1 - s.confidence) + s.success_rate * s.confidence

        # Bound the adjustment from neutral.
        delta = blended - neutral
        delta = max(-MAX_ADJUSTMENT, min(MAX_ADJUSTMENT, delta))
        result[hid] = neutral + delta

    return result