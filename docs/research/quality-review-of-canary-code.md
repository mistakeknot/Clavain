# Quality Review: Canary Monitoring Implementation

**Reviewer**: Flux-drive Quality & Style Reviewer
**Date**: 2026-02-16
**Scope**: ~350 lines bash functions, ~250 lines bats tests
**Languages**: Shell (bash), SQL, awk, jq

## Executive Summary

This diff implements canary monitoring for routing overrides with **strong quality overall**. Naming is consistent, error handling follows fail-open discipline, and test coverage is excellent. Several minor refinements recommended for edge-case robustness and maintainability.

**Verdict**: READY with suggested improvements (non-blocking).

---

## Universal Quality

### Naming Consistency ✓

- **`_INTERSPECT_` prefix** consistently applied to all new shell variables (`_INTERSPECT_CANARY_WINDOW_USES`, `_INTERSPECT_CANARY_ALERT_PCT`, etc.)
- Function naming follows established pattern: `_interspect_*` prefix, descriptive verb-noun structure (`_interspect_compute_canary_baseline`, `_interspect_record_canary_sample`)
- SQL schema names clear and non-colliding: `canary_samples` table, `canary_id` foreign key
- Test names follow bats convention with readable descriptions

### File Organization ✓

- New functions logically grouped under `# ─── Canary Monitoring ───` header (line 268, lib-interspect.sh)
- Schema migrations cleanly append to existing `ensure_db` function (lines 137-166)
- Configuration defaults co-located with other thresholds in `_interspect_load_confidence` (lines 174-211)

### Error Handling Patterns ✓

**Fail-open discipline** consistently applied:

- `hooks/interspect-session-end.sh:101` — `_interspect_record_canary_sample "$SESSION_ID" 2>/dev/null || true` prevents hook blocking on sample failure
- `hooks/interspect-session-end.sh:104` — `_interspect_check_canaries >/dev/null 2>&1 || true` prevents teardown abort on evaluation failure
- `hooks/interspect-session.sh:115` — Same pattern for session-start canary check
- `commands/interspect-status.md:36` — Status display degrades gracefully: `|| echo "[]"` and `|| echo "0"`

**SQL injection prevention**:

- Line 284, 290 — `_interspect_sql_escape` applied to timestamps and project filters before interpolation
- Line 356 — Session ID escaped before use in WHERE clause
- Line 532 — Verdict reason escaped before UPDATE

**Bounds-checking for config**:

- Lines 195-211 — `_interspect_clamp_int` helper validates numeric ranges (prevents unbounded LIMIT values)
- Lines 209-211 — Noise floor validated as float via awk (0 < value < 10)

**Baseline NULL handling**:

- Lines 434-438 (`_interspect_evaluate_canary`) — Explicit check for NULL baseline columns (SQLite returns empty strings via `-separator`)
- Lines 250-257 (`_interspect_apply_override_locked`) — Conditional INSERT with NULL literals when baseline unavailable

### Complexity Budget ✓

- Functions are single-purpose with clear inputs/outputs
- `_interspect_evaluate_canary` (lines 410-555) is the longest at ~145 lines, but **appropriately complex** for the business logic (baseline comparison, threshold checks, multi-metric evaluation)
- Helper function `_canary_check_metric` (lines 478-511) extracted for reuse across 3 metrics — good abstraction

### Dependency Discipline ✓

- No new external dependencies — uses existing tools (sqlite3, jq, awk, date)
- Reuses existing utilities (`_interspect_sql_escape`, `_interspect_db_path`)

---

## Shell-Specific Review

### 1. Date Command Portability ✓

**Lines 238-245** (`_interspect_apply_override_locked`):

```bash
expires_at=$(date -u -d "+${_INTERSPECT_CANARY_WINDOW_DAYS:-14} days" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
    || date -u -v+"${_INTERSPECT_CANARY_WINDOW_DAYS:-14}"d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)
if [[ -z "$expires_at" ]]; then
    echo "ERROR: date command does not support relative dates" >&2
    return 1
fi
```

**Good**: Fallback from GNU `-d` to BSD `-v` syntax with explicit error on unsupported systems.

**Suggestion**: Extract this pattern to a helper function (`_interspect_date_relative`) for reuse. Also used in other interspect code but not shown in this diff.

### 2. Variable Quoting ✓

All variable expansions properly quoted:

- Line 297, 302, 356 — `"${escaped_ts}"`, `"${project_filter}"`, `"${escaped_sid}"`
- Line 422, 424 — `"$canary_row"`, `"$current_status"`

### 3. SQL Subquery Reuse ⚠️

**Line 304** (`_interspect_compute_canary_baseline`):

```bash
local session_ids_sql="SELECT session_id FROM sessions WHERE start_ts < '${escaped_ts}' ${project_filter} ORDER BY start_ts DESC LIMIT ${window_size}"
```

This subquery is reused 3 times (lines 312, 322, 336) via `${session_ids_sql}` expansion in subsequent queries. This is **efficient** but **fragile** if any usage context requires modification (e.g., adding DISTINCT).

**Recommendation**: Document this pattern in a comment above the variable declaration:

```bash
# Reused subquery: sessions in the baseline window (last N sessions before timestamp)
local session_ids_sql="..."
```

### 4. Arithmetic Comparisons ✓

Consistent use of `(( ))` for integer tests:

- Line 298, 315, 329 — `(( session_count < min_baseline ))`, `(( total_sessions_in_window == 0 ))`
- Line 442 — `(( uses_so_far < window_uses ))`

### 5. String Length/Emptiness Checks ✓

Proper use of `[[ -z "$var" ]]` and `[[ -n "$var" ]]`:

- Line 288, 310, 369 — Checking for empty optional params and SQL results

### 6. Heredoc Delimiters ✓

Not applicable in this diff (no heredocs). Config JSON is read via jq.

### 7. `set -euo pipefail` Consideration

This code is sourced by hooks, not invoked as standalone scripts. The parent environment's `set -e` would abort on unchecked command failures. Every command that may fail is explicitly guarded with `|| true` or `2>/dev/null || status=$?` patterns.

**Good**: No risk of unhandled exit-on-error propagation.

---

## awk Usage (Floating-Point Math)

All awk usage is **correct** with attention to precision:

### Printf Formatting ✓

- Lines 323, 331, 337 — `printf \"%.4f\"` gives 4 decimal places for rates/densities
- Line 467-469 — Same precision in `_interspect_evaluate_canary` averages

### Division-by-Zero Handling ✓

- Lines 328-332 — Explicit `if (( total_overrides == 0 ))` check before awk division
- Line 377-383 — Same pattern for per-session fp_rate

### Comparison Idioms ✓

- Line 485 — `exit (${abs_diff} < ${noise_floor}) ? 0 : 1` — ternary used correctly with exit code
- Lines 494, 502 — Threshold comparisons via awk exit code pattern

### Edge Case: Baseline Zero ⚠️

**Line 496** (`_canary_check_metric`):

```bash
pct_change=$(awk "BEGIN {if (${baseline} > 0) printf \"%.0f\", (${current} - ${baseline}) / ${baseline} * 100; else print \"inf\"}")
```

**Good**: Handles `baseline == 0` with `"inf"` string. But the `"inf"` is stored in `reasons` string (line 497) and never re-parsed. This is **fine for display** but means the verdict reason may show `+inf%`.

**Suggestion**: Consider capping extreme percentages for readability:

```bash
else print \"+999\"  # "More than 999% increase" more actionable than "inf"
```

---

## jq Usage (JSON Output)

All jq invocations are **correct** with robust patterns:

### Null Coalescing ✓

- Lines 182-185 — `jq -r '.min_sessions // 3'` with fallback defaults
- Line 33 — `echo "$CANARY_SUMMARY" | jq 'length' 2>/dev/null || echo "0"` — fail-safe on parse error

### Variable Interpolation ✓

- Lines 340-346 — `jq -n --argjson` for numeric values, `--arg` for strings (correct type handling)
- Lines 542-554 — Same pattern for complex evaluation output

### JSON Array Construction

**Lines 573-589** (`_interspect_check_canaries`):

```bash
local results="["
local first=1
local canary_id
while IFS= read -r canary_id; do
    [[ -z "$canary_id" ]] && continue
    local result
    result=$(_interspect_evaluate_canary "$canary_id")
    if (( first )); then
        first=0
    else
        results+=","
    fi
    results+="$result"
done <<< "$ready_ids"
results+="]"
```

**Good**: Manual JSON array assembly with comma handling. This is **safe** because each `$result` is already valid JSON from `_interspect_evaluate_canary`.

**Suggestion**: Add a comment explaining why `jq -s` isn't used:

```bash
# Manual array assembly (not jq -s) to stream results and fail-fast on evaluation errors
```

### SQLite JSON Mode ✓

**Line 598** (`_interspect_get_canary_summary`):

```bash
result=$(sqlite3 -json "$db" "SELECT ... FROM canary c ..." 2>/dev/null) || true
```

**Good**: Uses `sqlite3 -json` (requires SQLite 3.33+, 2020). Fallback handled at line 609.

**Risk**: If SQLite version is too old, `-json` flag fails silently (captured by `|| true`) and result is empty string. The fallback at line 609 handles this:

```bash
[[ -z "$result" ]] && result="[]"
```

**Recommendation**: Add a runtime SQLite version check in `_interspect_ensure_db` to warn if < 3.33 (but this is out of scope for this diff).

---

## Test Coverage (bats)

**250 lines of tests** with **excellent breadth**:

### Schema Tests (lines 636-650)

- Table existence after migration
- UNIQUE constraint enforcement on `canary_samples(canary_id, session_id)`

### Baseline Computation (lines 654-704)

- Returns null with no sessions
- Returns null with insufficient sessions (< `min_baseline`)
- Returns metrics with sufficient data
- Correct override_rate calculation (10 overrides / 20 sessions = 0.5)

### Sample Collection (lines 708-750)

- Skips sessions with no evidence
- Inserts sample for active canary
- Skips non-active canaries
- Deduplication via INSERT OR IGNORE

### Evaluation Logic (lines 754-849)

- Returns "monitoring" for incomplete window
- Returns "monitoring" for NULL baseline
- Returns "passed" when metrics within threshold
- Returns "alert" when override_rate degrades >20%
- Returns "alert" when finding_density drops >20%
- Ignores differences below noise floor (0.1)
- Returns "expired_unused" when no samples collected

### Integration (lines 853-896)

- `check_canaries` returns empty when no canaries ready
- `check_canaries` evaluates completed window
- `get_canary_summary` returns empty/detailed output
- Confidence loading sets defaults and bounds-checks values

### Test Naming ✓

All test names are **descriptive** and follow the pattern:

```
<function>_<scenario>
```

Examples:

- `canary_samples unique constraint prevents duplicates`
- `evaluate_canary returns alert when override rate degrades >20%`
- `record_canary_sample skips sessions with no evidence`

### Missing Test Cases (Minor Gaps)

1. **Baseline window boundaries** (line 307-310) — No test verifies `window_start` calculation when `OFFSET` exceeds available sessions
2. **Multiple concurrent canaries** (line 536-540) — Only one test mentions `active_count` note in verdict, but no test validates the note text appears
3. **Time-based expiry** (lines 443-453) — Test at line 838 uses past `window_expires_at`, but no test for the `now < expires_at` branch (monitoring continues)
4. **Session-start alert injection** (hooks/interspect-session.sh:119-125) — No bats test validates `additionalContext` JSON output

**Recommendation**: Add 2-3 tests for these edge cases in a follow-up commit (non-blocking).

---

## SQL Quality

### Schema Design ✓

**Lines 137-166** (canary_samples table):

```sql
CREATE TABLE IF NOT EXISTS canary_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canary_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    override_rate REAL,
    fp_rate REAL,
    finding_density REAL,
    UNIQUE(canary_id, session_id)
);
CREATE INDEX IF NOT EXISTS idx_canary_samples_canary ON canary_samples(canary_id);
```

**Good**:

- UNIQUE constraint prevents duplicate samples (tested at line 642)
- Index on `canary_id` accelerates JOIN in `_interspect_get_canary_summary` (line 599-606)
- No foreign key constraint (SQLite requires `PRAGMA foreign_keys=ON` + enforcement overhead)

### INSERT OR IGNORE + changes() Pattern ✓

**Lines 399-403** (`_interspect_record_canary_sample`):

```sql
INSERT OR IGNORE INTO canary_samples (canary_id, session_id, ts, override_rate, fp_rate, finding_density)
    VALUES (${canary_id}, '${escaped_sid}', '${ts}', ${override_rate}, ${fp_rate}, ${finding_density});
UPDATE canary SET uses_so_far = uses_so_far + 1 WHERE id = ${canary_id} AND changes() > 0;
```

**Excellent**: The `changes() > 0` guard ensures `uses_so_far` increments **only if INSERT succeeded**. This prevents double-counting on deduplication (review P1 TOCTOU fix, per comment at line 398).

This pattern is **critical** and correctly implemented. The single `sqlite3` invocation ensures atomicity.

### Aggregation Performance

**Lines 598-607** (`_interspect_get_canary_summary`):

```sql
SELECT c.id, c.group_id as agent, ...,
       (SELECT COUNT(*) FROM canary_samples cs WHERE cs.canary_id = c.id) as sample_count,
       (SELECT printf('%.4f', AVG(cs.override_rate)) FROM canary_samples cs WHERE cs.canary_id = c.id) as avg_override_rate,
       ...
FROM canary c ORDER BY c.applied_at DESC;
```

**Pattern**: Correlated subqueries for aggregates.

**Performance**: Acceptable for small datasets (< 100 canaries). If `canary` table grows large, prefer LEFT JOIN with GROUP BY:

```sql
SELECT c.id, ..., COUNT(cs.id) as sample_count, AVG(cs.override_rate) as avg_override_rate
FROM canary c LEFT JOIN canary_samples cs ON cs.canary_id = c.id
GROUP BY c.id
ORDER BY c.applied_at DESC;
```

**Recommendation**: Monitor query time; optimize if `get_canary_summary` exceeds 500ms (out of scope for initial implementation).

---

## Documentation Quality

### Function Comments ✓

All major functions have clear docstrings:

- Line 270-273 — `_interspect_compute_canary_baseline` with args/output description
- Line 349-352 — `_interspect_record_canary_sample` with return codes
- Line 409-411 — `_interspect_evaluate_canary` with output format

### Inline Explanations ✓

- Line 219 — `# Canary record — compute baseline BEFORE insert`
- Line 283 — `# SQL-escape before_ts (review P0-1: prevent SQL injection)`
- Line 303 — `# Session IDs in the window (reused subquery)`
- Line 398 — `# Dedup: INSERT OR IGNORE + conditional increment in single transaction (review P1: TOCTOU fix)`

**Good**: Security rationale and concurrency notes documented inline.

### Status Display Template

**Lines 44-90** (commands/interspect-status.md):

Extensive template with conditional logic for rendering canary status. This is **human-readable pseudocode**, not executable bash.

**Issue**: The `{if status == "active" and uses_so_far > 0: ...}` syntax is **informal** and requires interpreter implementation in the command hook. No test validates the actual rendered output matches this spec.

**Recommendation**: Add an integration test that runs `/interspect:status` after creating a canary and asserts expected strings appear in output.

---

## Findings Summary

### Critical (None)

No blocking issues.

### High Priority (Non-Blocking)

1. **Missing integration test for status display** (commands/interspect-status.md:44-90) — Add test that validates rendered canary output format
2. **Baseline zero edge case** (lib-interspect.sh:496) — Cap extreme percentage changes at +/-999% for readability

### Medium Priority

3. **SQL performance monitoring** (lib-interspect.sh:598) — Add comment about correlated subquery performance, recommend monitoring
4. **Reused subquery documentation** (lib-interspect.sh:304) — Add comment explaining subquery reuse pattern
5. **Test coverage gaps** — Add tests for:
   - Baseline window boundary when offset exceeds sessions
   - Time-based expiry with ongoing monitoring
   - Session-start alert injection JSON output

### Low Priority

6. **Date command helper extraction** (lib-interspect.sh:238) — Extract relative date calculation to `_interspect_date_relative` for reuse
7. **SQLite version check** (lib-interspect.sh:598) — Warn if `sqlite3 -json` not supported (< v3.33)

---

## What NOT to Change

- **Manual JSON array assembly** (lines 573-589) is intentional for streaming results
- **Fail-open `|| true` patterns** are required for hook resilience
- **Correlated subqueries** in `get_canary_summary` are acceptable for current scale
- **No foreign key constraints** in SQLite schema (intentional performance/portability tradeoff)

---

## Language-Specific Idioms

### Shell Best Practices ✓

- ✓ Strict quoting on all variable expansions
- ✓ `[[ ]]` for string tests, `(( ))` for arithmetic
- ✓ `|| true` for fail-open hooks
- ✓ `$( )` for command substitution (not backticks)
- ✓ `local` variables in all functions

### awk Best Practices ✓

- ✓ `BEGIN` block for pure math (no input file processing)
- ✓ `printf` with explicit format strings for precision
- ✓ Exit code used for boolean logic

### SQL Best Practices ✓

- ✓ Parameterization via `_interspect_sql_escape`
- ✓ UNIQUE constraints for deduplication
- ✓ Indexes on foreign key columns
- ✓ `INSERT OR IGNORE` for idempotent operations

### jq Best Practices ✓

- ✓ `--argjson` for numeric values (preserves type)
- ✓ `--arg` for strings (auto-quoted)
- ✓ `-n` for constructing objects without input
- ✓ `-r` for raw string output (no quotes)

---

## Conclusion

This is **production-ready code** with excellent error handling, test coverage, and adherence to project conventions. The suggested improvements are **refinements**, not blockers. The canary monitoring implementation demonstrates strong shell scripting discipline and attention to edge cases.

**Recommended next steps**:

1. Merge as-is
2. Open follow-up ticket for the 5 medium-priority items (integration test, subquery docs, test gaps)
3. Monitor `get_canary_summary` performance in production; optimize if needed

**Confidence**: High. No correctness issues detected. Code quality exceeds typical shell script standards.
