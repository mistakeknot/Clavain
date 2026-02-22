# Correctness Review: Sprint Handover — Kernel-Driven Sprint Skill

**Plan:** `/root/projects/Interverse/docs/plans/2026-02-20-sprint-handover-kernel-driven.md`
**PRD:** `/root/projects/Interverse/docs/prds/2026-02-20-sprint-handover-kernel-driven.md`
**Source:** `/root/projects/Interverse/os/clavain/hooks/lib-sprint.sh`
**Date:** 2026-02-20
**Reviewer:** Julik, Flux-drive Correctness Reviewer

---

## Invariants That Must Hold

Before examining failure modes, establish what must remain true after this migration:

1. **I1 — One sprint, one run:** Each sprint bead has exactly one associated ic run. No sprint bead may be orphaned (run cancelled) without the bead also being cancelled. No run may exist without a reachable bead (or explicit tombstone).
2. **I2 — Cache coherence:** `_SPRINT_RUN_ID` always resolves to the live run associated with the current `CLAVAIN_BEAD_ID`. If the association breaks, functions must fail explicitly, not silently use a stale ID.
3. **I3 — Claim exclusivity:** At most one session may hold an active claim on any sprint at any instant (60-minute TTL grace aside). A claim is not considered held until it is confirmed in ic.
4. **I4 — Phase monotonicity:** Sprint phase advances only forward through the canonical chain. No function may set a stale or skipped phase as current.
5. **I5 — Atomic artifact registration:** An artifact is either recorded or not; no partial/corrupt state is visible to readers.
6. **I6 — Idempotent re-entry:** All sprint functions survive re-invocation in the same Bash session (same sourcing, same `_SPRINT_RUN_ID` already set from a prior call).
7. **I7 — Bead cancellation on ic failure:** If `sprint_create` fails at any step after creating the ic run, the ic run must be cancelled. No zombie ic runs.

---

## Finding 1 (CRITICAL): `_SPRINT_RUN_ID` Cache Is Not Keyed to `bead_id` — Any Multi-Sprint Session Silently Reads the Wrong Run

**Severity:** Data corruption — wrong phase, wrong artifacts, wrong claim on a different sprint's run.

### The Code

Plan Task 1 defines:

```bash
_SPRINT_RUN_ID=""  # Session-scoped cache: resolved once at claim time

_sprint_resolve_run_id() {
    local bead_id="$1"
    [[ -z "$bead_id" ]] && { echo ""; return 1; }

    # Cache hit
    if [[ -n "$_SPRINT_RUN_ID" ]]; then
        echo "$_SPRINT_RUN_ID"
        return 0
    fi

    # Resolve from bead
    local run_id
    run_id=$(bd state "$bead_id" ic_run_id 2>/dev/null) || run_id=""
    ...
    _SPRINT_RUN_ID="$run_id"
    echo "$run_id"
}
```

### Failure Scenario

The session-start hook (`session-start.sh`) calls `sprint_find_active`, which iterates all active sprints. Suppose there are two active sprints: `iv-alpha` (run-111) and `iv-beta` (run-222).

1. `session-start.sh` calls `sprint_find_active`. Internally, if any code path calls `_sprint_resolve_run_id "iv-alpha"` first, `_SPRINT_RUN_ID` is populated with `run-111`.
2. The user picks `iv-beta` as their working sprint. `CLAVAIN_BEAD_ID=iv-beta`.
3. `sprint_claim "iv-beta" "$session"` calls `_sprint_resolve_run_id "iv-beta"`. Cache is non-empty (`run-111`). Cache hit. Returns `run-111`. The claim is registered on `run-111` (alpha's run), not `run-222`.
4. All subsequent operations — `sprint_advance`, `sprint_read_state`, `checkpoint_write` — operate on `run-111` while the user believes they are working on `iv-beta`.

This is a full cross-sprint pollution of state. Sprint alpha gets spurious agents registered, spurious phase advances, and spurious artifacts. Sprint beta receives no state writes whatsoever.

The scenario does not require concurrency to trigger. A single session that calls `sprint_find_active` and then works on any sprint other than the first one returned will be silently corrupting state.

### Why The Current (Pre-Plan) Code Does Not Have This Problem

The existing `lib-sprint.sh` does NOT have a global cache variable. Every function resolves `bd state "$sprint_id" ic_run_id` inline. That is N+1 calls per function, but the mapping is always correct because it is always keyed to the `sprint_id` argument supplied by the caller.

### Root Cause in the Plan

The plan's cache is a singleton global (`_SPRINT_RUN_ID=""`). The comment says "resolved once at claim time." This works correctly only if exactly one sprint is ever active per Bash session. The PRD does not state this restriction, `session-start.sh` uses `sprint_find_active` which iterates all active sprints, and the discovery path explicitly handles multiple returns. The invariant is violated from the very first call into a multi-sprint environment.

### Minimal Correct Fix

Key the cache to `bead_id` using a Bash associative array:

```bash
declare -A _SPRINT_RUN_ID_CACHE=()  # Associative array: bead_id → run_id

_sprint_resolve_run_id() {
    local bead_id="$1"
    [[ -z "$bead_id" ]] && { echo ""; return 1; }

    # Cache hit — keyed by bead_id
    if [[ -n "${_SPRINT_RUN_ID_CACHE[$bead_id]:-}" ]]; then
        echo "${_SPRINT_RUN_ID_CACHE[$bead_id]}"
        return 0
    fi

    local run_id
    run_id=$(bd state "$bead_id" ic_run_id 2>/dev/null) || run_id=""
    if [[ -z "$run_id" || "$run_id" == "null" ]]; then
        echo ""
        return 1
    fi

    _SPRINT_RUN_ID_CACHE[$bead_id]="$run_id"
    echo "$run_id"
}
```

Also update `sprint_create` (Plan Task 2, line 150) where it sets `_SPRINT_RUN_ID="$run_id"` directly to use `_SPRINT_RUN_ID_CACHE[$sprint_id]="$run_id"` instead.

The test in Task 14 Step 4 checks `[[ -n "$_SPRINT_RUN_ID" ]]`. That check will fail after the fix because the plain variable no longer exists. The test must be rewritten to verify `[[ "${_SPRINT_RUN_ID_CACHE[iv-test1]}" == "run-cached-123" ]]`.

---

## Finding 2 (HIGH): `sprint_create` Order of Operations — `ic_run_id` Written to Bead Before Verification Passes, Then Cancelled Without Clearing the Key

**Severity:** Orphaned bead-to-run mapping pointing at a cancelled run (I1, I7 violations).

### The Code (Plan Task 2)

```bash
# Store run_id on bead (join key for future sessions)
if [[ -n "$sprint_id" ]]; then
    bd set-state "$sprint_id" "ic_run_id=$run_id" >/dev/null 2>&1 || {
        echo "sprint_create: failed to write ic_run_id to bead (non-fatal)" >&2
    }
    bd set-state "$sprint_id" "token_budget=$token_budget" >/dev/null 2>&1 || true
fi

# Verify ic run is at brainstorm phase
local verify_phase
verify_phase=$(intercore_run_phase "$run_id") || verify_phase=""
if [[ "$verify_phase" != "brainstorm" ]]; then
    echo "sprint_create: ic run verification failed (phase=$verify_phase)" >&2
    "$INTERCORE_BIN" run cancel "$run_id" 2>/dev/null || true
    [[ -n "$sprint_id" ]] && bd update "$sprint_id" --status=cancelled >/dev/null 2>&1 || true
    echo ""
    return 1
fi
```

### Failure Scenario

1. `intercore_run_create` succeeds. `run_id="run-xyz"` is returned.
2. `bd set-state "$sprint_id" "ic_run_id=$run_id"` succeeds. The bead now permanently stores `ic_run_id=run-xyz`.
3. `intercore_run_phase "run-xyz"` returns something other than `"brainstorm"` (transient DB issue, ic race between create and phase read).
4. Cleanup: `"$INTERCORE_BIN" run cancel "run-xyz"` is called. `bd update "$sprint_id" --status=cancelled` is called.
5. However, `bd set-state "$sprint_id" "ic_run_id="` is NOT called. The bead retains `ic_run_id=run-xyz` pointing at the now-cancelled run.

Result: the bead is cancelled so it will not appear in `sprint_find_active`. But if any recovery or re-use path encounters this bead (rollback, reactivation, debugging), `_sprint_resolve_run_id` will resolve `run-xyz` — a cancelled run — and every subsequent ic call will fail with "run not found" or "run is terminal." The failure is silent at the cache level because the string is non-empty and non-null.

This bug also exists in the current `lib-sprint.sh` (line 112-118). The plan inherits it without fixing it.

### Minimal Fix

Either clear `ic_run_id` on the failure path, or — more robustly — write `ic_run_id` only AFTER verification succeeds:

```bash
# Verify ic run is at brainstorm phase FIRST
local verify_phase
verify_phase=$(intercore_run_phase "$run_id") || verify_phase=""
if [[ "$verify_phase" != "brainstorm" ]]; then
    "$INTERCORE_BIN" run cancel "$run_id" 2>/dev/null || true
    [[ -n "$sprint_id" ]] && bd update "$sprint_id" --status=cancelled >/dev/null 2>&1 || true
    echo ""
    return 1
fi

# Run is confirmed at brainstorm — now write the join key
bd set-state "$sprint_id" "ic_run_id=$run_id" >/dev/null 2>&1 || {
    echo "sprint_create: failed to write ic_run_id to bead, cancelling" >&2
    "$INTERCORE_BIN" run cancel "$run_id" 2>/dev/null || true
    bd update "$sprint_id" --status=cancelled >/dev/null 2>&1 || true
    echo ""
    return 1
}
```

The key point: the bead never holds an `ic_run_id` that points at a cancelled run if the join-key write is the last step before `echo "$sprint_id"`.

---

## Finding 3 (HIGH): Stale Agent Eviction in `sprint_claim` Swallows Failure — Two Active Session Agents Can Coexist

**Severity:** Claim exclusivity broken (I3 violation) — two sessions may simultaneously believe they hold a valid claim on the same sprint.

### The Code (Plan Task 6)

```bash
if [[ $age_minutes -lt 60 ]]; then
    echo "Sprint $sprint_id is active in session ${existing_name:0:8} (${age_minutes}m ago)" >&2
    intercore_unlock "sprint-claim" "$sprint_id"
    return 1
fi
# Stale — mark old agent as failed, then claim
local old_agent_id
old_agent_id=$(echo "$active_agents" | jq -r '.[0].id')
intercore_run_agent_update "$old_agent_id" "failed" >/dev/null 2>&1 || true

# Registration follows immediately
if ! intercore_run_agent_add "$run_id" "session" "$session_id" >/dev/null 2>&1; then
```

The `|| true` on the agent update call means: if `intercore_run_agent_update` fails (ic transient error, DB locked, network issue), the stale agent remains in `active` status. `intercore_run_agent_add` is then called. ic now sees two active session agents on the same run.

If a concurrent session (Session C) arrives after this and calls `sprint_claim`, it sees `active_count > 1`. The code checks `.[0].name` against `session_id`. If `.[0]` is the stale agent (not Session C), Session C will read a stale timestamp and may again try to evict. This creates a chain of multiple concurrent claims all believing they hold the lock.

### Minimal Fix

Make eviction failure non-retrying — unlock and return 1:

```bash
if ! intercore_run_agent_update "$old_agent_id" "failed" >/dev/null 2>&1; then
    echo "sprint_claim: failed to evict stale agent $old_agent_id, retry later" >&2
    intercore_unlock "sprint-claim" "$sprint_id"
    return 1
fi
```

---

## Finding 4 (HIGH): `sprint_advance` Error Handler Produces No Structured Output When `intercore_run_advance` Writes Nothing to Stdout

**Severity:** Callers cannot distinguish "gate blocked" from "ic infrastructure failure" — both produce exit 1 with empty stdout.

### The Code (Plan Task 8)

```bash
local result
result=$(intercore_run_advance "$run_id") || {
    local rc=$?
    local event_type from_phase to_phase
    event_type=$(echo "$result" | jq -r '.event_type // ""' 2>/dev/null) || event_type=""
    ...
    case "$event_type" in
        block) echo "gate_blocked|$to_phase|Gate prerequisites not met" ;;
        pause) echo "manual_pause|$to_phase|auto_advance=false" ;;
        *)
            if [[ -z "$event_type" && -z "$from_phase" ]]; then
                echo "sprint_advance: ic run advance returned unexpected result: ${result:-<empty>}" >&2
            fi
            ...
        ;;
    esac
    return 1
}
```

### Problem A: Empty `result` When ic Writes Only to Stderr

`result=$(cmd)` captures stdout only. If `intercore_run_advance` fails and writes its error to stderr (not stdout), `result` is the empty string. `echo "" | jq -r '.event_type // ""'` produces no output (jq on empty input exits non-zero or produces empty). `event_type=""`. The case falls through to `*`. The error goes to stderr only. The caller receives exit 1 with no stdout.

Callers in `commands/sprint.md` that pattern-match the structured reason string:

```bash
pause_reason=$(sprint_advance "$bead" "$phase") && ... || {
    case "$pause_reason" in
        gate_blocked*) ... ;;
        manual_pause*) ... ;;
        budget_exceeded*) ... ;;
        *) # empty — what now?
    esac
}
```

The empty case has no handling specified. The sprint stalls with no user-visible reason, no retry, and no log entry that traces the actual ic error.

### Problem B: `local rc=$?` Loses the Exit Code

Inside the error handler: `local rc=$?`. In Bash, `local` is itself a builtin that always exits 0. The actual failing exit code is captured first in `$?`, then immediately overwritten by `local`'s exit code of 0. `rc` is always 0. This does not break current logic because `rc` is unused in the handler — but if anyone adds `[[ $rc -ne 0 ]]` routing based on this, it will always be false.

The correct pattern: `local rc; rc=$?` — declare first, assign second.

### Minimal Fix

Emit a discriminator for infrastructure failures so callers can route them:

```bash
local result advance_rc
result=$(intercore_run_advance "$run_id" 2>/dev/null)
advance_rc=$?
if [[ $advance_rc -ne 0 ]]; then
    local event_type to_phase
    event_type=$(echo "$result" | jq -r '.event_type // ""' 2>/dev/null) || event_type=""
    to_phase=$(echo "$result" | jq -r '.to_phase // ""' 2>/dev/null) || to_phase=""

    case "$event_type" in
        block) echo "gate_blocked|${to_phase:-$current_phase}|Gate prerequisites not met"; return 1 ;;
        pause) echo "manual_pause|${to_phase:-$current_phase}|auto_advance=false"; return 1 ;;
        *)
            echo "ic_error|$current_phase|ic run advance failed (rc=$advance_rc)" >&2
            ;;
    esac
    return 1
fi
```

Callers can then match `ic_error|` to alert or retry with backoff, rather than silently looping.

---

## Finding 5 (MEDIUM): Bead Creation "Non-Fatal" Can Produce an Orphaned ic Run With No Reachable Identity

**Severity:** I1 and I7 violations — ic run with no valid bead-to-run join key; run unreachable from any sprint function.

### The Code (Plan Task 2)

```bash
local sprint_id=""
if command -v bd &>/dev/null; then
    sprint_id=$(bd create ...) || sprint_id=""
    ...
fi

local scope_id="${sprint_id:-sprint-$(date +%s)}"

local run_id
run_id=$(intercore_run_create "$(pwd)" "$title" "$phases_json" "$scope_id" ...) || run_id=""

if [[ -z "$run_id" ]]; then
    ...
    return 1
fi

# Store run_id on bead (join key for future sessions)
if [[ -n "$sprint_id" ]]; then
    bd set-state "$sprint_id" "ic_run_id=$run_id" ...
fi
```

### Scenario: Bead Creation Fails, ic Run Succeeds

1. `bd create` fails. `sprint_id=""`.
2. `scope_id="sprint-1708000000"` (timestamp fallback).
3. `intercore_run_create` succeeds. `run_id="run-abc"`.
4. Verification passes.
5. `if [[ -n "$sprint_id" ]]` is false. `ic_run_id` is never written anywhere.
6. Cache population: `_SPRINT_RUN_ID_CACHE[""]="run-abc"` (with F1 fix applied) — key is empty string.
7. `sprint_create` echoes `""` (empty sprint_id).

The caller receives `""` as `CLAVAIN_BEAD_ID`. Every subsequent call `_sprint_resolve_run_id ""` hits the guard `[[ -z "$bead_id" ]] && return 1` and fails. The ic run `run-abc` is now entirely unreachable. `sprint_find_active` will return it (it has `scope_id="sprint-1708000000"`) but no bead-based lookup will ever match it. It will sit in ic as an active run forever, consuming budget headroom in the global run list, until manually cancelled.

The PRD states "Bead stays as user-facing identity." This means a bead IS required for sprint identity. Bead failure cannot be non-fatal if the entire rest of the architecture depends on `bead_id → ic_run_id` as the join key. The plan contradicts itself.

### Fix

Treat bead creation failure as fatal in `sprint_create`, consistent with the ic-only architecture:

```bash
local sprint_id=""
if command -v bd &>/dev/null; then
    sprint_id=$(bd create ...) || sprint_id=""
fi
if [[ -z "$sprint_id" ]]; then
    echo "sprint_create: bead creation failed — bead required for sprint identity" >&2
    echo ""
    return 1
fi
```

---

## Finding 6 (MEDIUM): `sprint_next_step` Mapping — Plan Maps `executing → ship` but PRD Says `executing → quality-gates`

**Severity:** Functional regression — the `quality-gates` skill is silently eliminated from the sprint workflow.

### The Discrepancy

**PRD F3 acceptance criteria:**
```
Phase-to-step mapping preserved: executing → quality-gates
```

**Plan Task 9 `sprint_next_step`:**
```bash
executing) echo "ship" ;;
```

**Current `lib-sprint.sh` `sprint_next_step` (lines 726-744):**
```
executing → shipping (via _sprint_transition_table) → ship command
```

The current code maps `executing` → next-phase `shipping` → command `ship`. This is effectively `executing → ship`. The PRD says it should be `executing → quality-gates`. Either the PRD is wrong (quality-gates was removed before the PRD was written and the PRD was not updated), or the plan is missing a phase.

If `quality-gates` is a real sprint skill that enforces shipping readiness checks, removing it from the `sprint_next_step` output means the orchestrator will skip it and jump directly to `ship`. This is a silent regression that passes all tests because no test covers the `quality-gates` command name.

### Required Action

Clarify with the team before Task 9 implementation whether `quality-gates` is intentionally removed. If it is removed, update the PRD acceptance criterion. If it should remain, restore `executing) echo "quality-gates" ;;`.

---

## Finding 7 (MEDIUM): Jq Stub Returns Integer `"3"` but 6+ Existing Tests Expect String Labels

**Severity:** Immediate test failures on Task 12 application — the test suite gates merge.

### The Code (Plan Task 12)

```bash
if ! command -v jq &>/dev/null; then
    ...
    sprint_classify_complexity() { echo "3"; }
    ...
fi
```

### The Tests

`test_lib_sprint.bats` tests 33-39 all check `sprint_classify_complexity` output against string labels (`"simple"`, `"medium"`, `"complex"`). These tests exercise the beads fallback path because the tests mock `bd()` to return `""` for `ic_run_id`, which pushes the function to the text-analysis path. The text-analysis path (lines 909-1040) correctly returns integers. But:

- Test 33: `assert_output "simple"` — the function returns `"2"` (integer), not `"simple"`.
- Test 36: `assert_output "medium"` — the function returns `"3"`, not `"medium"`.
- Test 38: `assert_output "medium"` — same.

These tests are currently passing because the test environment does not mock `intercore_available`, so the ic path is skipped (ic is unavailable in the test environment) and the function falls through to the text analysis. The text analysis returns integers. But the assertions expect strings.

Wait — let me re-examine. The test mocks `bd()` to return `""` for state calls. Without ic available, the function hits the text analysis. Text analysis returns integers like `"2"`, `"3"`. But the assertions say `"simple"`, `"medium"`. These tests should already be failing.

The existing test 36 (`assert_output "medium"`) with empty description: the actual function returns `"3"` for empty description. `assert_output "medium"` would fail against `"3"`. This means either these tests are already failing (indicating the test suite is broken), or `sprint_classify_complexity` with an empty description hits a different path. Looking at lines 931: `[[ -z "$description" ]] && { echo "3"; return 0; }` — the function does echo `"3"`, not `"medium"`. So test 36 should already be failing.

This is a pre-existing issue in the test suite that the plan does not address. Task 14 must include fixing all complexity tests to match integer outputs, not just the ones explicitly called out for deletion.

---

## Finding 8 (LOW): `sprint_record_phase_tokens` sqlite Query Uses `CLAUDE_SESSION_ID` Without a Null Guard That Prevents Cross-Session Overcounting

**Severity:** Token budget inaccuracy — premature budget exhaustion alerts.

### The Code (Plan Task 5, also lines 449-450 of current source)

```bash
actual_tokens=$(sqlite3 "$db_path" \
    "SELECT COALESCE(SUM(...), 0) FROM agent_runs WHERE session_id='${CLAUDE_SESSION_ID:-none}'" 2>/dev/null)
```

If `CLAUDE_SESSION_ID` is unset, the query uses `WHERE session_id='none'`. If any rows in the database have `session_id='none'` (from prior sessions where the variable was also unset), the sum includes all their tokens. A sprint that runs in environments without `CLAUDE_SESSION_ID` set will accumulate inflated token totals across its entire history.

Additionally, the query has no time bound. All agent runs across all time for this session ID are summed. If a session runs multiple phases sequentially, the second call to `sprint_record_phase_tokens` will include tokens from all prior phases in addition to the current one, double-counting all prior phase tokens.

The fix adds a time range predicate (e.g., `AND started_at > $phase_start_time`) or uses a separate per-dispatch token write that ic's own aggregation handles. Both require knowing when the current phase started.

---

## Finding 9 (LOW): Cache Test Is Untestable as Written Due to Bash Subshell Variable Isolation

**Severity:** False confidence — the test passes regardless of whether caching works.

### The Code (Plan Task 14 Step 4)

```bash
@test "_sprint_resolve_run_id caches after first call" {
    local call_count=0
    bd() {
        case "$1" in
            state)
                call_count=$((call_count + 1))
                echo "run-cached-123"
                ;;
        esac
    }
    export -f bd
    _source_sprint_lib

    local first second
    first=$(_sprint_resolve_run_id "iv-test1")
    second=$(_sprint_resolve_run_id "iv-test1")
    [[ "$first" == "run-cached-123" ]]
    [[ "$second" == "run-cached-123" ]]
    [[ -n "$_SPRINT_RUN_ID" ]]
}
```

Three problems:

1. `call_count` is a local variable in the test. Both `bd()` invocations run in subshells (`$(...)`). Each subshell gets a copy of `call_count` initialized to 0 and increments it to 1. The increment is discarded when the subshell exits. `call_count` in the parent is always 0. The test cannot verify that bd is called only once.

2. Both `_sprint_resolve_run_id` calls also run in subshells (`first=$(...)`, `second=$(...)`). The associative array `_SPRINT_RUN_ID_CACHE` modified inside the first subshell is discarded. The second subshell starts fresh, calls `bd state` again (another `call_count=1` in its own subshell), and returns the value. Caching is never actually exercised. Both calls hit the "miss" path.

3. `[[ -n "$_SPRINT_RUN_ID" ]]` will always fail after F1 fix because `_SPRINT_RUN_ID` no longer exists.

The correct test structure calls `_sprint_resolve_run_id` in the current shell:

```bash
@test "_sprint_resolve_run_id caches run_id per bead_id" {
    bd() { echo "run-cached-123"; }
    export -f bd
    _source_sprint_lib

    # Call in current shell to observe cache population
    _sprint_resolve_run_id "iv-test1" > /dev/null
    # Cache must now have the entry
    [[ "${_SPRINT_RUN_ID_CACHE[iv-test1]}" == "run-cached-123" ]]

    # Second call with different bead_id must NOT reuse cached value
    bd() { echo "run-different-456"; }
    export -f bd
    _sprint_resolve_run_id "iv-test2" > /dev/null
    [[ "${_SPRINT_RUN_ID_CACHE[iv-test2]}" == "run-different-456" ]]
    # First entry still intact
    [[ "${_SPRINT_RUN_ID_CACHE[iv-test1]}" == "run-cached-123" ]]
}
```

---

## Finding 10 (LOW): `enforce_gate` Silently Ignores `target_phase` in the ic Path — Misleading Function Signature

**Severity:** API contract mismatch — callers that pass `target_phase` for cross-validation get a different gate evaluated.

### The Code (Plan Task 7)

```bash
enforce_gate() {
    local bead_id="$1"
    local target_phase="$2"
    local artifact_path="${3:-}"

    local run_id
    run_id=$(_sprint_resolve_run_id "$bead_id") || return 0
    intercore_gate_check "$run_id"
}
```

`target_phase` is accepted as a parameter but never used. `intercore_gate_check` evaluates the run's current next transition as determined by ic's internal state machine — it does not accept a target phase parameter. A caller that passes `enforce_gate "iv-alpha" "plan-reviewed"` believing it is checking whether the gate for `plan-reviewed` is clear will actually get the gate check for whatever ic considers the run's current pending transition.

This behavior is already present in the existing ic-primary path (documented in the existing code comments). Removing the beads fallback makes it permanent. The correct fix is to either rename the parameter to signal its no-op nature or remove it from the signature, with a comment explaining that ic is the authoritative transition arbiter.

```bash
enforce_gate() {
    local bead_id="$1"
    # Note: target_phase is intentionally ignored — ic determines the applicable
    # transition from its own state machine. Pass "" if calling from ic-only code.
    local _unused_target_phase="$2"
    local _unused_artifact_path="${3:-}"

    local run_id
    run_id=$(_sprint_resolve_run_id "$bead_id") || return 0
    intercore_gate_check "$run_id"
}
```

---

## Summary Table

| # | Severity | Issue | Invariant Broken |
|---|----------|-------|-----------------|
| F1 | CRITICAL | `_SPRINT_RUN_ID` singleton cache is not keyed to `bead_id` — first-resolved run bleeds into all subsequent sprint operations in the same session | I2, I3 |
| F2 | HIGH | `ic_run_id` written to bead before phase verification; cleanup path does not clear it on cancel — orphan join key | I1, I7 |
| F3 | HIGH | Stale agent eviction `|| true` silently proceeds with two active session agents if eviction fails | I3 |
| F4 | HIGH | `sprint_advance` error handler emits empty stdout when ic writes nothing to stdout — callers cannot distinguish gate-blocked from infrastructure failure | I4 |
| F5 | MEDIUM | Bead creation labeled "non-fatal" but the entire architecture depends on the bead→run join key — bead failure produces unreachable orphan ic run | I1, I7 |
| F6 | MEDIUM | `sprint_next_step` maps `executing → ship` but PRD acceptance criterion says `executing → quality-gates` — silent regression | I4 |
| F7 | MEDIUM | Jq stub and 6+ existing tests expect string complexity labels; real function returns integers; Task 14 scope does not include these tests | Testing |
| F8 | LOW | `CLAUDE_SESSION_ID:-none` fallback may aggregate tokens across all sessions lacking a session ID; no time bound on the query | Budget accuracy |
| F9 | LOW | Cache test is structurally untestable — Bash subshell isolation means call_count is always 0 and the associative array is never populated in the observable scope | Testing |
| F10 | LOW | `enforce_gate` silently ignores `target_phase` in ic path — misleading signature with no comment | API contract |

---

## Recommended Action Before Implementation

1. **Must fix before Task 1:** Redesign the cache as `declare -A _SPRINT_RUN_ID_CACHE=()` keyed by `bead_id` (F1). This is the structural foundation everything else depends on.

2. **Fix in Task 2:** Reorder `sprint_create` so that `ic_run_id` is written to the bead only AFTER phase verification succeeds, not before (F2). Treat bead creation failure as fatal (F5).

3. **Fix in Task 6:** Make stale agent eviction failures cause `return 1` rather than proceeding with a corrupt agent list (F3).

4. **Fix in Task 8:** Capture exit code before `local`, emit `ic_error|` structured output for infrastructure failures, remove stderr-only error path that leaves callers with empty stdout (F4).

5. **Resolve before Task 9:** Confirm with the team whether `quality-gates` is intentionally dropped from the `executing` step mapping. Update PRD or restore the mapping in the plan (F6).

6. **Fix in Task 14:** Add multi-bead cache isolation test. Include complexity tests in the rewrite scope. Restructure cache test to avoid subshell isolation (F7, F9).

7. **Non-blocking:** F8 (token accounting time bound) and F10 (gate signature documentation) can be addressed as follow-up items, as they do not break invariants in the common case.
