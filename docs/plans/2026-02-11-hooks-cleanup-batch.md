# Hooks Cleanup Batch Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Fix the stop-hook cascade bug and narrow auto-compound triggers to reduce false positives.

**Architecture:** Two sequential fixes to the hooks subsystem. Task 1 adds a shared sentinel to prevent cross-hook cascading on Stop. Task 2 (depends on Task 1) raises the compound threshold, adds opt-out and throttle.

**Tech Stack:** Bash (hooks), bats-core (tests)

**Beads:** Clavain-8t5l (Task 1), Clavain-azlo (Task 2)

**Flux-drive review notes (incorporated):**
- TOCTOU fix: Write sentinel immediately after check, before transcript analysis
- No `local` in script scope (auto-compound.sh is not a function)
- Test fixtures must be updated for new threshold (insight+commit=2 < 3, recovery-only=2 < 3)
- Add stale sentinel cleanup
- Throttle stat fallback: use `date +%s` (fail-closed) not `echo 0` (fail-open)
- Task 3 (escape_for_json) dropped — control-char loop is required by JSON spec

---

### Task 1: Add shared Stop hook sentinel (Clavain-8t5l)

**Files:**
- Modify: `hooks/auto-compound.sh` (add sentinel check + write)
- Modify: `hooks/session-handoff.sh` (add sentinel check + write)
- Modify: `tests/shell/auto_compound.bats` (add sentinel test)

**Step 1: Write the failing test for sentinel behavior**

Add to `tests/shell/auto_compound.bats`:

```bash
@test "auto-compound: skips when cross-hook sentinel exists" {
    local session_id="test-sentinel-$$"
    local sentinel="/tmp/clavain-stop-${session_id}"
    touch "$sentinel"
    run bash -c "echo '{\"stop_hook_active\": false, \"session_id\": \"${session_id}\", \"transcript_path\": \"$TMPDIR_COMPOUND/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    rm -f "$sentinel"
    assert_success
    assert_output ""
}
```

**Step 2: Run test to verify it fails**

Run: `bats tests/shell/auto_compound.bats`
Expected: New test FAILS (auto-compound.sh doesn't check sentinel yet)

**Step 3: Add sentinel check to auto-compound.sh**

After the `STOP_ACTIVE` guard (line 38), extract SESSION_ID and add the shared sentinel check. **Critical: write sentinel immediately after check to minimize TOCTOU window:**

```bash
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')

# Guard: if another Stop hook already fired this cycle, don't cascade
STOP_SENTINEL="/tmp/clavain-stop-${SESSION_ID}"
if [[ -f "$STOP_SENTINEL" ]]; then
    exit 0
fi
# Write sentinel NOW — before transcript analysis — to minimize race window
touch "$STOP_SENTINEL"
```

Also add cleanup of stale sentinels (>60 min old) at the end of the script, before `exit 0`:

```bash
# Clean up stale sentinels from previous sessions
find /tmp -maxdepth 1 -name 'clavain-stop-*' -mmin +60 -delete 2>/dev/null || true
```

**Step 4: Add sentinel check to session-handoff.sh**

After the `STOP_ACTIVE` guard (line 30), SESSION_ID is already extracted on line 32. Insert the shared sentinel check between SESSION_ID extraction and the handoff-specific sentinel check. **Write sentinel immediately after check:**

```bash
# Guard: if another Stop hook already fired this cycle, don't cascade
STOP_SENTINEL="/tmp/clavain-stop-${SESSION_ID}"
if [[ -f "$STOP_SENTINEL" ]]; then
    exit 0
fi
# Write sentinel NOW — before signal analysis
touch "$STOP_SENTINEL"
```

Also add stale sentinel cleanup before `exit 0`:

```bash
# Clean up stale sentinels from previous sessions
find /tmp -maxdepth 1 -name 'clavain-stop-*' -mmin +60 -delete 2>/dev/null || true
```

**Step 5: Run tests to verify they pass**

Run: `bats tests/shell/auto_compound.bats`
Expected: All tests PASS including the new sentinel test

Run: `bash -n hooks/auto-compound.sh && bash -n hooks/session-handoff.sh`
Expected: Syntax OK

**Step 6: Commit**

```bash
git add hooks/auto-compound.sh hooks/session-handoff.sh tests/shell/auto_compound.bats
git commit -m "fix: add shared sentinel between Stop hooks to prevent cascade (Clavain-8t5l)"
```

---

### Task 2: Narrow auto-compound triggers (Clavain-azlo)

**Files:**
- Modify: `hooks/auto-compound.sh` (threshold, opt-out, throttle, signal weights, header comment)
- Modify: `tests/shell/auto_compound.bats` (update existing tests + add new)
- Modify: `tests/fixtures/transcript_with_insight.jsonl` (add investigation signal)
- Modify: `tests/fixtures/transcript_with_recovery.jsonl` (add investigation signal)

**Step 1: Write the failing test for opt-out file**

Add to `tests/shell/auto_compound.bats`:

```bash
@test "auto-compound: skips when opt-out file exists" {
    local tmpdir
    tmpdir=$(mktemp -d)
    mkdir -p "$tmpdir/.claude"
    touch "$tmpdir/.claude/clavain.no-autocompound"
    run bash -c "cd '$tmpdir' && echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_COMPOUND/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    rm -rf "$tmpdir"
    assert_success
    assert_output ""
}
```

**Step 2: Write the failing test for throttle**

Add to `tests/shell/auto_compound.bats`:

```bash
@test "auto-compound: skips when throttle sentinel is recent" {
    local session_id="test-throttle-$$"
    local throttle_sentinel="/tmp/clavain-compound-last-${session_id}"
    touch "$throttle_sentinel"
    run bash -c "echo '{\"stop_hook_active\": false, \"session_id\": \"${session_id}\", \"transcript_path\": \"$TMPDIR_COMPOUND/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    rm -f "$throttle_sentinel"
    assert_success
    assert_output ""
}
```

**Step 3: Run tests to verify new tests fail**

Run: `bats tests/shell/auto_compound.bats`
Expected: New opt-out and throttle tests FAIL

**Step 4: Implement changes in auto-compound.sh**

4a. Add opt-out check after the `STOP_ACTIVE` guard (before SESSION_ID extraction):

```bash
# Guard: per-repo opt-out
if [[ -f ".claude/clavain.no-autocompound" ]]; then
    exit 0
fi
```

4b. Add throttle check after SESSION_ID extraction (after the STOP_SENTINEL block from Task 1). **No `local` — this is script scope, not a function:**

```bash
# Guard: throttle — at most once per 5 minutes
THROTTLE_SENTINEL="/tmp/clavain-compound-last-${SESSION_ID}"
if [[ -f "$THROTTLE_SENTINEL" ]]; then
    THROTTLE_MTIME=$(stat -c %Y "$THROTTLE_SENTINEL" 2>/dev/null || stat -f %m "$THROTTLE_SENTINEL" 2>/dev/null || date +%s)
    THROTTLE_NOW=$(date +%s)
    if [[ $((THROTTLE_NOW - THROTTLE_MTIME)) -lt 300 ]]; then
        exit 0
    fi
fi
```

Note: fallback is `date +%s` (fail-closed: assumes fresh sentinel) not `echo 0` (fail-open).

4c. Remove `high-activity` signal (lines 94-99) entirely.

4d. Remove `error-fix-cycle` signal (lines 101-107) entirely.

4e. Raise threshold from 2 to 3. Replace the threshold block:

```bash
# Threshold: need weight >= 3 to trigger compound
# commit (1) + bead-close (1) = 2, not enough alone.
# Needs real investigation/resolution/recovery signal.
if [[ "$WEIGHT" -lt 3 ]]; then
    exit 0
fi
```

4f. Write throttle sentinel before the block decision output:

```bash
# Write throttle sentinel
touch "$THROTTLE_SENTINEL"
```

4g. Update the header comment (lines 3-18) to reflect new signal list and threshold:

```bash
# Analyzes the recent conversation for compoundable signals:
#   - Git commits (weight 1)
#   - Debugging resolutions ("that worked", "it's fixed", etc.) (weight 2)
#   - Non-trivial fix patterns (investigation language) (weight 2)
#   - Bead closures (completed work items) (weight 1)
#   - Insight blocks (★ Insight markers in explanatory mode) (weight 1)
#   - Build/test recovery (passing after failure) (weight 2)
#
# Signals are weighted. Compound triggers when total weight >= 3,
# so commit + bead-close (2) won't fire alone, but commit + resolution (3) will.
#
# Guards: stop_hook_active, cross-hook sentinel, per-repo opt-out, 5-min throttle.
```

**Step 5: Update test fixtures for new threshold**

The `transcript_with_insight.jsonl` fixture has insight(1)+commit(1)=2, now below threshold 3. Add an investigation signal:

Add this line after line 4 of `tests/fixtures/transcript_with_insight.jsonl`:
```jsonl
{"role":"assistant","content":"The problem was that cache invalidation raced with the write path."}
```

This adds investigation(2), making total: insight(1)+commit(1)+investigation(2)=4 ≥ 3.

The `transcript_with_recovery.jsonl` fixture has recovery(2) only after removing error-fix-cycle. Add an investigation signal:

Add this line after line 4 of `tests/fixtures/transcript_with_recovery.jsonl`:
```jsonl
{"role":"assistant","content":"The root cause was an expired token in the refresh logic."}
```

This adds investigation(2), making total: recovery(2)+investigation(2)=4 ≥ 3.

**Step 6: Update existing tests for new threshold**

Replace the `detects commit+bead-close signals` test with:

```bash
@test "auto-compound: commit+bead-close below threshold (weight 2 < 3)" {
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_COMPOUND/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-compound.sh'"
    assert_success
    # commit (1) + bead-closed (1) = 2, below new threshold of 3
    assert_output ""
}
```

The `detects insight+commit signals` and `detects build/test recovery` tests should still pass after the fixture updates (both now have total weight ≥ 3).

**Step 7: Run all tests**

Run: `bats tests/shell/auto_compound.bats`
Expected: All tests PASS

Run: `bash -n hooks/auto-compound.sh`
Expected: Syntax OK

**Step 8: Commit**

```bash
git add hooks/auto-compound.sh tests/shell/auto_compound.bats tests/fixtures/transcript_with_insight.jsonl tests/fixtures/transcript_with_recovery.jsonl
git commit -m "feat: narrow auto-compound triggers + opt-out + throttle (Clavain-azlo)

- Raise threshold from 2 to 3
- Remove high-activity and error-fix-cycle signals (too noisy)
- Add per-repo opt-out (.claude/clavain.no-autocompound)
- Add 5-minute throttle via timestamp sentinel
- Update test fixtures for new threshold"
```

---

## Final Verification

After both tasks complete:

```bash
# All bats tests
bats tests/shell/auto_compound.bats tests/shell/session_start.bats tests/shell/sprint_scan.bats tests/shell/lib.bats

# Syntax check all hooks
bash -n hooks/lib.sh && bash -n hooks/auto-compound.sh && bash -n hooks/session-handoff.sh && bash -n hooks/session-start.sh

# Structural tests
cd /root/projects/Clavain/tests && uv run pytest structural/ -q

# Session-start produces valid JSON
cd /tmp && bash /root/projects/Clavain/hooks/session-start.sh 2>/dev/null | jq .
```

Close beads:

```bash
bd close Clavain-8t5l Clavain-azlo
```
