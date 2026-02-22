# Quality Review: Sprint Handover Kernel-Driven Plan

**Target:** `/root/projects/Interverse/docs/plans/2026-02-20-sprint-handover-kernel-driven.md`
**Source files reviewed:**
- `/root/projects/Interverse/os/clavain/hooks/lib-sprint.sh` (1276 lines, current)
- `/root/projects/Interverse/os/clavain/tests/shell/test_lib_sprint.bats` (1003 lines, current)
**Date:** 2026-02-20

---

## Executive Summary

The plan is architecturally sound and the bash patterns are mostly idiomatic. There are five issues that warrant attention before implementation: a session-scoped global cache that breaks test isolation, three stdout discipline violations in the proposed code, incomplete jq stubs, a flawed test for `_sprint_resolve_run_id` caching, and a semantic mismatch in `sprint_next_step` that the plan introduces (or fails to fix).

---

## 1. Bash Idioms

### 1.1 Global cache variable — session scope is process scope (Medium)

The plan introduces `_SPRINT_RUN_ID=""` as a file-level global and writes to it from `_sprint_resolve_run_id`. This is called a "session-scoped cache" but in bash sourced files, "session" means the lifetime of the current shell process. There are two practical consequences.

**Test isolation:** Each bats test calls `_source_sprint_lib` which `source`s the file inside the same bats process. The double-source guard (`_SPRINT_LOADED`) is unset, but `_SPRINT_RUN_ID` is not reset — it persists across tests in the same bats run because bats test cases share one shell process. A test that happens to set `_SPRINT_RUN_ID` will silently corrupt subsequent tests.

The plan's `_sprint_resolve_run_id` caching test (Task 14, Step 4) does not account for this: if a prior test left `_SPRINT_RUN_ID` non-empty, `bd()` will never be called, `call_count` stays 0, and the test passes vacuously.

Fix: reset `_SPRINT_RUN_ID` in the setup() block alongside the other guard variables:

```bash
# in setup()
unset _SPRINT_LOADED _GATES_LOADED _PHASE_LOADED _DISCOVERY_LOADED _LIB_LOADED _SPRINT_RUN_ID
```

And the variable declaration in lib-sprint.sh must use `declare` with no initialiser guard check, so re-sourcing within a test resets it:

```bash
# After _SPRINT_LOADED guard, before jq check
_SPRINT_RUN_ID="${_SPRINT_RUN_ID:-}"  # Declared but not clobbered if already set
```

Actually the simpler and more correct fix is to just include it in the explicit setup reset list in the test file, since the production code is fine not clobbering it on re-source.

### 1.2 `sprint_require_ic` — `return 0` at end is unnecessary noise (Low)

```bash
sprint_require_ic() {
    if ! intercore_available; then
        echo "..." >&2
        return 1
    fi
    return 0   # <-- unnecessary
}
```

A function that falls through without a `return` exits with the last command's status, which here is the `if` conditional — already 0. The explicit `return 0` is not wrong but adds noise. The existing codebase omits it in comparable guards. Follow local style.

### 1.3 Arithmetic with `$((...))` vs `$((...))`-only — consistent in plan (Pass)

All arithmetic uses `$(( ... ))` consistently with the existing codebase. No issues.

### 1.4 Quoting — adequate (Pass)

Variable expansions in the new code are uniformly quoted. The `--arg id "$scope_id"` style (jq string injection) is correct. `bd` invocations that pass concatenated arguments use the right style matching the existing code.

### 1.5 `local` declarations — one issue in proposed sprint_record_phase_tokens (Medium)

In the Task 5 replacement:

```bash
local new_total=$(( current_spent + estimate ))
```

This pattern is found in the *existing* code (line 437, 477) and the plan carries it forward unchanged. In bash, `local var=$(command)` masks the exit status of `$(command)` — the `local` builtin always returns 0. For arithmetic expansion this is harmless (arithmetic errors cause `set -e` to fire on the expansion itself, not the local assignment), but it is a latent portability issue. The plan should use:

```bash
local new_total
new_total=$(( current_spent + in_tokens + out_tokens ))
```

The existing file has this same pattern at lines 437 and 477. Since those lines are being replaced, the plan is an opportunity to fix it. The plan does not take it.

### 1.6 `set -euo pipefail` — not applicable to sourced library (Pass)

`lib-sprint.sh` is a sourced library, not an executed script. `set -e` in a sourced file would exit the parent shell on any non-zero return. The file correctly omits strict mode (as documented in `lib-intercore.sh`'s header comment). No issue.

---

## 2. Stdout Discipline

This project has a documented gotcha: `bd` and `ic` commands write to stdout, and callers that capture via `$()` silently capture that output. The plan is careful in most places but has three violations.

### 2.1 `sprint_track_agent` — `intercore_run_agent_add` stdout not suppressed (High)

Task 7, Step 1 proposes:

```bash
sprint_track_agent() {
    ...
    intercore_run_agent_add "$run_id" "$agent_type" "$agent_name" "$dispatch_id"
}
```

The existing code (line 647) does the same: `intercore_run_agent_add ... ; return $?`. The current lib-intercore.sh wrappers pipe `ic run agent add` output to stdout. The function's declared contract says "Returns: agent_id on stdout, or empty on failure". If callers capture `sprint_track_agent`'s output via `$()`, they get the agent_id, which is the intended design.

However, the plan removes the explicit `return $?` and replaces it with a bare call:

```bash
intercore_run_agent_add "$run_id" "$agent_type" "$agent_name" "$dispatch_id"
```

This is fine when `sprint_track_agent`'s return value is the exit code of `intercore_run_agent_add`. But the current code has `return $?` to make this explicit. The bare form works identically in bash (the last command's exit code becomes the function's exit code), but removing the explicit `return $?` makes the intent less clear for reviewers and is inconsistent with the existing codebase style where intentional pass-through is written explicitly. This is low severity but worth noting.

### 2.2 `sprint_advance` — budget check stdout leaks to caller (High)

Task 8, Step 1, budget check:

```bash
"$INTERCORE_BIN" run budget "$run_id" 2>/dev/null
local budget_rc=$?
```

`ic run budget` may write to stdout (e.g., budget status messages). The plan redirects stderr to `/dev/null` but not stdout. If callers capture `sprint_advance`'s output via `$(sprint_advance ...)`, any stdout from `ic run budget` will be mixed into the captured value alongside the structured pause reason strings.

This is identical to the existing code (line 802). Since `sprint_advance` is not redesigned to be capture-safe in this plan, callers should call it without capturing:

```bash
sprint_advance "$sprint_id" "$current_phase"  # NOT: result=$(sprint_advance ...)
```

The plan should note this constraint explicitly in the function's comment, or add `>/dev/null` to the budget call. The existing comment on line 800 does not address this. The plan copies the existing behavior without improving it.

Fix:

```bash
"$INTERCORE_BIN" run budget "$run_id" >/dev/null 2>/dev/null
```

Or leave it as-is and document that `sprint_advance` must not be captured.

### 2.3 `sprint_advance` — `intercore_run_advance` result parsed from failed subshell (Medium)

The error-path `result` parsing:

```bash
result=$(intercore_run_advance "$run_id") || {
    local rc=$?
    event_type=$(echo "$result" | jq -r '.event_type // ""' 2>/dev/null) || event_type=""
    ...
```

When `intercore_run_advance` fails, `$result` captures whatever it wrote to stdout before exiting non-zero. If the command writes a JSON error body to stdout (expected design), this works. But if it writes nothing to stdout and only writes to stderr, `$result` is empty, which falls into the `*)` branch and triggers the raw-result debug log. This is existing code, not introduced by the plan, but worth documenting. The plan preserves this without comment.

---

## 3. Test Quality

### 3.1 Tests for deleted functions are listed but not all are correctly identified (Medium)

Task 14, Step 1 says to delete tests 3, 24, 25, 26. These correspond to `sprint_finalize_init` (test 3) and `_sprint_transition_table` (tests 24-26). This is correct.

However, `sprint_next_step` is being significantly changed (Task 9, Step 2 — no longer calls `_sprint_transition_table`). Test 18 (`sprint_next_step maps all phases correctly`) checks exact outputs. Some of those outputs *change* under the new implementation:

Current `sprint_next_step "shipping"` → calls `_sprint_transition_table("shipping")` → `"reflect"` → maps `reflect` → `"reflect"`. Output: `"reflect"`.

Proposed `sprint_next_step`:
```bash
shipping) echo "reflect" ;;
```
Wait — actually the proposed case statement outputs `"reflect"` for `shipping`, which matches. But look at `"reflect"`:

Current code: `_sprint_transition_table("reflect")` → `"done"` → maps `done` → `"done"`. Output: `"done"`.
Proposed: `reflect) echo "done" ;;`. Output: `"done"`. Same.

And `"done"` current: `_sprint_transition_table("done")` → `"done"` → maps `done` → `"done"`. Output: `"done"`.
Proposed: `done) echo "done" ;;`. Output: `"done"`. Same.

BUT: Test 18 in the current file says:
```
run sprint_next_step "shipping"
assert_output "done"    # Line 599-600 in test file: assert_output "done"
```

Wait — let me re-read test 18 more carefully. Line 598-600:
```bash
run sprint_next_step "executing"
assert_output "ship"

run sprint_next_step "shipping"
assert_output "done"
```

Current code for `sprint_next_step "executing"`: `_sprint_transition_table("executing")` → `"shipping"` → case maps `shipping` → `"ship"`. Output: `"ship"`. Test expects `"ship"`. Matches.

Proposed code: `executing) echo "ship" ;;`. Output: `"ship"`. Same. OK.

Current code for `sprint_next_step "shipping"`: `_sprint_transition_table("shipping")` → `"reflect"` → case maps `reflect` → `"reflect"`. Output: `"reflect"`. But test expects `"done"` (line 602). That means the **current test is wrong** — it would already fail against the current source. Or the current implementation has changed since the test was written.

Actually wait — re-reading the plan's proposed case for `sprint_next_step`:
```bash
shipping)            echo "reflect" ;;
reflect)             echo "done" ;;
```

Test 18 line 599-602:
```bash
run sprint_next_step "shipping"
assert_output "done"
```

The plan's implementation would output `"reflect"`, but the test expects `"done"`. This is a **test/implementation mismatch** that the plan does not flag or fix. The plan says to delete tests 3, 24-26, and rewrite 4-17, but test 18 is listed as unmodified and will fail against the new implementation.

The plan needs to update test 18 to `assert_output "reflect"` for the `shipping` phase.

### 3.2 `_sprint_resolve_run_id` caching test is structurally broken (High)

Task 14, Step 4:

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
    ...
    # bd should only be called once (cached on second call)
    # Note: can't easily verify call count with export -f, but the cache variable check works
    [[ -n "$_SPRINT_RUN_ID" ]]
}
```

The comment in the plan acknowledges the problem: `call_count` is declared `local` in the bats test body. When `bd()` is called from a subshell (any `$(...)` expansion), it runs in a child process and `call_count` in the parent is never incremented. The test cannot verify that `bd` was called only once.

The fallback assertion `[[ -n "$_SPRINT_RUN_ID" ]]` only checks that the global was set — it does not verify caching behavior at all. A broken implementation that calls `bd` N times would still pass this test.

Fix: use a file-based counter that survives subshell boundaries:

```bash
@test "_sprint_resolve_run_id caches after first call" {
    local counter_file="$TEST_PROJECT/bd_call_count"
    echo 0 > "$counter_file"

    bd() {
        case "$1" in
            state)
                local n; n=$(cat "$BD_COUNTER_FILE")
                echo $((n + 1)) > "$BD_COUNTER_FILE"
                echo "run-cached-123"
                ;;
        esac
    }
    export -f bd
    export BD_COUNTER_FILE="$counter_file"
    _source_sprint_lib

    _sprint_resolve_run_id "iv-test1" >/dev/null
    _sprint_resolve_run_id "iv-test1" >/dev/null

    local calls; calls=$(cat "$counter_file")
    [[ "$calls" -eq 1 ]]
}
```

### 3.3 `sprint_require_ic` test — `bd()` mock is unnecessary (Low)

Task 14, Step 3:

```bash
@test "sprint_require_ic succeeds when ic available" {
    intercore_available() { return 0; }
    export -f intercore_available
    bd() { return 0; }   # <-- why?
    export -f bd
    _source_sprint_lib
    run sprint_require_ic
    assert_success
}
```

`sprint_require_ic` only calls `intercore_available`. The `bd()` mock is unused and creates a misleading impression that `bd` is part of `sprint_require_ic`'s contract. Remove it.

### 3.4 Tests 4-17 rewrite guidance is incomplete (Medium)

Task 14, Step 2 says to rewrite tests 4-17 with intercore mocks "for each test", but only provides a complete example for test 4. Tests 8 (concurrent `sprint_set_artifact`), 9 (stale lock), 13 (first claimer), 14 (second claimer), 15 (TTL expiry), and 17 (sprint_release) have non-trivial lock and state machinery under the current beads path. Under ic-only, the locking is done by `intercore_lock`/`intercore_unlock` which are also wrappers in lib-intercore.sh.

The plan does not specify how to mock `intercore_lock` and `intercore_unlock` in tests. Without mocking these, the tests will fail in environments without a running ic instance. The plan should include:

```bash
# Standard intercore mock preamble for tests requiring lock operations
intercore_lock() { return 0; }
intercore_unlock() { return 0; }
export -f intercore_lock intercore_unlock
```

### 3.5 Test 23 (enforce_gate) will become incorrect (Medium)

Test 23 currently verifies that `enforce_gate` delegates to `check_phase_gate` via the interphase fallback. After Task 7, Step 2, the fallback is removed. `enforce_gate` becomes:

```bash
enforce_gate() {
    local run_id
    run_id=$(_sprint_resolve_run_id "$bead_id") || return 0
    intercore_gate_check "$run_id"
}
```

Test 23 will still pass because `_sprint_resolve_run_id` will fail (no `bd` mock for `ic_run_id`) and `enforce_gate` will `return 0`. This is a false positive — the test passes for the wrong reason (guard short-circuit, not gate delegation).

The plan says to update tests 4-17 but does not mention test 23. It needs a replacement test that mocks `_sprint_resolve_run_id` (or provides `bd` with an ic_run_id) and mocks `intercore_gate_check`, then asserts that `intercore_gate_check` was called.

---

## 4. Error Messages

### 4.1 Consistency — actionable and consistent (Pass)

The new error messages follow the `function_name: description` pattern used throughout the existing file. `sprint_claim: no ic run found for $sprint_id` and `sprint_claim: failed to register session agent for $sprint_id` are actionable. The budget exceeded message format `budget_exceeded|$current_phase|${spent}/${budget_val} billing tokens` is consistent with the structured pipe-delimited format used in `gate_blocked` and `manual_pause`.

### 4.2 `sprint_create` error is less informative than the current version (Low)

Current code (line 101): `"sprint_create: ic run create failed, cancelling bead $sprint_id"`
Proposed: `"sprint_create: ic run create failed"`

The proposed message drops `$sprint_id` from the error, making it harder to correlate with logs when multiple sprints are in flight. Keep `$sprint_id` in the message.

### 4.3 `sprint_require_ic` message is adequate but could be tighter (Low)

`"Sprint requires intercore (ic). Install ic or use beads directly for task tracking."` is clear. No issue.

---

## 5. jq Stubs Section (Task 12)

### 5.1 Missing stubs for functions that exist in the post-refactor file (High)

The proposed stub block:

```bash
if ! command -v jq &>/dev/null; then
    sprint_require_ic() { return 1; }
    sprint_create() { echo ""; return 1; }
    sprint_find_active() { echo "[]"; }
    sprint_read_state() { echo "{}"; }
    sprint_set_artifact() { return 0; }
    sprint_record_phase_completion() { return 0; }
    sprint_claim() { return 0; }
    sprint_release() { return 0; }
    sprint_next_step() { echo "brainstorm"; }
    sprint_invalidate_caches() { return 0; }
    sprint_should_pause() { return 1; }
    sprint_advance() { return 1; }
    sprint_classify_complexity() { echo "3"; }
    return 0
fi
```

Missing from the stubs (functions that will remain in the file post-refactor and use jq):

- `sprint_track_agent` — calls `intercore_run_agent_add` which may emit jq-parsed output in some ic wrapper versions. Low risk because `sprint_track_agent` itself does not call jq directly. However, omitting it leaves it callable when jq is absent, which could fail downstream if any caller chains its output through jq.
- `sprint_complete_agent` — calls `intercore_run_agent_update` with no jq. Safe to omit.
- `enforce_gate` — calls `_sprint_resolve_run_id` which calls `bd state`. After refactor, `_sprint_resolve_run_id` uses string comparison (`$run_id == "null"`) but no jq. Safe to omit.
- `sprint_should_pause` — already stubbed.
- `checkpoint_write` — uses jq heavily. **Missing from stubs.** If jq is absent and `checkpoint_write` is called, the jq invocation will fail silently (the `|| true` pattern absorbs it), but the checkpoint will not be written. This is acceptable fail-safe behavior, but it is inconsistent that `sprint_read_state` is stubbed while `checkpoint_write` is not.
- `checkpoint_read` — uses no jq directly (jq is used on its output by callers). Safe to omit.
- `sprint_classify_complexity` — already stubbed (returns `"3"`, which the plan correctly notes is the integer form).
- `_sprint_resolve_run_id` — internal helper, not part of the public API. Does not use jq. Safe to omit.
- `sprint_budget_remaining` — uses jq. **Missing from stubs.** Without jq, calls to `sprint_budget_remaining` will fail inside the jq pipeline.

The plan should add:

```bash
checkpoint_write() { return 0; }
sprint_budget_remaining() { echo "0"; }
```

### 5.2 `sprint_classify_complexity` return value change: "medium" → "3" (flag for callers)

The plan correctly notes the change. However, `sprint_complexity_label` is a downstream consumer that handles both forms (lines 1051-1054 of the existing file handle legacy string values). No callers need updating. But the plan should verify this explicitly — a grep for callers of `sprint_classify_complexity` that compare against `"medium"` is warranted:

```bash
grep -r 'sprint_classify_complexity' os/clavain/commands/ os/clavain/hooks/
```

If any command file compares the result to `"medium"` rather than passing through `sprint_complexity_label`, it will break.

---

## 6. Architecture and Naming

### 6.1 `_SPRINT_RUN_ID` is a single-sprint cache — does not support multiple active sprints (Medium)

The cache stores exactly one run ID per process lifetime. `_sprint_resolve_run_id` ignores `$bead_id` on cache hit — it returns `$_SPRINT_RUN_ID` regardless of which bead was asked. If code in the same session calls `_sprint_resolve_run_id "iv-sprint-A"` then `_sprint_resolve_run_id "iv-sprint-B"`, the second call returns sprint A's run ID.

The plan explicitly states "Call once at sprint_claim or sprint_create" and "Caches result in _SPRINT_RUN_ID." This design is intentional (single-sprint-per-session assumption), but the function signature accepts `$bead_id` without using it on cache hit, which is misleading. The plan should either:

(a) Document the single-sprint assumption explicitly in the function comment and as a hard assertion: `[[ "$bead_id" == "$_SPRINT_BEAD_ID" ]]` with a warning on mismatch.
(b) Make the cache keyed by bead_id: `_SPRINT_RUN_ID_${bead_id//[^a-zA-Z0-9]/_}`.

Option (a) is simpler and aligns with the stated design. Add a companion `_SPRINT_BEAD_ID=""` and populate it alongside `_SPRINT_RUN_ID`.

### 6.2 `sprint_find_active` no longer needs a `run_id` loop variable inside if-block (Low)

In the proposed `sprint_find_active`, `run_id`, `scope_id`, `phase`, and `goal` are declared with `local` inside a `while` loop. In bash, `local` declarations inside loops are fine — the variable is local to the function, not to the loop iteration. The plan's code is correct. No issue.

### 6.3 Naming: `sprint_require_ic` vs `sprint_assert_ic` — minor (Low)

`require_` is used in some frameworks to mean "source/import", not "assert". `assert_ic_available` would be clearer that this is a runtime precondition check that returns an error code. However, the existing codebase uses no `assert_` naming convention, and `require_` is legible in context. This is a pure preference note, not a defect.

---

## 7. Specific Plan Steps — Additional Concerns

### 7.1 Task 1: `_SPRINT_RUN_ID` is declared at file scope but not reset on re-source (see 1.1 above)

### 7.2 Task 2: `sprint_create` — bead creation error handling is inverted vs. current code (Medium)

Current `sprint_create` (line 63-131): if bead creation fails, return `""` with exit 0 (fail-safe).
Proposed `sprint_create`: if ic run fails, return `""` with exit 1 (hard fail).

But if bead creation fails (the optional step), the proposed code returns `""` with `return 1`:

```bash
sprint_id=$(bd create ... | awk ...) || sprint_id=""
if [[ -n "$sprint_id" ]]; then
    ...
else
    echo "sprint_create: bead creation failed (non-fatal), sprint will lack backlog entry" >&2
fi
# ... continues to ic run create
```

Wait, actually the proposed code does not return on bead failure — it continues to `ic run create`. That is the correct intent (bead is optional). But then at the end:

```bash
echo "$sprint_id"
```

If bead creation failed, `sprint_id=""` and the function outputs `""`. The caller (likely `sprint.md`) uses the output as `CLAVAIN_BEAD_ID`. If `CLAVAIN_BEAD_ID` is empty but the ic run was successfully created, the ic run is now orphaned (no bead_id → no way to look up the run_id from a bead).

The `scope_id="${sprint_id:-sprint-$(date +%s)}"` line handles this for the ic run side. But `_SPRINT_RUN_ID` is cached with the run_id from this ic run, and future calls to `_sprint_resolve_run_id ""` (with empty bead_id) will return early with `return 1` because:

```bash
[[ -z "$bead_id" ]] && { echo ""; return 1; }
```

So if bead creation fails, the entire sprint becomes unreachable via the sprint API after `sprint_create` returns. This is a correctness issue. Either:

(a) Hard-fail `sprint_create` if bead creation fails (ic run without bead_id is not useful in the current architecture).
(b) Accept bead-less sprints and make `_sprint_resolve_run_id` fall back to checking `_SPRINT_RUN_ID` even when `bead_id` is empty (using the cached value from `sprint_create`).

The plan states "bead creation failure is non-fatal" but the follow-on behavior makes it effectively fatal. This should be clarified.

### 7.3 Task 9: `sprint_next_step` semantic mismatch (see 3.1 above — test 18)

The proposed case statement maps `brainstorm` → `strategy` which matches the current behavior. But the test at line 599 expects `sprint_next_step "shipping"` → `"done"`, while the proposed implementation would output `"reflect"`. The plan does not flag this test for update.

### 7.4 Task 10: `checkpoint_clear` keeps file cleanup but removes the `CHECKPOINT_FILE` constant

If `CHECKPOINT_FILE` is removed from file scope, `checkpoint_clear` references `${CLAVAIN_CHECKPOINT_FILE:-.clavain/checkpoint.json}` inline, which works. But `checkpoint_read`'s existing fallback (line 1217) references `$CHECKPOINT_FILE`:

```bash
[[ -f "$CHECKPOINT_FILE" ]] && cat "$CHECKPOINT_FILE" 2>/dev/null || echo "{}"
```

After `CHECKPOINT_FILE` is removed from file scope, this line in `checkpoint_read` will expand to an empty string and the file check will always be false (`-f ""`). The plan says to replace `checkpoint_read` (Task 10, Step 2) which eliminates this reference. But if the replacement is applied before the constant removal, or if the replacement is incomplete, there is a silent regression. The plan should note the order dependency: remove `CHECKPOINT_FILE` constant only after `checkpoint_read` has been replaced.

---

## Summary of Findings by Priority

| Priority | Finding | Location in Plan |
|----------|---------|------------------|
| High | `_SPRINT_RUN_ID` not reset between bats tests — corrupts isolation | Task 1 + Task 14 |
| High | `_sprint_resolve_run_id` cache test uses local counter, can't count subshell calls | Task 14 Step 4 |
| High | `sprint_budget_remaining` and `checkpoint_write` missing from jq stubs | Task 12 |
| High | Bead-less `sprint_create` leaves ic run unreachable via sprint API | Task 2 |
| Medium | `sprint_advance` budget check leaks stdout to callers capturing output | Task 8 |
| Medium | Test 18 (`sprint_next_step "shipping"` → `"reflect"`) not updated in plan | Task 14 |
| Medium | Test 23 (enforce_gate) becomes false-positive after fallback removal | Task 14 |
| Medium | `intercore_lock`/`intercore_unlock` mocking not specified for claim/release tests | Task 14 |
| Medium | `_SPRINT_RUN_ID` cache ignores `bead_id` argument on hit — single-sprint-only assumption undocumented | Task 1 |
| Medium | `CHECKPOINT_FILE` removal order dependency with `checkpoint_read` replacement | Task 10 |
| Medium | `local new_total=$((...))` masks arithmetic exit status | Task 5 |
| Low | `sprint_create` error message drops `$sprint_id` vs. current | Task 2 |
| Low | `sprint_require_ic` has unnecessary `return 0` at end | Task 1 |
| Low | `sprint_require_ic` test mocks `bd()` unnecessarily | Task 14 Step 3 |
| Low | `sprint_classify_complexity` callers in commands/ not audited for "medium" string comparison | Task 12 |
