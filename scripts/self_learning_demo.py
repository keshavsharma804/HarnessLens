import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tempfile
from app.evolving_memory import EvolvingMemory
from app.memory_retriever import MemoryRetriever
from app.schema import TraceEvent, EventType


def _template(step=5):
    return TraceEvent(
        run_id="demo", harness_id="easyloops",
        event_index=0, turn_index=0, loop_step=step,
        event_type=EventType.TOOL_CALLED,
        budget_consumed_cents=5.0,
    )


def main():
    tmp = Path(tempfile.mkdtemp()) / "mem.db"
    mem = EvolvingMemory(db_path=tmp)
    retriever = MemoryRetriever(mem)

    print("\n=== Phase 1: Accumulate lessons from failures ===\n")
    lessons = [
        ("code_modification", "easyloops", "tool=analyze",
         "failure", "After analyze, verify the artifact exists before writing."),
        ("code_modification", "easyloops", "tool=read_file",
         "failure", "Do not loop on read_file; check tool result before retrying."),
        ("code_modification", "researchharness", "tool=write_file",
         "success", "researchharness reliably writes with strict verification."),
        ("data_analysis", "easyloops", "tool=parse",
         "failure", "Validate schema after parse before downstream steps."),
    ]
    for task, harness, ctx, outcome, lesson in lessons:
        entry = mem.write(task, harness, ctx, outcome, lesson)
        print(f"  [{outcome:7s}] {entry.memory_id}: {lesson[:50]}...")

    print("\n=== Phase 2: Simulate usage and fitness updates ===\n")
    # Simulate the "after analyze verify" lesson being used 5 times.
    entries = mem.retrieve("code_modification", context_signature="tool=analyze")
    target = entries[0]
    print(f"  Using memory: {target.memory_id} ({target.lesson[:40]}...)")
    for i in range(4):
        updated = mem.update_fitness(target.memory_id, success=True)
        print(f"    use {i+1}: fitness={updated.fitness:+.2f}  "
              f"({updated.successful_uses} success / "
              f"{updated.unsuccessful_uses} failure)")

    print("\n=== Phase 3: Memory retrieval for a new step ===\n")
    result = retriever.retrieve_for_step(
        task_type="code_modification",
        context_signature="tool=analyze|lang=python",
        template=_template(step=7),
    )
    print(f"  Retrieved {len(result.lessons)} lessons:")
    for lesson in result.lessons:
        print(f"    - {lesson}")

    print("\n=== Phase 4: Prune stale memories ===\n")
    # Add a memory that turns out wrong.
    bad = mem.write("code_modification", "easyloops", "tool=write_file",
                    "failure", "write_file without verification works.")
    for _ in range(5):
        mem.update_fitness(bad.memory_id, success=False)
    pruned = mem.prune()
    print(f"  Pruned {len(pruned)} memories:")
    for p in pruned:
        print(f"    - {p.memory_id}: {p.lesson[:50]}... (fitness {p.fitness:+.2f})")

    print("\n=== Final memory snapshot ===\n")
    for k, v in mem.snapshot().items():
        print(f"  {k}: {v}")

    print("\n=== Remaining memories ranked by fitness ===\n")
    for e in mem.all_entries():
        print(f"  [{e.fitness:+.2f}] {e.task_type:18s} {e.lesson[:50]}...")


if __name__ == "__main__":
    main()