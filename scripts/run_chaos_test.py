"""
Test 2: Circuit breaker behavior under real injected faults.

Proves:
1. The circuit breaker trips after N consecutive failures
2. Once open, the router excludes the failed harness
3. A healthy harness is still available
4. The breaker recovers after cooldown

Usage:
    python -m scripts.run_chaos_test
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.openhands_adapter import OpenHandsAdapter
from app.circuit_breaker import BreakerRegistry, BreakerState
from chaos.injector import ChaosInjector
from app.schema import TraceEvent, EventType


FIXTURE = Path("local_tests/fixture_01").resolve()


def _prepare_workspace():
    """Fresh workspace per test."""
    import tempfile
    import shutil
    import subprocess

    workspace = Path(tempfile.mkdtemp(prefix="chaos_"))
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


def main():
    print("\n=== Test 2: Circuit breaker under injected faults ===\n")

    # --- Setup: two harness configs ---
    registry = BreakerRegistry(failure_threshold=3, cooldown_seconds=5.0)

    broken_harness_id = "openhands-gpt-5-nano-broken"
    healthy_harness_id = "openhands-gpt-5-nano-healthy"

    broken_breaker = registry.get(broken_harness_id)
    healthy_breaker = registry.get(healthy_harness_id)

    print("Initial breaker states:")
    print(f"  {broken_harness_id}: {broken_breaker.state.value}")
    print(f"  {healthy_harness_id}: {healthy_breaker.state.value}")

    # --- Phase 1: Inject 3 failures on the "broken" harness ---
    print("\n--- Phase 1: Injecting 3 consecutive failures ---\n")

    workspace = _prepare_workspace()
    adapter = OpenHandsAdapter(
        model="gpt-5-nano",
        harness_id=broken_harness_id,
        workspace_dir=str(workspace),
    )

    # Fail on calls 1, 2, 3. Call 4 would succeed.
    injector = ChaosInjector(fail_on_calls={1, 2, 3}, fault_type="timeout")
    wrapped_run = injector.wrap(adapter.run)

    task_text = (FIXTURE / "INSTRUCTIONS.md").read_text()

    for attempt in range(1, 5):
        # Check breaker BEFORE attempting
        allowed = broken_breaker.allow_call()

        if not allowed:
            print(f"  Attempt {attempt}: BLOCKED by circuit breaker "
                  f"(state={broken_breaker.state.value})")
            continue

        try:
            events, patch = wrapped_run(task_text, f"chaos-{attempt}")
            broken_breaker.record_success()
            print(f"  Attempt {attempt}: SUCCESS "
                  f"(state={broken_breaker.state.value})")
        except Exception as e:
            broken_breaker.record_failure()
            print(f"  Attempt {attempt}: FAILED ({type(e).__name__}) "
                  f"-> breaker state={broken_breaker.state.value}")

    # --- Phase 2: Confirm the broken harness is excluded ---
    print("\n--- Phase 2: Routing decision with broken harness ---\n")

    allowed_harnesses = registry.allowed_harnesses(
        [broken_harness_id, healthy_harness_id]
    )
    print(f"  Candidate harnesses: {[broken_harness_id, healthy_harness_id]}")
    print(f"  Allowed by breaker:  {allowed_harnesses}")

    if broken_harness_id not in allowed_harnesses:
        print(f"  ✅ Correctly excluded: {broken_harness_id}")
    else:
        print(f"  ❌ FAIL: {broken_harness_id} still allowed")

    if healthy_harness_id in allowed_harnesses:
        print(f"  ✅ Healthy harness still available: {healthy_harness_id}")
    else:
        print(f"  ❌ FAIL: healthy harness was blocked")

    # --- Phase 3: Verify healthy harness actually works ---
    print("\n--- Phase 3: Healthy harness executes the task ---\n")

    healthy_workspace = _prepare_workspace()
    healthy_adapter = OpenHandsAdapter(
        model="gpt-5-nano",
        harness_id=healthy_harness_id,
        workspace_dir=str(healthy_workspace),
    )

    healthy_breaker = registry.get(healthy_harness_id)

    # Run one real task on the healthy harness
    try:
        events, patch = healthy_adapter.run(
            task_text, "healthy-1"
        )
        healthy_breaker.record_success()
        print(f"  Healthy harness ran: "
              f"{len(events)} events, patch {len(patch)} chars")
        print(f"  Breaker state: {healthy_breaker.state.value}")

        # Verify fix worked
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "test_buggy.py", "-q"],
            cwd=healthy_workspace,
            capture_output=True,
            text=True,
            timeout=60,
        )
        passed = result.returncode == 0
        print(f"  Fix verified: {'PASS' if passed else 'FAIL'}")

    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")

    # --- Phase 4: Cooldown and recovery ---
    print("\n--- Phase 4: Cooldown and recovery ---\n")

    print(f"  Waiting {broken_breaker.cooldown_seconds}s for cooldown...")
    time.sleep(broken_breaker.cooldown_seconds + 0.5)

    # Next allow_call should transition to HALF_OPEN
    now_allowed = broken_breaker.allow_call()
    print(f"  After cooldown, allow_call: {now_allowed}")
    print(f"  Breaker state: {broken_breaker.state.value}")

    if broken_breaker.state == BreakerState.HALF_OPEN:
        print(f"  ✅ Correctly transitioned to HALF_OPEN")
    elif broken_breaker.state == BreakerState.CLOSED:
        print(f"  ✅ Recovered to CLOSED")
    else:
        print(f"  ⚠️  State: {broken_breaker.state.value}")

    # --- Summary ---
    print("\n" + "=" * 60)
    print("CHAOS TEST RESULTS")
    print("=" * 60)
    snap = injector.snapshot()
    print(f"  Total calls attempted: {snap['total_calls']}")
    print(f"  Faults injected:       {snap['faults_injected']}")
    print(f"  Calls succeeded:       {snap['calls_succeeded']}")
    print(f"  Final broken state:    {broken_breaker.state.value}")
    print(f"  Final healthy state:   {healthy_breaker.state.value}")


if __name__ == "__main__":
    main()