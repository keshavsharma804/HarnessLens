"""
Memory retriever for routing-time integration.

Wraps EvolvingMemory and provides a simple interface the router can call:
given a task type and context, return the relevant lessons as a list of
strings (ready to inject as constraints).

Also emits MEMORY_RETRIEVED and MEMORY_FITNESS_UPDATED events so every
use of memory is auditable.
"""

from dataclasses import dataclass, field

from app.evolving_memory import EvolvingMemory, MemoryEntry
from app.schema import TraceEvent, EventType


@dataclass
class RetrievalResult:
    lessons: list[str]
    entries: list[MemoryEntry]
    events: list[TraceEvent] = field(default_factory=list)


class MemoryRetriever:
    def __init__(self, memory: EvolvingMemory, top_k: int = 5):
        self.memory = memory
        self.top_k = top_k

    def retrieve_for_step(
        self,
        task_type: str,
        context_signature: str,
        template: TraceEvent,
    ) -> RetrievalResult:
        """Retrieve lessons and emit an event for observability."""
        entries = self.memory.retrieve(
            task_type=task_type,
            context_signature=context_signature,
            top_k=self.top_k,
        )
        lessons = [e.lesson for e in entries]

        event = TraceEvent(
            run_id=template.run_id,
            harness_id=template.harness_id,
            event_index=template.event_index + 1,
            turn_index=template.turn_index,
            loop_step=template.loop_step,
            last_tool_called=template.last_tool_called,
            event_type=EventType.MEMORY_RETRIEVED,
            budget_consumed_cents=template.budget_consumed_cents,
            memory_lessons=lessons,
            verification_detail=(
                f"Retrieved {len(lessons)} lessons for "
                f"task_type='{task_type}', context='{context_signature}'."
            ),
        )
        return RetrievalResult(lessons=lessons, entries=entries, events=[event])

    def record_outcome(
        self,
        entries: list[MemoryEntry],
        success: bool,
        template: TraceEvent,
    ) -> list[TraceEvent]:
        """
        After a task completes, update the fitness of every memory entry
        that was retrieved. Emits MEMORY_FITNESS_UPDATED per entry.
        """
        events: list[TraceEvent] = []
        for i, entry in enumerate(entries):
            updated = self.memory.update_fitness(entry.memory_id, success)
            events.append(TraceEvent(
                run_id=template.run_id,
                harness_id=template.harness_id,
                event_index=template.event_index + 2 + i,
                turn_index=template.turn_index,
                loop_step=template.loop_step,
                last_tool_called=template.last_tool_called,
                event_type=EventType.MEMORY_FITNESS_UPDATED,
                budget_consumed_cents=template.budget_consumed_cents,
                memory_lessons=[updated.lesson],
                verification_detail=(
                    f"memory={updated.memory_id} new_fitness="
                    f"{updated.fitness:+.2f}"
                ),
            ))
        return events