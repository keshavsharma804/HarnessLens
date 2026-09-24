"""
Real SWE-bench smoke test for HarnessLens.

Runs ONE real task from SWE-bench Lite:
1. Loads the task from HuggingFace
2. Clones the repo at the base commit
3. Runs OpenHands against the problem statement
4. Saves the patch in SWE-bench prediction format
5. Grades it with the official evaluation harness

Usage:
    python -m scripts.run_real_task
    python -m scripts.run_real_task --task-index 0 --model gpt-5
"""

import sys
import json
import subprocess
import argparse
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datasets import load_dataset

from adapters.openhands_adapter import OpenHandsAdapter
from app.collector import insert_events, rollup_run, insert_run_summary


WORKSPACE = Path("workspace").resolve()
PREDICTIONS_DIR = Path("predictions").resolve()
PREDICTIONS_DIR.mkdir(exist_ok=True)


def load_task(task_index: int = 0):
    """Load a single task from SWE-bench Lite."""
    ds = load_dataset("SWE-bench/SWE-bench_Lite", split="test")
    task = ds[task_index]
    return task


def prepare_workspace(task):
    """Clone the repo at the base commit."""
    if WORKSPACE.exists():
        shutil.rmtree(WORKSPACE)
    WORKSPACE.mkdir(parents=True)

    repo = task["repo"]
    base_commit = task["base_commit"]

    print(f"  Cloning {repo} at {base_commit[:8]}...")
    subprocess.run(
        ["git", "clone", f"https://github.com/{repo}.git", str(WORKSPACE)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", base_commit],
        cwd=str(WORKSPACE),
        check=True,
        capture_output=True,
    )
    return WORKSPACE


def save_prediction(instance_id: str, model_name: str, patch: str):
    """Save a single prediction in SWE-bench JSONL format."""
    out_path = PREDICTIONS_DIR / f"pred_{instance_id}.jsonl"
    with open(out_path, "w") as f:
        f.write(json.dumps({
            "instance_id": instance_id,
            "model_name_or_path": model_name,
            "model_patch": patch,
        }) + "\n")
    return out_path


def grade_predictions(predictions_path: Path, instance_id: str):
    """Run the official SWE-bench evaluation harness."""
    print("\n  Grading with SWE-bench harness (requires Docker)...")
    result = subprocess.run(
        [
            sys.executable, "-m", "swebench.harness.run_evaluation",
            "--dataset_name", "princeton-nlp/SWE-bench_Lite",
            "--predictions_path", str(predictions_path),
            "--instance_ids", instance_id,
            "--max_workers", "1",
            "--run_id", f"harnesslens-{instance_id}",
        ],
        capture_output=True,
        text=True,
    )
    print(result.stdout[-2000:] if result.stdout else "(no stdout)")
    if result.stderr:
        print("STDERR:", result.stderr[-1000:])
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-index", type=int, default=0)
    parser.add_argument("--model", type=str, default="gpt-5")
    args = parser.parse_args()

    print("\n=== Loading task ===")
    task = load_task(args.task_index)
    instance_id = task["instance_id"]
    print(f"  Instance: {instance_id}")
    print(f"  Repo: {task['repo']}")
    print(f"  Problem length: {len(task['problem_statement'])} chars")

    print("\n=== Preparing workspace ===")
    prepare_workspace(task)

    print("\n=== Running OpenHands ===")
    adapter = OpenHandsAdapter(
        model=args.model,
        harness_id=f"openhands-{args.model}",
        workspace_dir=str(WORKSPACE),
    )

    events, patch = adapter.run(
        task=task["problem_statement"],
        instance_id=instance_id,
    )

    print(f"  Steps: {len([e for e in events if e.event_type == 'tool_called'])}")
    print(f"  Patch length: {len(patch)} chars")

    # Persist trace
    insert_events(events)
    summary = rollup_run(events)
    insert_run_summary(summary)

    if not patch.strip():
        print("\n  WARNING: No patch produced. The agent may not have modified anything.")
        print("  Check the workspace manually: cd workspace && git diff")
        return

    # Save prediction
    pred_path = save_prediction(instance_id, adapter.harness_id, patch)
    print(f"\n  Prediction saved: {pred_path}")

    # Grade
    grade_predictions(pred_path, instance_id)

    print("\n=== Done ===")
    print(f"  Check results in: logs/run_evaluation/harnesslens-{instance_id}/")


if __name__ == "__main__":
    main()