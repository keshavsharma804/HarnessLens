"""
Evolving memory for the control plane.

Stores natural-language lessons learned from failures and successes.
Each lesson has a fitness score that updates based on whether the memory
predicted the outcome correctly.

Design rationale (grounded in FORGE, ACM CAIS 2026):
- Memory evolves without weight updates. Lessons are stored, retrieved,
  and pruned based on observed usefulness.
- Fitness = (successful uses - unsuccessful uses) / total uses.
- Pruning removes memory entries whose fitness drops below threshold
  after sufficient uses. This prevents stale lessons from polluting
  future routing decisions.
- Memory is persisted to SQLite (reusing the collector's database).
- Retrieval is keyword-based over task_type and context_signature.
  Embeddings would be stronger but require a model dependency. The
  architecture allows swapping in embeddings later.
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


DB_PATH = Path("data/traces.db")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    memory_id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    harness_id TEXT NOT NULL,
    context_signature TEXT NOT NULL,
    outcome TEXT NOT NULL,
    lesson TEXT NOT NULL,
    fitness REAL NOT NULL DEFAULT 0.0,
    successful_uses INTEGER NOT NULL DEFAULT 0,
    unsuccessful_uses INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_used_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_memory_task ON memory(task_type);
CREATE INDEX IF NOT EXISTS idx_memory_harness ON memory(harness_id);
CREATE INDEX IF NOT EXISTS idx_memory_fitness ON memory(fitness);
"""


@dataclass
class MemoryEntry:
    memory_id: str
    task_type: str
    harness_id: str
    context_signature: str
    outcome: str           # "success" | "failure"
    lesson: str
    fitness: float = 0.0
    successful_uses: int = 0
    unsuccessful_uses: int = 0
    created_at: str = ""
    last_used_at: Optional[str] = None

    @property
    def total_uses(self) -> int:
        return self.successful_uses + self.unsuccessful_uses


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_SCHEMA)
    return conn


class EvolvingMemory:
    """
    Persistent memory with fitness-based pruning.

    Usage:
        mem = EvolvingMemory()
        mem.write(task_type="code_modification", harness_id="easyloops",
                  context_signature="tool=analyze", outcome="failure",
                  lesson="After analyze, always verify artifact before writing.")
        lessons = mem.retrieve(task_type="code_modification",
                               context_signature="tool=analyze")
    """

    def __init__(self, db_path: Optional[Path] = None):
        global DB_PATH
        if db_path is not None:
            DB_PATH = db_path
        self.prune_threshold = -0.3
        self.min_uses_before_prune = 5

    # --- Write ---

    def write(
        self,
        task_type: str,
        harness_id: str,
        context_signature: str,
        outcome: str,
        lesson: str,
    ) -> MemoryEntry:
        """Write a new memory entry. Deduplicates by lesson text within task_type."""
        if outcome not in ("success", "failure"):
            raise ValueError(f"Invalid outcome: {outcome}")

        conn = _connect()
        now = datetime.now(timezone.utc).isoformat()
        mem_id = None

        try:
            with conn:
                # Deduplicate: if the exact lesson already exists for this task+harness,
                # update its outcome counts instead of creating a new entry.
                existing = conn.execute(
                    """
                    SELECT memory_id, successful_uses, unsuccessful_uses
                    FROM memory
                    WHERE task_type = ? AND harness_id = ? AND lesson = ?
                    """,
                    (task_type, harness_id, lesson),
                ).fetchone()

                if existing:
                    mem_id, s, u = existing
                    if outcome == "success":
                        s += 1
                    else:
                        u += 1
                    fitness = (s - u) / (s + u) if (s + u) > 0 else 0.0
                    conn.execute(
                        """
                        UPDATE memory
                        SET successful_uses = ?, unsuccessful_uses = ?,
                            fitness = ?, last_used_at = ?
                        WHERE memory_id = ?
                        """,
                        (s, u, fitness, now, mem_id),
                    )
                else:
                    mem_id = f"mem-{uuid.uuid4().hex[:8]}"
                    s = 1 if outcome == "success" else 0
                    u = 1 if outcome == "failure" else 0
                    fitness = (s - u) / (s + u)
                    conn.execute(
                        """
                        INSERT INTO memory (
                            memory_id, task_type, harness_id, context_signature,
                            outcome, lesson, fitness, successful_uses,
                            unsuccessful_uses, created_at, last_used_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            mem_id, task_type, harness_id, context_signature,
                            outcome, lesson, fitness, s, u, now, now,
                        ),
                    )
        finally:
            conn.close()

        return self._load(mem_id)

    def _load(self, memory_id: str) -> MemoryEntry:
        conn = _connect()
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM memory WHERE memory_id = ?", (memory_id,)
        ).fetchone()
        conn.close()
        if not row:
            raise ValueError(f"Memory not found: {memory_id}")
        return MemoryEntry(**dict(row))

    # --- Retrieve ---

    def retrieve(
        self,
        task_type: str,
        context_signature: str = "",
        top_k: int = 5,
        min_fitness: float = -1.0,
    ) -> list[MemoryEntry]:
        """
        Retrieve relevant lessons for a task.

        Ranking: exact task_type matches first, then substring match on
        context_signature, ranked by fitness descending. Memories below
        min_fitness are excluded.
        """
        conn = _connect()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM memory
            WHERE task_type = ? AND fitness >= ?
            ORDER BY fitness DESC
            LIMIT ?
            """,
            (task_type, min_fitness, top_k * 3),
        ).fetchall()
        conn.close()

        entries = [MemoryEntry(**dict(r)) for r in rows]

        # Boost entries whose context_signature overlaps with the query.
        if context_signature:
            qparts = set(context_signature.split("|"))
            entries.sort(
                key=lambda e: (
                    len(qparts & set(e.context_signature.split("|"))),
                    e.fitness,
                ),
                reverse=True,
            )

        return entries[:top_k]

    # --- Fitness update ---

    def update_fitness(self, memory_id: str, success: bool) -> MemoryEntry:
        """
        Record that a memory was used and the outcome was success or failure.
        Fitness is recomputed.
        """
        conn = _connect()
        try:
            with conn:
                row = conn.execute(
                    "SELECT successful_uses, unsuccessful_uses FROM memory WHERE memory_id = ?",
                    (memory_id,),
                ).fetchone()
                if not row:
                    raise ValueError(f"Memory not found: {memory_id}")

                s, u = row
                if success:
                    s += 1
                else:
                    u += 1
                total = s + u
                fitness = (s - u) / total if total > 0 else 0.0
                now = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    """
                    UPDATE memory
                    SET successful_uses = ?, unsuccessful_uses = ?,
                        fitness = ?, last_used_at = ?
                    WHERE memory_id = ?
                    """,
                    (s, u, fitness, now, memory_id),
                )
        finally:
            conn.close()

        return self._load(memory_id)

    # --- Prune ---

    def prune(self) -> list[MemoryEntry]:
        """
        Remove memory entries whose fitness is below threshold AND
        have been used at least min_uses_before_prune times.

        Returns the list of pruned entries.
        """
        conn = _connect()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM memory
            WHERE fitness < ?
              AND (successful_uses + unsuccessful_uses) >= ?
            """,
            (self.prune_threshold, self.min_uses_before_prune),
        ).fetchall()
        entries = [MemoryEntry(**dict(r)) for r in rows]

        if entries:
            ids = [e.memory_id for e in entries]
            placeholders = ",".join("?" * len(ids))
            with conn:
                conn.execute(
                    f"DELETE FROM memory WHERE memory_id IN ({placeholders})",
                    ids,
                )
        conn.close()
        return entries

    # --- Observability ---

    def snapshot(self) -> dict:
        conn = _connect()
        total = conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
        by_outcome = dict(conn.execute(
            "SELECT outcome, COUNT(*) FROM memory GROUP BY outcome"
        ).fetchall())
        avg_fitness = conn.execute(
            "SELECT AVG(fitness) FROM memory"
        ).fetchone()[0]
        conn.close()
        return {
            "total": total,
            "by_outcome": by_outcome,
            "avg_fitness": round(avg_fitness, 3) if avg_fitness is not None else 0.0,
        }

    def all_entries(self) -> list[MemoryEntry]:
        conn = _connect()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM memory ORDER BY fitness DESC"
        ).fetchall()
        conn.close()
        return [MemoryEntry(**dict(r)) for r in rows]