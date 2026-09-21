import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.failure_classifier import FailureClassifier
from app.repair_library import RepairLibrary
from app.repair_executor import RepairExecutor
from app.schema import TraceEvent, EventType
from app.trajectory_diagnostics import TrajectoryDigest


def _digest(reason, last_tool="analyze", preceding=None):
    return TrajectoryDigest(
        run_id="demo-run",
        harness_id="easyloops",
        total_steps=7,
        failed_at_step=7,
        last_valid_tool=last_tool,
        last_valid_step=6,
        divergence_reason=reason,
        preceding_tools=preceding or ["read_file", "analyze", "analyze"],
        cost_so_far_cents=10.0,
        salvageable=True,
    )


def main():
    classifier = FailureClassifier()
    library = RepairLibrary("policies/repair_rules.yaml")

    # Simulated handlers: first attempt fails, second succeeds.
    def retry_handler(action, ctx):
        return (False, "retry timed out again")

    def switch_handler(action, ctx):
        return (True, f"switched to {action.params.get('target', 'easyloops')}")

    def escalate_handler(action, ctx):
        return (True, "escalated to human")

    def refresh_handler(action, ctx):
        return (True, "context refreshed")

    def rerun_handler(action, ctx):
        return (True, "rerun with verifier passed")

    handlers = {
        "retry_with_backoff": retry_handler,
        "switch_harness": switch_handler,
        "escalate": escalate_handler,
        "inject_context": refresh_handler,
        "rerun_with_verifier": rerun_handler,
    }

    executor = RepairExecutor(library, handlers)
    template = TraceEvent(
        run_id="demo-run", harness_id="easyloops",
        event_index=0, turn_index=0, loop_step=7,
        event_type=EventType.RUN_FAILED,
        budget_consumed_cents=10.0,
        error="step 7 timed out",
    )

    print("\n=== Scenario 1: Timeout failure ===\n")
    sig = classifier.classify(_digest("step 7 timed out"))
    print(f"  Classified as: {sig.failure_class.value}")
    print(f"  Signature: {sig.signature_id}")
    print(f"  Computable: {sig.computable}")
    outcome = executor.repair(sig, template)
    print(f"  Repair attempted: {outcome.attempted}")
    print(f"  Action used: {outcome.action_id}")
    print(f"  Succeeded: {outcome.succeeded}")
    print(f"  Detail: {outcome.detail}")

    print("\n=== Scenario 2: Loop detected ===\n")
    sig = classifier.classify(_digest(
        "no progress",
        last_tool="read_file",
        preceding=["read_file"] * 5,
    ))
    print(f"  Classified as: {sig.failure_class.value}")
    print(f"  Signature: {sig.signature_id}")
    outcome = executor.repair(sig, template)
    print(f"  Action used: {outcome.action_id}")
    print(f"  Succeeded: {outcome.succeeded}")

    print("\n=== Scenario 3: Silent failure ===\n")
    sig = classifier.classify(_digest("expected artifact missing", last_tool="write_file"))
    print(f"  Classified as: {sig.failure_class.value}")
    outcome = executor.repair(sig, template)
    print(f"  Action used: {outcome.action_id}")
    print(f"  Succeeded: {outcome.succeeded}")

    print("\n=== Library success rates ===\n")
    for action_id in ["retry_with_shorter_context", "switch_to_cheaper_harness"]:
        rate = library.success_rate("timeout_after_analyze", action_id)
        print(f"  {action_id}: {rate:.2f}")


if __name__ == "__main__":
    main()