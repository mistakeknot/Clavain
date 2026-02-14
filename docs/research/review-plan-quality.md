# Quality Review: Auto-Drift-Check Implementation Plan

**Reviewer:** fd-quality (via flux-drive)
**Date:** 2026-02-14
**Plan:** `/root/projects/Clavain/docs/plans/2026-02-14-auto-drift-check.md`

## Executive Summary

**Verdict:** APPROVE with minor refinements
**Confidence:** High

The plan demonstrates strong attention to detail with TDD methodology, proper sentinel isolation, and graceful degradation patterns. However, there are several areas where bash idioms could be improved, test coverage could be enhanced, and naming conventions could be more consistent with the existing codebase.

---

## 1. Naming Conventions

### 1.1 lib-signals.sh — GOOD ✓

**Assessment:** Consistent with existing patterns in `hooks/lib.sh` and the interphase companion's `lib-gates.sh`, `lib-phase.sh` structure.

**Evidence:**
- `hooks/lib.sh` — shared utilities with discovery functions
- Interphase has `lib-gates.sh` and `lib-phase.sh`
- Pattern: `lib-<domain>.sh` for shared libraries

**Recommendation:** Keep as-is.

### 1.2 detect_signals() — GOOD with caveat ✓

**Assessment:** Function name follows snake_case convention seen in `hooks/lib.sh` (`_discover_beads_plugin`, `escape_for_json`), BUT the leading underscore convention indicates private/internal functions while `detect_signals()` is a public API.

**Evidence:**
```bash
# From hooks/lib.sh (lines 7, 26, 45, 64)
_discover_beads_plugin()
_discover_interflux_plugin()
_discover_interpath_plugin()
_discover_interwatch_plugin()
```

**Recommendation:** Consider either:
- Rename to `_detect_signals()` if it's meant to be internal-only (but the header comment suggests it's part of the public API)
- Keep as `detect_signals()` without leading underscore to mark it as a public API function

**Suggested convention:** Public API = no underscore, internal helpers = underscore prefix.

### 1.3 CLAVAIN_SIGNALS and CLAVAIN_SIGNAL_WEIGHT — EXCELLENT ✓

**Assessment:** Strong naming convention using `CLAVAIN_` prefix to avoid collision with user environment or other plugins. Consistent with existing patterns.

**Evidence:**
- `CLAUDE_PLUGIN_ROOT` used throughout hooks
- `CLAVAIN_` prefix clearly namespaces these as plugin-specific exports

**Recommendation:** Keep as-is. This is exemplary namespace hygiene.

### 1.4 Sentinel naming: Per-hook vs shared — EXCELLENT IMPROVEMENT ✓

**Original issue:**
- Old: `STOP_SENTINEL="/tmp/clavain-stop-${SESSION_ID}"` (shared across all Stop hooks)
- Problem: First Stop hook writes sentinel, blocks all subsequent hooks

**New design:**
- `auto-compound.sh`: `/tmp/clavain-stop-compound-${SESSION_ID}`
- `auto-drift-check.sh`: `/tmp/clavain-stop-drift-${SESSION_ID}`
- `session-handoff.sh`: `/tmp/clavain-stop-handoff-${SESSION_ID}`

**Assessment:** This fix is CRITICAL and demonstrates deep understanding of the race condition. Each hook now has its own sentinel namespace.

**Recommendation:** Keep as-is. This is a significant architectural improvement.

---

## 2. Test Design

### 2.1 lib_signals.bats — GOOD with gaps ⚠️

**Strengths:**
- 12 tests covering all 7 signal types
- Tests for edge cases: no signals, multiple signals, accumulation
- Explicit assertion on trailing comma removal (line 120-121)
- Tests for both uppercase/lowercase patterns (investigation line 69)

**Gaps identified:**

#### Gap 1: Missing quoted pattern edge case
The plan's grep patterns use quotes like `'"git commit'` but tests use bare strings:

```bash
# Test line 42 (should work):
local transcript='{"role":"assistant","content":"Running \"git commit -m fix\""}'

# But what about these edge cases?
local transcript='Running git commit'  # no JSON wrapper
local transcript='git commit -m "fix"' # different quote style
```

**Recommendation:** Add test for unquoted git commands (regression guard if grep patterns change).

#### Gap 2: Greedy accumulation test is weak
Line 103-108 tests accumulation but uses a contrived multi-signal string:
```bash
local transcript=$'Running "git commit -m fix"\nInsight ─ key insight\nthe issue was a cache bug'
```

**Issue:** Real transcripts are JSONL. This test doesn't match fixture format.

**Recommendation:** Add a `transcript_multi_signal.jsonl` fixture that's realistic.

#### Gap 3: No test for version-bump vs interpub:release distinction
Lines 89-101 test both `bump-version.sh` and `/interpub:release`, but the implementation (line 206) treats them identically with a single OR pattern:
```bash
if echo "$text" | grep -q 'bump-version\|interpub:release'; then
```

**Recommendation:** This is fine, but add a comment in the test explaining why both map to the same signal.

#### Gap 4: Missing empty string test
What happens if `detect_signals ""` is called? The plan's implementation should handle it gracefully, but there's no explicit test.

**Recommendation:** Add test:
```bash
@test "lib-signals: empty string returns weight 0" {
    detect_signals ""
    [[ -z "$CLAVAIN_SIGNALS" ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 0 ]]
}
```

### 2.2 auto_drift_check.bats — GOOD with one major gap ⚠️

**Strengths:**
- 10 tests covering all guards (stop_hook_active, sentinel, opt-out, throttle)
- Reuses fixtures from auto-compound (DRY principle)
- Tests threshold boundaries (weight 1 vs weight 2)
- Tests both passthrough (no output) and block (JSON output) paths

**Major gap:**

#### Gap 5: No test for interwatch discovery failure
Lines 507-513 in the plan's `auto-drift-check.sh`:
```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib.sh"
INTERWATCH_ROOT=$(_discover_interwatch_plugin)
if [[ -z "$INTERWATCH_ROOT" ]]; then
    exit 0
fi
```

**Issue:** The plan says "graceful degradation if not installed" but there's NO test verifying this behavior.

**Recommendation:** Add test:
```bash
@test "auto-drift-check: skips when interwatch not installed" {
    # Mock _discover_interwatch_plugin to return empty string
    export INTERWATCH_ROOT=""
    run bash -c "echo '{\"stop_hook_active\": false, \"transcript_path\": \"$TMPDIR_DRIFT/transcript_commit.jsonl\"}' | bash '$HOOKS_DIR/auto-drift-check.sh'"
    assert_success
    assert_output ""
}
```

**NOTE:** This test is tricky because it requires mocking the discovery function. A simpler approach might be to test with `INTERWATCH_ROOT=""` set in the environment.

### 2.3 Test suite integration — EXCELLENT ✓

Task 5 Step 3 (line 635) runs the full suite:
```bash
bats tests/shell/*.bats && uv run --project tests pytest tests/structural/ -v
```

**Assessment:** This is proper integration testing. Combining shell tests (behavior) with structural tests (schema/manifest) ensures both layers are verified.

**Recommendation:** Keep as-is.

---

## 3. Bash Idioms

### 3.1 echo | grep pattern — ACCEPTABLE but not ideal ⚠️

**Current pattern (pervasive in auto-compound.sh and planned for lib-signals.sh):**
```bash
if echo "$text" | grep -q '"git commit\|"git add.*&&.*git commit'; then
```

**Issues:**
1. **Spawns subshell for echo** — unnecessary overhead
2. **Spawns separate process for grep** — more overhead
3. **Not following POSIX best practices** — could use bash built-ins

**Better alternatives:**

#### Option A: Use grep with here-string (bash 3.0+)
```bash
if grep -q '"git commit\|"git add.*&&.*git commit' <<< "$text"; then
```
- One fewer process (no echo)
- Cleaner syntax
- Still portable across bash 3.0+

#### Option B: Use bash regex matching (bash 3.0+)
```bash
if [[ "$text" =~ \"git\ commit|\"git\ add.*\&\&.*git\ commit ]]; then
```
- No external processes
- Fastest option
- Requires escaping spaces and special chars
- Less readable for complex patterns

#### Option C: Keep echo | grep for readability
- Current pattern is widely understood
- Already used in 7 places in auto-compound.sh
- Consistency across codebase matters

**Recommendation:**

**Use Option A (here-string) for new code in lib-signals.sh.** It's a strict improvement over echo | grep with no downsides. Example:

```bash
# 1. Git commit (weight 1)
if grep -q '"git commit\|"git add.*&&.*git commit' <<< "$text"; then
    CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS}commit,"
    CLAVAIN_SIGNAL_WEIGHT=$((CLAVAIN_SIGNAL_WEIGHT + 1))
fi
```

**For auto-compound.sh refactor (Task 2):** Keep the existing echo | grep patterns to minimize diff size. The refactor is already changing the sentinel logic; changing the grep style too would make the diff harder to review.

**For future work:** Consider a follow-up task to migrate all echo | grep to here-string syntax across the codebase for consistency.

### 3.2 Variable scoping in detect_signals() — GOOD ✓

```bash
detect_signals() {
    local text="$1"
    CLAVAIN_SIGNALS=""
    CLAVAIN_SIGNAL_WEIGHT=0
```

**Assessment:** Correct scoping. Input is `local`, output vars are **global** (no `local` keyword). This is the right pattern for a function that sets state via side effects.

**Evidence:** Same pattern in `escape_for_json()` from `hooks/lib.sh` (lines 82-100) — takes input, modifies output via printf (side effect).

**Recommendation:** Keep as-is. Add a comment clarifying the scoping contract:
```bash
# Detect signals in transcript text. Sets CLAVAIN_SIGNALS and CLAVAIN_SIGNAL_WEIGHT.
# Args: $1 = transcript text (multi-line string)
# Side effects: Sets global CLAVAIN_SIGNALS and CLAVAIN_SIGNAL_WEIGHT
```

### 3.3 Double-source guard — EXCELLENT ✓

```bash
# Guard against double-sourcing
[[ -n "${_LIB_SIGNALS_LOADED:-}" ]] && return 0
_LIB_SIGNALS_LOADED=1
```

**Assessment:** This is textbook bash library practice. Prevents duplicate function definitions and variable initialization.

**Evidence:** Same pattern used in interphase's `lib-gates.sh` and `lib-phase.sh`.

**Recommendation:** Keep as-is. This is exemplary.

### 3.4 Trailing comma removal — GOOD ✓

```bash
# Remove trailing comma
CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS%,}"
```

**Assessment:** Correct use of parameter expansion. Efficient and readable.

**Alternative considered:**
```bash
CLAVAIN_SIGNALS="${CLAVAIN_SIGNALS%%,}"  # removes longest match, same effect for single trailing comma
```

**Recommendation:** Keep `%,` (shortest match from end). It's more precise and matches the intent.

### 3.5 Arithmetic — GOOD ✓

```bash
CLAVAIN_SIGNAL_WEIGHT=$((CLAVAIN_SIGNAL_WEIGHT + 1))
```

**Assessment:** Correct use of `$(( ))` arithmetic expansion. Portable and efficient.

**Recommendation:** Keep as-is.

### 3.6 stat portability (Linux vs macOS) — GOOD ✓

From auto-drift-check.sh line 500:
```bash
THROTTLE_MTIME=$(stat -c %Y "$THROTTLE_SENTINEL" 2>/dev/null || stat -f %m "$THROTTLE_SENTINEL" 2>/dev/null || date +%s)
```

**Assessment:** Handles both GNU stat (`-c %Y`) and BSD/macOS stat (`-f %m`) with fallback to current time. This is correct.

**Evidence:** Same pattern used in auto-compound.sh line 57.

**Recommendation:** Keep as-is. This is best practice for cross-platform bash.

### 3.7 set -euo pipefail — EXCELLENT ✓

All hooks and the planned lib-signals.sh use `set -euo pipefail`.

**Assessment:** This is strict mode and the right choice for hooks that must not silently fail.

**Breakdown:**
- `set -e` — exit on first error
- `set -u` — exit on undefined variable reference
- `set -o pipefail` — pipeline fails if any command fails (not just the last)

**Recommendation:** Keep as-is. This is best practice for production bash.

---

## 4. Consistency with auto-compound.sh

### 4.1 Refactor plan (Task 2) — EXCELLENT ✓

**Changes:**
1. Sentinel name: `clavain-stop-${SESSION_ID}` → `clavain-stop-compound-${SESSION_ID}`
2. Signal detection: inline 52-line block → `source lib-signals.sh` + `detect_signals()` call
3. Variable mapping: `CLAVAIN_SIGNALS` and `CLAVAIN_SIGNAL_WEIGHT` → `SIGNALS` and `WEIGHT`

**Assessment:** The refactor is well-scoped. It preserves all guards, throttle logic, and output format while extracting only the signal detection logic.

**Evidence from plan (lines 246-269):**
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

**Potential issue:** The plan says "Remove the old inline signal detection block" (line 271) but doesn't show the exact diff. This could be error-prone.

**Recommendation:**

**In Task 2 Step 2, be more explicit about the line deletion:**

Add this note:
```
DELETE lines 75-126 in auto-compound.sh (the entire inline signal detection block):
- Lines 75-77: SIGNALS and WEIGHT initialization
- Lines 79-116: The 7 grep-based signal checks
- Lines 118-126: Threshold check and trailing comma removal

REPLACE with the 22-line source + detect_signals block shown above.

NET CHANGE: -52 lines of inline detection, +22 lines of library usage = 30 lines removed.
```

### 4.2 Header comment update (Task 5 Step 2) — GOOD but incomplete ⚠️

**Planned change (line 625):**
```bash
# Stop hook: auto-compound non-trivial problem-solving after each turn
#
# Uses shared signal detection from lib-signals.sh.
# Compound triggers when total signal weight >= 3.
#
# Guards: stop_hook_active, per-hook sentinel, per-repo opt-out, 5-min throttle.
```

**Issue:** This removes the detailed signal list (lines 4-10 in current auto-compound.sh). That list is valuable documentation for understanding what triggers compound.

**Recommendation:** Keep the signal list but reference the library:
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
# Guards: stop_hook_active, per-hook sentinel, per-repo opt-out, 5-min throttle.
```

---

## 5. Demo Hook Quality

**File:** `/root/projects/interwatch/examples/hooks/auto-drift-check-example.sh`

### 5.1 Structure — EXCELLENT ✓

**Strengths:**
- Standalone (no dependencies on Clavain's lib-signals.sh)
- Heavily commented with usage instructions
- Customizable settings section (lines 690-702)
- Inline signal detection (lines 744-763) makes it easy to understand and modify

**Assessment:** This is a model example of plugin documentation. It can be copied and adapted without needing to understand Clavain's internals.

**Recommendation:** Keep as-is.

### 5.2 Signal patterns — SIMPLIFIED but GOOD ✓

**Differences from lib-signals.sh:**

| Signal | lib-signals.sh (full) | demo (simplified) |
|--------|----------------------|-------------------|
| commit | 7 patterns | 1 pattern |
| resolution | not included | not included |
| investigation | not included | not included |
| bead-closed | 2 patterns | 1 pattern |
| insight | not included | not included |
| recovery | not included | not included |
| version-bump | 2 patterns | 1 pattern |

**Assessment:** The demo uses a minimal signal set (3 signals instead of 7). This is appropriate for a starting point. Users can add more signals if needed.

**Recommendation:** Add a comment in the demo explaining the simplification:
```bash
# --- SIGNAL DETECTION (customize these patterns) ---
#
# This example uses a minimal signal set. For a full reference
# of all possible signals, see:
#   https://github.com/.../clavain/hooks/lib-signals.sh

WEIGHT=0
```

### 5.3 Settings — GOOD ✓

```bash
# Minimum signal weight to trigger a drift check.
# Lower = more sensitive. commit(1) + bead-close(1) = 2.
THRESHOLD=2

# Throttle window in seconds (600 = 10 minutes).
THROTTLE_SECONDS=600

# Per-repo opt-out file. Create this file to disable drift checking.
OPT_OUT_FILE=".claude/no-driftcheck"
```

**Assessment:** Clear documentation of tunable parameters with examples. The comment "commit(1) + bead-close(1) = 2" is especially helpful.

**Recommendation:** Keep as-is.

### 5.4 Throttle sentinel naming — INCONSISTENT ⚠️

**Demo uses:**
```bash
THROTTLE_FILE="/tmp/driftcheck-last-${SESSION_ID}"
```

**Clavain's auto-drift-check.sh uses:**
```bash
THROTTLE_SENTINEL="/tmp/clavain-drift-last-${SESSION_ID}"
```

**Issue:** The demo uses `driftcheck-last` (no namespace prefix) which could collide with other plugins or user scripts.

**Recommendation:** Change the demo to use a namespaced sentinel:
```bash
THROTTLE_FILE="/tmp/yourplugin-drift-last-${SESSION_ID}"
```

And add a comment:
```bash
# Throttle sentinel file. Use a unique prefix to avoid collision with other plugins.
# Example: /tmp/yourplugin-drift-last-${SESSION_ID}
THROTTLE_FILE="/tmp/yourplugin-drift-last-${SESSION_ID}"
```

---

## 6. Missing Documentation

### 6.1 CLAUDE.md updates — GOOD but count needs verification ✓

**Line 619 in plan:**
> Also update the hook count in the Overview line from "7 hooks" to "8 hooks"

**Question:** What is the current hook count?

**Checking:**
- SessionStart: 1 (session-start.sh)
- Stop: currently 2 (auto-compound.sh, session-handoff.sh) → will be 3 after adding auto-drift-check.sh
- Other hooks: dotfiles-sync, auto-publish, catalog-reminder

**Expected total:** At least 6, possibly 7 if there's another hook not listed.

**Recommendation:** In Task 5 Step 1, verify the exact count before updating:
```bash
# Count registered hooks in hooks.json
jq '[.hooks[]] | add | length' hooks/hooks.json
```

Then update CLAUDE.md with the correct count.

### 6.2 No memory update for lessons learned ⚠️

**Observation:** This plan introduces a new pattern (per-hook sentinel namespacing) that fixes a critical race condition. This is exactly the kind of lesson that should be written to `MEMORY.md` per the global instructions.

**Recommendation:** Add Task 7 to write a memory entry:

```markdown
## Task 7: Document lesson in MEMORY.md

**Step 1: Add entry to project memory**

Append to `/root/projects/Clavain/memory/MEMORY.md`:

```markdown
## Per-Hook Sentinel Namespacing (2026-02-14)
- **Old pattern:** Shared sentinel `/tmp/clavain-stop-${SESSION_ID}` across all Stop hooks
- **Problem:** First hook writes sentinel, blocks all subsequent hooks from firing
- **Fix:** Per-hook namespacing: `clavain-stop-compound-*`, `clavain-stop-drift-*`, `clavain-stop-handoff-*`
- **Key insight:** Stop hooks can run in parallel or rapid succession — sentinel MUST be per-hook to allow independent throttling
- **Files:** hooks/auto-compound.sh (line 47), hooks/auto-drift-check.sh (line 491), hooks/session-handoff.sh (line 35)
```

**Step 2: Commit**

```bash
git add memory/MEMORY.md
git commit -m "docs: add per-hook sentinel pattern to memory"
```
```

---

## 7. Risk Analysis

### 7.1 Critical path risks — LOW ✓

**Mitigations:**
- TDD approach (write tests first, verify fail, implement, verify pass)
- Syntax checks after each task (`bash -n`)
- Full test suite run before final commit
- No changes to existing signal detection logic in auto-compound (just extraction)

**Assessment:** Risk is well-managed.

### 7.2 Refactor risk (Task 2) — MEDIUM ⚠️

**Risk:** Extracting 52 lines from auto-compound.sh and replacing with lib-signals.sh sourcing could introduce subtle bugs if the extraction is not exact.

**Specific concerns:**

1. **Variable name mapping:**
   - Old: `SIGNALS` and `WEIGHT` (local to auto-compound.sh)
   - New: `CLAVAIN_SIGNALS` and `CLAVAIN_SIGNAL_WEIGHT` (from lib-signals.sh) → then copied to `SIGNALS` and `WEIGHT`

   **Risk:** If the copying step is omitted, the REASON string construction (line 129) will fail.

2. **Transcript tail size:**
   - Both old and new use `tail -80` (line 69 vs plan line 253)
   - Risk: LOW — this is preserved

3. **Threshold:**
   - Old: `>= 3` (line 121)
   - New: `>= 3` (plan line 263)
   - Risk: LOW — this is preserved

**Mitigation:**

The plan includes a test suite verification step (Task 2 Step 3):
```bash
Run: bats tests/shell/auto_compound.bats
Expected: All 10 tests PASS (identical behavior).
```

**Assessment:** This is the right mitigation. If the refactor breaks behavior, the existing tests will catch it.

**Additional recommendation:** Add a manual smoke test to Task 2:
```bash
# Task 2 Step 3.5: Manual verification
# Start a claude session with --plugin-dir, make a commit, and verify auto-compound fires
```

### 7.3 Sentinel timing (TOCTOU) — ALREADY MITIGATED ✓

**Observation:** auto-compound.sh writes the cross-hook sentinel BEFORE analyzing the transcript (line 52 in current code):
```bash
# Write sentinel NOW — before transcript analysis — to minimize TOCTOU window
touch "$STOP_SENTINEL"
```

**Assessment:** This is correct and demonstrates awareness of time-of-check-to-time-of-use race conditions.

**Recommendation:** Ensure this pattern is preserved in the refactor AND in auto-drift-check.sh. The plan's auto-drift-check.sh does include this (line 495):
```bash
touch "$STOP_SENTINEL"
```

Keep as-is.

---

## 8. Recommendations Summary

### 8.1 MUST FIX (blocking issues)

1. **Add interwatch discovery test** (Section 2.2, Gap 5)
   - Test that auto-drift-check gracefully degrades when interwatch is not installed
   - Without this test, the graceful degradation claim is unverified

2. **Fix demo hook throttle sentinel naming** (Section 5.4)
   - Change from `/tmp/driftcheck-last-*` to `/tmp/yourplugin-drift-last-*`
   - Add comment about namespace collision

3. **Clarify refactor diff** (Section 4.1)
   - Make the line deletion explicit in Task 2 Step 2
   - Show exact line numbers and net change

### 8.2 SHOULD FIX (quality improvements)

4. **Use here-string instead of echo | grep in lib-signals.sh** (Section 3.1)
   - Change `echo "$text" | grep -q` to `grep -q <<< "$text"`
   - Reduces process overhead and follows better bash idioms

5. **Preserve signal list in auto-compound.sh header** (Section 4.2)
   - Keep the detailed signal list for documentation
   - Add reference to lib-signals.sh for implementation

6. **Add empty string test for lib-signals.sh** (Section 2.1, Gap 4)
   - Guard against edge case: `detect_signals ""`

7. **Add memory entry for per-hook sentinel pattern** (Section 6.2)
   - Document the fix for future reference

### 8.3 NICE TO HAVE (optional refinements)

8. **Add multi-signal fixture** (Section 2.1, Gap 2)
   - Replace contrived test string with realistic JSONL fixture

9. **Add comment explaining detect_signals scoping** (Section 3.2)
   - Clarify that CLAVAIN_SIGNALS and CLAVAIN_SIGNAL_WEIGHT are global side effects

10. **Add demo signal pattern reference** (Section 5.2)
    - Comment in demo explaining simplified signal set with link to full reference

---

## 9. Language-Specific Review (Bash)

### 9.1 Bash idioms applied ✓

- `set -euo pipefail` — PRESENT in all hooks
- Quoting hygiene — GOOD (all variable expansions quoted)
- Parameter expansion for string manipulation — GOOD (`${var%,}`, `${var:-default}`)
- Arithmetic expansion — GOOD (`$((WEIGHT + 1))`)
- Here-docs for JSON output — GOOD (lines 549-554 in auto-drift-check.sh)
- Portability (stat) — GOOD (handles both GNU and BSD stat)

### 9.2 Bash anti-patterns avoided ✓

- No `eval` usage
- No unquoted expansions
- No `ls` parsing
- No `which` (uses `command -v`)
- No backticks (uses `$()`)

### 9.3 Bash improvements recommended

- **echo | grep → here-string** (see Section 3.1)
- **Consider shellcheck integration** — Run `shellcheck hooks/*.sh` as part of the test suite

---

## 10. Test Design Review

### 10.1 Coverage metrics

**lib_signals.bats:**
- 12 tests, 7 signal types
- Coverage: ~90% (missing empty string test)

**auto_drift_check.bats:**
- 10 tests, 6 guards + 2 thresholds
- Coverage: ~85% (missing interwatch discovery test)

**auto_compound.bats:**
- 10 tests (existing, will be updated for new sentinel)
- Coverage: ~90% (good baseline)

### 10.2 Test isolation ✓

Both test files use:
- `setup_file()` to create temp dirs and copy fixtures
- `teardown_file()` to clean up temp dirs
- `teardown()` to remove sentinel files after each test

**Assessment:** Good isolation. Tests won't interfere with each other.

### 10.3 Assertions

**Good patterns:**
- Uses `jq -e` to assert JSON structure (auto_compound.bats line 45)
- Uses `assert_output ""` to verify no output (passthrough cases)
- Uses `assert_success` to verify exit 0

**Recommendation:** Keep as-is.

---

## 11. Final Verdict

**APPROVE with refinements**

The plan is well-structured, follows TDD methodology, and demonstrates deep understanding of bash idioms and race conditions. The per-hook sentinel fix is a significant improvement.

**Required changes before implementation:**
1. Add interwatch discovery test
2. Fix demo hook sentinel naming
3. Use here-string instead of echo | grep in lib-signals.sh
4. Clarify refactor diff in Task 2

**Recommended changes:**
5. Preserve signal list in auto-compound.sh header
6. Add empty string test
7. Add memory entry

**Implementation readiness:** 90%

With the above changes, this plan is ready for implementation using clavain:executing-plans.

---

## Appendix: Pattern Reference

### Sentinel naming convention

| Hook | Sentinel name | Purpose |
|------|--------------|---------|
| auto-compound | `/tmp/clavain-stop-compound-${SESSION_ID}` | Prevent re-trigger in same Stop cycle |
| auto-drift-check | `/tmp/clavain-stop-drift-${SESSION_ID}` | Prevent re-trigger in same Stop cycle |
| session-handoff | `/tmp/clavain-stop-handoff-${SESSION_ID}` | Prevent re-trigger in same Stop cycle |
| auto-compound | `/tmp/clavain-compound-last-${SESSION_ID}` | Throttle: 5-min window |
| auto-drift-check | `/tmp/clavain-drift-last-${SESSION_ID}` | Throttle: 10-min window |
| session-handoff | `/tmp/clavain-handoff-${SESSION_ID}` | Once per session |

**Pattern:** `clavain-<hook-name>-<purpose>-${SESSION_ID}`

### Signal weight reference

| Signal | Weight | Pattern |
|--------|--------|---------|
| commit | 1 | `"git commit` |
| bead-closed | 1 | `"bd close` |
| insight | 1 | `Insight ─` |
| resolution | 2 | `"that worked`, `"it's fixed`, etc. |
| investigation | 2 | `"the issue was`, `"root cause`, etc. |
| recovery | 2 | `FAILED` → `passed` |
| version-bump | 2 | `bump-version`, `interpub:release` |

**Threshold:**
- auto-compound: weight >= 3
- auto-drift-check: weight >= 2

**Rationale:** Drift checking is cheaper and should trigger earlier than compound (which involves memory writes and beads sync).
