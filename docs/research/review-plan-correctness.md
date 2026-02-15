# Correctness Review: Auto-Drift-Check Implementation Plan

**Reviewer:** Julik (fd-correctness agent)
**Date:** 2026-02-14
**Plan:** `/root/projects/Clavain/docs/plans/2026-02-14-auto-drift-check.md`
**Bead:** Clavain-iwuy

---

## Executive Summary

The plan has **one critical correctness defect** that breaks Stop hook coordination:

1. **Per-hook sentinel strategy creates a race window** — hooks no longer coordinate Stop cycle ownership, allowing multiple hooks to return conflicting "block" decisions in the same cycle

Additional findings:
2. **Double-sourcing guard in lib-signals.sh is misleading** — suggests state isolation that doesn't exist (low severity)
3. **Grep pattern false positive** — `the issue was` pattern matches user messages, not just assistant analysis (low severity)
4. **Test fixture reuse is correct** — no error found (initial concern was invalid)

---

## Detailed Findings

### 1. Per-Hook Sentinel Race (CRITICAL)

**Location:** Plan Task 2, Task 3, Task 4

**Defect:**

The plan changes from a **shared** sentinel (`/tmp/clavain-stop-${SESSION_ID}`) to **per-hook** sentinels (`clavain-stop-compound-*`, `clavain-stop-drift-*`, `clavain-stop-handoff-*`). The PRD states:

> "Each Stop hook gets its own sentinel [...] instead of the current shared `clavain-stop-*`. This lets both hooks fire in the same Stop cycle without blocking each other."

This is **incorrect** — the current shared sentinel exists to ensure **only one hook outputs block+reason per Stop cycle**. Claude Code processes Stop hooks sequentially, but if multiple hooks return `{"decision":"block"}`, behavior is undefined (likely: last hook wins, or Claude gets confused by multiple conflicting prompts).

**Current implementation (auto-compound.sh lines 46-52):**

```bash
# Guard: if another Stop hook already fired this cycle, don't cascade
STOP_SENTINEL="/tmp/clavain-stop-${SESSION_ID}"
if [[ -f "$STOP_SENTINEL" ]]; then
    exit 0
fi
# Write sentinel NOW — before transcript analysis — to minimize TOCTOU window
touch "$STOP_SENTINEL"
```

**Proposed implementation (per-hook sentinels):**

```bash
# auto-compound.sh
STOP_SENTINEL="/tmp/clavain-stop-compound-${SESSION_ID}"

# auto-drift-check.sh
STOP_SENTINEL="/tmp/clavain-stop-drift-${SESSION_ID}"
```

**Race condition interleaving:**

Claude Code calls Stop hooks in order: `auto-compound.sh` → `auto-drift-check.sh` → `session-handoff.sh`.

1. `auto-compound.sh` runs, detects signals (weight 4), writes `/tmp/clavain-stop-compound-${SESSION_ID}`
2. `auto-compound.sh` returns `{"decision":"block", "reason":"Run /compound"}` → Claude is now blocked, waiting to run compound
3. `auto-drift-check.sh` runs next in the same Stop cycle
4. Per-hook sentinel check: `/tmp/clavain-stop-drift-${SESSION_ID}` does not exist → continues
5. Detects signals (weight 2), returns `{"decision":"block", "reason":"Run /interwatch:watch"}`
6. **Result:** Two hooks both return "block" in the same Stop cycle

**Expected behavior (undefined):**
- Does Claude Code run both prompts? In what order?
- Does the second "block" decision override the first?
- If session-handoff also triggers (uncommitted changes), now we have **three** block decisions in one cycle

**Current behavior (with shared sentinel):**
- `auto-compound.sh` writes shared sentinel, outputs "block" → Claude runs compound
- `auto-drift-check.sh` sees shared sentinel, exits 0 silently → no cascade
- Only one "block" decision per Stop cycle

**Root cause:**

The plan conflates two different synchronization needs:

1. **Throttle sentinels** (per-hook, time-based) — prevent same hook from firing twice in N minutes
2. **Stop cycle sentinel** (shared, cycle-based) — ensure only one hook outputs "block" per Stop event

The plan removes the shared sentinel without replacing its coordination role.

**Fix:**

Keep the **shared sentinel** for Stop cycle coordination (`/tmp/clavain-stop-${SESSION_ID}`), and use **separate throttle sentinels** per hook (`/tmp/clavain-compound-last-${SESSION_ID}`, `/tmp/clavain-drift-last-${SESSION_ID}`).

Updated guard logic for all three hooks:

```bash
# Guard: shared sentinel — ensure only one hook outputs "block" per Stop cycle
STOP_SENTINEL="/tmp/clavain-stop-${SESSION_ID}"
if [[ -f "$STOP_SENTINEL" ]]; then
    exit 0
fi
touch "$STOP_SENTINEL"

# Guard: per-hook throttle — at most once per N minutes
THROTTLE_SENTINEL="/tmp/clavain-compound-last-${SESSION_ID}"
if [[ -f "$THROTTLE_SENTINEL" ]]; then
    THROTTLE_MTIME=$(stat -c %Y "$THROTTLE_SENTINEL" 2>/dev/null || stat -f %m "$THROTTLE_SENTINEL" 2>/dev/null || date +%s)
    THROTTLE_NOW=$(date +%s)
    if [[ $((THROTTLE_NOW - THROTTLE_MTIME)) -lt 300 ]]; then
        exit 0
    fi
fi
```

**This preserves the current coordination semantics while keeping per-hook throttle state separate.**

---

### 2. Double-Sourcing Guard vs. State Reset (MODERATE)

**Location:** Plan Task 1, `hooks/lib-signals.sh` lines 157-158, 162-165

**Defect:**

The proposed `lib-signals.sh` has a double-sourcing guard:

```bash
# Guard against double-sourcing
[[ -n "${_LIB_SIGNALS_LOADED:-}" ]] && return 0
_LIB_SIGNALS_LOADED=1
```

But the `detect_signals()` function **resets state on every call**:

```bash
detect_signals() {
    local text="$1"
    CLAVAIN_SIGNALS=""           # RESET
    CLAVAIN_SIGNAL_WEIGHT=0      # RESET
    # ... detection logic ...
}
```

**Scenario where the guard is useless:**

If two hooks both source `lib-signals.sh` in the same shell session:

```bash
# Hook A
source hooks/lib-signals.sh
detect_signals "$RECENT"
echo "Hook A: weight=$CLAVAIN_SIGNAL_WEIGHT"

# Hook B (later in the same shell)
source hooks/lib-signals.sh  # guard returns immediately
detect_signals "$RECENT"     # function exists, runs fine
echo "Hook B: weight=$CLAVAIN_SIGNAL_WEIGHT"
```

The guard prevents re-parsing the function definition, but **does not prevent state pollution** because `detect_signals()` resets variables on each call.

**But is this actually a problem?**

No — because **Stop hooks run in separate processes**. Each `bash hooks/auto-compound.sh` and `bash hooks/auto-drift-check.sh` is a fresh shell with no shared state. The guard only matters if a single hook sources `lib-signals.sh` twice in one execution.

**Verdict:**

The guard is **not harmful**, but it is **misleading** because it suggests state isolation that doesn't exist. The comment should clarify:

```bash
# Guard against re-parsing function definitions (performance optimization).
# Note: detect_signals() resets CLAVAIN_SIGNALS and CLAVAIN_SIGNAL_WEIGHT
# on each call, so there is no persistent state isolation.
[[ -n "${_LIB_SIGNALS_LOADED:-}" ]] && return 0
_LIB_SIGNALS_LOADED=1
```

Alternatively, **remove the guard entirely** — it serves no functional correctness purpose and adds cognitive load.

---

### 3. Test Fixture Reuse (NO ERROR)

**Location:** Plan Task 4, `tests/shell/auto_drift_check.bats` lines 343-347, 369-374

**Initial concern:** `transcript_with_commit.jsonl` has weight 2 (commit + bead-close). auto-compound threshold is 3, auto-drift-check threshold is 2. Would the same fixture produce different results?

**Analysis:** YES, and that's correct:
- auto-compound test expects weight < 3 → no output ✓
- auto-drift-check test expects weight >= 2 → block output ✓

**Verdict:** No error. The test assertions are correct for their respective thresholds.

---

### 4. Grep Pattern False Positive (LOW)

**Location:** Plan Task 1, `hooks/lib-signals.sh` line 180

**Defect:**

The "investigation" signal pattern:

```bash
if echo "$text" | grep -iq '"root cause\|"the issue was\|"the problem was\|"turned out\|"the fix is\|"solved by\|the issue was'; then
```

The pattern `the issue was` (without leading `"`) will match **user messages** as well as assistant analysis:

```json
{"role":"user","content":"I think the issue was with the database connection"}
```

This user message would trigger the investigation signal (weight +2), even though it's not Claude diagnosing a problem — it's the user speculating.

**Impact:**

Low — user diagnosis language is still a signal that problem-solving happened. If the user is explaining root cause, the session likely involved investigation.

**But:** The other patterns use `"` prefix to anchor to assistant tool calls (`"root cause`, `"the issue was`), suggesting intent to match only Claude's actions, not user text.

**Fix:**

Be consistent — remove the standalone `the issue was` pattern:

```bash
if echo "$text" | grep -iq '"root cause\|"the issue was\|"the problem was\|"turned out\|"the fix is\|"solved by'; then
```

**Recommended:** Strict matching (only assistant actions) because other signal patterns (`"git commit`, `"bd close`) explicitly anchor to assistant tool calls.

---

## Additional Observations

### interwatch Discovery Guard

**Location:** Plan Task 4, `hooks/auto-drift-check.sh` lines 508-513

**Correct.** The hook checks if interwatch is installed before triggering. If not installed, it exits 0 silently. This is graceful degradation as intended.

### Throttle Sentinel Logic

**Location:** All three Stop hooks

**Correct.** The `stat -c %Y` (Linux) / `stat -f %m` (macOS) fallback pattern is robust. The 600-second (10-minute) throttle for drift-check is reasonable.

**Minor improvement:** The fallback `|| date +%s` will always succeed even if the file doesn't exist, causing the age check to compare against "now", which means throttle fails open (no throttle if stat fails). This is safe behavior.

### Cleanup Sentinel Logic

**Location:** All three Stop hooks (bottom)

```bash
find /tmp -maxdepth 1 -name 'clavain-stop-*' -mmin +60 -delete 2>/dev/null || true
```

**Correct.** Old sentinels are cleaned up after 60 minutes. The `|| true` ensures hook never fails on cleanup errors.

**But:** With the per-hook sentinel strategy (if adopted), this pattern would need to be updated:

```bash
find /tmp -maxdepth 1 \( -name 'clavain-stop-*' -o -name 'clavain-compound-last-*' -o -name 'clavain-drift-last-*' \) -mmin +60 -delete 2>/dev/null || true
```

---

## Recommendations

### Critical Fixes

1. **Revert per-hook sentinel strategy** — keep shared `/tmp/clavain-stop-${SESSION_ID}` for Stop cycle coordination, add per-hook throttle sentinels with different names (`clavain-compound-last-*`, `clavain-drift-last-*`)

2. **Fix grep pattern consistency** — remove standalone `the issue was` pattern from investigation signal, or document that user messages are intentionally included

### Optional Improvements

3. **Clarify or remove double-sourcing guard** — either document that it's a performance optimization (not state isolation), or remove it entirely

4. **Test coverage for concurrent block decisions** — add a test that simulates two hooks both returning "block" to verify Claude Code's behavior (currently untested assumption)

### Test Plan Additions

Add a new test to `auto_drift_check.bats`:

```bash
@test "auto-drift-check: respects shared sentinel from auto-compound" {
    local session_id="test-shared-sentinel-$$"
    # Simulate auto-compound running first and writing shared sentinel
    touch "/tmp/clavain-stop-${session_id}"

    run bash -c "echo '{\"stop_hook_active\": false, \"session_id\": \"${session_id}\", \"transcript_path\": \"$TMPDIR_DRIFT/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-drift-check.sh'"

    rm -f "/tmp/clavain-stop-${session_id}"
    assert_success
    assert_output ""  # Should exit early due to shared sentinel
}
```

This verifies that the shared sentinel prevents cascading Stop hooks.

---

## Severity Assessment

| Finding | Severity | Impact if Deployed |
|---------|----------|-------------------|
| Per-hook sentinel race | **CRITICAL** | Multiple hooks return "block" in same Stop cycle → undefined Claude behavior, likely prompt confusion or last-hook-wins |
| Double-sourcing guard misleading | **LOW** | No runtime impact, only cognitive load and misleading comments |
| Grep pattern false positive | **LOW** | User messages trigger investigation signal, slight over-counting (acceptable) |
| Test fixture assumption | **NONE** | Tests are correct as written |

---

## Verdict

**Do not implement as written.** The per-hook sentinel strategy breaks Stop cycle coordination and introduces a race where multiple hooks can return conflicting "block" decisions.

The fix is straightforward: keep the shared sentinel, rename the throttle sentinels.

Updated sentinel architecture:

```
/tmp/clavain-stop-${SESSION_ID}           # shared, written by first hook to trigger, prevents cascading blocks
/tmp/clavain-compound-last-${SESSION_ID}  # per-hook, throttle for auto-compound (5 min)
/tmp/clavain-drift-last-${SESSION_ID}     # per-hook, throttle for auto-drift-check (10 min)
/tmp/clavain-handoff-${SESSION_ID}        # per-session, ensures handoff only fires once per session
```

All other aspects of the plan are sound.
