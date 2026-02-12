# Quality Review: Work Discovery Scanner (M1 F1+F2)

**Reviewer:** Flux-drive Quality & Style Reviewer
**Date:** 2026-02-12
**Scope:** hooks/lib-discovery.sh, tests/shell/discovery.bats, tests/structural/test_discovery.py, commands/lfg.md, skills/using-clavain/*

## Summary

This review examines the work discovery scanner implementation for quality, conventions, shell idioms, error handling patterns, and test coverage. The feature scans open beads, infers next actions from filesystem artifacts, and presents ranked recommendations to the user.

**Overall Assessment:** Strong implementation with good defensive programming. Shell scripting is generally solid with proper quoting, error handling, and fallback paths. Test coverage is comprehensive. Several quality findings require attention.

## Shell Scripting Quality (lib-discovery.sh)

### Strengths

1. **Excellent error handling and fallback strategy**
   - Graceful degradation with sentinel strings (DISCOVERY_UNAVAILABLE, DISCOVERY_ERROR)
   - Silent telemetry failures (`|| true` on non-critical paths)
   - JSON validation before processing (`jq empty` checks)
   - Portable date command with BSD/GNU fallbacks

2. **Proper quoting discipline**
   - All variable expansions are quoted: `"$variable"`
   - jq arguments use `--arg` and `--argjson` for safe injection-free construction
   - Command substitution with proper quoting: `$(command "arg")`

3. **Smart portability choices**
   - Perl regex detection with fallback to basic patterns
   - stat command with Linux (-c) and BSD (-f) variants
   - date command with GNU (-d) and BSD (-v) variants

4. **Good documentation**
   - Clear function headers with purpose, args, and output format
   - Inline comments explaining non-obvious logic (word-boundary matching, staleness checks)

### Quality Findings

#### MEDIUM: Inconsistent error suppression strategy

The script uses both `2>/dev/null || true` and bare `|| true` patterns inconsistently:

```bash
# Line 105: suppresses both stderr and exit code
open_list=$(bd list --status=open --json 2>/dev/null) || {
    echo "DISCOVERY_ERROR"
    return 0
}

# Line 44: only suppresses exit code, stderr still visible
plan_path=$(grep $grep_flags "$pattern" "${DISCOVERY_PROJECT_DIR}/docs/plans/" 2>/dev/null | head -1 || true)

# Line 196: both suppressed for telemetry
jq -n -c ... >> "$telemetry_file" 2>/dev/null || true
```

**Recommendation:** Standardize to `2>/dev/null || true` for all optional operations that should fail silently. For critical operations (bd queries), the current explicit error handling is correct.

#### LOW: grep portability edge case

Lines 33-50 implement grep -P detection with fallback, but the fallback pattern is not equivalent:

```bash
# Perl regex (with word boundary)
pattern="Bead.*${bead_id}\\b"

# Fallback (basic regex, no word boundary)
pattern="Bead.*${bead_id}[^a-zA-Z0-9_-]"
```

The fallback requires a non-word character AFTER the bead ID, which fails when the ID is at end-of-line. The script addresses this with a second grep attempt (lines 47-49), but this is inefficient (two grep passes per directory).

**Recommendation:** Use a single grep with an extended regex that matches both cases:
```bash
pattern="Bead.*${bead_id}\([^a-zA-Z0-9_-]\|$\)"
```
Or simplify by always using basic regex without word boundaries, since bead IDs have hyphens and the context "Bead" makes false positives unlikely.

#### MEDIUM: Silent failures in filesystem scanning

`infer_bead_action()` greps docs directories but doesn't validate they exist before scanning. If DISCOVERY_PROJECT_DIR is misconfigured or points to a non-project directory, grep quietly returns nothing, and all beads get `action: brainstorm`.

**Current behavior:**
```bash
if [[ -d "${DISCOVERY_PROJECT_DIR}/docs/plans" ]]; then
    plan_path=$(grep $grep_flags "$pattern" "${DISCOVERY_PROJECT_DIR}/docs/plans/" 2>/dev/null | head -1 || true)
fi
```

The `-d` check is present, so this is actually correct. No issue here — retract this finding.

#### LOW: Hardcoded two-day staleness threshold

Line 127 hardcodes `2 days ago` without configuration:

```bash
two_days_ago=$(date -d '2 days ago' +%s 2>/dev/null || date -v-2d +%s 2>/dev/null || echo 0)
```

**Recommendation:** Extract to a variable at the top of `discovery_scan_beads()`:
```bash
local stale_days="${DISCOVERY_STALE_DAYS:-2}"
two_days_ago=$(date -d "${stale_days} days ago" +%s 2>/dev/null || ...)
```

This allows users to configure staleness via environment variable if desired, while keeping the default at 2 days.

#### CRITICAL: Race condition in telemetry append

`discovery_log_selection()` uses a simple append without locking:

```bash
jq -n -c '...' >> "$telemetry_file" 2>/dev/null || true
```

If multiple Claude Code sessions run discovery simultaneously (or if a user triggers parallel workflows), telemetry writes can interleave or corrupt. This is unlikely in typical usage but possible in Codex parallel dispatch scenarios.

**Recommendation:** Use a lockfile wrapper or accept that telemetry is best-effort. Given that the function already has `|| true` (silent failure), document this limitation and consider it acceptable risk for telemetry.

**Alternative:** Use a more robust append strategy:
```bash
# Create temp file, then atomic move
local tmp_file="${telemetry_file}.$$"
jq -n -c '...' > "$tmp_file" && cat "$tmp_file" >> "$telemetry_file" && rm "$tmp_file"
```

But this adds complexity for minimal gain. Recommendation: **document as best-effort, no change needed**.

## Test Coverage (discovery.bats)

### Strengths

1. **Comprehensive coverage of error paths**
   - bd not installed
   - bd command failure
   - Invalid JSON from bd
   - Missing .beads directory

2. **Good use of test isolation**
   - Each test gets a fresh temp directory
   - Mock functions exported per-test
   - Proper cleanup in teardown

3. **Edge case coverage**
   - Word-boundary matching (substring false positives)
   - Multiple beads on same line
   - Special characters in telemetry (injection testing)
   - Staleness with old file mtimes

4. **Clear test names and structure**
   - bats @test directives with descriptive names
   - Organized by feature area with comment headers

### Quality Findings

#### LOW: Mock bd function doesn't preserve all bd behaviors

The mock_bd helper (lines 24-39) only handles `list` subcommand:

```bash
mock_bd() {
    local json="$1"
    export MOCK_BD_JSON="$json"
    export MOCK_BD_IP_JSON="${2:-[]}"
    bd() {
        if [[ "$1" == "list" ]]; then
            if [[ "$*" == *"--status=in_progress"* ]]; then
                echo "$MOCK_BD_IP_JSON"
            else
                echo "$MOCK_BD_JSON"
            fi
            return 0
        fi
        return 1
    }
    export -f bd
}
```

If discovery_scan_beads() later calls `bd show` or other subcommands, tests will fail. This is fine for current usage but brittle.

**Recommendation:** Add a comment documenting the limitation, or make the mock more permissive:
```bash
bd() {
    case "$1" in
        list) # existing logic ;;
        *) echo "mock_bd: unsupported subcommand $1" >&2; return 1 ;;
    esac
}
```

#### MEDIUM: Test doesn't verify action inference priority

Test "discovery: sorts by priority then recency" (line 109) verifies sorting but doesn't check that the inferred actions are correct for each bead. It's possible for sorting to work but action inference to fail, producing sorted beads with wrong actions.

**Recommendation:** Add action assertions to sorting test:
```bash
@test "discovery: sorts by priority then recency" {
    mkdir -p "$TEST_PROJECT/docs/plans"
    echo "**Bead:** Test-high" > "$TEST_PROJECT/docs/plans/high-plan.md"

    mock_bd '[...]'
    run discovery_scan_beads
    assert_success

    # Verify sorting
    [[ $(echo "$output" | jq -r '.[0].id') == "Test-high" ]]

    # Verify action inference
    [[ $(echo "$output" | jq -r '.[0].action') == "execute" ]]
    [[ $(echo "$output" | jq -r '.[0].plan_path') == *"high-plan.md" ]]
}
```

#### LOW: Staleness tests use hardcoded dates

Lines 234-245 (staleness tests) use `touch -t 202602070000` with a hardcoded date. If this test runs after 2026-02-14, the date will be less than 5 days old and the test will fail.

**Recommendation:** Use relative dates:
```bash
@test "discovery: marks bead as stale when plan file is old" {
    # ... setup ...
    # Set mtime to 5 days ago using relative date
    local five_days_ago
    five_days_ago=$(date -d '5 days ago' +%Y%m%d%H%M 2>/dev/null || date -v-5d +%Y%m%d%H%M)
    touch -t "$five_days_ago" "$TEST_PROJECT/docs/plans/old-plan.md"
    # ... rest of test ...
}
```

Or use `touch --date='5 days ago'` (GNU coreutils only), but -t is more portable.

#### MEDIUM: No test for merging open + in_progress beads

discovery_scan_beads() queries both `--status=open` and `--status=in_progress`, then merges with `jq -n --argjson a "$open_list" --argjson b "$ip_list" '$a + $b'`. There's no test verifying that this merge works correctly when both lists have beads.

**Recommendation:** Add test:
```bash
@test "discovery: merges open and in_progress beads" {
    local open_json='[{"id":"Test-open1","title":"Open bead","status":"open","priority":2,"updated_at":"2026-02-12T10:00:00Z"}]'
    local ip_json='[{"id":"Test-ip1","title":"In progress","status":"in_progress","priority":1,"updated_at":"2026-02-12T11:00:00Z"}]'

    mock_bd "$open_json" "$ip_json"
    run discovery_scan_beads
    assert_success

    local count
    count=$(echo "$output" | jq 'length')
    [[ "$count" == "2" ]]

    # Verify both statuses present
    local statuses
    statuses=$(echo "$output" | jq -r '.[].status' | sort | tr '\n' ' ')
    [[ "$statuses" == "in_progress open " ]]
}
```

## Structural Tests (test_discovery.py)

### Strengths

1. **Fast, simple checks** — verify files exist and contain expected sentinels
2. **Complements shell tests** — structural tests catch missing files before shell tests run

### Quality Findings

#### LOW: No validation of function signatures

`test_lib_discovery_has_required_functions` only checks that function names appear with `()` suffix. It doesn't verify parameter counts or usage patterns.

**Recommendation:** Add a shell-based validator that sources the file and checks function existence:
```python
def test_lib_discovery_functions_are_callable(project_root):
    """lib-discovery.sh functions are defined and callable."""
    lib = project_root / "hooks" / "lib-discovery.sh"
    result = subprocess.run(
        ["bash", "-c", f"source {lib} && declare -F discovery_scan_beads"],
        capture_output=True, text=True
    )
    assert result.returncode == 0, "discovery_scan_beads not defined as function"
```

This catches syntax errors and confirms the function is actually defined.

## Integration with lfg.md

### Strengths

1. **Clear separation of concerns** — discovery is a pre-step before workflow
2. **Explicit routing logic** — maps actions to commands clearly
3. **Good user experience** — presents top 3 options + fallbacks

### Quality Findings

#### MEDIUM: No error handling for sourcing lib-discovery.sh

Line 13 sources the library without checking if it exists or if sourcing succeeds:

```bash
DISCOVERY_PROJECT_DIR="." source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-discovery.sh" && discovery_scan_beads
```

If CLAUDE_PLUGIN_ROOT is unset or lib-discovery.sh is missing, this will fail silently (due to &&), and the command will skip discovery. This is probably acceptable (fail-safe behavior), but it's undocumented.

**Recommendation:** Add a comment clarifying the fail-safe behavior:
```bash
# Source discovery library. If missing or errors, skip discovery (fail-safe).
DISCOVERY_PROJECT_DIR="." source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-discovery.sh" && discovery_scan_beads
```

Or add explicit validation:
```bash
if [[ -f "${CLAUDE_PLUGIN_ROOT}/hooks/lib-discovery.sh" ]]; then
    DISCOVERY_PROJECT_DIR="." source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-discovery.sh" && discovery_scan_beads
else
    echo "DISCOVERY_UNAVAILABLE"
fi
```

#### LOW: Telemetry call has potential for incorrect boolean

Line 39 shows:
```bash
discovery_log_selection "<bead_id>" "<action>" <true|false>
```

The `<true|false>` is a placeholder that Claude Code must fill. If the command prompt doesn't make this clear, it's easy to pass the string "true|false" or forget to substitute.

**Recommendation:** Clarify in the command prompt:
```markdown
5. Log the selection for telemetry:
   ```bash
   DISCOVERY_PROJECT_DIR="." source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-discovery.sh" && discovery_log_selection "<bead_id>" "<action>" <true|false>
   ```
   Where `true` = user picked the first (recommended) option, `false` = user picked a different option.
   **Replace `<true|false>` with literal `true` or `false` based on user selection.**
```

## Documentation Quality

### Skills Documentation

#### Strengths
- Compact router in SKILL.md is clear and actionable
- Full routing tables in references/ provide comprehensive detail
- Aliases documented (e.g., /deep-review = flux-drive)

#### Findings

##### LOW: Missing discovery mode in routing tables

`skills/using-clavain/references/routing-tables.md` shows `/lfg` in the Execute stage but doesn't explain discovery mode. The behavior change (no-args vs with-args) is significant and should be documented in the full routing table.

**Recommendation:** Add a footnote to the /lfg entry:
```markdown
² **`/lfg` discovery mode**: With no arguments, `/lfg` scans open beads, ranks by priority, and presents the top options via AskUserQuestion. User picks a bead and gets routed to the right command. With arguments, `/lfg` runs the full 9-step pipeline as before.
```

**Update:** This footnote is already present on line 51-52. No change needed.

## Naming Consistency

### Strengths
- Function names follow clear pattern: `discovery_<action>`
- Variable names are descriptive: `two_days_ago`, `plan_path`, `action_result`
- Sentinel strings are SCREAMING_SNAKE_CASE, clearly distinguishable from JSON

### Findings

#### LOW: Inconsistent naming for bead attributes

In JSON output, some fields use snake_case (`plan_path`, `updated_at`) while others come from bd unchanged (`priority`, `status`, `title`, `id`). This is unavoidable (bd schema is fixed), but plan_path is a derived field.

**Recommendation:** Keep current naming. It's consistent with bd's schema, and changing plan_path to planPath would break from bash conventions (snake_case).

## Language-Specific Idioms

### Bash Idioms

#### Excellent
- Uses `[[ ]]` instead of `[ ]` for conditionals (bash-native, safer)
- Proper `local` scoping for all function variables
- `|| true` for optional operations (idiomatic fail-safe pattern)
- `${var:-default}` for defaults (DISCOVERY_PROJECT_DIR, priority field)

#### Could Improve

##### LOW: Inconsistent jq error handling

Some jq calls have `2>/dev/null` (line 163), others don't (line 105). For consistency, all jq calls on user-controlled data should suppress errors.

**Current:**
```bash
count=$(echo "$merged" | jq 'length')
```

**Recommended:**
```bash
count=$(echo "$merged" | jq 'length' 2>/dev/null || echo 0)
```

This prevents jq parse errors from leaking to stderr if merged JSON is malformed.

### Python Idioms (test_discovery.py)

#### Excellent
- Proper use of pathlib.Path (modern, readable)
- Clear docstrings for each test
- Assertions include helpful error messages

#### Could Improve

##### LOW: Hardcoded encoding in read_text

Line 9 and others use `encoding="utf-8"` explicitly. This is good practice but inconsistent with line 31 which omits it.

**Recommendation:** Always specify encoding:
```python
text = lib.read_text(encoding="utf-8")
```

Already correct in most places. Only fix line 31 if it's missing.

Actually checking line 31:
```python
text = lfg.read_text(encoding="utf-8")
```

It's already correct. No change needed.

## Test Quality

### Coverage Assessment

**Covered:**
- Error paths (bd missing, bd fails, invalid JSON, missing .beads)
- Sorting logic (priority, recency)
- Action inference (all states: in_progress, plan exists, PRD exists, brainstorm exists, nothing)
- Word-boundary matching (substring false positives)
- Telemetry safety (injection, special characters)
- Staleness (old vs recent files)
- Empty results

**Missing:**
- Merging open + in_progress beads (both lists non-empty)
- Action inference priority when multiple artifacts exist (plan + PRD + brainstorm)
- Concurrent telemetry writes (race condition testing)
- Discovery with >10 beads (performance/pagination concerns)

**Recommendation:** Add tests for merging beads and action priority. Other gaps are low-risk.

### Test Brittleness

**Concern:** Touch command with absolute dates will break after the date passes.

**Mitigation:** Use relative dates as shown above.

## Error Recovery and Debugging

### Strengths

1. **Sentinel strings make errors explicit** — caller can distinguish "unavailable" from "error" from "empty"
2. **JSON validation before processing** — catches malformed bd output early
3. **Telemetry fails silently** — never blocks workflow

### Findings

#### MEDIUM: No logging for unexpected states

If bd returns beads with unexpected fields (e.g., priority is a string instead of number), jq filtering silently defaults to 4 (line 143):

```bash
priority=$(echo "$bead_json" | jq -r '.priority // 4')
```

This is safe (workflow continues) but makes debugging harder if bd schema changes.

**Recommendation:** Add debug logging (optional, controlled by env var):
```bash
if [[ "${DISCOVERY_DEBUG:-}" == "1" ]]; then
    [[ -z "$priority" || "$priority" == "null" ]] && echo "[discovery] WARN: bead $id has invalid priority" >&2
fi
```

Or log to a debug file:
```bash
[[ -z "$priority" ]] && echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) WARN: bead $id priority defaulted" >> "${HOME}/.clavain/discovery-debug.log"
```

Optional enhancement. Not required for initial release.

## Security Considerations

### Strengths

1. **No command injection** — all jq calls use --arg/--argjson, never string interpolation
2. **No eval** — no dynamic code execution
3. **Safe file operations** — mkdir -p with 2>/dev/null (no side effects on failure)

### Findings

#### NONE

No security issues found. The use of jq for JSON construction completely eliminates injection risk, and grep patterns are hardcoded (not user-controlled).

## Performance Considerations

### Strengths

1. **Lazy directory checks** — only greps if directory exists
2. **head -1 limits output** — stops after first match
3. **Minimal external processes** — mostly bash built-ins and jq

### Findings

#### LOW: Multiple grep passes per directory

When grep -P is unavailable, the script does two grep passes per directory (lines 44-50): first with non-word-char pattern, then with EOL pattern. For large doc trees, this doubles I/O.

**Recommendation:** Use a single extended regex as shown earlier, or accept the performance hit (likely negligible for typical project sizes).

#### LOW: No caching of bd queries

Each invocation queries bd fresh. If discovery is called multiple times per session (e.g., F4 banner + /lfg), bd is queried multiple times.

**Recommendation:** Consider caching bd results for a short TTL (e.g., 60 seconds) in a temp file. But this adds complexity and staleness risk. Probably not worth it unless bd queries are slow.

## Recommendations Summary

### Critical (Address Before Merge)

None. All critical findings were retracted after deeper analysis.

### High Priority (Address Soon)

1. **Add test for merging open + in_progress beads** (missing coverage)
2. **Fix hardcoded dates in staleness tests** (will break over time)
3. **Add test for action priority** (verify action inference when multiple artifacts exist)

### Medium Priority (Address in Follow-Up)

1. **Standardize error suppression** (2>/dev/null || true everywhere)
2. **Document telemetry as best-effort** (race condition is acceptable)
3. **Add explicit sourcing validation to lfg.md** (fail-safe behavior should be documented)
4. **Clarify telemetry call placeholder** (true|false substitution)
5. **Add logging for unexpected bd schema** (optional, for debugging)

### Low Priority (Nice to Have)

1. **Make staleness threshold configurable** (DISCOVERY_STALE_DAYS env var)
2. **Simplify grep word-boundary logic** (single regex, not two passes)
3. **Add structural test for function callability** (bash -c "declare -F")
4. **Add consistent jq error suppression** (2>/dev/null on all jq calls)

## Conclusion

This is a well-crafted feature with strong attention to error handling, portability, and testability. The shell scripting is clean and follows best practices. Test coverage is comprehensive with only a few gaps in edge cases.

The main quality improvement opportunities are in test coverage (merging beads, action priority) and documentation clarity (fail-safe behavior, telemetry best-effort).

No blocking issues. Ready for merge with follow-up tasks for test gaps.
