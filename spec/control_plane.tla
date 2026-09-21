---- MODULE control_plane ----
EXTENDS Integers, Sequences

\* The control plane's safety invariants, specified in TLA+.
\*
\* This file is documentation of design-time verification. The runtime
\* counterpart lives in app/invariant_checker.py. Together they cover the
\* two failure modes: design errors (caught here) and runtime drift (caught
\* by the checker).
\*
\* To model-check this locally, install TLA+ Toolbox + Java 11+ and run
\* TLC against this spec. The spec is small enough to check in seconds.

CONSTANTS
    Harnesses,           \* Set of available harnesses
    MaxBudget,           \* Budget ceiling in cents
    MaxSteps             \* Loop step ceiling

VARIABLES
    current_harness,
    budget_consumed,
    last_action_verdict,
    last_action_executed,
    loop_step

vars == <<current_harness, budget_consumed,
          last_action_verdict, last_action_executed, loop_step>>

\* --- Type invariant ---
TypeOK ==
    /\ current_harness \in Harnesses
    /\ budget_consumed \in 0..MaxBudget
    /\ last_action_verdict \in {"allow", "deny", "flag"}
    /\ last_action_executed \in BOOLEAN
    /\ loop_step \in 0..MaxSteps

\* --- Invariant 1: No denied action executes. ---
\*
\* If the behavior gate returned "deny", then the action must not have
\* been executed. This is the non-bypassability property.
NoDeniedActionExecutes ==
    (last_action_verdict = "deny") => (last_action_executed = FALSE)

\* --- Invariant 2: Budget never exceeds the ceiling. ---
BudgetNeverExceeds ==
    budget_consumed <= MaxBudget

\* --- Invariant 3: Loop step never exceeds the ceiling. ---
LoopStepBounded ==
    loop_step <= MaxSteps

\* --- Invariant 4: Selection is always from the harness set. ---
SelectionInHarnessSet ==
    current_harness \in Harnesses

\* --- Combined safety ---
Safety ==
    /\ NoDeniedActionExecutes
    /\ BudgetNeverExceeds
    /\ LoopStepBounded
    /\ SelectionInHarnessSet

\* --- Init predicate ---
Init ==
    /\ current_harness \in Harnesses
    /\ budget_consumed = 0
    /\ last_action_verdict = "allow"
    /\ last_action_executed = FALSE
    /\ loop_step = 0

\* --- Next-state relation (simplified) ---
\* Each step: a decision is made, then either the action executes or is
\* blocked. If the verdict is "deny", execution is impossible.
Next ==
    \E h \in Harnesses, v \in {"allow", "deny", "flag"}:
        /\ current_harness' = h
        /\ last_action_verdict' = v
        /\ last_action_executed' = (v /= "deny")
        /\ loop_step' = loop_step + 1
        /\ budget_consumed' = budget_consumed + 1

Spec == Init /\ [][Next]_vars

====