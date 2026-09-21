"""Tests for the memory retriever."""

import tempfile
from pathlib import Path

from app.evolving_memory import EvolvingMemory
from app.memory_retriever import MemoryRetriever
from app.schema import TraceEvent, EventType


def _mem():
    tmp = Path(tempfile.mkdtemp()) / "test.db"
    return EvolvingMemory(db_path=tmp)


def _template():
    return TraceEvent(
        run_id="r1", harness_id="h1",
        event_index=0, turn_index=0, loop_step=5,
        event_type=EventType.TOOL_CALLED,
        budget_consumed_cents=5.0,
    )


def test_retrieve_for_step_returns_lessons():
    mem = _mem()
    mem.write("code_modification", "h1", "tool=analyze", "success", "Lesson A")
    mem.write("code_modification", "h1", "tool=analyze", "success", "Lesson B")
    retriever = MemoryRetriever(mem)
    result = retriever.retrieve_for_step(
        task_type="code_modification",
        context_signature="tool=analyze",
        template=_template(),
    )
    assert len(result.lessons) == 2
    assert len(result.events) == 1
    assert result.events[0].event_type in (EventType.MEMORY_RETRIEVED, "memory_retrieved")


def test_record_outcome_updates_fitness():
    mem = _mem()
    entry = mem.write("t", "h", "ctx", "failure", "Lesson X")
    retriever = MemoryRetriever(mem)
    events = retriever.record_outcome([entry], success=True, template=_template())
    assert len(events) == 1
    assert events[0].event_type in (EventType.MEMORY_FITNESS_UPDATED, "memory_fitness_updated")
    # Fitness should now be 0.0 (1 success, 1 failure).
    assert mem.all_entries()[0].fitness == 0.0


def test_record_outcome_multiple_entries():
    mem = _mem()
    e1 = mem.write("t", "h", "ctx", "failure", "A")
    e2 = mem.write("t", "h", "ctx", "failure", "B")
    retriever = MemoryRetriever(mem)
    events = retriever.record_outcome([e1, e2], success=True, template=_template())
    assert len(events) == 2


def test_empty_retrieval_emits_event():
    mem = _mem()
    retriever = MemoryRetriever(mem)
    result = retriever.retrieve_for_step(
        task_type="nonexistent",
        context_signature="",
        template=_template(),
    )
    assert result.lessons == []
    assert len(result.events) == 1