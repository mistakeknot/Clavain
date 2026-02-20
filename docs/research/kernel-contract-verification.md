# Kernel Contract Verification: Sprint Handover Plan

**Plan reviewed:** `/root/projects/Interverse/docs/plans/2026-02-20-sprint-handover-kernel-driven.md`
**Date:** 2026-02-20
**Reviewer:** Claude Opus 4.6 (automated kernel contract review)

---

## Summary

The sprint handover plan has **6 P0 (runtime failure) issues** and **3 P1 (silent data loss) issues**. The root cause is that the plan calls 6 shell wrapper functions (`intercore_run_create`, `intercore_run_list`, `intercore_run_status`, `intercore_run_advance`, `intercore_run_agent_list`, `intercore_run_agent_update`) that **do not exist** in `lib-intercore.sh` or anywhere else in the codebase. The current code gets away with this because it has beads fallback paths; the plan removes those fallbacks, making the missing functions fatal.

Additionally, the plan calls `ic` CLI subcommands (`dispatch create`, `dispatch update`, `run show`) that don't exist, and parses JSON fields with wrong names.

---

## P0: Functions That Don't Exist or Have Wrong Signatures (Runtime Failures)

### P0-1: `intercore_run_create()` does not exist

**Location in plan:** Task 2, line 120
```bash
run_id=$(intercore_run_create "$(pwd)" "$title" "$phases_json" "$scope_id" "$complexity" "$token_budget") || run_id=""
```

**Status:** This function is NOT defined in `lib-intercore.sh` (checked `/root/projects/Interverse/hub/clavain/hooks/lib-intercore.sh` and `/root/projects/Interverse/infra/intercore/lib-intercore.sh`). It is called in the existing `lib-sprint.sh:98` but was never implemented as a wrapper.

**The ic CLI does accept `ic run create`** with flags `--project=`, `--goal=`, `--phases=`, `--scope-id=`, `--complexity=`, `--token-budget=`, `--budget-warn-pct=`. But the wrapper function that translates the positional args to these flags does not exist.

**Fix required:** Add `intercore_run_create()` to `lib-intercore.sh` with this signature:
```bash
intercore_run_create() {
    local project="$1" goal="$2" phases_json="$3" scope_id="${4:-}" complexity="${5:-3}" token_budget="${6:-}"
    if ! intercore_available; then return 1; fi
    local args=(run create --project="$project" --goal="$goal" --complexity="$complexity")
    [[ -n "$phases_json" ]] && args+=(--phases="$phases_json")
    [[ -n "$scope_id" ]] && args+=(--scope-id="$scope_id")
    [[ -n "$token_budget" ]] && args+=(--token-budget="$token_budget")
    "$INTERCORE_BIN" "${args[@]}" 2>/dev/null
}
```

**Note on `--phases`:** The project memory says "`ic run create` has NO `--phases` flag" but this is **outdated** — the Go source at `/root/projects/Interverse/infra/intercore/cmd/ic/run.go:88-89` clearly accepts `--phases=`. The memory entry should be corrected.

---

### P0-2: `intercore_run_list()` does not exist

**Location in plan:** Task 3, line 188
```bash
runs_json=$(intercore_run_list "--active") || { echo "[]"; return 0; }
```

**Status:** NOT defined anywhere. Called at `lib-sprint.sh:154`.

**Additional issue:** Even if the wrapper existed, the plan parses `.id`, `.scope_id`, `.phase`, `.goal` as JSON fields, which requires `--json` flag. The current call `intercore_run_list "--active"` would need to pass `--json` to get JSON output. Without `--json`, `ic run list --active` outputs tab-separated text.

**Fix required:** Add wrapper to `lib-intercore.sh`:
```bash
intercore_run_list() {
    if ! intercore_available; then return 1; fi
    "$INTERCORE_BIN" run list "$@" --json 2>/dev/null
}
```

---

### P0-3: `intercore_run_status()` does not exist

**Location in plan:** Task 4, line 255 and Task 11, line 834
```bash
run_json=$(intercore_run_status "$run_id") || { echo "{}"; return 0; }
```

**Status:** NOT defined anywhere. Called at `lib-sprint.sh:253` and `lib-sprint.sh:920`.

**Fix required:** Add wrapper:
```bash
intercore_run_status() {
    local id="$1"
    if ! intercore_available; then return 1; fi
    "$INTERCORE_BIN" run status "$id" --json 2>/dev/null
}
```

---

### P0-4: `intercore_run_advance()` does not exist

**Location in plan:** Task 8, line 615
```bash
result=$(intercore_run_advance "$run_id") || {
```

**Status:** NOT defined anywhere. Referenced at `lib-sprint.sh:817`.

**Fix required:** Add wrapper:
```bash
intercore_run_advance() {
    local id="$1"
    if ! intercore_available; then return 1; fi
    "$INTERCORE_BIN" run advance "$id" --json 2>/dev/null
}
```

**Note:** Without `--json`, `ic run advance` outputs `from → to` as plain text. The plan parses `.event_type`, `.from_phase`, `.to_phase` as JSON fields, so `--json` is required.

---

### P0-5: `intercore_run_agent_list()` and `intercore_run_agent_update()` do not exist

**Location in plan:** Task 6, lines 446, 470-471, 492-493
```bash
agents_json=$(intercore_run_agent_list "$run_id") || agents_json="[]"
intercore_run_agent_update "$old_agent_id" "failed" >/dev/null 2>&1 || true
```

**Status:** NOT defined anywhere. `intercore_run_agent_add` IS defined in `lib-intercore.sh:254` but `agent_list` and `agent_update` are not.

**Fix required:** Add both wrappers:
```bash
intercore_run_agent_list() {
    local run_id="$1"
    if ! intercore_available; then return 1; fi
    "$INTERCORE_BIN" run agent list "$run_id" --json 2>/dev/null
}

intercore_run_agent_update() {
    local agent_id="$1" status="$2"
    if ! intercore_available; then return 1; fi
    "$INTERCORE_BIN" run agent update "$agent_id" --status="$status" 2>/dev/null
}
```

---

### P0-6: `dispatch create` and `dispatch update` CLI subcommands do not exist

**Location in plan:** Task 5, lines 395-399
```bash
dispatch_id=$("$INTERCORE_BIN" dispatch create "$run_id" --agent="phase-${phase}" --json 2>/dev/null \
    | jq -r '.id // ""' 2>/dev/null) || dispatch_id=""
if [[ -n "$dispatch_id" ]]; then
    "$INTERCORE_BIN" dispatch tokens "$dispatch_id" --set --in="$in_tokens" --out="$out_tokens" 2>/dev/null || true
    "$INTERCORE_BIN" dispatch update "$dispatch_id" --status=completed 2>/dev/null || true
fi
```

**Status:** The `ic dispatch` subcommands are: `spawn`, `status`, `list`, `poll`, `wait`, `kill`, `prune`, `tokens`. There is NO `dispatch create` and NO `dispatch update`.

**Additional issue:** `dispatch tokens` does NOT accept `--set` flag. It directly takes `--in=N`, `--out=N`, `--cache=N`.

**Impact:** The entire `sprint_record_phase_tokens` function will silently fail (it's wrapped in `|| true`), causing all phase token tracking to be lost.

**Fix required:** Either:
1. Use `dispatch spawn` to create a dispatch record (but it actually spawns a process, which is not wanted here), or
2. Create a new `dispatch create` subcommand for metadata-only dispatch records, or
3. Redesign to use `ic state set` for phase token tracking instead.

---

### P0-7: `ic run show` does not exist

**Location in plan:** Task 8, line 608
```bash
budget_val=$("$INTERCORE_BIN" run show "$run_id" --json 2>/dev/null | jq -r '.token_budget // "?"' 2>/dev/null) || budget_val="?"
```

**Status:** There is no `run show` subcommand. The correct command is `ic run status`.

**Fix:** Replace `run show` with `run status`.

---

## P1: Output Format Mismatches (Silent Data Loss)

### P1-1: `ic run tokens --json` field names are wrong

**Location in plan:** Task 4 (sprint_read_state), line 295
```bash
tokens_spent=$(echo "$token_agg" | jq -r '(.total_in // 0) + (.total_out // 0)')
```

**Actual output fields from `cmdRunTokens`** (run.go lines 1184-1194):
```json
{
    "run_id": "...",
    "input_tokens": 1234,
    "output_tokens": 567,
    "cache_hits": 89,
    "total_tokens": 1801
}
```

The plan references `.total_in` and `.total_out` but the actual fields are `.input_tokens` and `.output_tokens`.

**Fix:** Change jq to: `'(.input_tokens // 0) + (.output_tokens // 0)'` or just use `.total_tokens`.

---

### P1-2: `ic run events --json` field names are wrong

**Location in plan:** Task 4 (sprint_read_state), lines 276-278
```bash
history=$(echo "$events_json" | jq -s '
    [.[] | select(.source == "phase" and .type == "advance") |
     {((.to_state // "") + "_at"): (.timestamp // "")}] | add // {}' 2>/dev/null) || history="{}"
```

**Actual event JSON fields** (from `eventToMap`, run.go lines 1454-1473):
```json
{
    "id": 1,
    "run_id": "...",
    "from_phase": "brainstorm",
    "to_phase": "brainstorm-reviewed",
    "event_type": "advance",
    "created_at": 1708000000,
    "gate_result": "pass",
    "gate_tier": "soft",
    "reason": "..."
}
```

Four field name mismatches:
| Plan references | Actual field | Impact |
|---|---|---|
| `.source` | (does not exist) | `select()` always false, history always `{}` |
| `.type` | `.event_type` | `select()` always false |
| `.to_state` | `.to_phase` | Key names wrong if select worked |
| `.timestamp` | `.created_at` | Values would be empty |

**Fix:**
```bash
history=$(echo "$events_json" | jq '
    [.[] | select(.event_type == "advance") |
     {((.to_phase // "") + "_at"): (.created_at // 0 | tostring)}] | add // {}' 2>/dev/null) || history="{}"
```

Also note: the existing code (line 276) already has this bug — it's not introduced by the plan, just preserved from the current implementation.

Also note: `ic run events --json` outputs a JSON array directly (not newline-delimited JSON), so the `jq -s` (slurp) is unnecessary and would double-wrap the array. Use `jq` without `-s`.

---

### P1-3: `dispatch tokens --set` flag does not exist

**Location in plan:** Task 5, line 398
```bash
"$INTERCORE_BIN" dispatch tokens "$dispatch_id" --set --in="$in_tokens" --out="$out_tokens" 2>/dev/null || true
```

**Actual CLI:** `ic dispatch tokens <id> --in=N --out=N [--cache=N]` — no `--set` flag. The `--set` flag will cause the command to fail with "unknown flag" but the `|| true` swallows the error.

**Impact:** Token recording for phases will silently fail. All phase token data will be lost.

**Fix:** Remove `--set`:
```bash
"$INTERCORE_BIN" dispatch tokens "$dispatch_id" --in="$in_tokens" --out="$out_tokens" 2>/dev/null || true
```

---

## P2: Minor API Usage Concerns

### P2-1: Custom phase chain diverges from DefaultPhaseChain

**Plan's chain:**
```
brainstorm → brainstorm-reviewed → strategized → planned → plan-reviewed → executing → shipping → reflect → done
```

**Go DefaultPhaseChain:**
```
brainstorm → brainstorm-reviewed → strategized → planned → executing → review → polish → reflect → done
```

Differences:
- Plan adds `plan-reviewed` (not in default)
- Plan replaces `review` + `polish` with `shipping`

This is intentional (custom chain passed to `--phases=`) and will work correctly since `ParsePhaseChain` validates only format/duplicates, not specific phase names. But the `sprint_next_step` mapping must stay synchronized with this custom chain.

### P2-2: `sprint_next_step` phase mapping has a gap

**Plan's mapping (Task 9):**
```bash
brainstorm)          echo "strategy" ;;
brainstorm-reviewed) echo "strategy" ;;
strategized)         echo "write-plan" ;;
planned)             echo "flux-drive" ;;
plan-reviewed)       echo "work" ;;
executing)           echo "ship" ;;
shipping)            echo "reflect" ;;
reflect)             echo "done" ;;
done)                echo "done" ;;
```

Both `brainstorm` and `brainstorm-reviewed` map to `"strategy"`. This is fine — it means the same command handles both, advancing when ready.

### P2-3: `intercore_run_advance` JSON parsing on failure path

**Plan's sprint_advance (Task 8), lines 615-641:**
```bash
result=$(intercore_run_advance "$run_id") || {
    local rc=$?
    local event_type from_phase to_phase
    event_type=$(echo "$result" | jq -r '.event_type // ""' 2>/dev/null) || event_type=""
```

When `intercore_run_advance` fails (returns non-zero), `$result` will still contain the command's stdout — but only if the wrapper captures both exit code and output correctly. Since the wrapper doesn't exist yet (P0-4), the exact behavior depends on how it's implemented. If the wrapper uses `"$INTERCORE_BIN" run advance "$id" --json`, then on gate-block the CLI outputs JSON with `advanced: false` and exits with code 1. The `|| {` block captures `$?` but `$result` will be empty because `$()` on a failed command may not capture output in all shells. This is fragile.

**Recommendation:** Use a two-step pattern:
```bash
result=$("$INTERCORE_BIN" run advance "$run_id" --json 2>/dev/null) || true
local advanced
advanced=$(echo "$result" | jq -r '.advanced // false' 2>/dev/null) || advanced="false"
if [[ "$advanced" != "true" ]]; then
    # handle blocked/paused case
fi
```

### P2-4: `sprint_find_active` doesn't add `--json` flag

**Plan's Task 3, line 188:**
```bash
runs_json=$(intercore_run_list "--active") || { echo "[]"; return 0; }
```

The `"--active"` is passed as a string argument. The wrapper (once created) needs to also ensure `--json` is passed to get JSON output rather than tab-separated text. Otherwise the jq parsing on lines 192-200 will fail.

### P2-5: `ic run events --json` output is already an array — `-s` (slurp) double-wraps

**Plan's Task 4, line 276:**
```bash
events_json=$("$INTERCORE_BIN" run events "$run_id" --json 2>/dev/null) || events_json=""
# ...
history=$(echo "$events_json" | jq -s '...')
```

The `cmdRunEvents` function outputs a JSON array (`json.NewEncoder(os.Stdout).Encode(items)`). Using `jq -s` on a single JSON array creates `[[...]]` (array of arrays), causing the `select()` to fail. Remove `-s`.

---

## Summary Table

| ID | Priority | Issue | Tasks Affected |
|----|----------|-------|---------------|
| P0-1 | P0 | `intercore_run_create()` not defined | Task 2 |
| P0-2 | P0 | `intercore_run_list()` not defined | Task 3 |
| P0-3 | P0 | `intercore_run_status()` not defined | Tasks 4, 11 |
| P0-4 | P0 | `intercore_run_advance()` not defined | Task 8 |
| P0-5 | P0 | `intercore_run_agent_list/update()` not defined | Task 6 |
| P0-6 | P0 | `dispatch create` and `dispatch update` CLI subcommands don't exist | Task 5 |
| P0-7 | P0 | `ic run show` doesn't exist (use `ic run status`) | Task 8 |
| P1-1 | P1 | Token JSON fields: `total_in`/`total_out` should be `input_tokens`/`output_tokens` | Task 4 |
| P1-2 | P1 | Event JSON fields: `.source`, `.type`, `.to_state`, `.timestamp` all wrong | Task 4 |
| P1-3 | P1 | `dispatch tokens --set` flag doesn't exist | Task 5 |
| P2-1 | P2 | Custom phase chain diverges from default (intentional, but needs sync) | Task 2, 9 |
| P2-2 | P2 | sprint_next_step mapping quirk (two phases map to same command) | Task 9 |
| P2-3 | P2 | Fragile result capture on advance failure path | Task 8 |
| P2-4 | P2 | `intercore_run_list` needs `--json` flag for jq parsing | Task 3 |
| P2-5 | P2 | `jq -s` on already-array events output creates double-wrap | Task 4 |

---

## Required Pre-work Before Executing This Plan

1. **Add 6 missing wrappers to `lib-intercore.sh`**: `intercore_run_create`, `intercore_run_list`, `intercore_run_status`, `intercore_run_advance`, `intercore_run_agent_list`, `intercore_run_agent_update`. All must pass `--json` to the CLI.

2. **Fix or redesign `sprint_record_phase_tokens`** (Task 5): `dispatch create` and `dispatch update` don't exist. Either add these CLI subcommands or use `ic state set` for token tracking.

3. **Fix all JSON field name references** in `sprint_read_state` (Task 4): event fields (`.source`/`.type`/`.to_state`/`.timestamp`) and token fields (`.total_in`/`.total_out`).

4. **Replace `ic run show` with `ic run status`** in `sprint_advance` (Task 8).

5. **Remove `--set` from `dispatch tokens`** calls (Task 5).

6. **Update project memory**: Remove the outdated entry that says "`ic run create` has NO `--phases` flag" — it does accept `--phases=` per the Go source.
