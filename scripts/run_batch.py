"""
Run N SWE-bench Lite tasks sequentially.

Tracks real cost, token usage, patch production, and pass/fail per task.
Writes a summary JSON to predictions/batch_summary.json.

Usage:
    python -m scripts.run_batch --start 0 --count 5 --model gpt-5
"""

import sys
import json
import time
import argparse
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datasets import load_dataset

from adapters.openhands_adapter import OpenHandsAdapter
from app.collector import insert_events, rollup_run, insert_run_summary


WORKSPACE = Path("workspace").resolve()
PREDICTIONS_DIR = Path("predictions").resolve()
PREDICTIONS_DIR.mkdir(exist_ok=True)


def load_tasks(start: int, count: int):
    ds = load_dataset("SWE-bench/SWE-bench_Lite", split="test")
    end = min(start + count, len(ds))
    return [(i, ds[i]) for i in range(start, end)]


def prepare_workspace(task):
    """
    Clone the repo into a fresh, unique directory.

    Why unique: Windows locks .git folders from deleted workspaces.
    shutil.rmtree(ignore_errors=True) leaves residue, and `git clone`
    fails with exit 128 if the target is not empty. A unique dir per
    task avoids the problem entirely.
    """
    import tempfile

    workspace_path = Path(tempfile.mkdtemp(
        prefix=f"swebench_{task['instance_id'].replace('__', '_')}_"
    ))

    # Clone with depth 1 for speed
    clone_result = subprocess.run(
        ["git", "clone", "--filter=blob:none", "--no-checkout",
         f"https://github.com/{task['repo']}.git", str(workspace_path)],
        capture_output=True,
        text=True,
    )
    if clone_result.returncode != 0:
        raise RuntimeError(
            f"git clone failed: {clone_result.stderr.strip() or clone_result.stdout.strip()}"
        )

    # Fetch and checkout the specific commit
    subprocess.run(
        ["git", "fetch", "--depth", "1", "origin", task["base_commit"]],
        cwd=str(workspace_path),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", task["base_commit"]],
        cwd=str(workspace_path),
        check=True,
        capture_output=True,
    )
    return workspace_path

def save_prediction(instance_id: str, model_name: str, patch: str) -> Path:
    out_path = PREDICTIONS_DIR / f"pred_{instance_id}.jsonl"
    with open(out_path, "w") as f:
        f.write(json.dumps({
            "instance_id": instance_id,
            "model_name_or_path": model_name,
            "model_patch": patch,
        }) + "\n")
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--model", type=str, default="gpt-5")
    args = parser.parse_args()

    tasks = load_tasks(args.start, args.count)
    print(f"\n=== Running {len(tasks)} tasks from index {args.start} ===\n")

    summary = {
        "model": args.model,
        "start_index": args.start,
        "count": args.count,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "tasks": [],
        "totals": {
            "cost_cents": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "patches_produced": 0,
            "total_seconds": 0.0,
        },
    }

    for idx, task in tasks:
        instance_id = task["instance_id"]
        print(f"\n[{idx}] {instance_id}")
        print(f"     repo: {task['repo']}")

        task_start = time.time()

        try:
            workspace_path = prepare_workspace(task)
        except Exception as e:
            print(f"     ERROR preparing workspace: {e}")
            summary["tasks"].append({
                "index": idx,
                "instance_id": instance_id,
                "error": f"workspace: {e}",
            })
            continue

        adapter = OpenHandsAdapter(
            model=args.model,
            harness_id=f"openhands-{args.model}",
            workspace_dir=str(workspace_path),
        )

        try:
            events, patch = adapter.run(
                task=(
                    task["problem_statement"]
                    + "\n\n---\n\n"
                    + "IMPORTANT: Your goal is to produce a git patch that fixes this issue. "
                    + "Modify the source files directly. Do not just explain the fix or diagnose the bug. "
                    + "Do not install dependencies or run the full test suite — just make the code change and finish. "
                    + "The patch will be extracted with `git diff HEAD`."
                ),
                instance_id=instance_id,
            )
        except Exception as e:
            print(f"     ERROR running agent: {e}")
            summary["tasks"].append({
                "index": idx,
                "instance_id": instance_id,
                "error": f"agent: {e}",
            })
            continue

        duration = time.time() - task_start

        # Extract metrics from events
        cost_cents = max((e.budget_consumed_cents or 0.0) for e in events) if events else 0.0
        input_tokens = sum(e.input_tokens or 0 for e in events)
        output_tokens = sum(e.output_tokens or 0 for e in events)
        patch_length = len(patch)
        patch_produced = patch_length > 0

        # Persist trace
        try:
            insert_events(events)
            summary_obj = rollup_run(events)
            insert_run_summary(summary_obj)
        except Exception as e:
            print(f"     (trace persist warning: {e})")

        # Save prediction only if a patch was produced
        pred_path = None
        if patch_produced:
            pred_path = save_prediction(instance_id, adapter.harness_id, patch)

        print(f"     cost: ${cost_cents/100:.4f}  "
              f"tokens: {input_tokens}+{output_tokens}  "
              f"patch: {'YES' if patch_produced else 'NO'}  "
              f"time: {duration:.0f}s")

        summary["tasks"].append({
            "index": idx,
            "instance_id": instance_id,
            "repo": task["repo"],
            "cost_cents": cost_cents,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "patch_produced": patch_produced,
            "patch_length": patch_length,
            "prediction_file": str(pred_path) if pred_path else None,
            "duration_seconds": duration,
        })

        summary["totals"]["cost_cents"] += cost_cents
        summary["totals"]["input_tokens"] += input_tokens
        summary["totals"]["output_tokens"] += output_tokens
        summary["totals"]["total_seconds"] += duration
        if patch_produced:
            summary["totals"]["patches_produced"] += 1

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()

    # Print final summary
    t = summary["totals"]
    print("\n" + "=" * 60)
    print("BATCH SUMMARY")
    print("=" * 60)
    print(f"  Tasks run:         {len(tasks)}")
    print(f"  Patches produced:  {t['patches_produced']} / {len(tasks)}")
    print(f"  Total cost:        ${t['cost_cents']/100:.4f}")
    print(f"  Input tokens:      {t['input_tokens']:,}")
    print(f"  Output tokens:     {t['output_tokens']:,}")
    print(f"  Wall time:         {t['total_seconds']:.0f}s")

    out_path = PREDICTIONS_DIR / "batch_summary.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n  Summary saved: {out_path}")


if __name__ == "__main__":
    main()