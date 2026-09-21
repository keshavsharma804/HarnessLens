# Where This Breaks

Every system has failure modes. Documenting them is more valuable than pretending they do not exist. This file lists everything I found while building HarnessLens — bugs, limitations, and design tradeoffs that will bite at scale.

If you are evaluating this project, start here. It tells you more about the engineering than the tests do.

---

## Part 1: Failure Modes Discovered While Building

These are real bugs I hit, debugged, and fixed. Each one is documented with symptom, root cause, fix, and the lesson it taught.

### 1. Pydantic v2 class-based `Config` deprecation

**Symptom:** `PydanticDeprecatedSince20: Support for class-based config is deprecated` warning on every test run. Tests passed but the output was noisy.

**Root cause:** `schema.py` used the Pydantic v1 pattern:

```python
class TraceEvent(BaseModel):
    class Config:
        use_enum_values = True
```

Pydantic v2 replaced this with `model_config = ConfigDict(...)`.

**Fix:** Replaced the nested `Config` class with a `model_config` attribute and imported `ConfigDict` from `pydantic`.

**Lesson:** Framework migrations are silent. Pydantic v2 was released in 2023; this codebase was written in 2026. Deprecation warnings become breaking changes. Fix them when they appear, not when they break.

---

### 2. Windows pytest `tmp_path` permission errors

**Symptom:** `PermissionError: [WinError 5] Access is denied: 'C:\\Users\\...\\AppData\\Local\\Temp\\pytest-of-...'` during test setup. Two tests failed before any test code ran.

**Root cause:** pytest's `tmp_path` fixture scans `%TEMP%\pytest-of-<user>` to find numbered subdirectories. On Windows, antivirus or a previous crashed run can hold a lock on that folder. The fixture raises before the test executes.

**Fix:** Bypassed `tmp_path` entirely. Every test that needed an isolated directory uses `tempfile.TemporaryDirectory()` instead:

```python
import tempfile
from pathlib import Path

def test_something():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        # ...
```

**Lesson:** Do not rely on framework conveniences you cannot control. On Windows, `tmp_path` is unreliable. `tempfile` is a Python standard library module that always works.

---

### 3. Cross-folder import resolution for CLI scripts

**Symptom:** `ModuleNotFoundError: No module named 'adapters'` when running `python scripts/run_demo.py` from the project root.

**Root cause:** Python adds the **script's folder** to `sys.path`, not the current working directory. When you run `scripts/run_demo.py`, Python adds `scripts/` to the import path. `adapters/` is one level up and invisible.

**Fix:** Two options, both valid:

- **Option A:** Run as a module: `python -m scripts.run_demo`. Requires `scripts/__init__.py`.
- **Option B:** Add a path shim at the top of the script:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

**Lesson:** Python's import resolution depends on where the script lives, not where you run it from. Every CLI script in a multi-folder project needs explicit path bootstrapping.

---

### 4. Verification status semantics — absence of evidence is not evidence of failure

**Symptom:** The `dummy` harness completed successfully but its runs were marked as `failed` in the rollup.

**Root cause:** `rollup_run` computed verification as:

```python
verification_passed = any(e.verification_status == "passed" for e in events)
```

The dummy harness never emits a verification event, so this returned `False`, and the final status became `failed`.

**Fix:** Distinguished three states:

- **Verified-pass:** an event explicitly says `passed`
- **Verified-fail:** an event explicitly says `failed`
- **Unverified:** no verification event at all

Only explicit failure marks a run as failed. Unverified runs trust the harness's own completion signal.

**Lesson:** Absence of evidence is not evidence of failure. In verification systems, "no data" and "bad data" are different states. Conflating them causes false positives.

---

### 5. Router weight imbalance — the weights ARE the policy

**Symptom:** The router always chose `easyloops`, even at loop_step 0 where the policy said to prefer `researchharness`.

**Root cause:** Initial weights were:

```yaml
weights:
  historical_success: 0.40
  cost: 0.30
  latency: 0.20
  step_affinity: 0.10
```

Cost and latency combined gave `easyloops` a 0.05 point advantage. Step affinity gave `researchharness` a 0.05 point advantage. They cancelled out, so the cheap harness won.

**Fix:** Reweighted to make trajectory position the dominant signal:

```yaml
weights:
  historical_success: 0.30
  cost: 0.20
  latency: 0.10
  step_affinity: 0.40
```

Now `researchharness` wins early by ~0.15, and `easyloops` wins late.

**Lesson:** In scoring systems, the weights are not configuration. They are the policy. A silent weight change silently changes behavior. Every weight change should be a PR with evidence.

---

### 6. Verdict value drift between YAML and code

**Symptom:** `test_gate_denies_high_risk_write` failed with `assert 'deny' == 'denied'`. Five gate tests failed.

**Root cause:** The YAML used `action: deny`, but the Python enum was:

```python
class Verdict:
    DENIED = "denied"
```

Two different vocabularies for the same concept.

**Fix:** Made the enum values match the YAML strings exactly:

```python
class Verdict:
    ALLOWED = "allow"
    DENIED = "deny"
    FLAGGED = "flag"
```

No conversion layer. The code mirrors the source of truth.

**Lesson:** When YAML is the source of truth, the code's constants must mirror it, not translate it. Translation layers are where bugs live.

---

### 7. Glob key lookup in behavior gate was self-defeating

**Symptom:** A rule with `path_glob: "**/.env"` never fired. `.env` reads were silently allowed instead of flagged.

**Root cause:** The matcher looked up the wrong key:

```python
for key, expected in when.items():   # key = "path_glob"
    actual = context.get(key)         # looks up "path_glob", not "path"
    if key.endswith("_glob") and actual is not None:
        # never reached: actual is always None
```

The `actual` was always `None` because `context` contains `path`, not `path_glob`.

**Fix:** Stripped the `_glob` suffix first, then looked up the base key:

```python
if key.endswith("_glob"):
    target_key = key[:-5]
    target_value = context.get(target_key, "")
    if not fnmatch.fnmatch(str(target_value), expected):
        return False
    continue
```

**Lesson:** Test the negative case as well as the positive one. A rule that never fires looks identical to a rule that correctly allows.

---

### 8. Patch ID collision in staging

**Symptom:** `test_snapshot_summarizes` failed with `assert 1 == 2`. Two patches were staged but only one appeared in the snapshot.

**Root cause:** The test fixture used the same hardcoded `patch_id` for every patch:

```python
def _patch():
    return EvolvedPatch(patch_id="ep-test", ...)
```

The `StagingDeployer` stores patches in a dict keyed by `patch_id`. Two patches with the same ID overwrite each other.

**Fix:** Made the fixture generate unique IDs:

```python
def _patch():
    return EvolvedPatch(patch_id=f"ep-test-{uuid.uuid4().hex[:6]}", ...)
```

**Lesson:** A `patch_id` is an identity, not a label. Two patches are two identities. When a fixture returns "the same thing," it often returns "the same identity," which is a bug in disguise.

---

### 9. SQLite connection closed inside transaction context

**Symptom:** `sqlite3.ProgrammingError: Cannot operate on a closed database` when the `write` or `update_fitness` path re-entered the same connection.

**Root cause:** `conn.close()` was called **inside** a `with conn:` block:

```python
conn = _connect()
with conn:
    # ... do work ...
    conn.close()   # <-- wrong
    return self._load(mem_id)
```

When the `with` block exited, Python tried to commit on a closed connection.

**Fix:** Moved the close outside the transaction context using `try / finally`:

```python
conn = _connect()
try:
    with conn:
        # ... do work ...
finally:
    conn.close()
return self._load(mem_id)
```

**Lesson:** `with conn:` manages the transaction. `conn.close()` manages the connection. They are two separate lifecycles. Never conflate them.

---

### 10. Deduplication path missed by first-use tests

**Symptom:** Nine of eleven memory tests passed. The two failing tests — `test_write_deduplicates_by_lesson` and `test_update_fitness_rejects_unknown_id` — only exercised the **second use** path. That path was where bug #9 lived.

**Root cause:** Every other test used a fresh database. Only the dedup path re-entered the same connection.

**Fix:** Fixed bug #9, then both tests passed.

**Lesson:** Test the second-use path. The first-use path almost always works. The reentry path is where resource lifecycle bugs live. Deduplication, caching, retry logic — all of these have a "first time is fine, second time breaks" failure mode.

---

## Part 2: Known Limitations

These are not bugs. They are deliberate design choices with known costs.

### Synthetic harnesses only

The `dummy_adapter` and `slow_adapter` simulate harness behavior. They do not call real Claude Code, OpenHands, DeepSeek Harness, or any production system. The benchmark numbers reflect the simulator, not real provider performance.

**What this costs:** You cannot use the benchmark numbers to predict real-world cost reduction without replacing the adapters.

**What this preserves:** The full control-plane architecture is testable without GPU access or API keys. Swapping adapters is a one-file change per harness.

### In-process breaker and memory state

Circuit breakers and memory state live in the same Python process as the control plane. Restarting the process resets all breakers and reloads memory from SQLite.

**What this costs:** Multi-replica deployments do not share breaker state. A harness that is broken for replica A is still considered healthy for replica B.

**What this preserves:** Zero external dependencies for local development. SQLite is the only stateful component.

### Bounded learning can under-react

The fleet learning adjustment is capped at ±0.30 from the neutral prior. A harness with a 0% success rate over 100 runs can only drop to `0.5 - 0.30 = 0.20` in the score.

**What this costs:** A catastrophically bad harness is not pushed to zero. It still receives some traffic.

**What this preserves:** One bad batch of runs cannot permanently blacklist a harness. The system requires ongoing evidence to keep a harness penalized.

### Verifier is generic

The independent verifier checks for artifact existence, error presence, and schema shape. Real workloads need task-specific predicates (e.g., "does the unit test pass?", "does the SQL query return the expected schema?").

**What this costs:** Verification catches surface-level failures but not domain-specific ones.

**What this preserves:** The `PredicateDecomposer` accepts custom evaluators. Adding domain-specific checks is a config change, not a code change.

### Memory retrieval is keyword-based

`EvolvingMemory.retrieve()` uses exact `task_type` match and substring overlap on `context_signature`. No embeddings, no semantic similarity.

**What this costs:** Retrieval misses relevant lessons that use different vocabulary.

**What this preserves:** No model dependency. The retrieval interface is a single function that can be swapped for embedding-based retrieval later.

### No async execution

Request handling is synchronous. Harness calls block.

**What this costs:** Throughput is bounded by the slowest harness. Under load, the queue grows.

**What this preserves:** Deterministic ordering, simpler debugging, no race conditions in the trace pipeline.

### Windows `pytest tmp_path` is broken

Documented in failure mode #2. Workaround is `tempfile.TemporaryDirectory`.

**What this costs:** Tests must avoid `tmp_path`, which is a standard pytest idiom.

**What this preserves:** Tests run on Windows without CI changes.

---

## Part 3: What Breaks at 100x Scale

If this system were deployed to handle 100x the current load, these are the components that would fail first, in order.

### 1. SQLite write contention

SQLite allows one writer at a time. Under concurrent writes, requests will queue and time out.

**Fix:** Replace SQLite with Postgres for the collector, and a time-series store (TimescaleDB or ClickHouse) for telemetry.

### 2. In-process breaker state

Each control-plane replica maintains its own breaker state. Under horizontal scaling, replicas disagree about which harnesses are healthy.

**Fix:** Move breaker state to Redis with pub/sub for state transitions.

### 3. Synchronous harness calls

Every routing decision blocks on the harness response. At 100x throughput, the request queue is the bottleneck.

**Fix:** Async execution with a bounded work queue and backpressure. Return a stream of events, not a single response.

### 4. Memory retrieval without embeddings

Keyword matching over 10,000+ memory entries is fast. Over 1,000,000 entries, it is slow and inaccurate.

**Fix:** Embed lessons with a small local model (e.g., sentence-transformers) and index them in a vector store. Retrieve by cosine similarity.

### 5. Unbounded trace storage

Every step writes a TraceEvent to SQLite. At scale, the `events` table grows without bound.

**Fix:** Retention policy — keep raw traces for 7 days, rollups for 90 days, then archive to Parquet.

### 6. Single-region deployment

Latency to a harness in another region adds 100–200ms per step. On a 10-step trajectory, that is 1–2 seconds of pure network overhead.

**Fix:** Regional control planes with a global routing layer. Route to the nearest healthy replica.

---

## Part 4: Design Tradeoffs That Will Bite Later

Each of these was a deliberate choice. Each has a cost.

### Deterministic scoring vs. learned scoring

The router uses a hand-tuned linear combination of signals. This is auditable and testable. It is also unlikely to be optimal.

**What it buys:** Every decision is explainable. You can point to the exact weights that produced a choice.

**What it costs:** A learned policy (e.g., reinforcement learning) would likely outperform the linear model after enough data.

### Static policies vs. dynamic policies

Routing, verification, and repair rules are YAML files. They do not adapt at runtime.

**What it buys:** Auditable, diffable, reviewable via PR. Policy changes are code changes.

**What it costs:** Rapid shifts in workload require manual policy updates.

### Single-node persistence vs. distributed persistence

SQLite is the only stateful component. Everything else is in-process.

**What it buys:** Zero setup. `pip install -r requirements.txt` and everything works.

**What it costs:** No horizontal scaling without replacing the persistence layer.

### Predicate decomposition vs. LLM-as-judge

The neuro-symbolic verifier decomposes into atomic predicates and composes with formal logic. It does not ask a language model to score the output.

**What it buys:** Deterministic verification. No probabilistic supervision. Composable proofs.

**What it costs:** More code to write per task type. The predicate library must be maintained.

### Bounded learning vs. aggressive learning

The fleet learning adjustment is capped at ±0.30.

**What it buys:** Stability. One bad batch cannot blacklist a harness.

**What it costs:** Slow adaptation. A harness that becomes catastrophically bad is not immediately deprioritized.

---

## Part 5: What I Would Investigate Next

If I had another month on this project, here is the order I would attack.

1. **Real harness adapters.** Replace the synthetic adapters with real Claude Code and OpenHands integrations. This is the largest step toward production.

2. **Embedding-based memory retrieval.** Replace keyword matching with sentence-transformers and a vector store. Measure retrieval precision and recall against the keyword baseline.

3. **Learned routing policy.** Compare the current linear scorer against a trained bandit or RL policy using the same held-out validation framework.

4. **Distributed breaker state.** Move to Redis and test the system with two replicas under a harness-failure scenario.

5. **Task-specific predicate libraries.** Build predicate catalogs for three concrete workloads (code modification, data analysis, document extraction) and measure verification accuracy against human review.

6. **Chaos testing at scale.** Inject systematic failures (network partitions, clock skew, memory pressure) and measure MTTR for each self-* behavior.

---

## Conclusion

The value of this project is not that it works. It is that it documents where it does not. Every failure mode in Part 1 is real. Every limitation in Part 2 is honest. Every tradeoff in Part 4 was a decision, not an accident.

If you are considering contributing, start with Part 5. If you are evaluating this project as a hiring signal, read Part 1. That is where the engineering lives.