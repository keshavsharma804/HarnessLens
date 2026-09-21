"""
Demo runner. Executes N runs against both harnesses and persists traces.

Usage:
    python scripts/run_demo.py --runs 5
"""

import argparse
from adapters.dummy_adapter import DummyHarness
from adapters.slow_adapter import SlowHarness
from app.collector import insert_events, rollup_run, insert_run_summary
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
from adapters.dummy_adapter import DummyHarness
from adapters.slow_adapter import SlowHarness
from app.collector import insert_events, rollup_run, insert_run_summary

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3, help="Runs per harness")
    args = parser.parse_args()

    dummy = DummyHarness()
    slow = SlowHarness()

    for harness, name in [(dummy, "dummy"), (slow, "slow")]:
        print(f"\n=== {name} ===")
        for i in range(args.runs):
            events = harness.run(task=f"demo-task-{i}")
            inserted = insert_events(events)
            summary = rollup_run(events)
            insert_run_summary(summary)

            print(
                f"  run {summary.run_id} "
                f"steps={summary.total_steps} "
                f"cost={summary.total_cost_cents:.2f}c "
                f"latency={summary.total_latency_ms}ms "
                f"status={summary.final_status}"
            )


if __name__ == "__main__":
    main()