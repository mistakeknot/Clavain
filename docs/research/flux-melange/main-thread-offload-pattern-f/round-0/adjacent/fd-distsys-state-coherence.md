# fd-distsys-state-coherence — round 0

## Findings Index
- [P1] plan-staleness-no-precondition-pin — plan carries no repo-state pin an executor can check before applying (§The shape / Executor)
- [P1] partial-application-no-rollback-contract — "report, not repair" says what stops, not what state a half-applied plan leaves behind (§The shape / Executor)
- [P1] strike-counter-no-durable-store — two-strikes count has no named storage across separate spawns (§Escalation)
- [P2] validator-rerun-not-isolated — validator re-runs the same verify block with no stated isolation from the executor's mutated worktree (§The shape / Validator)
- [P2] no-concurrent-writer-exclusion — executor's touch-set has no reservation/lock step despite sibling-session and autosync risk (§The shape / Executor)

## Findings

### plan-staleness-no-precondition-pin
- **Severity**: P1
- **Where**: "The shape" § Executor (line 16: "Receives one plan file path and the repo path... Applies the plan, runs the plan's verify block") and § "What makes it enforceable" bullet 3 (line 25: "Plans live where the executor can read them without the orchestrator's context")
- **What**: The plan is authored once, by the orchestrator, against whatever repo state existed at write time. Nothing in either bullet names a mechanism — base commit SHA, clean-tree assertion, branch check — by which the executor (or the validator) can tell whether the tree it is about to mutate still matches the tree the plan was written against. An executor spawned after a concurrent goal lands, or after an autosync push moves the tree, applies the plan against a moved base.
- **Evidence**: The doc names this exact failure mode itself, unresolved, as Q-E (line 34): "plan drift — a plan written against stale repo state that a fresh executor cannot notice." The verify block is authored against the same stale snapshot as the rest of the plan, so it can pass on the moved tree for the wrong reason; the validator re-runs that identical block (line 17) on the same now-current tree, so it inherits the same blind spot. The gate (line 15) and the validator's PASS both report green while the underlying drift goes undetected.
- **Suggestion**: Add a required field to the plan-file schema (base commit SHA at authoring time) and a mandatory first step in the executor contract: assert the repo is at that SHA (or a fast-forward of it) before applying anything; on mismatch, report "stale plan" as a distinct outcome from "plan defect" or "verify failure," so the orchestrator can tell drift apart from a bad plan.

### partial-application-no-rollback-contract
- **Severity**: P1
- **Where**: "The shape" § Executor (line 16: "Never expands scope; a plan defect is reported, not repaired")
- **What**: This sentence specifies the executor's behavior toward a defect it *notices*, but not what happens to files it has already edited when it stops partway through a multi-step plan — whether mid-plan, or after applying edits but before the "commits with the plan's message file" step also named in line 16. There is no stated reset-to-clean-state step between a failed attempt and the retry that the two-strikes rule (line 19) implies will follow.
- **Evidence**: Line 16 bundles "applies the plan," "runs the verify block," and "commits with the plan's message file" as sequential executor actions with no stated transaction boundary. Line 19's escalation counts "an executor that fails a plan twice" as one of two strike triggers — implying at least one retry happens on the same item — but nothing says the second attempt starts from the pre-plan tree state rather than whatever partial mutation the first attempt left behind.
- **Suggestion**: State explicitly whether a failed attempt's edits are reset (git checkout/stash) before a retry spawn, or whether the plan is required to be re-appliable-in-place (idempotent by construction). Either is fine; the ambiguity is the defect, and it compounds directly with the staleness gap above — a retry on a dirty, partially-mutated tree is a second, self-inflicted precondition mismatch.

### strike-counter-no-durable-store
- **Severity**: P1
- **Where**: "The shape" § Escalation (line 19: "two-strikes... an executor that fails a plan twice, or a validator that rejects twice, returns the item to the orchestrator")
- **What**: A durable per-item strike counter is required for this rule to hold across separate executor and validator spawns (each fresh-context, per lines 16-17) and, plausibly, across orchestrator turns on the same goal. No storage for that counter is named anywhere: not the plan file (line 25's schema is "path, not the plan body" plus whatever fields exist — none described as strike-bearing), not a bead, not the meter (line 23 describes model/context/token-share reporting, not per-item retry state).
- **Evidence**: The doc's own "What makes it enforceable rather than aspirational" section (lines 21-26) lists every mechanism it considers load-bearing for the design — a meter, an inheritance closure, a plan-file convention, the small-task exemption — and a strike-counter store is absent from that list despite the escalation rule depending on one existing.
- **Suggestion**: Name the store explicitly — a field in the plan file that each executor/validator spawn increments and reads back (`attempts: 0`, `validator_rejections: 0`), or a bead per item with that state. Without it, a context compaction or a fresh orchestrator invocation on the same goal silently resets the count, and a defective plan can cycle through executor attempts indefinitely without ever reaching frontier-in-the-loop escalation.

### validator-rerun-not-isolated
- **Severity**: P2
- **Where**: "The shape" § Validator (line 17: "Re-runs the verify block itself")
- **What**: No isolation guarantee is stated between the validator's re-run and the state the executor's prior run left behind (same worktree, same commit, presumably same test fixtures). For any verify block with a non-idempotent assertion — an append-only log check, a rate-limited external call already consumed once, a seed-data insert — the validator's independent run can fail for reasons the executor's earlier, identical run never encountered.
- **Evidence**: Line 17 states re-execution as the entire verification mechanism ("Re-runs the verify block itself. Judges ONLY against the frozen criteria in the plan") with no mention of a fresh checkout, branch, or sandbox for that second run.
- **Suggestion**: Either require verify blocks to be idempotent by construction (a lint rule alongside the existing `writing-plans` machine-checkable-verify-block requirement), or have the validator re-run against a fresh clone/worktree at the executor's final commit rather than the executor's live tree, so a non-idempotent side effect can't fire twice.

### no-concurrent-writer-exclusion
- **Severity**: P2
- **Where**: "The shape" § Executor (line 16) and § "What makes it enforceable" (lines 21-26)
- **What**: Nothing in either section names a reservation or locking step for the files an executor is about to touch, despite the same repo being editable by sibling sessions and autosync pushes — both named as live, ongoing risks in this project's own operating context (interlock's `reserve_files`/`release_files` already exists in this plugin ecosystem for exactly this purpose). Two executors dispatched concurrently against overlapping file sets (plausible once pilots move from one item to a queue) have no stated mechanism to avoid stomping each other.
- **Evidence**: The design's own "48 command/skill sites" inheritance-closure count (line 24) and the framing of pilots as plural, queued work suggest more than one executor spawn will be live in the same repo at once; no file-reservation step appears in the executor contract.
- **Suggestion**: Add a reservation step to the executor contract — call out `reserve_files` (or equivalent) for the plan's touch-set before applying, release on completion or failure — so two concurrently-dispatched executors can't silently overwrite each other's work.

## Verdict
The design names the right roles but leaves every boundary between them undefended against ordinary distributed-systems failure classes — staleness, partial-write rollback, and durable counters — that its own Q-E already flags as a live worry. These are cheap to close (one field, one precondition check, one reset step) and should be closed before pilot dispatch, since all three fail silently: the gate and the validator both report green while the underlying drift, dirty state, or lost counter goes undetected.
