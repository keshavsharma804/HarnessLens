# Control Plane Invariants

These are the safety properties the control plane must guarantee at all times.
Each has a TLA+ formalization in `control_plane.tla` and a Python runtime
checker in `app/invariant_checker.py`.

## INV-1: No denied action executes

**Informal:** If the behavior gate returns `deny`, the action must not run.

**Why it matters:** This is the non-bypassability property. Without it, an
agent could rephrase a denied request and slip past the gate.

**TLA+ name:** `NoDeniedActionExecutes`

## INV-2: Budget never exceeds ceiling

**Informal:** Cumulative spend for a run must never exceed the policy ceiling.

**Why it matters:** Runaway loops are the primary cost failure mode of
autonomous agents. A hard ceiling prevents unbounded spend.

**TLA+ name:** `BudgetNeverExceeds`

## INV-3: Loop step bounded

**Informal:** No run may exceed `max_loop_steps` from policy.

**Why it matters:** Bounds the worst-case latency and cost. Prevents
infinite loops that never terminate.

**TLA+ name:** `LoopStepBounded`

## INV-4: Selection from harness set

**Informal:** The router may only select a harness from the declared set.

**Why it matters:** Prevents typos or injection from routing to an
unauthorized backend.

**TLA+ name:** `SelectionInHarnessSet`