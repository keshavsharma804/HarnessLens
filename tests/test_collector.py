"""Verify SQLite persistence and run rollup."""

import tempfile
from pathlib import Path

from adapters.dummy_adapter import DummyHarness
from app import collector


def test_insert_and_query(monkeypatch):
    """Write events, roll up a run, and confirm we can read it back."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        monkeypatch.setattr(collector, "DB_PATH", db_path)

        harness = DummyHarness()
        events = harness.run("task")

        n = collector.insert_events(events)
        assert n == len(events)

        summary = collector.rollup_run(events)
        collector.insert_run_summary(summary)

        recent = collector.query_recent_runs()
        assert len(recent) == 1
        assert recent[0]["harness_id"] == "dummy"
        assert recent[0]["final_status"] == "success"