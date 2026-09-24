"""
Test 3: Latency under concurrent load.

Runs N real tasks sequentially, then N tasks in parallel.
Reports p50/p95 latency and total wall time for each mode.

Proves: concurrency overlaps work without inflating per-task latency.

Usage:
    python -m scripts.run_concurrent_test
"""

import sys
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.openhands_adapter import OpenHandsAdapter


FIXTURE = Path("local_tests/fixture_01").resolve()
N_TASKS = 5
MODEL = "gpt-5-nano"


def prepare_workspace() -> Path:
    """Create a fresh workspace per task."""
    workspace = Path(tempfile.mkdtemp(prefix="concurrent_"))
    for name in ("buggy.py", "test_buggy.py", "INSTRUCTIONS.md"):
        shutil.copy(FIXTURE / name, workspace / name)
    subprocess.run(["git", "init"], cwd=workspace, capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=workspace, capture_output=True, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t.com", "-c", "user.name=t",
         "commit", "-m", "initial"],
        cwd=workspace, capture_output=True, check=True,
    )
    return workspace


def run_one_task(task_id: int) -> dict:
    """Run one full task. Returns timing and result."""
    workspace = prepare_workspace()
    task_text = (FIXTURE / "INSTRUCTIONS.md").read_text()

    adapter = OpenHandsAdapter(
        model=MODEL,
        harness_id=f"concurrent-{task_id}",
        workspace_dir=str(workspace),
    )

    start = time.time()
    try:
        events, patch = adapter.run(task_text, f"concurrent-{task_id}")
        error = None
    except Exception as e:
        events, patch = [], ""
        error = f"{type(e).__name__}: {e}"
    duration = time.time() - start

    # Verify the fix
    if error is None:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "test_buggy.py", "-q"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=60,
        )
        passed = result.returncode == 0
    else:
        passed = False

    cost_cents = max((e.budget_consumed_cents or 0.0) for e in events) if events else 0.0

    return {
        "task_id": task_id,
        "duration": duration,
        "passed": passed,
        "cost_cents": cost_cents,
        "patch_length": len(patch),
        "error": error,
    }


def percentile(values: list, p: int) -> float:
    """Simple percentile without numpy."""
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[int(k)]
    return s[f] + (s[c] - s[f]) * (k - f)


def main():
    print(f"\n=== Test 3: Latency under concurrent load ===")
    print(f"    Model: {MODEL}")
    print(f"    Tasks per mode: {N_TASKS}\n")

    # --- Sequential ---
    print("--- Sequential mode ---\n")
    seq_start = time.time()
    seq_results = []
    for i in range(N_TASKS):
        r = run_one_task(i)
        seq_results.append(r)
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  Task {i+1}/{N_TASKS}: {r['duration']:.1f}s  "
              f"{status}  ${r['cost_cents']/100:.4f}")
    seq_wall = time.time() - seq_start
    seq_durations = [r["duration"] for r in seq_results]

    # --- Concurrent ---
    print(f"\n--- Concurrent mode (parallelism={N_TASKS}) ---\n")
    con_start = time.time()
    con_results = []
    with ThreadPoolExecutor(max_workers=N_TASKS) as pool:
        futures = {pool.submit(run_one_task, i + 100): i for i in range(N_TASKS)}
        for future in as_completed(futures):
            r = future.result()
            con_results.append(r)
            status = "PASS" if r["passed"] else "FAIL"
            print(f"  Task {r['task_id']}: {r['duration']:.1f}s  "
                  f"{status}  ${r['cost_cents']/100:.4f}")
    con_wall = time.time() - con_start
    con_durations = [r["duration"] for r in con_results]

    # --- Summary ---
    print("\n" + "=" * 60)
    print("LATENCY COMPARISON")
    print("=" * 60)

    def row(label, durations, wall, results):
        passes = sum(1 for r in results if r["passed"])
        total_cost = sum(r["cost_cents"] for r in results) / 100
        return (
            f"{label:<12} "
            f"wall={wall:>6.1f}s  "
            f"p50={percentile(durations, 50):>5.1f}s  "
            f"p95={percentile(durations, 95):>5.1f}s  "
            f"pass={passes}/{len(results)}  "
            f"cost=${total_cost:.4f}"
        )

    print(row("Sequential", seq_durations, seq_wall, seq_results))
    print(row("Concurrent", con_durations, con_wall, con_results))

    speedup = seq_wall / con_wall if con_wall > 0 else 0
    print(f"\nWall-time speedup: {speedup:.2f}x")
    print(f"Total cost across both modes: "
          f"${(sum(r['cost_cents'] for r in seq_results) + sum(r['cost_cents'] for r in con_results)) / 100:.4f}")


if __name__ == "__main__":
    main()