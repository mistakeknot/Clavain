# E3 Hook Cutover — Code Quality Review

**Reviewer:** Flux-drive Quality & Style Reviewer
**Date:** 2026-02-19
**Scope:** Shell — Bash library and hook scripts
**Files:** hooks/lib-intercore.sh, hooks/lib-sprint.sh, hooks/lib-gates.sh,
.clavain/hooks/on-phase-advance, .clavain/hooks/on-dispatch-change,
scripts/migrate-sprints-to-ic.sh

---

## Executive Summary

The E3 Hook Cutover is a well-structured migration from dual-path (ic + temp-file sentinel
fallback) to ic-primary with beads fallback. The overall approach is sound: fail-open on
unavailability, structured error reasons on stdout with status messages on stderr, and
explicit cleanup of the zombie-state problem via cancel-on-failure in sprint_create. There
are no blocking correctness bugs, but six issues warrant attention before this becomes
permanent production code, ranging from a subtle lock-omission in sprint_create's
ic-path verification block, to subshell isolation in sprint_release's pipeline, to a
phase-alignment loop bug in the migration script.

---

## Detailed Findings

### F1 — MEDIUM: sprint_create does not cancel the ic run when phase verification fails

**File:** hooks/lib-sprint.sh, lines 99-107 (sprint_create, ic-path verification block)

After `bd set-state "$sprint_id" "ic_run_id=$run_id"` succeeds, the code verifies the
run is at brainstorm phase. If that verification fails, the bead is cancelled but the ic
run is left in an active (brainstorm) state with no bead linking it:

```bash
verify_phase=$(intercore_run_phase "$run_id") || verify_phase=""
if [[ "$verify_phase" != "brainstorm" ]]; then
    echo "sprint_create: ic run verification failed, cancelling bead $sprint_id" >&2
    bd update "$sprint_id" --status=cancelled >/dev/null 2>&1 || true
    echo ""
    return 0
fi
```

The ic run is never cancelled here. It is an orphan that `ic run list --active` will
return, and future migrations or `sprint_find_active` may pick it up spuriously. The
correct pattern — already used in the `ic_run_id write` failure branch two lines above —
is to also call `"$INTERCORE_BIN" run cancel "$run_id"` before returning.

**Fix:**
```bash
if [[ "$verify_phase" != "brainstorm" ]]; then
    echo "sprint_create: ic run verification failed, cancelling" >&2
    "$INTERCORE_BIN" run cancel "$run_id" 2>/dev/null || true
    bd update "$sprint_id" --status=cancelled >/dev/null 2>&1 || true
    echo ""
    return 0
fi
```

---

### F2 — MEDIUM: sprint_release — pipeline subshell prevents intercore_run_agent_update errors from being observed

**File:** hooks/lib-sprint.sh, lines 472-475 (sprint_release, ic path)

```bash
echo "$agents_json" | jq -r '.[] | select(...) | .id' | \
    while read -r agent_id; do
        intercore_run_agent_update "$agent_id" "completed" >/dev/null 2>&1 || true
    done
```

The `while read` loop runs in a subshell because it is on the right side of a pipe.
In Bash with `set -euo pipefail` (which the hook callers use), the exit status of the
pipe is the status of the last command — the subshell. But the `|| true` inside the
subshell masks all failures, so this is functionally benign. The real issue is
structural: any variables set inside the loop are invisible to the parent shell. This
is not a current bug since no variables are assigned there, but it is a fragile
pattern. The comment says "release failure is recoverable via the 60-minute TTL" —
acceptable — but the pipeline form should be replaced with process substitution for
consistency with the rest of the file:

```bash
while read -r agent_id; do
    intercore_run_agent_update "$agent_id" "completed" >/dev/null 2>&1 || true
done < <(echo "$agents_json" | jq -r '.[] | select(.status == "active" and .agent_type == "session") | .id')
```

This matches the established pattern in `intercore_sentinel_reset_all` and
`intercore_state_delete_all` (lib-intercore.sh lines 95-99 and 107-109).

---

### F3 — MEDIUM: migrate-sprints-to-ic.sh phase-alignment loop never advances `current_ic_phase` past the first phase

**File:** scripts/migrate-sprints-to-ic.sh, lines 94-105

The outer loop uses `current_ic_phase` to track where the ic run currently sits, but
the inner loop that updates `current_ic_phase` only triggers when `"$p" == "$current_ic_phase"`:

```bash
for p in "${phases_array[@]}"; do
    [[ "$p" == "$phase" ]] && break          # stop at target
    [[ "$p" == "$current_ic_phase" ]] || continue   # only process current phase
    ic run skip "$run_id" "$p" --reason="historical-migration" 2>/dev/null || { skip_failed=true; break; }
    # Find the next phase in the array
    for (( j=0; j<${#phases_array[@]}; j++ )); do
        if [[ "${phases_array[$j]}" == "$p" ]]; then
            current_ic_phase="${phases_array[$((j+1))]}"
            break
        fi
    done
done
```

On the first iteration `p="brainstorm"` and `current_ic_phase="brainstorm"`, so the
`continue` guard is skipped, the skip is issued, and `current_ic_phase` advances to
`"brainstorm-reviewed"`. On the second iteration `p="brainstorm-reviewed"` and
`current_ic_phase="brainstorm-reviewed"`, so it also fires. This logic is correct but
only because the outer loop visits phases in order and `current_ic_phase` is always
equal to `p` when the guard passes. However, if `ic run skip` fails mid-way
(`skip_failed=true; break`), `current_ic_phase` holds the phase that failed, not the
phase the run actually reached. The verification step at line 111 catches misalignment,
so data integrity is preserved, but the `echo "  → Created run $run_id (phase: $current_ic_phase)"` at
line 131 will log the wrong phase in this failure case (the run is cancelled so no
confusion persists, but the log is misleading and the `current_ic_phase` variable
at line 131 is not the phase the run ended up at anyway when cancelled).

More importantly: there is no guard for the case where `j+1` equals `${#phases_array[@]}`
(i.e., the skip loop reaches the last element "done"), causing an out-of-bounds array
access. In Bash this produces an empty string, but since "done" is also the target
phase for any fully-completed sprint, the break at `[[ "$p" == "$phase" ]]` will fire
first. So in practice the OOB cannot trigger, but the absence of a guard is
a latent fragility.

**Fix:** Add a bounds check in the inner j-loop and document the assumption:
```bash
if [[ $((j+1)) -lt ${#phases_array[@]} ]]; then
    current_ic_phase="${phases_array[$((j+1))]}"
fi
```

---

### F4 — LOW: intercore_check_or_die's fourth argument is accepted but silently dropped

**File:** hooks/lib-intercore.sh, lines 72-81

The function header comment says `$4=legacy_path (ignored)` but the `local` declaration
only captures three parameters:

```bash
intercore_check_or_die() {
    local name="$1" scope_id="$2" interval="$3"
    ...
}
```

All call sites were passing four arguments. Now that the fourth argument is ignored,
callers will pass it harmlessly, but static analysis tools and future authors reading
call sites will see four-argument calls to a three-parameter function. The comment
documents the intent, which is the right approach. The issue is that the `local`
declaration could capture the fourth parameter explicitly to make the "ignored" intent
visible and prevent shellcheck warnings about unused positional parameters at call sites:

```bash
local name="$1" scope_id="$2" interval="$3" _legacy_path="${4:-}"
```

The underscore prefix convention (`_legacy_path`) signals "intentionally unused" and
is already used elsewhere in this file (`_phases`, `_name`, `_fired`, `_ckpt_scope`).

Same applies to `intercore_sentinel_check_or_legacy` and `intercore_sentinel_reset_or_legacy`.

---

### F5 — LOW: sprint_read_state calls $INTERCORE_BIN directly, bypassing the wrapper

**File:** hooks/lib-sprint.sh, lines 243, 251, 262 (inside sprint_read_state ic-path)

Three calls in sprint_read_state bypass the `intercore_*` wrappers and invoke
`$INTERCORE_BIN` directly:

```bash
artifact_json=$("$INTERCORE_BIN" run artifact list "$run_id" --json 2>/dev/null) || artifact_json="[]"
events_json=$("$INTERCORE_BIN" run events "$run_id" --json 2>/dev/null) || events_json=""
agents_json=$("$INTERCORE_BIN" run agent list "$run_id" --json 2>/dev/null) || agents_json="[]"
```

`intercore_run_agent_list` already exists (lib-intercore.sh line 282) and handles the
availability check and empty-array fallback. The `run artifact list` and `run events`
calls have no wrappers yet, but the raw `$INTERCORE_BIN` access means: (a) if
`intercore_available` was checked at function entry but `ic` disappeared mid-function
(unlikely, but the pattern is inconsistent), there is no defensive fallback; (b) these
calls are not testable by swapping the wrapper. The agents call can be fixed immediately:

```bash
agents_json=$(intercore_run_agent_list "$run_id")
```

For `run artifact list` and `run events`, the preferred fix is adding thin wrappers
to lib-intercore.sh (`intercore_run_artifact_list`, `intercore_run_events`) following
the existing pattern. In the short term, the raw calls are acceptable given that
`intercore_available` is checked before the block, but the inconsistency should be noted.

---

### F6 — LOW: on-phase-advance and on-dispatch-change use multiple echo-pipe-jq invocations on the same $event

**File:** .clavain/hooks/on-phase-advance (lines 10-13), .clavain/hooks/on-dispatch-change (lines 10-12)

Each field extraction spawns a separate subshell:

```bash
run_id=$(echo "$event" | jq -r '.run_id // empty' 2>/dev/null) || exit 0
from=$(echo "$event" | jq -r '.from_state // "?"' 2>/dev/null) || from="?"
to=$(echo "$event" | jq -r '.to_state // "?"' 2>/dev/null) || to="?"
reason=$(echo "$event" | jq -r '.reason // ""' 2>/dev/null) || reason=""
```

These are observability-only hooks (no side effects, just stderr logging) so the
performance cost is negligible. However, for consistency with the established jq
pattern in sprint_find_active and sprint_read_state — where multiple fields are
extracted in one jq call — a single extraction is cleaner:

```bash
read -r run_id from to reason < <(echo "$event" | \
    jq -r '[.run_id // "", .from_state // "?", .to_state // "?", .reason // ""] | @tsv' 2>/dev/null) || exit 0
```

This is a style improvement, not a correctness issue. The existing approach is
acceptable for these small hooks given their observability-only role.

---

## Improvements (Non-Issue)

### I1: sprint_find_active — jq while-loop can be replaced with a single jq filter

The ic-path in `sprint_find_active` uses a Bash while loop to build `results` by
calling jq on each iteration. A single `jq` call over the filtered array would be more
efficient and idiomatic:

```bash
runs_json=$(intercore_run_list "--active") || runs_json="[]"
echo "$runs_json" | jq -c '[.[] | select(.scope_id != null and .scope_id != "") |
    {id: .scope_id, title: (.goal // "Untitled"), phase: (.phase // ""), run_id: .id}]'
```

The Bash fallback case would then handle the bd-show fallback for empty goals only if
needed. This eliminates N+1 jq invocations in the common case.

### I2: intercore_run_create — the _phases parameter comment mismatch

The wrapper accepts `$3=phases_json` but documents it as ignored. The call site in
`sprint_create` still passes the phases array. The comment explains why, but the
parameter name `_phases` should be used (matching the established underscore-prefix
convention) to prevent the "unused parameter" appearance for readers:

```bash
intercore_run_create() {
    local project="$1" goal="$2" _phases="${3:-}" scope_id="${4:-}" complexity="${5:-3}"
```

This is already in the current code — this improvement is confirming it is correct and
should remain.

### I3: Migration script — add `--scope` flag consistency note

The migration script uses `ic run list --active --scope="$bead_id"` for orphan
detection (line 69) but the lib-intercore.sh `intercore_run_list` wrapper passes flags
as `"$@"` (lib-intercore.sh line 267). The migration script calls `ic` directly
(appropriate for a one-shot script), but a comment noting the intentional direct-call
(vs using the wrapper) would reduce reviewer confusion.

---

## Verdict

**needs-changes** — Two medium findings (F1: orphaned ic run in verification failure path;
F2: pipeline subshell anti-pattern in sprint_release) and one medium finding in the
migration script (F3: phase-alignment loop bounds) should be addressed before this code
handles production sprint data. The low findings (F4, F5, F6) are quality improvements
that can be addressed in a follow-up pass.
