# E3 Hook Cutover — Correctness Review

**Date:** 2026-02-19
**Reviewer:** Julik (fd-correctness)
**Diff:** /tmp/qg-diff-1771554951.txt
**Files reviewed:** hooks/lib-intercore.sh, hooks/lib-sprint.sh, scripts/migrate-sprints-to-ic.sh

---

## Invariants Established Before Review

These are the correctness properties that must hold across all paths:

1. **Single-owner invariant:** At most one active session agent per sprint run at any time.
2. **Phase monotonicity:** Sprints only advance forward through the canonical phase chain; no backward transitions.
3. **Bead-run linkage atomicity:** Either bead+run both exist and are linked, or neither is observable to callers.
4. **Idempotent migration:** Running `migrate-sprints-to-ic.sh` N times produces the same result as running it once.
5. **Fail-open safety:** If `ic` is unavailable, hooks return 0 (allow) and no workflow is blocked.
6. **Artifact write-safety:** Two concurrent calls to `sprint_set_artifact` for the same sprint must not lose either write.
7. **Phase verification before link:** Migration must not link a bead to a misaligned ic run.
8. **Lock hygiene:** Every acquired lock must be released on all exit paths, including error paths.

---

## Summary

The cutover from temp-file sentinels and beads-only state to an ic-primary / beads-fallback architecture is structurally sound. The most important design decisions — intercore_lock serializing sprint_claim, verify-before-link in both sprint_create and migration, and using `ic run skip` instead of `ic run advance` for historical migration — are correct and explicitly documented.

Four issues were found. None are catastrophic, but two (C1, C2) are latent correctness gaps that can corrupt the single-owner invariant or silently leave a partially-initialized sprint linked and exposed to discovery. Two others (C3, C4) are reliability gaps in the migration script that can cause silent data loss or script abort.

---

## Issue Analysis

### C1 — MEDIUM: sprint_claim ic-path does not unlock on agent-add failure

**Location:** `hooks/lib-sprint.sh`, `sprint_claim()`, ic-path block (around diff hunk `+@@ -882,33 +...)

**Problem:** The code acquires `intercore_lock "sprint-claim"` and holds it across the staleness check, the `intercore_run_agent_update` (mark old as failed), and the `intercore_run_agent_add` call. After `intercore_run_agent_add`, `intercore_unlock` is called — but if `intercore_run_agent_add` fails, there is no explicit unlock before the implicit `return 0`. In the current code, `intercore_run_agent_add` suppresses failures with `|| true`, so this path is not reachable today. However, the lock semantics are subtle and worth hardening.

More critically: if `intercore_run_agent_update "$old_agent_id" "failed"` succeeds but `intercore_run_agent_add` then fails (ic DB write error), the stale session agent is marked failed but NO new session agent is registered. The sprint is now in a state where it has no active agent and the lock is released — so the next caller will succeed and claim the sprint, which is the correct outcome. This specific scenario is actually safe, but only by accident of the implementation not checking the `agent_add` return code. If a future change makes `agent_add` failures observable, this reasoning breaks.

**Failure narrative:**
1. Session A holds sprint-claim lock, marks stale agent as failed, calls `intercore_run_agent_add` → ic returns error (DB full, network, etc.)
2. `|| true` swallows the error. `intercore_unlock` is called. Return 0.
3. Session A believes it holds the sprint. The ic run has no active agent registered.
4. Session B now claims the sprint via the same path. Both sessions believe they own it. Invariant 1 broken.

**Fix:** Check the return code of `intercore_run_agent_add` and return 1 on failure, ensuring the lock is released either way:

```bash
if ! intercore_run_agent_add "$run_id" "session" "$session_id" >/dev/null 2>&1; then
    echo "sprint_claim: agent registration failed" >&2
    intercore_unlock "sprint-claim" "$sprint_id"
    return 1
fi
intercore_unlock "sprint-claim" "$sprint_id"
return 0
```

---

### C2 — MEDIUM: sprint_create verification failure cancels bead but does NOT cancel the ic run

**Location:** `hooks/lib-sprint.sh`, `sprint_create()`, verification block (lines 99-107 in current file)

**Problem:** After `bd set-state "$sprint_id" "ic_run_id=$run_id"` succeeds, the code calls `intercore_run_phase "$run_id"` to verify the ic run is at the `brainstorm` phase. If this verification fails, the code cancels the bead with `bd update "$sprint_id" --status=cancelled` but does NOT cancel the ic run. The ic run is left active in intercore with `scope_id="$sprint_id"`, unreferenced from any bead the sprint API knows about.

**Consequence:** `sprint_find_active` in ic-mode filters for runs with a `scope_id`. An orphaned ic run with `scope_id` pointing to a cancelled bead will be returned by `sprint_find_active` as an active sprint, with the cancelled bead's id as the sprint id. Any subsequent operation on that sprint will hit the cancelled bead and misbehave silently.

**Failure narrative:**
1. `sprint_create` succeeds through bead creation and ic_run_id write.
2. `intercore_run_phase` returns wrong phase (ic DB temporarily inconsistent, race with another process, ic bug).
3. Bead is cancelled. ic run is NOT cancelled. Orphaned run persists.
4. `sprint_find_active` returns an entry with `id=<cancelled-bead-id>`.
5. Caller tries to `sprint_claim` the phantom sprint. `bd state` returns stale/empty data. Logic proceeds against a cancelled bead.

**Fix:** Add `"$INTERCORE_BIN" run cancel "$run_id" 2>/dev/null || true` in the verification failure branch, mirroring the pattern used in the `ic_run_id` write-failure branch (which already does this correctly):

```bash
if [[ "$verify_phase" != "brainstorm" ]]; then
    echo "sprint_create: ic run verification failed, cancelling bead $sprint_id" >&2
    "$INTERCORE_BIN" run cancel "$run_id" 2>/dev/null || true   # ADD THIS
    bd update "$sprint_id" --status=cancelled >/dev/null 2>&1 || true
    echo ""
    return 0
fi
```

---

### C3 — LOW: Migration phase-walk logic has an unreachable path for non-brainstorm-starting phase

**Location:** `scripts/migrate-sprints-to-ic.sh`, phase skip loop (lines 91-105)

**Problem:** The phase-walk loop has a guard `[[ "$p" == "$current_ic_phase" ]] || continue`. The intent is: only emit `ic run skip` when `$p` is the phase the ic run is currently at. But after the first successful skip, the code updates `current_ic_phase` to the next phase using the inner `for (( j=... ))` loop. On the next outer loop iteration, `$p` will be the next phase in `phases_array`, and `$current_ic_phase` will also have been updated to that phase — so the guard will pass. This is correct for phases that are visited in order.

However, the guard condition `[[ "$p" == "$current_ic_phase" ]] || continue` means that if `skip` advances the ic run but the inner lookup for `current_ic_phase` fails to find the current phase in the array (edge case if `$p` is `done` or the last element), `current_ic_phase` will be set to `phases_array[$((j+1))]` which is an array-bounds-out access in bash — it returns an empty string, not an error. Subsequent loop iterations will have `current_ic_phase=""`, the guard will never match any `$p`, all remaining skips will be silently skipped, and the final phase verification (`actual_ic_phase != "$phase"`) will catch this and report an error — but the ic run will be left in a partially skipped state before cancellation.

**Consequence:** If the sprint's target phase is beyond `shipping`, or if the ic run's `skip` advances to an unexpected phase, the migration will fail with an error and cancel the run. This is safe (no zombie state) but means some sprints cannot be migrated without manual intervention.

**Fix:** Bounds-check before array access:

```bash
if [[ $((j+1)) -lt ${#phases_array[@]} ]]; then
    current_ic_phase="${phases_array[$((j+1))]}"
else
    current_ic_phase="done"
fi
```

Also: the log line `echo "  → Created run $run_id (phase: $current_ic_phase)"` at line 131 prints `current_ic_phase` rather than `actual_ic_phase`. After the loop, `current_ic_phase` may lag one phase behind the actual ic state (since it is updated to the NEXT phase before the skip is performed). The log is confusing but not harmful.

---

### C4 — LOW: Migration orphan-cancel uses a subshell pipe, error is invisible to the outer script

**Location:** `scripts/migrate-sprints-to-ic.sh`, orphan cancellation block (lines 73-75)

**Problem:** The `ic run cancel` calls for orphaned runs happen inside a `while read -r orphan_id; do ... done` subshell created by the pipe `echo "$existing_json" | jq -r '.[].id' | while read -r orphan_id; do`. Bash pipelines run in subshells. The `|| true` inside the loop suppresses errors, which is intentional. But if `jq` itself fails (malformed JSON in `existing_json`), the pipe sends nothing to `while`, the loop executes zero times, and the orphaned runs are silently left alive. The outer script continues and attempts to create a new ic run — potentially creating a second orphan for the same bead scope_id.

This is a pre-existing resilience gap. The orphan-cancel is a best-effort step, so silent failure is by design. But it means a re-run after a partial failure may accumulate multiple orphaned runs per bead rather than cleaning them up. The final `ic run create` will succeed (ic allows multiple runs per scope_id), but subsequent `sprint_find_active` calls will return multiple entries for the same bead.

**Note:** `set -euo pipefail` is active at the top of the script. In bash, `set -o pipefail` makes the pipeline exit code the rightmost non-zero exit code. `jq` failing would cause the pipeline to have a non-zero exit, but because the `while` is in a pipe, not a direct command, `pipefail` behavior here is implementation-defined. On GNU bash, the whole pipeline's exit code is what `pipefail` sees, but since this is used in a command position (not a condition), `set -e` would trigger an abort. The `|| true` at the outer context is missing — the pipe itself could abort the script if `jq` fails and `pipefail` applies.

**Fix:** Capture the jq output first, check for failure, then iterate:

```bash
orphan_ids=$(echo "$existing_json" | jq -r '.[].id' 2>/dev/null) || orphan_ids=""
if [[ -n "$orphan_ids" ]]; then
    while IFS= read -r orphan_id; do
        ic run cancel "$orphan_id" 2>/dev/null || true
    done <<< "$orphan_ids"
fi
```

---

## Improvements (Non-blocking)

### I1: sprint_find_active ic-path has no cap against non-sprint scope_id entries

The ic-path in `sprint_find_active` trusts that any run with a `scope_id` is a sprint. This is correct today (only `sprint_create` creates runs with `scope_id`), but it means future ic uses of `scope_id` for non-sprint purposes will silently pollute the sprint list. A lightweight guard — checking that the `scope_id` format matches bead ID patterns — would make this invariant explicit.

### I2: Lock fallback in intercore_lock uses `mkdir` without TTL enforcement

The fallback `mkdir /tmp/intercore/locks/${name}/${scope}` path (when `ic lock acquire` returns exit 2+) has no TTL. If a hook process is `kill -9`'d while holding a fallback lock, `intercore_lock_clean` will only remove it if called explicitly. The lock is not self-expiring. This is pre-existing and not introduced by this diff, but the diff increases reliance on locking for the ic-path and the fallback-path (legacy sprints). Adding a note about this in `intercore_lock` would help future operators.

### I3: checkpoint_read project-scoped fallback can cross-contaminate with multiple active runs

`checkpoint_read` with no `bead_id` falls back to `intercore_run_current "$(pwd)"` which returns the "current" run for the project. With multiple active sprint runs in the same project directory, this is non-deterministic. The comment in the diff acknowledges this ("may be wrong with multiple active runs"). Sites calling `checkpoint_read` without a bead_id should be audited and updated to pass the bead_id. This is a pre-existing design limitation made explicit here.

### I4: intercore_sentinel_check_or_legacy now always fails open when ic errors

The old code had a three-way split: allowed (0), throttled (1), ic-error (2+) → fall through to legacy temp file. The new code maps ic-error to fail-open (return 0). For throttle sentinels protecting idempotent operations (e.g., auto-publish, drift-check), this is fine. For any future sentinel where throttling is a safety property rather than a convenience, this new behavior would silently bypass throttling on ic errors. The design decision (fail-open) is documented and appropriate for this use case, but warrants a comment that future safety-critical sentinels should not use this wrapper.

---

## Verdict

**needs-changes** — Two medium issues (C1, C2) require targeted fixes before production use. Both involve cleanup paths that can leave ghost state under specific error conditions. The fixes are small (3-5 lines each) and do not require architectural changes.

The concurrency architecture is sound. The lock-based TOCTOU serialization in `sprint_claim` and the verify-before-link pattern in `sprint_create` are correct. The decision to use `ic run skip` (not `ic run advance`) for migration phase alignment is the correct call and eliminates the risk of triggering live agent handlers on historical data.
