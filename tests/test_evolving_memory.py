"""Tests for the evolving memory store."""

import tempfile
from pathlib import Path

from app.evolving_memory import EvolvingMemory


def _mem():
    tmp = Path(tempfile.mkdtemp()) / "test.db"
    return EvolvingMemory(db_path=tmp)


def test_write_creates_entry():
    mem = _mem()
    entry = mem.write(
        task_type="code_modification",
        harness_id="easyloops",
        context_signature="tool=analyze",
        outcome="failure",
        lesson="After analyze, always verify artifact before writing.",
    )
    assert entry.memory_id.startswith("mem-")
    assert entry.successful_uses == 0
    assert entry.unsuccessful_uses == 1
    assert entry.fitness == -1.0


def test_write_deduplicates_by_lesson():
    mem = _mem()
    mem.write("t", "h", "ctx", "success", "Lesson A")
    entry = mem.write("t", "h", "ctx", "success", "Lesson A")
    assert entry.successful_uses == 2
    assert entry.unsuccessful_uses == 0


def test_retrieve_returns_relevant_lessons():
    mem = _mem()
    mem.write("code_modification", "h1", "tool=analyze", "success", "Lesson A")
    mem.write("data_analysis", "h1", "tool=analyze", "success", "Lesson B")
    results = mem.retrieve(task_type="code_modification")
    assert len(results) == 1
    assert results[0].lesson == "Lesson A"


def test_retrieve_ranks_by_context_overlap():
    mem = _mem()
    mem.write("t", "h", "tool=analyze", "success", "Unrelated lesson")
    mem.write("t", "h", "tool=analyze|lang=python", "success", "Relevant lesson")
    results = mem.retrieve(
        task_type="t", context_signature="tool=analyze|lang=python"
    )
    assert results[0].lesson == "Relevant lesson"


def test_update_fitness_improves_on_success():
    mem = _mem()
    entry = mem.write("t", "h", "ctx", "failure", "Lesson X")
    assert entry.fitness == -1.0
    updated = mem.update_fitness(entry.memory_id, success=True)
    assert updated.fitness == 0.0
    updated = mem.update_fitness(entry.memory_id, success=True)
    assert abs(updated.fitness - 1/3) < 1e-6


def test_update_fitness_worsens_on_failure():
    mem = _mem()
    entry = mem.write("t", "h", "ctx", "success", "Lesson Y")
    updated = mem.update_fitness(entry.memory_id, success=False)
    assert updated.fitness == 0.0
    updated = mem.update_fitness(entry.memory_id, success=False)
    assert abs(updated.fitness - (-1/3)) < 1e-6


def test_prune_removes_low_fitness_after_min_uses():
    mem = _mem()
    mem.min_uses_before_prune = 3
    mem.prune_threshold = -0.3
    entry = mem.write("t", "h", "ctx", "failure", "Bad lesson")
    mem.update_fitness(entry.memory_id, False)
    mem.update_fitness(entry.memory_id, False)
    pruned = mem.prune()
    assert len(pruned) == 1
    assert pruned[0].memory_id == entry.memory_id
    assert mem.all_entries() == []


def test_prune_keeps_healthy_memories():
    mem = _mem()
    mem.min_uses_before_prune = 3
    entry = mem.write("t", "h", "ctx", "success", "Good lesson")
    mem.update_fitness(entry.memory_id, True)
    mem.update_fitness(entry.memory_id, True)
    pruned = mem.prune()
    assert pruned == []


def test_snapshot_summarizes():
    mem = _mem()
    mem.write("t", "h", "ctx", "success", "A")
    mem.write("t", "h", "ctx", "failure", "B")
    snap = mem.snapshot()
    assert snap["total"] == 2
    assert snap["by_outcome"]["success"] == 1
    assert snap["by_outcome"]["failure"] == 1


def test_write_rejects_invalid_outcome():
    import pytest
    mem = _mem()
    with pytest.raises(ValueError, match="Invalid outcome"):
        mem.write("t", "h", "ctx", "maybe", "Lesson")


def test_update_fitness_rejects_unknown_id():
    import pytest
    mem = _mem()
    with pytest.raises(ValueError, match="Memory not found"):
        mem.update_fitness("mem-fake", True)