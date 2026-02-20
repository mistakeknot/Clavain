# E3 Hook Cutover — Architecture Review

**Date:** 2026-02-19
**Scope:** E3 milestone: migrate sprint runtime from beads to intercore (ic)
**Changed files:**
- `hooks/lib-intercore.sh` — ic CLI wrappers, temp-file sentinel fallback removed
- `hooks/lib-sprint.sh` — sprint CRUD rewritten for ic-primary with beads fallback
- `hooks/lib-gates.sh` — deprecation comment added
- `.clavain/hooks/on-phase-advance` — new ic event reactor hook
- `.clavain/hooks/on-dispatch-change` — new ic event reactor hook
- `scripts/migrate-sprints-to-ic.sh` — one-time migration script

---

## 1. Structural Overview

The E3 cutover is a coherent backend migration. The stated pattern — ic-primary with
beads fallback — is consistently implemented across all six sprint CRUD functions
(`sprint_create`, `sprint_find_active`, `sprint_read_state`, `sprint_set_artifact`,
`sprint_record_phase_completion`, `sprint_claim`, `sprint_release`, `sprint_advance`,
`sprint_should_pause`, `sprint_classify_complexity`, `checkpoint_write`,
`checkpoint_read`). The fallback path is isolated inside each function and does not
cross into the primary path, which is correct.

The bead join key (`ic_run_id` stored on the bead via `bd set-state`) is the single
coordination point between the two systems. Every ic-path function reads this key first
before attempting any ic operation. This is a clear contract: the presence of
`ic_run_id` on the bead is the migration flag.

The lib-intercore.sh cutover (removing temp-file sentinel fallback) is a separate
concern bundled in the same diff. Both changes are directionally correct and belong
together since the sentinel wrappers support the same migration boundary.

---

## 2. Boundaries and Coupling

### 2.1 The `ic_run_id` Join Key

The bead is the primary identity for a sprint externally (all callers use the bead ID).
The ic run ID is an internal join key stored on the bead and read back on every ic-path
call. This introduces a soft dependency on beads even after the ic primary path is
active: `bd state "$sprint_id" ic_run_id` is called at the top of every major sprint
function in the ic path.

This is acceptable for the transition, but has a long-term cost: the ic path is
dependent on beads for run resolution. If the intent is to eventually make beads
optional, the join key lookup needs a secondary resolution path (e.g., ic run list
--scope). The current code has `sprint_find_active` using the ic `scope_id` field
correctly for discovery, but individual state functions still go through beads for the
join key.

### 2.2 `intercore_check_or_die` at existing call sites

`intercore_check_or_die` is called with four arguments at all existing call sites
(`auto-compound.sh`, `auto-drift-check.sh`, `auto-publish.sh`, `catalog-reminder.sh`,
`session-handoff.sh`), for example:

```bash
intercore_check_or_die "$INTERCORE_STOP_DEDUP_SENTINEL" "$SESSION_ID" 0 "/tmp/clavain-stop-${SESSION_ID}"
```

The new signature in `lib-intercore.sh` only declares three locals:
```bash
intercore_check_or_die() {
    local name="$1" scope_id="$2" interval="$3"
```

The fourth argument is silently dropped. Bash does not error on extra positional
arguments, so this is a backward-compatible change — the $4 legacy path is simply
ignored. However, the function signature divergence is a maintenance hazard: if a
future author reads an existing call site and the function signature, the mismatch will
create confusion about what the fourth argument does. The call sites still pass a
temp-file path that the implementation now ignores. These call sites should be cleaned
up (removing the fourth argument) to accurately reflect the new contract.

### 2.3 Fail-open for sentinel unavailability

When `intercore_available` returns false (ic binary missing or unhealthy), all sentinel
checks in the new `intercore_check_or_die` are bypassed and the hook proceeds:

```bash
if intercore_available; then
    intercore_sentinel_check "$name" "$scope_id" "$interval" || exit 0
    return 0
fi
# No ic available — allow (fail-open)
return 0
```

The old code fell through to the temp-file path as a backup throttle. The new code
has no throttle at all when ic is unavailable. For sentinel use cases that are
non-critical (catalog-reminder, drift-check), fail-open is acceptable. For
`auto-compound.sh` and `session-handoff.sh` where deduplication of the stop cycle
matters, fail-open means multiple hooks can fire concurrently in a degraded environment.
The comment in `session-handoff.sh:39` acknowledges this: the fallback "prevents loops
in the common case." The behavioral change is real but documented and intentional.

### 2.4 `sprint_advance` error parsing: `result` variable scoping

In `sprint_advance`, the `|| { ... }` block reads `$result` after `intercore_run_advance`
returns non-zero:

```bash
result=$(intercore_run_advance "$run_id") || {
    local rc=$?
    local event_type from_phase to_phase
    event_type=$(echo "$result" | jq -r '.event_type // ""' 2>/dev/null) || event_type=""
```

When `intercore_run_advance` exits non-zero, `$result` contains stdout from the
failed command. The `ic` binary may or may not emit JSON on a failure exit. If ic
emits nothing (empty stdout on error), `jq` will receive an empty string and produce
empty values — the `*` case handles this and falls through to a phase-check recovery.
This is safe but relies on ic never emitting non-JSON to stdout on error. If ic emits
a plain error message, jq will silently fail (due to `2>/dev/null`) and produce empty
event_type, triggering the recovery branch. This is the correct behavior but the
assumption should be documented.

### 2.5 Migration script uses `--phases` flag that does not exist in ic

The migration script passes `--phases="$PHASES_JSON"` to `ic run create`:

```bash
run_id=$(ic run create --project="$(pwd)" --goal="$title" --phases="$PHASES_JSON" --scope-id="$bead_id" 2>/dev/null) || run_id=""
```

The `lib-intercore.sh` wrapper comment explicitly states:
```bash
# NOTE: --phases is not a valid ic flag. The sprint phase chain matches
# intercore's DefaultPhaseChain, so no custom phases needed.
```

And the wrapper omits `--phases` from its args array. But the migration script calls
`ic` directly and passes `--phases`. If `ic run create` does not accept `--phases`,
this flag is silently ignored (due to `2>/dev/null`) but the run is still created —
at `DefaultPhaseChain` which matches the sprint phases. This is acceptable for the
migration but creates an inconsistency: the wrapper is correct, the migration script
is not. If `ic` were to reject unknown flags in a future version, the migration would
silently fail to create runs.

### 2.6 `on-dispatch-change` and `on-phase-advance` hook registration

Both new reactor hooks are placed in `.clavain/hooks/` rather than `hooks/`. The
AGENTS.md documentation states hook scripts live in `hooks/` and are registered via
`hooks/hooks.json`. The `.clavain/hooks/` path is the ic event reactor path, distinct
from Claude Code's hook system. This is architecturally correct — these are ic event
hooks, not Claude Code hooks. However, `hooks.json` does not reference them (they are
registered with ic directly), and neither `AGENTS.md` nor `CLAUDE.md` mentions the
`.clavain/hooks/` directory. The architecture is correct; the documentation gap creates
risk that future contributors will not know these hooks exist or how they are invoked.

---

## 3. Pattern Analysis

### 3.1 Consistent ic-primary-with-fallback pattern

The pattern is uniform across all sprint functions and is the correct structural choice
for a migration with a live system. No variations or shortcuts were introduced.

### 3.2 Phase transition table duplication

The `_sprint_transition_table` and `phases_array` in the migration script define the
same ordered phase sequence. The migration script hardcodes:

```bash
phases_array=("brainstorm" "brainstorm-reviewed" "strategized" "planned" "plan-reviewed" "executing" "shipping" "done")
```

And `lib-sprint.sh` encodes the same sequence in `_sprint_transition_table`. This
duplication is intentional (the migration script is one-shot and standalone), but if
phases change in ic's DefaultPhaseChain, both locations need updating. The migration
script's comment explains why `ic run skip` is used over `ic run advance`, which is
the critical domain knowledge that prevents agent-spawn side effects during migration.
This is correctly documented inline.

### 3.3 `sprint_read_state` calls `$INTERCORE_BIN` directly (three places)

Inside `sprint_read_state`, there are three direct calls to `$INTERCORE_BIN` that bypass
the wrapper functions:

```bash
artifact_json=$("$INTERCORE_BIN" run artifact list "$run_id" --json 2>/dev/null)
events_json=$("$INTERCORE_BIN" run events "$run_id" --json 2>/dev/null)
agents_json=$("$INTERCORE_BIN" run agent list "$run_id" --json 2>/dev/null)
```

The `intercore_run_agent_list` wrapper exists and is used elsewhere. The artifact and
events calls have no wrapper equivalents yet. This is a mild consistency gap: if the
ic CLI flag changes, these calls need updating separately from the wrappers. The
wrapper coverage is incomplete. This is not a blocking issue but represents
maintenance debt.

### 3.4 Removed lock ordering comment

The old `sprint_advance` contained:
```bash
# NOTE: sprint_record_phase_completion acquires "sprint" lock inside this "sprint-advance" lock.
# Lock ordering: sprint-advance > sprint. Do not reverse.
```

This comment was removed. In the ic primary path, `sprint_record_phase_completion`
is a no-op (auto-recorded), so the nested lock no longer fires. In the beads fallback
path, `sprint_advance` calls `sprint_record_phase_completion` which still acquires
the "sprint" lock inside the "sprint-advance" lock. The lock ordering constraint
still exists in the fallback path. The comment was correct documentation and its
removal introduces a latent hazard for the fallback code path.

### 3.5 `sprint_should_pause` pre-flight gate check with ic

In `sprint_should_pause`, when `run_id` is available, `intercore_gate_check` is called
as a pre-flight check:

```bash
if ! intercore_gate_check "$run_id" 2>/dev/null; then
    echo "gate_blocked|$target_phase|Gate prerequisites not met"
    return 0
fi
return 1
```

But `sprint_advance` in the ic path calls `intercore_run_advance` directly, which also
evaluates gates internally. The `sprint_should_pause` is called from the beads fallback
path inside `sprint_advance`. The ic primary path in `sprint_advance` does NOT call
`sprint_should_pause` — it relies entirely on `ic run advance`'s internal gate logic.
This means the pre-flight gate check in `sprint_should_pause`'s ic branch is dead code
— it is only reachable if something other than `sprint_advance` calls `sprint_should_pause`
directly with an ic-backed sprint. The function contract says it's a pre-flight check,
but the primary caller no longer exercises it. This is accidental dead code in the
sprint_should_pause ic branch.

---

## 4. Simplicity and YAGNI

### 4.1 `sprint_read_state` ic path spawns four ic CLI calls

The ic primary path in `sprint_read_state` makes four sequential CLI calls:
1. `intercore_run_status` (run JSON)
2. `$INTERCORE_BIN run artifact list`
3. `$INTERCORE_BIN run events`
4. `$INTERCORE_BIN run agent list`

Each call requires process spawning, ic binary startup, and SQLite access. If this
function is called in a hot path (session-start context injection), it is 4x slower than
the old single `bd state` read. The old `sprint_scan.sh` reads all sprint state in a
tight loop over active sprints. With the ic path, each sprint in the active list
triggers four ic calls. At scale (multiple active sprints), this is an O(4n) CLI-call
pattern versus the old O(3n) beads pattern (phase, artifacts, phase_history). The
comments in `sprint_find_active` note the N+1 elimination for discovery. The same
concern applies to state reads. Whether this is acceptable depends on session-start
latency requirements. It is not a blocking concern for the migration but should be
benchmarked.

### 4.2 `sprint_should_pause` ic path check is inverted relative to `auto_advance`

In the beads fallback, `sprint_should_pause` checks `auto_advance=false` explicitly.
In the ic path, `auto_advance` is a field on the ic run that `ic run advance` reads
internally — so `sprint_should_pause`'s ic branch skips the `auto_advance` check and
only does a gate check. The comment says "ic run advance handles pause internally
(auto_advance field on run)." This means `sprint_should_pause` with ic is not a full
analog to the beads version — it cannot tell callers "pause because auto_advance=false"
in the ic path. If a caller needs to distinguish gate-blocked from manual-pause before
calling advance, the ic path does not provide that information pre-advance. This is an
intentional trade-off (ic is the authority) but is not documented.

### 4.3 Migration script phase alignment loop is O(n^2)

The phase alignment loop iterates `phases_array` once per phase to find the skip
target, and inside the loop iterates again to find the next phase index:

```bash
for p in "${phases_array[@]}"; do
    [[ "$p" == "$phase" ]] && break
    [[ "$p" == "$current_ic_phase" ]] || continue
    ic run skip "$run_id" "$p" --reason="historical-migration" ...
    for (( j=0; j<${#phases_array[@]}; j++ )); do
        if [[ "${phases_array[$j]}" == "$p" ]]; then
            current_ic_phase="${phases_array[$((j+1))]}"
```

With a fixed array of 8 phases, this is O(1) in practice. For a one-time migration
script this is irrelevant. The inner loop to find the next phase index is unnecessary
complexity — a `next_phase` tracking variable incremented alongside the outer loop
would eliminate it. This is a simplicity observation, not a blocking issue.

---

## 5. Key Risk: `sprint_create` Cancellation Does Not Cancel the ic Run

In `sprint_create`, when `bd set-state "$sprint_id" "ic_run_id=..."` fails, the code
correctly cancels both the bead and the ic run:

```bash
bd set-state "$sprint_id" "ic_run_id=$run_id" >/dev/null 2>&1 || {
    "$INTERCORE_BIN" run cancel "$run_id" 2>/dev/null || true
    bd update "$sprint_id" --status=cancelled >/dev/null 2>&1 || true
```

However, `$INTERCORE_BIN` may be unset at this point if `intercore_available` was called
via `intercore_run_create` and `INTERCORE_BIN` was set by it, but then something reset
it. Looking at `intercore_available()`: it sets `INTERCORE_BIN` as a module-level
variable (no `local`) and caches it. Once set, it persists for the shell session.
There is no path that unsets it between `intercore_run_create` and the error handler.
This is safe.

However: if `intercore_run_create` returns a run_id but `intercore_available` later
returns false (e.g., if health check is cached), the cancel call would be skipped (the
cancel uses `$INTERCORE_BIN` directly, not through a wrapper). On inspection,
`INTERCORE_BIN` is set as a module-level variable. The cancel call is safe as written.

---

## 6. Documentation Gaps

- `.clavain/hooks/` directory and its purpose are undocumented in AGENTS.md and CLAUDE.md
- `intercore_check_or_die` comment says "Args: $1=name, $2=scope_id, $3=interval, $4=legacy_path (ignored)" but all existing call sites still pass the fourth argument. The cleanup plan is not specified.
- Removed lock-ordering comment for `sprint-advance > sprint` in beads fallback path
- `sprint_should_pause` ic path limitations (cannot distinguish gate-blocked from auto_advance=false pre-advance) are not documented in the function contract

---

## 7. Summary

The E3 cutover is structurally sound. The ic-primary-with-beads-fallback pattern is
implemented consistently, the join key design is clear, and the migration script has
strong correctness properties (use of `ic run skip` to avoid triggering SpawnHandler,
phase verification before writing the join key, orphan cleanup). The main risks are:

1. All existing `intercore_check_or_die` call sites pass a now-ignored fourth argument
   (documentation and call-site drift, not a runtime failure)
2. The migration script passes `--phases` to `ic run create` directly, which the
   wrapper explicitly avoids (flag may be silently ignored or may fail in future ic versions)
3. The `sprint_should_pause` ic branch is effectively dead code in the primary
   sprint advance flow
4. The beads fallback path's lock ordering constraint (`sprint-advance > sprint`) is
   no longer documented
5. `.clavain/hooks/` is undocumented in the development guides
