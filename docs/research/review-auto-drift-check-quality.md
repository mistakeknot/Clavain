# Auto-Drift-Check Implementation Quality Review

**Date:** 2026-02-14
**Reviewer:** fd-quality agent
**Scope:** Shell code quality and bash idioms

## Executive Summary

Overall quality is **strong**, with consistent patterns, good error handling, and well-designed tests. Found 7 minor improvements across naming, bash idioms, and documentation. No correctness issues.

## Files Reviewed

- `hooks/lib-signals.sh` (82 lines)
- `hooks/auto-drift-check.sh` (112 lines)
- `hooks/auto-compound.sh` (113 lines, refactored)
- `tests/shell/lib_signals.bats` (102 lines, 13 tests)
- `tests/shell/auto_drift_check.bats` (101 lines, 10 tests)
- `tests/shell/auto_compound.bats` (128 lines, 12 tests)

---

## 1. Naming Conventions Consistency

### Finding 1.1: Inconsistent Signal Name Format
**Severity:** Low
**Files:** `lib-signals.sh`, all test files

**Issue:**
Signal names use inconsistent hyphenation:
- `commit` (no hyphens)
- `resolution` (no hyphens)
- `investigation` (no hyphens)
- `bead-closed` (hyphenated)
- `insight` (no hyphens)
- `recovery` (no hyphens)
- `version-bump` (hyphenated)

**Recommendation:**
Either use hyphens consistently (`git-commit`, `bead-closed`, `version-bump`) or drop them (`beadclosed`, `versionbump`). Current mix is arbitrary.

**Rationale:**
The hyphenated names (`bead-closed`, `version-bump`) correspond to multi-word concepts, while single-word signals don't need hyphens. This is actually defensible, but document the rule: "hyphenate multi-word signal names, use bare words for single concepts."

---

### Finding 1.2: Variable Naming Convention
**Severity:** Low
**Files:** All hook scripts

**Issue:**
Mix of uppercase globals and lowercase locals is correct, but some locals don't have explicit `local` declarations:

```bash
# lib-signals.sh line 31 - good, explicit local
local text="$1"

# auto-drift-check.sh lines 87-88 - good, but could be local
SIGNALS="$CLAVAIN_SIGNALS"
WEIGHT="$CLAVAIN_SIGNAL_WEIGHT"
```

**Recommendation:**
Lines 87-88 in both `auto-drift-check.sh` and `auto-compound.sh` assign globals to new variables for brevity. These should be marked `local` since they're script-scoped:

```bash
local signals="$CLAVAIN_SIGNALS"
local weight="$CLAVAIN_SIGNAL_WEIGHT"
```

And update the JSON construction to use lowercase vars.

**Rationale:**
Prevents accidental pollution of environment. The current code works because these scripts exit immediately, but the pattern is brittle.

---

## 2. Bash Idioms

### Finding 2.1: Echo Pipe vs Here-String for grep
**Severity:** Low
**Files:** `lib-signals.sh` lines 36, 42, 48, 54, 60, 66, 74

**Issue:**
All signal checks use `echo "$text" | grep` pattern:

```bash
if echo "$text" | grep -q '"git commit\|"git add.*&&.*git commit'; then
```

**Recommendation:**
Use here-string for single-variable grep (avoids subshell):

```bash
if grep -q '"git commit\|"git add.*&&.*git commit' <<< "$text"; then
```

**Rationale:**
Here-strings are more efficient (no fork for `echo`) and idiomatic for single-variable grep. The `echo | grep` pattern is not wrong, but here-strings are preferred in modern bash.

**Counter-argument:**
The `echo | grep` pattern is more portable (works in POSIX `sh`). However, the script already uses `#!/usr/bin/env bash` and bash-specific features (`[[`, `$((...))`), so portability is not a constraint.

---

### Finding 2.2: Quoting Consistency
**Severity:** None (already correct)

**Observation:**
All variable expansions in conditionals are properly quoted:
- `"$STOP_ACTIVE"` (line 30)
- `"$TRANSCRIPT"` (line 67)
- `"$RECENT"` (line 73)

All command substitutions are properly quoted:
- `INPUT=$(cat)` (line 26) - safe unquoted because stdin is trusted
- `RECENT=$(tail -80 "$TRANSCRIPT" 2>/dev/null || true)` (line 72) - quoted

No issues found.

---

### Finding 2.3: Portable stat Command
**Severity:** Low
**Files:** `auto-drift-check.sh` lines 51-52, `auto-compound.sh` lines 58-59

**Issue:**
Stat command uses GNU (`-c %Y`) and BSD (`-f %m`) fallback pattern:

```bash
THROTTLE_MTIME=$(stat -c %Y "$THROTTLE_SENTINEL" 2>/dev/null || stat -f %m "$THROTTLE_SENTINEL" 2>/dev/null || date +%s)
```

**Recommendation:**
The pattern is correct but could be clearer with explicit platform detection:

```bash
if stat -c %Y "$THROTTLE_SENTINEL" &>/dev/null 2>&1; then
    # GNU stat
    THROTTLE_MTIME=$(stat -c %Y "$THROTTLE_SENTINEL")
elif stat -f %m "$THROTTLE_SENTINEL" &>/dev/null 2>&1; then
    # BSD stat
    THROTTLE_MTIME=$(stat -f %m "$THROTTLE_SENTINEL")
else
    # Fallback: assume sentinel is fresh
    THROTTLE_MTIME=$(date +%s)
fi
```

**Counter-argument:**
The current one-liner is more concise and works identically. The explicit form is clearer but verbose. Keep current pattern.

**Verdict:**
No change needed. The one-liner is idiomatic for cross-platform stat usage.

---

### Finding 2.4: Subprocess Cleanup Pattern
**Severity:** None (already correct)

**Observation:**
Both hooks use `|| true` correctly to prevent `set -e` failures on cleanup:

```bash
# auto-drift-check.sh line 109
find /tmp -maxdepth 1 \( -name 'clavain-stop-*' -o -name 'clavain-drift-last-*' -o -name 'clavain-compound-last-*' \) -mmin +60 -delete 2>/dev/null || true
```

```bash
# auto-compound.sh line 111
find /tmp -maxdepth 1 -name 'clavain-stop-*' -mmin +60 -delete 2>/dev/null || true
```

**Issue:**
`auto-drift-check.sh` cleans up 3 sentinel patterns (stop, drift-last, compound-last), while `auto-compound.sh` only cleans up stop sentinels. This is asymmetric.

**Recommendation:**
Both hooks should clean up both sentinel types:

```bash
# Both hooks should use this pattern
find /tmp -maxdepth 1 \( -name 'clavain-stop-*' -o -name 'clavain-drift-last-*' -o -name 'clavain-compound-last-*' \) -mmin +60 -delete 2>/dev/null || true
```

**Rationale:**
Cleanup is a shared responsibility. Each hook should clean all Clavain sentinels to prevent accumulation from crashed sessions.

---

## 3. Test Design Quality

### Finding 3.1: Test Coverage
**Severity:** None (already excellent)

**Coverage analysis:**

**lib-signals.sh (13 tests):**
- ✅ All 7 signal types (commit, resolution, investigation, bead-closed, insight, recovery, version-bump)
- ✅ Weight accumulation
- ✅ Edge cases (empty input, no signals)
- ✅ Trailing comma removal
- ✅ interpub:release as version-bump alias

**auto-drift-check.sh (10 tests):**
- ✅ All guards (stop_hook_active, sentinel, opt-out, throttle)
- ✅ Threshold behavior (below/above threshold 2)
- ✅ Interwatch discovery (implicitly tested by running hook)
- ✅ Reason content validation

**auto-compound.sh (12 tests):**
- ✅ All guards (stop_hook_active, sentinel, opt-out, throttle)
- ✅ Threshold behavior (below/above threshold 3)
- ✅ New test added for version-bump+commit at threshold 3

**Coverage verdict:** Comprehensive. All guard conditions, thresholds, and signal types are tested.

---

### Finding 3.2: Test Fixture Sharing
**Severity:** Low

**Observation:**
Both test suites share the same fixtures via `cp` in `setup_file()`:

```bash
# auto-drift-check.bats line 7
cp "$BATS_TEST_DIRNAME/../fixtures/transcript_with_commit.jsonl" "$TMPDIR_DRIFT/transcript_commit.jsonl"
```

```bash
# auto-compound.bats line 7
cp "$BATS_TEST_DIRNAME/../fixtures/transcript_with_commit.jsonl" "$TMPDIR_COMPOUND/transcript_commit.jsonl"
```

**Recommendation:**
This is fine, but consider symlinking instead of copying to reduce disk I/O:

```bash
ln -s "$BATS_TEST_DIRNAME/../fixtures/transcript_with_commit.jsonl" "$TMPDIR_DRIFT/transcript_commit.jsonl"
```

**Counter-argument:**
Copying is safer (tests can't accidentally modify shared fixtures) and the files are tiny (< 1KB). Keep current pattern.

**Verdict:**
No change needed.

---

### Finding 3.3: Test Naming Convention
**Severity:** None (already consistent)

**Observation:**
All test names follow the pattern `<script-name>: <behavior>`:

```
lib-signals: detect_signals sets CLAVAIN_SIGNALS and CLAVAIN_SIGNAL_WEIGHT
auto-drift-check: noop when stop_hook_active
auto-compound: detects insight+commit+investigation signals (weight >= 3)
```

This is clear and consistent. No changes needed.

---

## 4. Error Handling Patterns

### Finding 4.1: Fail-Open Strategy
**Severity:** None (already correct)

**Observation:**
All hooks use fail-open pattern (exit 0 on all errors):

```bash
# Guard: fail-open if jq is not available
if ! command -v jq &>/dev/null; then
    exit 0
fi
```

```bash
# Guard: if another Stop hook already fired this cycle, don't cascade
STOP_SENTINEL="/tmp/clavain-stop-${SESSION_ID}"
if [[ -f "$STOP_SENTINEL" ]]; then
    exit 0
fi
```

**Verdict:**
Correct for Stop hooks. A broken hook should not break Claude Code sessions.

---

### Finding 4.2: Sentinel TOCTOU Window
**Severity:** Low
**Files:** `auto-drift-check.sh` line 46, `auto-compound.sh` line 53

**Issue:**
Both hooks check for shared sentinel existence, then touch it:

```bash
# auto-drift-check.sh lines 43-46
if [[ -f "$STOP_SENTINEL" ]]; then
    exit 0
fi
touch "$STOP_SENTINEL"
```

**TOCTOU window:**
If two hooks run in parallel:
1. Hook A checks sentinel → not found
2. Hook B checks sentinel → not found
3. Hook A touches sentinel
4. Hook B touches sentinel
5. Both hooks proceed

**Mitigation:**
Use `mkdir` (atomic on POSIX) instead of `touch`:

```bash
if ! mkdir "$STOP_SENTINEL" 2>/dev/null; then
    exit 0
fi
```

**Counter-argument:**
Claude Code likely runs hooks sequentially, not in parallel. The TOCTOU race is theoretical.

**Verdict:**
Document that hooks are assumed to run sequentially. If parallel execution is ever added, switch to `mkdir`-based locking.

---

### Finding 4.3: Missing Error Check on `source`
**Severity:** Low
**Files:** `auto-drift-check.sh` line 78, `auto-compound.sh` line 78

**Issue:**
Both hooks source `lib-signals.sh` without checking if it exists:

```bash
source "${SCRIPT_DIR}/lib-signals.sh"
detect_signals "$RECENT"
```

**Recommendation:**
Add existence check:

```bash
if [[ ! -f "${SCRIPT_DIR}/lib-signals.sh" ]]; then
    exit 0
fi
source "${SCRIPT_DIR}/lib-signals.sh"
```

**Counter-argument:**
`set -euo pipefail` will cause the script to exit on `source` failure. The current behavior (hard fail) is acceptable for a missing critical library.

**Verdict:**
No change needed. Hard fail on missing `lib-signals.sh` is appropriate.

---

## 5. Comment Quality and Documentation

### Finding 5.1: Header Comment Quality
**Severity:** None (already excellent)

**Observation:**
All three scripts have clear header comments:

```bash
# lib-signals.sh lines 2-20
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
```

**Verdict:**
Excellent. Self-contained reference for all signals.

---

### Finding 5.2: Inline Comment Density
**Severity:** Low

**Observation:**
Inline comments are used for:
- Guard explanations (lines 20, 28, 34, etc.)
- Signal detection blocks (lines 35, 41, 47, etc.)
- Threshold logic (lines 81-83)

**Good examples:**
```bash
# Guard: if another Stop hook already fired this cycle, don't cascade
# Write sentinel NOW — before transcript analysis — to minimize TOCTOU window
# Threshold: need weight >= 3 to trigger compound
```

**Recommendation:**
Add one comment explaining the sentinel cleanup pattern at the end:

```bash
# Clean up stale sentinels from previous sessions (>1 hour old)
# to prevent /tmp accumulation from crashed sessions
find /tmp -maxdepth 1 \( -name 'clavain-stop-*' ... \) -mmin +60 -delete 2>/dev/null || true
```

**Rationale:**
The cleanup line is complex (`find` with `-mmin +60 -delete`) and its purpose is not immediately obvious.

---

### Finding 5.3: Test Documentation
**Severity:** None (already good)

**Observation:**
Test files have clear setup/teardown comments:

```bash
# tests/shell/auto_drift_check.bats lines 4-5
setup_file() {
    export TMPDIR_DRIFT="$(mktemp -d)"
    # Reuse transcript fixtures from auto-compound tests
```

Test names are self-documenting:

```
@test "auto-drift-check: commit+bead-close triggers at threshold 2"
@test "auto-compound: version-bump+commit triggers (weight >= 3)"
```

**Verdict:**
No changes needed.

---

## 6. Code Duplication Analysis

### Finding 6.1: Guard Block Duplication
**Severity:** Low (acceptable)

**Observation:**
Both `auto-drift-check.sh` and `auto-compound.sh` have nearly identical guard blocks:

```bash
# Lines 26-63 (auto-drift-check.sh)
# Lines 26-62 (auto-compound.sh)
```

Differences:
- Throttle sentinel name (`clavain-drift-last-*` vs `clavain-compound-last-*`)
- Throttle duration (600s vs 300s)
- Opt-out file name (`.claude/clavain.no-driftcheck` vs `.claude/clavain.no-autocompound`)
- Discovery check (auto-drift-check requires interwatch, auto-compound does not)

**Recommendation:**
Consider extracting guard logic into `lib-guards.sh`:

```bash
# hooks/lib-guards.sh
check_stop_guards() {
    local hook_name="$1"
    local session_id="$2"
    local throttle_seconds="$3"
    local opt_out_file="$4"
    local require_plugin="${5:-}"  # optional

    # Check stop_hook_active, sentinel, opt-out, throttle
    # Return 0 if passed, 1 if should exit
}
```

**Counter-argument:**
The guards are only ~40 lines per hook and have meaningful differences. Extracting would add indirection without significant reduction in code. The duplication is acceptable for clarity.

**Verdict:**
No change needed. Keep guards inline for readability.

---

### Finding 6.2: JSON Output Duplication
**Severity:** Low

**Observation:**
Both hooks have identical JSON output blocks:

```bash
# auto-drift-check.sh lines 97-106
# auto-compound.sh lines 98-108
```

**Recommendation:**
Extract to a function in `lib-signals.sh`:

```bash
emit_block_decision() {
    local reason="$1"
    if command -v jq &>/dev/null; then
        jq -n --arg reason "$reason" '{"decision":"block","reason":$reason}'
    else
        cat <<ENDJSON
{
  "decision": "block",
  "reason": "${reason}"
}
ENDJSON
    fi
}
```

Then both hooks can call:

```bash
emit_block_decision "$REASON"
```

**Counter-argument:**
The duplication is only 10 lines and clear. Adding a function obscures the output format. Keep inline.

**Verdict:**
No change needed. Inline JSON is more transparent.

---

## 7. Bash-Specific Idiom Review

### Finding 7.1: `[[` vs `[` Consistency
**Severity:** None (already correct)

**Observation:**
All conditionals use `[[ ]]` (bash) consistently:

```bash
if [[ "$STOP_ACTIVE" == "true" ]]; then
if [[ -f "$STOP_SENTINEL" ]]; then
if [[ -z "$RECENT" ]]; then
if [[ "$CLAVAIN_SIGNAL_WEIGHT" -lt 2 ]]; then
```

No instances of `[ ]` (POSIX `test`). Consistent and correct.

---

### Finding 7.2: Arithmetic Expansion
**Severity:** None (already correct)

**Observation:**
All arithmetic uses `$((...))`:

```bash
CLAVAIN_SIGNAL_WEIGHT=$((CLAVAIN_SIGNAL_WEIGHT + 1))
if [[ $((THROTTLE_NOW - THROTTLE_MTIME)) -lt 600 ]]; then
```

No instances of `expr` or `let`. Correct and idiomatic.

---

### Finding 7.3: Command Substitution
**Severity:** None (already correct)

**Observation:**
All command substitutions use `$(...)`, not backticks:

```bash
INPUT=$(cat)
RECENT=$(tail -80 "$TRANSCRIPT" 2>/dev/null || true)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
```

Consistent and modern.

---

## Summary of Findings

| Finding | Severity | File(s) | Action |
|---------|----------|---------|--------|
| 1.1 Signal name hyphenation | Low | lib-signals.sh | Document rule or normalize |
| 1.2 Local variable declarations | Low | auto-*.sh | Add `local` to SIGNALS/WEIGHT |
| 2.1 Echo pipe vs here-string | Low | lib-signals.sh | Use `grep <<< "$text"` |
| 2.4 Cleanup pattern asymmetry | Low | auto-compound.sh | Clean all 3 sentinel types |
| 5.2 Cleanup comment missing | Low | auto-*.sh | Add comment to find/delete |

**Correctness issues:** 0
**Bash idiom issues:** 1 (echo|grep vs here-string)
**Naming consistency issues:** 2 (signal names, local vars)
**Documentation gaps:** 1 (cleanup comment)

---

## Recommendations Priority

### High Priority (Fix Now)
None. All findings are cosmetic or minor improvements.

### Medium Priority (Consider)
1. Add `local` to `SIGNALS` and `WEIGHT` variables (lines 87-88 in both hooks)
2. Normalize sentinel cleanup to all 3 types in both hooks
3. Add comment explaining cleanup pattern

### Low Priority (Nice to Have)
1. Replace `echo "$text" | grep` with `grep <<< "$text"` in `lib-signals.sh`
2. Document signal naming convention (hyphenate multi-word, bare for single-word)

---

## Overall Quality Assessment

**Code Quality:** 9/10
**Test Coverage:** 10/10
**Documentation:** 9/10
**Bash Idioms:** 8/10 (minor echo|grep preference)
**Error Handling:** 10/10

**Overall:** 9.2/10

The implementation is production-ready. All findings are minor style improvements that do not affect correctness or maintainability.
