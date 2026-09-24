"""
Run a local bug-fix task through OpenHands across multiple models.

Fastest real test:
- No repo cloning
- No dependency install
- Grading is: does pytest pass?

Usage:
    python -m scripts.run_local_test
"""

import sys
import subprocess
import shutil
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.openhands_adapter import OpenHandsAdapter
from app.collector import insert_events, rollup_run, insert_run_summary


FIXTURE = Path("local_tests/fixture_01").resolve()
MODELS = ["gpt-5", "gpt-5-nano"]


def prepare_workspace() -> Path:
    """
    Copy the fixture into a fresh unique directory.

    Why unique: Windows locks files in deleted workspaces.
    A unique dir per run avoids FileExistsError and lock issues entirely.
    """
    import tempfile
    workspace = Path(tempfile.mkdtemp(prefix="local_fixture_"))

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


def run_pytest(workspace: Path) -> tuple[bool, str]:
    """Run pytest in the given workspace. Returns (passed, output)."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "test_buggy.py", "-v"],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.returncode == 0, result.stdout + result.stderr


def run_one(model_name: str) -> dict:
    """Run one model against a fresh fixture copy. Returns metrics dict."""
    print(f"\n{'=' * 60}")
    print(f"Running with model: {model_name}")
    print(f"{'=' * 60}")

    workspace_path = prepare_workspace()

    passed_before, _ = run_pytest(workspace_path)
    print(f"  Baseline: {'PASS' if passed_before else 'FAIL'}")

    adapter = OpenHandsAdapter(
        model=model_name,
        harness_id=f"openhands-{model_name}-local",
        workspace_dir=str(workspace_path),
    )

    task = (FIXTURE / "INSTRUCTIONS.md").read_text()
    start = time.time()
    events, patch = adapter.run(task, f"local-{model_name}")
    duration = time.time() - start

    cost_cents = max((e.budget_consumed_cents or 0.0) for e in events) if events else 0.0
    input_tokens = sum(e.input_tokens or 0 for e in events)
    output_tokens = sum(e.output_tokens or 0 for e in events)

    passed_after, _ = run_pytest(workspace_path)

    # Persist trace
    try:
        insert_events(events)
        summary = rollup_run(events)
        insert_run_summary(summary)
    except Exception as e:
        print(f"  (trace persist warning: {e})")

    result = {
        "model": model_name,
        "passed_before": passed_before,
        "passed_after": passed_after,
        "fix_produced": passed_after and not passed_before,
        "cost_cents": cost_cents,
        "duration": duration,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "patch_length": len(patch),
    }

    print(f"  After agent:  {'PASS' if passed_after else 'FAIL'}")
    print(f"  Fix produced: {'YES' if result['fix_produced'] else 'NO'}")
    print(f"  Cost:         ${cost_cents/100:.4f}")
    print(f"  Time:         {duration:.0f}s")
    print(f"  Tokens:       {input_tokens} in, {output_tokens} out")
    return result


def main():
    print("\n=== Local bug-fix task — multi-model comparison ===\n")

    results = []
    for model_name in MODELS:
        try:
            results.append(run_one(model_name))
        except Exception as e:
            print(f"  ERROR running {model_name}: {type(e).__name__}: {e}")
            results.append({
                "model": model_name,
                "error": str(e),
                "fix_produced": False,
                "cost_cents": 0.0,
                "duration": 0.0,
            })

    print("\n" + "=" * 60)
    print("COMPARISON")
    print("=" * 60)
    print(f"{'Model':<20} {'Fix?':<6} {'Cost':<14} {'Time':<8}")
    print("-" * 60)
    for r in results:
        if "error" in r:
            print(f"{r['model']:<20} ERROR  {r['error'][:40]}")
            continue
        print(
            f"{r['model']:<20} "
            f"{'YES' if r['fix_produced'] else 'NO':<6} "
            f"${r['cost_cents']/100:<13.4f} "
            f"{r['duration']:.0f}s"
        )


if __name__ == "__main__":
    main()