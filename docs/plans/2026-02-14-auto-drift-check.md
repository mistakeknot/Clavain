# Auto-Drift-Check Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Add a Stop hook that auto-triggers `/interwatch:watch` after shipped work, with shared signal detection library extracted from auto-compound.sh.

**Architecture:** Extract weighted signal detection from `auto-compound.sh` into `hooks/lib-signals.sh`. Refactor auto-compound to source it. Build new `hooks/auto-drift-check.sh` that also sources it with a lower threshold. Stop hooks share a single cycle sentinel (`/tmp/clavain-stop-${SESSION_ID}`) for mutual exclusion — only the first hook to fire in a Stop cycle returns `block`. Each hook has its own throttle sentinel for time-based rate limiting.

**Review findings applied:** Shared sentinel preserved (not per-hook), version-bump signal documented as intentional addition, grep pattern false positive fixed, shared sentinel test added, cleanup glob expanded for throttle sentinels, empty string test added, auto-compound header preserves signal list, demo hook sentinel namespaced.

**Tech Stack:** Bash (hooks), Python (structural tests), bats-core (shell tests)

**Bead:** Clavain-iwuy
**Phase:** executing (as of 2026-02-14T22:44:13Z)
**PRD:** docs/prds/2026-02-14-auto-drift-check.md

---

## Task 1: Extract lib-signals.sh

**Files:**
- Create: `hooks/lib-signals.sh`
- Test: `tests/shell/lib_signals.bats`

**Step 1: Write the test file**

Create `tests/shell/lib_signals.bats` with these tests:

```bash
#!/usr/bin/env bats
# Tests for hooks/lib-signals.sh

setup() {
    load test_helper
    source "$HOOKS_DIR/lib-signals.sh"
}

teardown() {
    unset CLAVAIN_SIGNALS CLAVAIN_SIGNAL_WEIGHT
}

@test "lib-signals: detect_signals sets CLAVAIN_SIGNALS and CLAVAIN_SIGNAL_WEIGHT" {
    local transcript='{"role":"assistant","content":"Running \"git commit -m fix\""}'
    detect_signals "$transcript"
    [[ -n "$CLAVAIN_SIGNALS" ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -ge 1 ]]
}

@test "lib-signals: detects commit signal (weight 1)" {
    local transcript='{"role":"assistant","content":"Running \"git commit -m fix\""}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"commit"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 1 ]]
}

@test "lib-signals: detects bead-closed signal (weight 1)" {
    local transcript='{"role":"assistant","content":"Running \"bd close Clavain-abc1\""}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"bead-closed"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 1 ]]
}

@test "lib-signals: detects resolution signal (weight 2)" {
    local transcript='{"role":"user","content":"that worked, thanks!"}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"resolution"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 2 ]]
}

@test "lib-signals: detects investigation signal (weight 2)" {
    local transcript='{"role":"assistant","content":"the issue was a race condition in the cache layer"}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"investigation"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 2 ]]
}

@test "lib-signals: detects insight signal (weight 1)" {
    local transcript='Insight ─ The key realization is that X causes Y'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"insight"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 1 ]]
}

@test "lib-signals: detects recovery signal (weight 2)" {
    local transcript=$'test FAILED: expected 5 got 3\nAll tests passed after fix'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"recovery"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 2 ]]
}

@test "lib-signals: detects version-bump signal (weight 2)" {
    local transcript='{"role":"assistant","content":"Running bump-version.sh 0.7.0"}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"version-bump"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 2 ]]
}

@test "lib-signals: detects interpub:release as version-bump (weight 2)" {
    local transcript='{"role":"assistant","content":"Running /interpub:release 1.0.0"}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"version-bump"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 2 ]]
}

@test "lib-signals: accumulates weights from multiple signals" {
    local transcript=$'Running "git commit -m fix"\nInsight ─ key insight\nthe issue was a cache bug'
    detect_signals "$transcript"
    # commit(1) + insight(1) + investigation(2) = 4
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 4 ]]
}

@test "lib-signals: no signals returns weight 0 and empty SIGNALS" {
    local transcript='{"role":"user","content":"What is Python?"}'
    detect_signals "$transcript"
    [[ -z "$CLAVAIN_SIGNALS" ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 0 ]]
}

@test "lib-signals: empty string returns weight 0" {
    detect_signals ""
    [[ -z "$CLAVAIN_SIGNALS" ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 0 ]]
}

@test "lib-signals: CLAVAIN_SIGNALS has no trailing comma" {
    local transcript=$'Running "git commit -m fix"\nRunning "bd close Clavain-abc1"'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" != *"," ]]  # no trailing comma
    [[ "$CLAVAIN_SIGNALS" == *","* ]]  # but has internal comma (2 signals)
}
```

**Step 2: Run tests to verify they fail**

Run: `bats tests/shell/lib_signals.bats`
Expected: FAIL — `hooks/lib-signals.sh` does not exist yet.

**Step 3: Create lib-signals.sh**

Create `hooks/lib-signals.sh`:

```bash
#!/usr/bin/env bash
# Shared signal detection library for Clavain Stop hooks.
#
# Usage:
#   source hooks/lib-signals.sh
#   detect_signals "$TRANSCRIPT_TEXT"
#   echo "Signals: $CLAVAIN_SIGNALS (weight: $CLAVAIN_SIGNAL_WEIGHT)"
#
# After calling detect_signals(), two variables are set:
#   CLAVAIN_SIGNALS       — comma-separated list of detected signal names
#   CLAVAIN_SIGNAL_WEIGHT — integer total weight of all detected signals
#
# Signal definitions:
#   commit          (weight 1) — git commit in transcript
#   resolution      (weight 2) — debugging resolution phrases
#   investigation   (weight 2) — root cause / investigation language
#   bead-closed     (weight 1) — bd close in transcript
#   insight         (weight 1) — ★ Insight block marker
#   recovery        (weight 2) — test/build failure followed by pass
#   version-bump    (weight 2) — bump-version.sh or interpub:release

# Guard against re-parsing function definitions (performance optimization).
# Note: detect_signals() resets output vars on each call — no persistent state.
[[ -n "${_LIB_SIGNALS_LOADED:-}" ]] && return 0
_LIB_SIGNALS_LOADED=1

# Detect signals in transcript text. Sets CLAVAIN_SIGNALS and CLAVAIN_SIGNAL_WEIGHT.
# Args: $1 = transcript text (multi-line string)
detect_signals() {
    local text="$1"
    CLAVAIN_SIGNALS=""
    CLAVAIN_SIGNAL_WEIGHT=0

    # 1. Git commit (weight 1)
    if echo "$text" | grep -q '"git commit\|"git add.*&&.*git commit'; then
        CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS}commit,"
        CLAVAIN_SIGNAL_WEIGHT=$((CLAVAIN_SIGNAL_WEIGHT + 1))
    fi

    # 2. Debugging resolution phrases (weight 2)
    if echo "$text" | grep -iq '"that worked\|"it'\''s fixed\|"working now\|"problem solved\|"that did it\|"bug fixed\|"issue resolved'; then
        CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS}resolution,"
        CLAVAIN_SIGNAL_WEIGHT=$((CLAVAIN_SIGNAL_WEIGHT + 2))
    fi

    # 3. Investigation language (weight 2)
    if echo "$text" | grep -iq '"root cause\|"the issue was\|"the problem was\|"turned out\|"the fix is\|"solved by'; then
        CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS}investigation,"
        CLAVAIN_SIGNAL_WEIGHT=$((CLAVAIN_SIGNAL_WEIGHT + 2))
    fi

    # 4. Bead closed (weight 1)
    if echo "$text" | grep -q '"bd close\|"bd update.*completed'; then
        CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS}bead-closed,"
        CLAVAIN_SIGNAL_WEIGHT=$((CLAVAIN_SIGNAL_WEIGHT + 1))
    fi

    # 5. Insight block (weight 1)
    if echo "$text" | grep -q 'Insight ─'; then
        CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS}insight,"
        CLAVAIN_SIGNAL_WEIGHT=$((CLAVAIN_SIGNAL_WEIGHT + 1))
    fi

    # 6. Build/test recovery (weight 2)
    if echo "$text" | grep -iq 'FAIL\|FAILED\|ERROR.*build\|error.*compile\|test.*failed'; then
        if echo "$text" | grep -iq 'passed\|BUILD SUCCESSFUL\|build succeeded\|tests pass\|all.*pass'; then
            CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS}recovery,"
            CLAVAIN_SIGNAL_WEIGHT=$((CLAVAIN_SIGNAL_WEIGHT + 2))
        fi
    fi

    # 7. Version bump (weight 2)
    if echo "$text" | grep -q 'bump-version\|interpub:release'; then
        CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS}version-bump,"
        CLAVAIN_SIGNAL_WEIGHT=$((CLAVAIN_SIGNAL_WEIGHT + 2))
    fi

    # Remove trailing comma
    CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS%,}"
}
```

**Step 4: Run tests to verify they pass**

Run: `bats tests/shell/lib_signals.bats`
Expected: All 13 tests PASS.

**Step 5: Commit**

```bash
git add hooks/lib-signals.sh tests/shell/lib_signals.bats
git commit -m "feat: extract lib-signals.sh shared signal detection library"
```

---

## Task 2: Refactor auto-compound.sh to use lib-signals.sh

**Files:**
- Modify: `hooks/auto-compound.sh` (lines 46-47 sentinel, lines 75-126 signal detection)

**Step 1: Run existing auto-compound tests as baseline**

Run: `bats tests/shell/auto_compound.bats`
Expected: All 10 tests PASS (baseline before refactor).

**Step 2: Refactor auto-compound.sh**

Keep the shared sentinel unchanged (`/tmp/clavain-stop-${SESSION_ID}`) — it provides mutual exclusion so only one Stop hook returns `block` per cycle.

Replace inline signal detection (lines 75-126) with lib-signals.sh sourcing:

```bash
# Source shared signal detection
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib-signals.sh"

# Extract recent transcript (last 80 lines for broader context)
RECENT=$(tail -80 "$TRANSCRIPT" 2>/dev/null || true)
if [[ -z "$RECENT" ]]; then
    exit 0
fi

# Detect signals using shared library
detect_signals "$RECENT"

# Threshold: need weight >= 3 to trigger compound
if [[ "$CLAVAIN_SIGNAL_WEIGHT" -lt 3 ]]; then
    exit 0
fi

SIGNALS="$CLAVAIN_SIGNALS"
WEIGHT="$CLAVAIN_SIGNAL_WEIGHT"
```

Remove the old inline signal detection block (the 7 grep patterns and WEIGHT/SIGNALS variable init).

Keep everything else identical: guards, throttle, REASON string, JSON output, cleanup.

**Step 3: Run existing auto-compound tests to verify no regression**

Run: `bats tests/shell/auto_compound.bats`
Expected: All 10 tests PASS (identical behavior).

**Step 4: Add version-bump test**

Add a new test to `tests/shell/auto_compound.bats` documenting that version-bump is now detected (intentional behavior change from lib-signals.sh extraction):

```bash
@test "auto-compound: version-bump+commit triggers (weight >= 3)" {
    # Create a transcript fixture with version bump + commit
    local fixture="$TMPDIR_COMPOUND/transcript_version_bump.jsonl"
    printf '{"role":"assistant","content":"Running bump-version.sh 0.7.0"}\n{"role":"assistant","content":"Running \"git commit -m bump\""}\n' > "$fixture"
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$fixture\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success
    # version-bump (2) + commit (1) = 3, meets threshold
    echo "$output" | jq -e '.decision == "block"'
}
```

**Step 5: Run updated tests**

Run: `bats tests/shell/auto_compound.bats`
Expected: All 11 tests PASS.

**Step 6: Commit**

```bash
git add hooks/auto-compound.sh tests/shell/auto_compound.bats
git commit -m "refactor: auto-compound.sh uses lib-signals.sh for shared signal detection"
```

---

## Task 3: (Removed — shared sentinel preserved)

Session-handoff.sh keeps the shared sentinel `/tmp/clavain-stop-${SESSION_ID}` unchanged. No modification needed. Task removed per flux-drive review finding #1.

---

## Task 4: Build auto-drift-check.sh

**Files:**
- Create: `hooks/auto-drift-check.sh`
- Modify: `hooks/hooks.json` (add Stop hook entry)
- Test: `tests/shell/auto_drift_check.bats`

**Step 1: Write test file**

Create `tests/shell/auto_drift_check.bats`:

```bash
#!/usr/bin/env bats
# Tests for hooks/auto-drift-check.sh

setup_file() {
    export TMPDIR_DRIFT="$(mktemp -d)"
    # Reuse transcript fixtures from auto-compound tests
    cp "$BATS_TEST_DIRNAME/../fixtures/transcript_with_commit.jsonl" "$TMPDIR_DRIFT/transcript_commit.jsonl"
    cp "$BATS_TEST_DIRNAME/../fixtures/transcript_with_insight.jsonl" "$TMPDIR_DRIFT/transcript_insight.jsonl"
    cp "$BATS_TEST_DIRNAME/../fixtures/transcript_clean.jsonl" "$TMPDIR_DRIFT/transcript_clean.jsonl"
    cp "$BATS_TEST_DIRNAME/../fixtures/transcript_single_commit.jsonl" "$TMPDIR_DRIFT/transcript_single_commit.jsonl"
    cp "$BATS_TEST_DIRNAME/../fixtures/transcript_with_recovery.jsonl" "$TMPDIR_DRIFT/transcript_recovery.jsonl"
}

teardown_file() {
    rm -rf "$TMPDIR_DRIFT"
}

setup() {
    load test_helper
}

teardown() {
    rm -f /tmp/clavain-stop-* /tmp/clavain-drift-last-* 2>/dev/null || true
}

@test "auto-drift-check: noop when stop_hook_active" {
    run bash -c "echo '{\"stop_hook_active\": true, \"transcript_path\": \"$TMPDIR_DRIFT/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    assert_success
    assert_output ""
}

@test "auto-drift-check: commit+bead-close triggers at threshold 2" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_DRIFT/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    assert_success
    # commit (1) + bead-closed (1) = 2, meets drift threshold of 2
    echo "$output" | jq -e '.decision == "block"'
}

@test "auto-drift-check: single commit below threshold (weight 1)" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_DRIFT/transcript_single_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    assert_success
    assert_output ""
}

@test "auto-drift-check: no signal passthrough" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_DRIFT/transcript_clean.jsonl\"}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    assert_success
    assert_output ""
}

@test "auto-drift-check: reason mentions interwatch:watch" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_DRIFT/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    assert_success
    echo "$output" | jq -r '.reason' | grep -q 'interwatch:watch'
}

@test "auto-drift-check: exits zero always" {
    run bash -c "echo '{\"stop_hook_active\": true}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    assert_success
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"/nonexistent/file.jsonl\"}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    assert_success
}

@test "auto-drift-check: skips when shared sentinel exists" {
    local session_id="test-drift-sentinel-$$"
    local sentinel="/tmp/clavain-stop-${session_id}"
    touch "$sentinel"
    run bash -c "echo '{\"stop_hook_active\": false, \"session_id\": \"${session_id}\", \"transcript_path\": \"$TMPDIR_DRIFT/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    rm -f "$sentinel"
    assert_success
    assert_output ""
}

@test "auto-drift-check: skips when opt-out file exists" {
    local tmpdir
    tmpdir=$(mktemp -d)
    mkdir -p "$tmpdir/.claude"
    touch "$tmpdir/.claude/clavain.no-driftcheck"
    run bash -c "cd '$tmpdir' && echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_DRIFT/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    rm -rf "$tmpdir"
    assert_success
    assert_output ""
}

@test "auto-drift-check: skips when throttle sentinel is recent" {
    local session_id="test-drift-throttle-$$"
    local throttle_sentinel="/tmp/clavain-drift-last-${session_id}"
    touch "$throttle_sentinel"
    run bash -c "echo '{\"stop_hook_active\": false, \"session_id\": \"${session_id}\", \"transcript_path\": \"$TMPDIR_DRIFT/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    rm -f "$throttle_sentinel"
    assert_success
    assert_output ""
}

@test "auto-drift-check: recovery signals trigger (weight 2)" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_DRIFT/transcript_recovery.jsonl\"}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    assert_success
    # recovery (2) + investigation (2) = 4, above threshold
    echo "$output" | jq -e '.decision == "block"'
}

```

**Step 2: Run tests to verify they fail**

Run: `bats tests/shell/auto_drift_check.bats`
Expected: FAIL — `hooks/auto-drift-check.sh` does not exist.

**Step 3: Create auto-drift-check.sh**

Create `hooks/auto-drift-check.sh`:

```bash
#!/usr/bin/env bash
# Stop hook: auto-trigger /interwatch:watch after shipped work
#
# Detects work signals (commits, bead closures, version bumps, etc.)
# using the shared lib-signals.sh library. When total weight >= 2,
# outputs a block+reason JSON telling Claude to run /interwatch:watch.
#
# Lower threshold than auto-compound (>= 2 vs >= 3) because doc drift
# checking is cheap and important to trigger early.
#
# Guards: stop_hook_active, shared sentinel, per-repo opt-out, 10-min throttle,
#         interwatch discovery (graceful degradation if not installed).
#
# Input: Hook JSON on stdin (session_id, transcript_path, stop_hook_active)
# Output: JSON on stdout
# Exit: 0 always

set -euo pipefail

# Guard: fail-open if jq is not available
if ! command -v jq &>/dev/null; then
    exit 0
fi

# Read hook input
INPUT=$(cat)

# Guard: if stop hook is already active, don't re-trigger (prevents infinite loop)
STOP_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
if [[ "$STOP_ACTIVE" == "true" ]]; then
    exit 0
fi

# Guard: per-repo opt-out
if [[ -f ".claude/clavain.no-driftcheck" ]]; then
    exit 0
fi

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')

# Guard: shared sentinel — only one Stop hook returns "block" per cycle
STOP_SENTINEL="/tmp/clavain-stop-${SESSION_ID}"
if [[ -f "$STOP_SENTINEL" ]]; then
    exit 0
fi
touch "$STOP_SENTINEL"

# Guard: throttle — at most once per 10 minutes
THROTTLE_SENTINEL="/tmp/clavain-drift-last-${SESSION_ID}"
if [[ -f "$THROTTLE_SENTINEL" ]]; then
    THROTTLE_MTIME=$(stat -c %Y "$THROTTLE_SENTINEL" 2>/dev/null || stat -f %m "$THROTTLE_SENTINEL" 2>/dev/null || date +%s)
    THROTTLE_NOW=$(date +%s)
    if [[ $((THROTTLE_NOW - THROTTLE_MTIME)) -lt 600 ]]; then
        exit 0
    fi
fi

# Guard: interwatch must be installed
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib.sh"
INTERWATCH_ROOT=$(_discover_interwatch_plugin)
if [[ -z "$INTERWATCH_ROOT" ]]; then
    exit 0
fi

TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty')
if [[ -z "$TRANSCRIPT" || ! -f "$TRANSCRIPT" ]]; then
    exit 0
fi

# Extract recent transcript (last 80 lines for broader context)
RECENT=$(tail -80 "$TRANSCRIPT" 2>/dev/null || true)
if [[ -z "$RECENT" ]]; then
    exit 0
fi

# Detect signals using shared library
source "${SCRIPT_DIR}/lib-signals.sh"
detect_signals "$RECENT"

# Threshold: need weight >= 2 to trigger drift check
# commit (1) + bead-close (1) = 2, enough for drift check
if [[ "$CLAVAIN_SIGNAL_WEIGHT" -lt 2 ]]; then
    exit 0
fi

SIGNALS="$CLAVAIN_SIGNALS"
WEIGHT="$CLAVAIN_SIGNAL_WEIGHT"

# Build the reason prompt
REASON="Auto-drift-check: detected shipped-work signals [${SIGNALS}] (weight ${WEIGHT}). Documentation may be stale. Run /interwatch:watch using the Skill tool to scan for doc drift. If interwatch finds drift, follow its recommendations (auto-refresh for Certain/High confidence, suggest for Medium)."

# Write throttle sentinel
touch "$THROTTLE_SENTINEL"

# Return block decision
if command -v jq &>/dev/null; then
    jq -n --arg reason "$REASON" '{"decision":"block","reason":$reason}'
else
    cat <<ENDJSON
{
  "decision": "block",
  "reason": "${REASON}"
}
ENDJSON
fi

# Clean up stale sentinels from previous sessions
find /tmp -maxdepth 1 \( -name 'clavain-stop-*' -o -name 'clavain-drift-last-*' -o -name 'clavain-compound-last-*' \) -mmin +60 -delete 2>/dev/null || true

exit 0
```

**Step 4: Run tests**

Run: `bats tests/shell/auto_drift_check.bats`
Expected: All 10 tests PASS.

**Step 5: Register in hooks.json**

Update `hooks/hooks.json` — add auto-drift-check.sh between auto-compound and session-handoff in the Stop hooks array:

Current Stop hooks order:
1. auto-compound.sh
2. session-handoff.sh

New Stop hooks order:
1. auto-compound.sh
2. auto-drift-check.sh (NEW)
3. session-handoff.sh

The hook entry:
```json
{
    "type": "command",
    "command": "${CLAUDE_PLUGIN_ROOT}/hooks/auto-drift-check.sh",
    "timeout": 5
}
```

**Step 6: Run structural tests to verify hooks.json is valid**

Run: `cd /root/projects/Clavain && uv run --project tests pytest tests/structural/test_hooks_json.py -v`
Expected: All tests PASS (hooks.json is valid, command file exists, timeout <= 30).

**Step 7: Commit**

```bash
git add hooks/auto-drift-check.sh hooks/hooks.json tests/shell/auto_drift_check.bats
git commit -m "feat: add auto-drift-check Stop hook for interwatch integration"
```

---

## Task 5: Update CLAUDE.md and run full test suite

**Files:**
- Modify: `CLAUDE.md` (add syntax check lines)
- Modify: `hooks/auto-compound.sh` header comment (update signal list reference)

**Step 1: Update CLAUDE.md quick commands**

Add two new syntax check lines to the Quick Commands section:

```bash
bash -n hooks/lib-signals.sh             # Syntax check
bash -n hooks/auto-drift-check.sh        # Syntax check
```

Also update the hook count in the Overview line from "7 hooks" to "8 hooks" (adding auto-drift-check).

**Step 2: Update auto-compound.sh header comment**

Update the comment block at the top of `auto-compound.sh` to reference lib-signals.sh:

```bash
# Stop hook: auto-compound non-trivial problem-solving after each turn
#
# Uses shared signal detection from lib-signals.sh with these signals:
#   - Git commits (weight 1)
#   - Debugging resolutions (weight 2)
#   - Investigation language (weight 2)
#   - Bead closures (weight 1)
#   - Insight blocks (weight 1)
#   - Build/test recovery (weight 2)
#   - Version bumps (weight 2)
#
# Compound triggers when total signal weight >= 3.
# See hooks/lib-signals.sh for signal pattern definitions.
#
# Guards: stop_hook_active, shared sentinel, per-repo opt-out, 5-min throttle.
```

**Step 3: Run full test suite**

Run: `cd /root/projects/Clavain && bats tests/shell/*.bats && uv run --project tests pytest tests/structural/ -v`
Expected: All shell tests and structural tests PASS.

**Step 4: Syntax check all new/modified files**

Run:
```bash
bash -n hooks/lib-signals.sh && bash -n hooks/auto-compound.sh && bash -n hooks/auto-drift-check.sh && bash -n hooks/session-handoff.sh
```
Expected: No errors.

**Step 5: Commit**

```bash
git add CLAUDE.md hooks/auto-compound.sh
git commit -m "docs: update CLAUDE.md with new hook syntax checks and count"
```

---

## Task 6: Demo hook for interwatch repo

**Files:**
- Create: `/root/projects/interwatch/examples/hooks/auto-drift-check-example.sh`
- Modify: `/root/projects/interwatch/README.md` (add hooks section)

**Step 1: Create examples directory and demo hook**

Create `/root/projects/interwatch/examples/hooks/auto-drift-check-example.sh`:

```bash
#!/usr/bin/env bash
# Example: Auto-trigger /interwatch:watch from a Claude Code Stop hook.
#
# This is a standalone example showing how to detect work signals
# and trigger Interwatch drift scanning. It does NOT depend on
# Clavain's lib-signals.sh — all signal detection is inline.
#
# To use this in your own plugin:
# 1. Copy this file to your plugin's hooks/ directory
# 2. Register it in your hooks.json under "Stop" event
# 3. Customize the signals and threshold below
#
# Hook JSON input (stdin):
#   { "session_id": "...", "transcript_path": "...", "stop_hook_active": false }
#
# Output (stdout):
#   { "decision": "block", "reason": "..." } — when drift check is warranted
#   (empty) — when no action needed
#
# Exit: always 0 (hooks must not fail)

set -euo pipefail

# --- CUSTOMIZABLE SETTINGS ---

# Minimum signal weight to trigger a drift check.
# Lower = more sensitive. commit(1) + bead-close(1) = 2.
THRESHOLD=2

# Throttle window in seconds (600 = 10 minutes).
THROTTLE_SECONDS=600

# Per-repo opt-out file. Create this file to disable drift checking.
OPT_OUT_FILE=".claude/no-driftcheck"

# --- END SETTINGS ---

# Guard: fail-open if jq is not available
if ! command -v jq &>/dev/null; then
    exit 0
fi

INPUT=$(cat)

# Guard: prevent infinite loop
STOP_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
if [[ "$STOP_ACTIVE" == "true" ]]; then
    exit 0
fi

# Guard: per-repo opt-out
if [[ -f "$OPT_OUT_FILE" ]]; then
    exit 0
fi

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')

# Guard: throttle
# Use a unique prefix to avoid collision with other plugins.
THROTTLE_FILE="/tmp/yourplugin-drift-last-${SESSION_ID}"
if [[ -f "$THROTTLE_FILE" ]]; then
    MTIME=$(stat -c %Y "$THROTTLE_FILE" 2>/dev/null || stat -f %m "$THROTTLE_FILE" 2>/dev/null || date +%s)
    NOW=$(date +%s)
    if [[ $((NOW - MTIME)) -lt $THROTTLE_SECONDS ]]; then
        exit 0
    fi
fi

TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty')
if [[ -z "$TRANSCRIPT" || ! -f "$TRANSCRIPT" ]]; then
    exit 0
fi

RECENT=$(tail -80 "$TRANSCRIPT" 2>/dev/null || true)
if [[ -z "$RECENT" ]]; then
    exit 0
fi

# --- SIGNAL DETECTION (customize these patterns) ---

WEIGHT=0

# Git commit (weight 1)
if echo "$RECENT" | grep -q '"git commit'; then
    WEIGHT=$((WEIGHT + 1))
fi

# Bead/issue closed (weight 1)
if echo "$RECENT" | grep -q '"bd close'; then
    WEIGHT=$((WEIGHT + 1))
fi

# Version bump (weight 2)
if echo "$RECENT" | grep -q 'bump-version\|interpub:release'; then
    WEIGHT=$((WEIGHT + 2))
fi

# --- END SIGNAL DETECTION ---

if [[ "$WEIGHT" -lt "$THRESHOLD" ]]; then
    exit 0
fi

touch "$THROTTLE_FILE"

REASON="Shipped work detected (weight ${WEIGHT}). Run /interwatch:watch to check for documentation drift."
jq -n --arg reason "$REASON" '{"decision":"block","reason":$reason}'

exit 0
```

**Step 2: Update interwatch README.md**

Add a "Hook Integration" section to the README explaining the demo hook and how to integrate.

**Step 3: Verify syntax**

Run: `bash -n /root/projects/interwatch/examples/hooks/auto-drift-check-example.sh`
Expected: No errors.

**Step 4: Commit in interwatch repo**

```bash
cd /root/projects/interwatch
git add examples/hooks/auto-drift-check-example.sh README.md
git commit -m "docs: add demo Stop hook for auto-drift-check integration"
```

---

## Verification Checklist

After all tasks are complete, verify:

```bash
# 1. All new files exist
ls hooks/lib-signals.sh hooks/auto-drift-check.sh

# 2. Syntax checks pass
bash -n hooks/lib-signals.sh
bash -n hooks/auto-drift-check.sh
bash -n hooks/auto-compound.sh
bash -n hooks/session-handoff.sh

# 3. All shell tests pass
bats tests/shell/*.bats

# 4. All structural tests pass
cd /root/projects/Clavain && uv run --project tests pytest tests/structural/ -v

# 5. hooks.json is valid JSON with 3 Stop hooks
python3 -c "import json; h=json.load(open('hooks/hooks.json')); print(len(h['hooks']['Stop'][0]['hooks']), 'Stop hooks')"

# 6. Demo hook syntax passes
bash -n /root/projects/interwatch/examples/hooks/auto-drift-check-example.sh
```
