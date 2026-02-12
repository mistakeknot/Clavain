# Correctness Review: F5 Phase State Tracking

**Reviewer:** Julik (fd-correctness agent)
**Date:** 2026-02-12
**Plan:** docs/plans/2026-02-12-phase-state-tracking.md
**PRD:** docs/prds/2026-02-12-phase-gated-lfg.md

## Executive Summary

Phase state tracking has **four critical correctness issues** that will cause production failures:

1. **Silent corruption from stale bead ID resolution** — grep fallback can match the wrong bead ID when documents reference multiple beads
2. **Race-free by accident, not by design** — no concurrent command execution today, but no documentation or guardrails prevent future breakage
3. **Missing error propagation** — phase_set swallows bd failures, but phase_infer_bead has no error handling for jq/grep failures
4. **Ambiguous "failure" vs "no bead" states** — empty string return values conflate "lookup failed" with "no bead associated with this run"

**High-confidence finding:** Issue 1 (multi-bead grep) will corrupt state within the first week of use. Issues 3 and 4 will cause silent failures that corrupt telemetry and phase tracking.

## Issue 1: Multi-Bead Grep Corruption (HIGH SEVERITY)

### Problem

`phase_infer_bead()` greps the target file for `**Bead:** Clavain-XXXX` patterns. Multiple existing files reference **multiple beads**:

```
docs/plans/2026-02-12-p2-quick-wins.md:**Beads:** Clavain-np7b (Task 1), Clavain-4728 (Task 2), Clavain-p5ex (Task 3)
docs/plans/2026-02-11-p1-beads.md:**Beads:** Clavain-5kea, Clavain-5o97, Clavain-zp9n, Clavain-id6d
docs/plans/2026-02-11-hooks-cleanup-batch.md:**Beads:** Clavain-8t5l (Task 1), Clavain-azlo (Task 2)
```

When `/work` runs on `docs/plans/2026-02-12-p2-quick-wins.md`, the grep will match **all three bead IDs**. The plan says "grep the command's target file" but provides no disambiguation strategy.

### Failure Narrative

1. User runs `/clavain:work docs/plans/2026-02-12-p2-quick-wins.md` (plan tracks 3 separate beads)
2. `phase_infer_bead()` greps for `Bead.*Clavain-` pattern
3. Grep returns: `Clavain-np7b (Task 1), Clavain-4728 (Task 2), Clavain-p5ex (Task 3)`
4. Extraction logic (not yet written) takes the first match: `Clavain-np7b`
5. `/work` executes Task 2 (related to `Clavain-4728`) but sets `phase=executing` on `Clavain-np7b`
6. **Result:** Wrong bead gets phase transition. User checks `Clavain-4728` and sees no phase change. Discovery ranking breaks.

### Root Cause

The plan assumes one bead per artifact. This is violated by:
- Multi-task plans (one plan, multiple feature beads)
- PRDs with multiple child beads (explicitly allowed by PRD design)
- Brainstorm docs that track multiple alternative approaches as separate beads

### Recommended Fix

**Short-term (required for F5):**
1. `phase_infer_bead()` must return an **error** (not empty string) when multiple bead IDs match
2. Commands must log a warning and skip phase tracking when multi-bead ambiguity is detected
3. Document the constraint: "Phase tracking only works for single-bead artifacts"

**Medium-term (required for F6):**
1. Add `$CLAVAIN_BEAD_ID` env var as the ONLY source of truth for multi-bead plans
2. `/lfg` discovery must set `CLAVAIN_BEAD_ID` when routing to commands (plan already includes this, good)
3. Artifact grep becomes a fallback ONLY for single-bead artifacts (brainstorms, single-feature plans)

**Test case:**
```bash
# Create a plan with multiple bead references
echo "**Beads:** Clavain-aaa, Clavain-bbb" > /tmp/multi-bead-plan.md
# Run phase_infer_bead on it
# Expected: error or empty, NOT silent wrong-bead selection
```

## Issue 2: Concurrent Command Race Conditions (MEDIUM SEVERITY)

### Problem

The plan states: "Commands are markdown files that instruct Claude — they run sequentially in a single conversation, not concurrently."

This is **true today** but creates a hidden coupling between execution model (Claude's single-threaded conversation loop) and data safety. No documentation or guardrails prevent future breakage if:
- A future MCP server exposes commands as async operations
- A shell script wrapper runs multiple `/clavain:*` commands in parallel
- A CI/CD pipeline runs quality-gates + flux-drive concurrently on different files

### Failure Narrative (Hypothetical but Plausible)

1. User writes a shell script: `parallel clavain ::: /work plan1.md ::: /work plan2.md`
2. Both commands call `phase_infer_bead()` on different plans that reference the same bead (e.g., a PRD with two child feature plans)
3. Both extract the same bead ID `Clavain-xyz`
4. Both call `bd set-state Clavain-xyz phase=executing` within milliseconds
5. **bd's atomicity guarantees:**
   - Each `set-state` creates a separate event bead (no data loss)
   - Label replacement is atomic (no torn writes)
   - Last write wins (deterministic final state)
6. **The problem:** One phase transition is lost from the event history perspective — two "executing" events instead of one

### Why This Is Not a Critical Issue Today

`bd set-state` is atomic at the database level:
- Creates event bead (SQLite INSERT with ACID guarantees)
- Removes old label (SQLite DELETE)
- Adds new label (SQLite INSERT)
- All within a single transaction (based on help text "atomically set")

**Last write wins** is acceptable for phase tracking because:
- Phase is a single dimension (not a composite state)
- All concurrent callers are setting the SAME phase value (e.g., both setting "executing")
- If setting different phases, the race indicates a workflow bug (should be fixed at caller level)

### Why This Is Still a Problem

The plan provides **no documentation** of concurrency assumptions:
- No comment in lib-phase.sh saying "assumes single-threaded execution"
- No warning in CLAUDE.md about parallel command risks
- No detection or logging when multiple processes set state on the same bead

Future developers (or AI agents) will not know this is unsafe.

### Recommended Fix

**Documentation (required for F5):**
1. Add a comment in `lib-phase.sh`:
   ```bash
   # CONCURRENCY ASSUMPTION: Commands run sequentially in a single Claude Code conversation.
   # Parallel execution of commands operating on the same bead is NOT supported.
   # bd set-state is atomic, so no data corruption occurs, but duplicate phase events
   # may be created if two commands set the same phase concurrently.
   ```

2. Add a section to `commands/lfg.md`:
   ```markdown
   ## Concurrency Safety

   /lfg routes to a single command at a time. Do NOT run multiple workflow commands
   in parallel on the same bead (e.g., via shell scripts or CI/CD pipelines).
   Phase tracking is safe for sequential execution only.
   ```

**Runtime Detection (optional for F6):**
1. `phase_set()` could check if the phase value is already set to the target value
2. If setting "executing" when phase is already "executing", log a warning: "Redundant phase set detected — possible concurrent command execution"
3. This catches accidental parallel runs without blocking them

**Test case:**
```bash
# Simulate concurrent set-state (run in subshells)
(bd set-state Clavain-test phase=executing --reason "Command 1" &)
(bd set-state Clavain-test phase=executing --reason "Command 2" &)
wait
# Expected: both succeed, last write wins, 2 events created
# Desired: warning logged about duplicate phase set
```

## Issue 3: Missing Error Handling in phase_infer_bead (MEDIUM SEVERITY)

### Problem

`phase_infer_bead()` (not yet implemented) will call:
- `grep` to search for bead patterns
- `sed`/`awk` to extract bead ID from matched lines
- No error handling for grep failures, malformed patterns, or IO errors

`lib-discovery.sh` already has this grep pattern, but it wraps results in JSON and validates with jq. The phase library must do the same.

### Failure Narrative

1. User runs `/clavain:work docs/plans/corrupted-file.md` (file has UTF-8 encoding errors)
2. `phase_infer_bead()` calls `grep "Bead.*Clavain-" corrupted-file.md`
3. Grep exits with code 2 (read error), no output
4. Extraction code (e.g., `grep | head -1 | sed 's/.*Clavain-\([a-z0-9]*\).*/\1/'`) outputs empty string
5. Caller interprets empty string as "no bead associated" (valid case)
6. Command proceeds without phase tracking
7. **Result:** Silent failure. No log, no telemetry, no indication that phase tracking was attempted and failed

### Root Cause

Bash's default error handling conflates:
- "grep found no matches" (exit 1)
- "grep encountered IO error" (exit 2)
- "pattern is valid but file doesn't exist" (exit 2)

Without explicit error checks, all failures become empty strings.

### Recommended Fix

**Error Handling (required for F5):**

```bash
phase_infer_bead() {
    local target_file="$1"

    # Check env var first (authoritative source)
    if [[ -n "${CLAVAIN_BEAD_ID:-}" ]]; then
        echo "$CLAVAIN_BEAD_ID"
        return 0
    fi

    # Validate target file exists and is readable
    if [[ ! -f "$target_file" || ! -r "$target_file" ]]; then
        echo "" >&1  # No bead (not an error — file may not be a plan)
        return 0
    fi

    # Grep for bead pattern (with error detection)
    local matches exit_code
    matches=$(grep -o "Clavain-[a-z0-9]\{4\}" "$target_file" 2>/dev/null) || exit_code=$?

    # Distinguish: no matches (exit 1) vs IO error (exit 2)
    if [[ $exit_code -eq 2 ]]; then
        echo "ERROR: failed to read $target_file for bead ID extraction" >&2
        echo ""  # Return empty but log the error
        return 0
    fi

    # Count matches
    local match_count
    match_count=$(echo "$matches" | grep -c "Clavain-" || echo 0)

    if [[ $match_count -eq 0 ]]; then
        echo ""  # No bead found (valid case)
        return 0
    elif [[ $match_count -gt 1 ]]; then
        # Multi-bead ambiguity (Issue 1)
        echo "ERROR: multiple bead IDs found in $target_file — set CLAVAIN_BEAD_ID explicitly" >&2
        echo ""  # Skip phase tracking for this run
        return 0
    else
        # Single match — extract and return
        echo "$matches"
        return 0
    fi
}
```

**Test cases:**
```bash
# Case 1: No bead reference
echo "Some plan content" > /tmp/no-bead.md
phase_infer_bead /tmp/no-bead.md  # Expected: empty, no error

# Case 2: Single bead
echo "**Bead:** Clavain-abc" > /tmp/single-bead.md
phase_infer_bead /tmp/single-bead.md  # Expected: "Clavain-abc"

# Case 3: Multiple beads
echo "**Beads:** Clavain-abc, Clavain-def" > /tmp/multi-bead.md
phase_infer_bead /tmp/multi-bead.md  # Expected: empty + stderr warning

# Case 4: File does not exist
phase_infer_bead /tmp/missing.md  # Expected: empty, no error

# Case 5: File is not readable (permission denied)
touch /tmp/unreadable.md && chmod 000 /tmp/unreadable.md
phase_infer_bead /tmp/unreadable.md  # Expected: empty, no error
```

## Issue 4: Ambiguous Empty String Return Values (LOW SEVERITY)

### Problem

Both `phase_set()` and `phase_infer_bead()` use empty string to mean:
- "No bead associated with this run" (valid case, skip tracking)
- "Lookup failed due to error" (error case, should log)

Callers cannot distinguish these cases without inspecting stderr.

### Failure Narrative

1. User runs `/clavain:brainstorm` on a new feature (no bead created yet)
2. `phase_infer_bead()` returns empty string (expected behavior)
3. Later, user runs `/clavain:brainstorm` on a corrupted file
4. `phase_infer_bead()` returns empty string (error case, but silent)
5. **Result:** Both cases look identical in telemetry. Can't distinguish "no bead yet" from "bead lookup broken"

### Recommended Fix

**Sentinel Values (optional for F5, required for F6 telemetry):**

```bash
# phase_infer_bead returns:
# - "Clavain-XXXX" on success
# - "" (empty) when no bead found (valid case)
# - "ERROR_MULTIPLE_BEADS" when ambiguous
# - "ERROR_READ_FAILED" when file unreadable

# Caller checks:
local bead_id
bead_id=$(phase_infer_bead "$target_file")

if [[ "$bead_id" =~ ^ERROR_ ]]; then
    # Log the error case for telemetry
    echo "Phase tracking failed: $bead_id" >&2
    return 0  # Don't block workflow
elif [[ -z "$bead_id" ]]; then
    # No bead associated (valid case)
    return 0
else
    # Proceed with phase tracking
    phase_set "$bead_id" "$new_phase" --reason "..."
fi
```

**Why This Matters for Telemetry:**

The PRD (F8 Work Discovery + Phase Integration) will use phase data to rank beads. If 50% of phase tracking attempts silently fail, the ranking will be biased toward beads that happened to avoid errors. Distinguishing "no bead" from "lookup failed" lets you fix the underlying issue (e.g., file encoding, grep version incompatibility).

## Issue 5: bd Failure Modes Not Documented (MEDIUM SEVERITY)

### Problem

The plan states: "Silent on failure (phase tracking must never block workflow)". This is correct, but `bd set-state` can fail in ways that indicate **workflow bugs**, not just transient errors:

- Invalid bead ID (typo, deleted bead)
- Database locked (another process writing)
- Disk full
- .beads directory deleted

Swallowing all failures treats workflow bugs (wrong bead ID) the same as transient errors (db locked).

### Failure Narrative

1. User runs `/clavain:work docs/plans/old-plan.md` (plan references a bead that was later deleted)
2. `phase_infer_bead()` extracts `Clavain-OLD` from the plan
3. `phase_set()` calls `bd set-state Clavain-OLD phase=executing`
4. `bd` exits with code 1: "no issue found matching Clavain-OLD"
5. `phase_set()` suppresses the error (silent failure policy)
6. User expects the plan to advance phase, but it doesn't
7. **Result:** User wastes time debugging why discovery isn't surfacing the bead, when the real issue is a stale bead reference in the plan

### Recommended Fix

**Tiered Error Handling (required for F5):**

```bash
phase_set() {
    local bead_id="$1"
    local phase="$2"
    local reason="${3:-}"

    # Validate inputs
    if [[ -z "$bead_id" || -z "$phase" ]]; then
        echo "ERROR: phase_set requires bead_id and phase" >&2
        return 0
    fi

    # Call bd set-state (capture stderr)
    local output exit_code
    output=$(bd set-state "$bead_id" "phase=$phase" --reason "$reason" 2>&1) || exit_code=$?

    if [[ $exit_code -ne 0 ]]; then
        # Classify error
        if echo "$output" | grep -q "no issue found matching"; then
            # Workflow bug: stale bead reference
            echo "ERROR: cannot set phase on $bead_id (bead not found) — plan may reference deleted bead" >&2
        elif echo "$output" | grep -q "database is locked"; then
            # Transient error: retry possible
            echo "WARNING: phase tracking skipped ($bead_id) — database locked" >&2
        else
            # Unknown error: log for debugging
            echo "WARNING: phase tracking failed ($bead_id): $output" >&2
        fi
        return 0  # Never block workflow
    fi

    # Success (no output)
    return 0
}
```

**Test cases:**
```bash
# Case 1: Invalid bead ID
phase_set "Clavain-FAKE" "executing" "test"
# Expected: stderr message about bead not found

# Case 2: Valid bead, valid phase
phase_set "Clavain-z661" "planned" "Test phase set"
bd state Clavain-z661 phase  # Expected: "planned"

# Case 3: Database locked (simulate with PRAGMA locking_mode=EXCLUSIVE in another shell)
# Expected: stderr warning, command proceeds
```

## Issue 6: Artifact Grep Pattern Inconsistency (LOW SEVERITY)

### Problem

`lib-discovery.sh` uses two different grep patterns for bead ID extraction:

```bash
# Pattern 1: Perl regex with word boundary
grep -rlP "Bead.*${bead_id}\b"

# Pattern 2: Portable fallback
grep -rl "Bead.*${bead_id}[^a-zA-Z0-9_-]"
```

The plan says "reuses the `**Bead:** Clavain-XXXX` pattern that `lib-discovery.sh` already searches for", but doesn't specify which pattern. The two patterns have different behavior:

- Pattern 1 matches `Clavain-abc)` (parenthesis is a word boundary)
- Pattern 2 matches `Clavain-abc)` (parenthesis is not alphanumeric)
- Pattern 1 matches `Clavain-abc` at end of line
- Pattern 2 does NOT match `Clavain-abc` at end of line (requires non-alnum AFTER the ID)

This causes false negatives on some platforms.

### Recommended Fix

**Consistent Pattern (required for F5):**

Extract the grep logic into a shared function in `hooks/lib.sh`:

```bash
# Extract bead ID from file using the same pattern as lib-discovery.sh
# Args: $1 = file path
# Output: bead ID (one per line) or empty
grep_bead_ids() {
    local file="$1"

    if ! [[ -f "$file" && -r "$file" ]]; then
        return 0
    fi

    # Use Perl regex if available (handles word boundaries correctly)
    if grep -P "" /dev/null 2>/dev/null; then
        grep -oP "Clavain-[a-z0-9]{4}\b" "$file" 2>/dev/null || true
    else
        # Portable fallback: match ID followed by non-word char OR end of line
        grep -o "Clavain-[a-z0-9]\{4\}" "$file" 2>/dev/null || true
    fi
}
```

Then `lib-discovery.sh` and `lib-phase.sh` both call `grep_bead_ids()` instead of duplicating the pattern.

**Test case:**
```bash
# Create test file with various bead reference formats
cat > /tmp/bead-patterns.md <<'EOF'
**Bead:** Clavain-abc
**Beads:** Clavain-def, Clavain-ghi
Tracking bead Clavain-jkl for this feature
Reference: Clavain-mno (parenthetical)
End of line: Clavain-pqr
EOF

grep_bead_ids /tmp/bead-patterns.md
# Expected output (6 lines):
# Clavain-abc
# Clavain-def
# Clavain-ghi
# Clavain-jkl
# Clavain-mno
# Clavain-pqr
```

## Edge Case Analysis

### Q: What if a command is run on a file that references multiple beads?

**Current plan behavior:** Undefined. Grep will match multiple IDs, but the plan doesn't specify extraction logic.

**Correct behavior:** Detect multi-bead case, log warning, skip phase tracking (already covered in Issue 1 fix).

### Q: Can phase_set fail silently in ways that corrupt state?

**No**, because:
- `bd set-state` either succeeds (atomic write) or fails (no state change)
- There is no "partial success" mode where labels are updated but events are not created
- The label is derived from the event (cache), not authoritative state

**However**, setting the wrong phase due to stale bead ID (Issue 1) IS a silent corruption.

### Q: What happens if $CLAVAIN_BEAD_ID is set but points to a deleted bead?

**Current plan behavior:** `bd set-state` will fail with "no issue found". `phase_set()` will suppress the error (silent failure).

**Correct behavior:** Log the error to stderr so the user knows phase tracking was attempted but failed (Issue 5 fix).

### Q: What if two commands set different phases concurrently?

**Example:** `/work` sets "executing" while `/quality-gates` sets "shipping" (both running in parallel on the same bead).

**bd behavior:**
- Both `set-state` calls succeed (atomic writes)
- Two event beads created
- Last write wins for the label
- Final state is deterministic but depends on exact timing

**Why this is a workflow bug, not a data bug:**
- If both commands are setting different phases, the workflow is wrong (should be sequential)
- The race is detectable via event bead count (two phase changes in <1 second)
- No data is lost or corrupted (both events are recorded)

**Recommendation:** Document this as "unsupported" (Issue 2 fix), but don't add runtime detection in F5 (can defer to F6 if it becomes a problem).

## Summary of Required Fixes for F5

| Issue | Severity | Fix Required | Deferrable to F6? |
|-------|----------|--------------|------------------|
| 1. Multi-bead grep corruption | HIGH | Detect + error on ambiguity | No |
| 2. Concurrent command race | MEDIUM | Document assumptions | No (docs only) |
| 3. Missing error handling in infer_bead | MEDIUM | Add error detection | No |
| 4. Ambiguous empty string returns | LOW | Use sentinel values | Yes (telemetry only) |
| 5. bd failure modes not classified | MEDIUM | Tiered error messages | No |
| 6. Grep pattern inconsistency | LOW | Shared grep function | Yes (low impact) |

## Test Coverage Recommendations

The plan includes Task 11 (Verification) but only tests syntax and API availability. Add these correctness tests:

**Unit tests for lib-phase.sh:**
```bash
# Test 1: Single bead extraction
# Test 2: Multi-bead detection (should error)
# Test 3: No bead found (should return empty)
# Test 4: Invalid bead ID (bd set-state should fail gracefully)
# Test 5: Concurrent phase_set (should succeed, last write wins)
```

**Integration tests for /lfg workflow:**
```bash
# Test 1: Run /work on a multi-bead plan (should log warning, skip phase tracking)
# Test 2: Run /work with CLAVAIN_BEAD_ID set (should use env var, not grep)
# Test 3: Run /work on a plan with deleted bead reference (should log error, skip phase tracking)
```

**Concurrency stress test (optional for F6):**
```bash
# Run 10 concurrent /work commands on different plans that reference the same bead
# Verify: all succeed, no data corruption, final phase is deterministic
```

## Recommended Implementation Order

1. **Create lib-phase.sh with Issue 1 + 3 + 5 fixes** (multi-bead detection, error handling, tiered error messages)
2. **Add concurrency assumptions to documentation** (Issue 2)
3. **Add unit tests** (single bead, multi-bead, no bead, invalid bead)
4. **Update commands to call phase_set** (Tasks 3-10 in plan)
5. **Add integration tests** (multi-bead plan, deleted bead reference)
6. **Defer Issue 4 + 6 to F6** (sentinel values, shared grep function) — low impact, can ship F5 without them

## Sign-Off

This review found **no blocking data corruption issues** with the bd set-state API (it is correctly atomic). However, the **bead ID resolution strategy has a critical flaw** (multi-bead grep) that will corrupt state within the first week of use.

**Recommendation:** Implement Issues 1, 3, and 5 fixes before shipping F5. Issues 2, 4, and 6 can ship with docs-only fixes and be hardened in F6.
