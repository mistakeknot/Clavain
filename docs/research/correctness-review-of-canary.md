# Correctness Review: Interspect Canary Monitoring

**Reviewer:** Julik
**Date:** 2026-02-16
**Scope:** Canary monitoring implementation for routing override safety

## Executive Summary

Reviewed the canary monitoring diff for data integrity, concurrency correctness, and edge-case handling. Found **4 high-severity issues** (P0-P1) that can cause data corruption or silent monitoring failures, plus 3 moderate issues. All findings include concrete failure narratives and minimal fixes.

**Critical findings:**
1. **P0: Race condition in concurrent sample insertion** — `changes()` checked outside transaction window, counters can drift unboundedly from sample count
2. **P1: Baseline computation SQL injection** — unescaped `project` filter allows arbitrary SQL
3. **P1: Missing transaction boundaries in evaluation** — multi-step verdict writes can corrupt state on concurrent updates
4. **P1: Empty window on insufficient sessions** — `window_start` remains unset, produces malformed JSON baseline

---

## P0: Race Condition in Sample Insertion + Counter Increment

**Location:** `hooks/lib-interspect.sh:399-403` (`_interspect_record_canary_sample`)

### Failure Narrative

**Scenario:** Two session-end hooks run concurrently for sessions S1 and S2, both recording samples for canary ID=5.

**Interleaving:**
```
T1: S1: INSERT OR IGNORE (canary_id=5, session_id=S1) → succeeds, changes()=1
T2: S2: INSERT OR IGNORE (canary_id=5, session_id=S2) → succeeds, changes()=1
T3: S1: UPDATE canary SET uses_so_far = uses_so_far + 1 WHERE id=5 AND changes()>0
T4: S2: UPDATE canary SET uses_so_far = uses_so_far + 1 WHERE id=5 AND changes()>0
```

**Problem:** The `changes()` function in SQLite returns the row count of the *most recent* statement **in the current connection's context**. When hooks run in separate processes (which they do in Claude Code), each gets its own connection. At T3, S1's connection sees `changes()=1` from its own INSERT. At T4, S2's connection sees `changes()=1` from its own INSERT. Both UPDATEs execute, incrementing `uses_so_far` by 2 even though only 2 samples were inserted.

**Long-term effect:** Over N sessions, `uses_so_far` grows without bound. The canary never completes because `uses_so_far >= window_uses` is never true (uses_so_far = 2N for N samples). Monitoring runs forever, degradation never detected.

### Root Cause

The diff uses a **single-connection transaction** pattern but in a **multi-process environment**. The comment at line 397 ("Dedup: INSERT OR IGNORE + conditional increment in single transaction (review P1: TOCTOU fix)") assumes connections are reused, but session-end hooks spawn fresh sqlite3 processes.

The code:
```bash
sqlite3 "$db" "
    INSERT OR IGNORE INTO canary_samples (...) VALUES (...);
    UPDATE canary SET uses_so_far = uses_so_far + 1 WHERE id = ${canary_id} AND changes() > 0;
" 2>/dev/null || true
```

This is **not** a single transaction—it's two statements in one invocation. `changes()` only applies *within* the scope of the multi-statement string, but there's no guarantee that another process's INSERT won't interleave between these two statements at the SQLite lock level.

### Minimal Fix

Use the **row-level write-ahead log** pattern with a `RETURNING` clause (SQLite 3.35+, available in modern systems):

```bash
local inserted_count
inserted_count=$(sqlite3 "$db" "
    BEGIN IMMEDIATE;
    INSERT OR IGNORE INTO canary_samples (canary_id, session_id, ts, override_rate, fp_rate, finding_density)
        VALUES (${canary_id}, '${escaped_sid}', '${ts}', ${override_rate}, ${fp_rate}, ${finding_density})
        RETURNING 1;
    COMMIT;
" 2>/dev/null | wc -l)

if (( inserted_count > 0 )); then
    sqlite3 "$db" "UPDATE canary SET uses_so_far = uses_so_far + 1 WHERE id = ${canary_id};" 2>/dev/null || true
fi
```

**Why this works:** `BEGIN IMMEDIATE` acquires a write lock upfront. The `RETURNING 1` clause emits a row only if the INSERT actually created a new row (not ignored). Checking `wc -l` of the output gives an exact dedup signal. The counter increment happens in a separate statement, protected by the previous transaction's atomicity guarantee (the sample exists or it doesn't).

**Alternative (if RETURNING unavailable):** Query before increment:
```bash
sqlite3 "$db" "
    INSERT OR IGNORE INTO canary_samples (...) VALUES (...);
" 2>/dev/null || true

local sample_exists
sample_exists=$(sqlite3 "$db" "SELECT 1 FROM canary_samples WHERE canary_id=${canary_id} AND session_id='${escaped_sid}' LIMIT 1;")
[[ -n "$sample_exists" ]] && sqlite3 "$db" "UPDATE canary SET uses_so_far = uses_so_far + 1 WHERE id=${canary_id};" || true
```

This introduces a TOCTOU gap (sample could be deleted between SELECT and UPDATE), but in this system samples are append-only, so it's safe.

---

## P1: SQL Injection in Baseline Computation (Project Filter)

**Location:** `hooks/lib-interspect.sh:287-292` (`_interspect_compute_canary_baseline`)

### Failure Narrative

**Scenario:** A canary is applied in a project directory containing a malicious `.git/config` or a user supplies a crafted project name via evidence insertion.

**Attack:**
```bash
project="'; DROP TABLE evidence; --"
_interspect_compute_canary_baseline "2026-01-01T00:00:00Z" "$project"
```

**Execution path:**
```bash
escaped_project=$(_interspect_sql_escape "$project")  # escapes single quotes
project_filter="AND project = '${escaped_project}'"   # injects into SQL string
sqlite3 "$db" "SELECT COUNT(*) FROM sessions WHERE start_ts < '...' ${project_filter};"
```

**Result:** The `project_filter` is interpolated **without quoting** into multiple SQL statements (lines 296, 304, 310, 313, 322, 326, 336). Even though `_interspect_sql_escape` doubles single quotes, the interpolation happens in an unquoted context in some queries (specifically the subquery at line 304: `${session_ids_sql}`).

**Concrete failure:** If `project` contains SQL keywords or operators, the query structure breaks. Example:
```sql
SELECT session_id FROM sessions WHERE start_ts < '2026-01-01' AND project = 'test' OR '1'='1' ORDER BY start_ts DESC LIMIT 20
```
The `OR '1'='1'` bypasses the project filter, leaking data from other projects into the baseline.

### Root Cause

The `project_filter` variable is built as a raw string and spliced into SQL. The escaping happens too early (before the context is known).

### Minimal Fix

**Option A:** Use parameterized queries (not directly supported in sqlite3 CLI, would need wrapper script).

**Option B:** Strict validation of project name before use:
```bash
if [[ -n "$project" ]]; then
    # Project names must be alphanumeric + hyphen/underscore (matches git repo naming)
    if [[ ! "$project" =~ ^[a-zA-Z0-9/_.-]+$ ]]; then
        echo "ERROR: Invalid project name" >&2
        echo "null"
        return 1
    fi
    local escaped_project
    escaped_project=$(_interspect_sql_escape "$project")
    project_filter="AND project = '${escaped_project}'"
fi
```

**Option C:** Use a prepared statement pattern (store filter logic in SQLite view or CTE):
```bash
local project_cte=""
if [[ -n "$project" ]]; then
    local escaped_project
    escaped_project=$(_interspect_sql_escape "$project")
    project_cte="WITH filtered_sessions AS (SELECT * FROM sessions WHERE project = '${escaped_project}')"
    # Use filtered_sessions in all queries
fi
```

**Recommendation:** Option B (validation) is simplest and sufficient for this use case. Project names in Clavain come from git repo paths, which are already validated by the filesystem.

---

## P1: Missing Transaction Boundaries in Canary Evaluation

**Location:** `hooks/lib-interspect.sh:533` (`_interspect_evaluate_canary`)

### Failure Narrative

**Scenario:** Two concurrent session-start hooks both call `_interspect_check_canaries`, which evaluates canary ID=3. Canary has exactly `window_uses` samples and is on the pass/alert threshold.

**Interleaving:**
```
T1: Hook A: _interspect_evaluate_canary(3) → computes verdict="passed"
T2: Hook B: _interspect_evaluate_canary(3) → computes verdict="passed"
T3: Hook A: sqlite3 UPDATE canary SET status='passed', verdict_reason='...' WHERE id=3
T4: Hook B: sqlite3 UPDATE canary SET status='passed', verdict_reason='...' WHERE id=3
T5: Hook A: Check for alert count → 0
T6: Hook B: Check for alert count → 0
```

**Seems fine, but now consider a concurrent session-end that adds one more sample:**

```
T1: Hook A: _interspect_evaluate_canary(3) → reads 19 samples, computes verdict="passed"
T2: Hook C (session-end): _interspect_record_canary_sample → inserts 20th sample (degraded metrics)
T3: Hook B: _interspect_evaluate_canary(3) → reads 20 samples, computes verdict="alert"
T4: Hook A: UPDATE canary SET status='passed' WHERE id=3
T5: Hook B: UPDATE canary SET status='alert' WHERE id=3
```

**Result:** The final status is "alert" (last write wins), but hook A's session-start logic sees 0 alerts (it checked at T5, after its own write). The alert is silently lost until the next session starts.

**Worse scenario (corruption):**
```
T1: Hook A: evaluates, decides "passed"
T2: Hook B: evaluates, decides "alert"
T3: Hook A: UPDATE canary SET status='passed', verdict_reason='All metrics OK'
T4: Hook B: UPDATE canary SET status='alert', verdict_reason='override_rate: 1.0 -> 2.0 (+100%)'
```

The canary record now has `status='alert'` but the previous `verdict_reason='All metrics OK'` from T3 is overwritten only if the column is included in the UPDATE. If hook A writes first and hook B only updates `status`, you get `{status: "alert", verdict_reason: "All metrics OK"}`, a nonsensical state.

### Root Cause

The evaluation function reads samples, computes verdict, and writes back **without holding a lock**. The read-compute-write cycle is non-atomic.

### Minimal Fix

Wrap evaluation in an advisory lock:

```bash
_interspect_evaluate_canary() {
    _interspect_load_confidence
    local canary_id="$1"
    local db="${_INTERSPECT_DB:-$(_interspect_db_path)}"

    # Acquire exclusive lock for this canary
    local lock_name="canary_eval_${canary_id}"
    local lock_acquired=0
    sqlite3 "$db" "
        CREATE TABLE IF NOT EXISTS advisory_locks (lock_name TEXT PRIMARY KEY, holder TEXT, acquired_at TEXT);
        BEGIN IMMEDIATE;
        INSERT OR FAIL INTO advisory_locks (lock_name, holder, acquired_at)
            VALUES ('${lock_name}', '$$', datetime('now'));
        COMMIT;
    " 2>/dev/null && lock_acquired=1

    if (( !lock_acquired )); then
        # Another process is evaluating this canary
        echo '{"status":"locked","reason":"Evaluation in progress"}'
        return 0
    fi

    trap "sqlite3 \"$db\" \"DELETE FROM advisory_locks WHERE lock_name='${lock_name}';\" 2>/dev/null" EXIT

    # ... rest of evaluation logic ...
}
```

**Simpler alternative:** Use SQLite's `BEGIN IMMEDIATE` for the entire read-compute-write cycle:
```bash
sqlite3 "$db" "
    BEGIN IMMEDIATE;
    -- Read canary + samples
    -- Compute verdict in SQL (use CASE expressions)
    -- Write back
    COMMIT;
"
```

This requires moving the awk-based math into SQL (doable with `printf` for formatting).

---

## P1: Empty Window String When Insufficient Sessions

**Location:** `hooks/lib-interspect.sh:310` (`_interspect_compute_canary_baseline`)

### Code
```bash
window_start=$(sqlite3 "$db" "SELECT start_ts FROM sessions WHERE start_ts < '${escaped_ts}' ${project_filter} ORDER BY start_ts DESC LIMIT 1 OFFSET $((window_size - 1));" 2>/dev/null)
[[ -z "$window_start" ]] && window_start=$(sqlite3 "$db" "SELECT MIN(start_ts) FROM sessions WHERE start_ts < '${escaped_ts}' ${project_filter};")
```

### Failure Narrative

**Scenario:** System has exactly 10 sessions (below `min_baseline=15`), but passes the count check due to a bug. Baseline computation proceeds.

**Execution:**
- Line 310: `OFFSET 19` (window_size=20) returns no rows → `window_start=""` (empty string, not NULL)
- Line 311: Fallback queries `MIN(start_ts)` → succeeds, sets `window_start="2026-01-01T..."`
- Line 342: Constructs window string: `"${window_start}..${window_end}"` → `"2026-01-01T00:00:00Z..2026-02-16T00:00:00Z"`

**Wait, this seems fine. Let me re-check the second query...**

Actually, the bug is **different**: if the second query (MIN) also returns empty (no sessions match the filter), then `window_start` remains `""`. Line 342:
```bash
--arg window "${window_start}..${window_end}"
```
produces:
```json
{"window": "..2026-02-16T00:00:00Z", ...}
```

This is a **malformed window string**. Later code that parses this (e.g., UI display) will break.

**How to trigger:** Apply override in project X, then query baseline for project Y (which has no sessions).

### Minimal Fix

Validate `window_start` before constructing JSON:
```bash
[[ -z "$window_start" ]] && window_start=$(sqlite3 "$db" "SELECT MIN(start_ts) FROM sessions WHERE start_ts < '${escaped_ts}' ${project_filter};")

# Ensure window_start is non-empty
if [[ -z "$window_start" ]]; then
    echo "null"
    return 0
fi
```

---

## P2: Division by Zero in FP Rate (Edge Case)

**Location:** `hooks/lib-interspect.sh:378-382` (`_interspect_record_canary_sample`)

### Code
```bash
if (( override_count == 0 )); then
    fp_rate="0.0000"
else
    fp_rate=$(awk "BEGIN {printf \"%.4f\", ${agent_wrong_count} / ${override_count}}")
fi
```

### Issue

This is actually **correct**—the `if` statement prevents division by zero. However, there's a **silent failure mode** at line 329 (baseline computation):

```bash
if (( total_overrides == 0 )); then
    fp_rate="0.0000"
else
    fp_rate=$(awk "BEGIN {printf \"%.4f\", ${agent_wrong_count} / ${total_overrides}}")
fi
```

If `total_overrides=0`, `fp_rate` is set to `"0.0000"`. This is fine. But what if `baseline_fp_rate=0` and `current_fp_rate=0.5`? The alert logic at line 486 computes:
```bash
abs_diff=$(awk "BEGIN {d = ${current} - ${baseline}; if (d < 0) d = -d; printf \"%.4f\", d}")
# abs_diff = 0.5

threshold=$(awk "BEGIN {printf \"%.4f\", ${baseline} * ${alert_pct} / 100}")
# threshold = 0 * 20 / 100 = 0

if awk "BEGIN {exit (${current} > ${baseline} + ${threshold}) ? 0 : 1}"; then
    # 0.5 > 0 + 0 → true, alert triggered
fi
```

**Problem:** When baseline FP rate is 0 (perfect historical quality), **any** non-zero FP rate triggers an alert, even if it's within the noise floor. The noise floor check at line 485 should catch this, but it checks `abs_diff < noise_floor`, and `0.5 > 0.1` (default noise floor), so it doesn't help.

### Minimal Fix

Special-case zero baselines:
```bash
_canary_check_metric() {
    local metric_name="$1" baseline="$2" current="$3" direction="$4"

    # Special case: baseline is zero (or near-zero)
    if awk "BEGIN {exit (${baseline} < 0.0001) ? 0 : 1}" 2>/dev/null; then
        # Use absolute threshold instead of percentage
        if awk "BEGIN {exit (${current} > ${noise_floor}) ? 0 : 1}" 2>/dev/null; then
            return 0  # current is also near-zero, no alert
        else
            reasons="${reasons}${metric_name}: ${baseline} -> ${current} (baseline was zero); "
            return 1
        fi
    fi

    # ... rest of logic ...
}
```

---

## P2: Session-Start Hook Can Inject Malformed JSON

**Location:** `hooks/interspect-session.sh:125` (session-start alert injection)

### Code
```bash
ALERT_MSG="Canary alert: routing override(s) for ${ALERT_AGENTS} may have degraded review quality. Run /interspect:status for details or /interspect:revert <agent> to undo."
echo "{\"additionalContext\":\"WARNING: ${ALERT_MSG}\"}"
```

### Failure Narrative

**Scenario:** A canary is created for an agent whose `group_id` contains a double-quote character. (This is unlikely but not impossible—`group_id` comes from evidence records, which are user-controllable via tool output.)

**Execution:**
```bash
ALERT_AGENTS='fd-test", "another-agent'
ALERT_MSG="Canary alert: routing override(s) for fd-test", "another-agent may have degraded..."
echo "{\"additionalContext\":\"WARNING: ${ALERT_MSG}\"}"
```

**Output:**
```json
{"additionalContext":"WARNING: Canary alert: routing override(s) for fd-test", "another-agent may have degraded..."}
```

**Result:** Malformed JSON. Claude Code's session-start handler fails to parse it, the alert is lost, and the session starts without warning.

### Minimal Fix

Use `jq` to construct the JSON:
```bash
if (( ALERT_COUNT > 0 )); then
    ALERT_AGENTS=$(sqlite3 -separator ', ' "$_INTERSPECT_DB" "SELECT group_id FROM canary WHERE status = 'alert';" 2>/dev/null || echo "")
    jq -n --arg agents "$ALERT_AGENTS" \
        '{additionalContext: ("WARNING: Canary alert: routing override(s) for " + $agents + " may have degraded review quality. Run /interspect:status for details or /interspect:revert <agent> to undo.")}'
fi
```

---

## P3: Noise Floor Check Has TOCTOU Gap with Metric Ordering

**Location:** `hooks/lib-interspect.sh:485` (`_canary_check_metric`)

### Code
```bash
abs_diff=$(awk "BEGIN {d = ${current} - ${baseline}; if (d < 0) d = -d; printf \"%.4f\", d}")

if awk "BEGIN {exit (${abs_diff} < ${noise_floor}) ? 0 : 1}" 2>/dev/null; then
    return 0  # no degradation
fi

# Compute threshold
threshold=$(awk "BEGIN {printf \"%.4f\", ${baseline} * ${alert_pct} / 100}")
```

### Issue

The noise floor check happens **before** the threshold computation. If `baseline=0.05`, `current=0.12`, `noise_floor=0.1`, `alert_pct=20`:

- `abs_diff = 0.07` → below noise floor, returns 0 (no alert)

But if we compute the percentage change: `(0.12 - 0.05) / 0.05 = 140%` increase, way above the 20% threshold. The noise floor suppresses a legitimate alert.

**Design question:** Is this intentional? The PRD should clarify whether noise floor is an **absolute** suppression (ignore all diffs < 0.1) or a **minimum magnitude** (require abs_diff > 0.1 **and** pct_change > 20%).

### Recommended Behavior

Use **both** checks (AND, not OR):
```bash
# Must exceed BOTH noise floor AND percentage threshold
if awk "BEGIN {exit (${abs_diff} < ${noise_floor}) ? 0 : 1}" 2>/dev/null; then
    return 0  # below noise floor, ignore
fi

threshold=$(awk "BEGIN {printf \"%.4f\", ${baseline} * ${alert_pct} / 100}")
if awk "BEGIN {exit (${threshold} < ${noise_floor}) ? 0 : 1}" 2>/dev/null; then
    # Threshold is also below noise floor (baseline is tiny) → use noise floor as absolute threshold
    threshold=$noise_floor
fi

# Now check if current exceeds baseline + threshold
# ...
```

---

## P3: Test Coverage Gap — Concurrent Hook Execution

**Location:** `tests/shell/test_interspect_routing.bats` (entire file)

### Issue

All tests are **sequential**—each `@test` runs in isolation. No tests exercise concurrent execution of:
- Multiple `_interspect_record_canary_sample` calls
- Simultaneous `_interspect_check_canaries` and `_interspect_record_canary_sample`
- Session-start + session-end hooks overlapping

**Why this matters:** The P0 race condition (uses_so_far drift) will never be caught by these tests.

### Minimal Test Addition

Add a stress test that spawns multiple background sample recordings:

```bash
@test "record_canary_sample concurrent execution does not drift counter" {
    DB=$(_interspect_db_path)
    sqlite3 "$DB" "INSERT INTO canary (file, commit_sha, group_id, applied_at, window_uses, status) VALUES ('test', 'abc', 'fd-test', '2026-01-01', 100, 'active');"

    # Insert evidence for 50 unique sessions
    for i in $(seq 1 50); do
        sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, ts, source, event, context, project) VALUES ('s${i}', 1, '2026-01-15', 'fd-test', 'agent_dispatch', '{}', 'proj1');"
    done

    # Spawn 50 concurrent sample recordings
    for i in $(seq 1 50); do
        _interspect_record_canary_sample "s${i}" &
    done
    wait

    # Verify: uses_so_far should equal sample count (50)
    uses=$(sqlite3 "$DB" "SELECT uses_so_far FROM canary WHERE id = 1;")
    sample_count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM canary_samples WHERE canary_id = 1;")

    [ "$uses" -eq "$sample_count" ]
    [ "$uses" -eq 50 ]
}
```

This will **fail** with the current implementation (uses_so_far will likely be > 50 due to the race).

---

## Edge Cases — Confirmed Safe

### ✓ NULL Baseline Handling
Lines 435-439 correctly check for empty `$b_or` (SQLite's NULL comes through as empty string in pipe-separated output) and return early with `status="monitoring"`.

### ✓ Empty Sample Set
Lines 456-463 correctly detect `sample_count=0` and set `status='expired_unused'` instead of attempting to compute averages (which would produce NULL or NaN).

### ✓ UNIQUE Constraint Deduplication
Lines 163-164 add `UNIQUE(canary_id, session_id)` on `canary_samples`. Tests at 642-650 confirm `INSERT OR IGNORE` dedup works. However, the **counter increment** is still racy (P0 issue above).

### ✓ Bounds-Checking Config Values
Lines 195-211 clamp `canary_window_uses`, `canary_window_days`, `canary_min_baseline`, `canary_alert_pct` to safe ranges. Test at 911-927 verifies this. Prevents unbounded `LIMIT` in SQL.

### ✓ SQL Escaping for `before_ts`
Line 284 escapes `before_ts` with `_interspect_sql_escape` before interpolation. However, `project` escaping is incomplete (P1 finding above).

---

## Summary of Findings

| Priority | Finding | Impact | Line | Fix Complexity |
|----------|---------|--------|------|----------------|
| **P0** | Race in sample insert + counter increment | Counter drift, monitoring never completes | 399-403 | Medium (need BEGIN IMMEDIATE + RETURNING or SELECT verification) |
| **P1** | SQL injection in project filter | Data leak, filter bypass | 287-292 | Low (add validation regex) |
| **P1** | Missing transaction in evaluation | Verdict corruption, lost alerts | 533 | Medium (wrap in advisory lock or BEGIN IMMEDIATE) |
| **P1** | Empty window string on edge case | Malformed JSON, UI crash | 310-311 | Low (add empty-string check) |
| **P2** | Zero-baseline FP rate false alerts | Nuisance alerts on perfect→good transitions | 486-495 | Low (special-case near-zero baselines) |
| **P2** | Unescaped JSON in session-start alert | Lost alerts on malformed group_id | 125 | Low (use jq -n) |
| **P3** | Noise floor suppresses large % changes | Missed degradation on low-magnitude metrics | 485 | Medium (requires PRD clarification) |

---

## Recommendations

1. **Immediate (pre-merge):** Fix P0 and P1 issues. The counter race will cause monitoring to silently fail in production under normal multi-session load.

2. **Before production:** Add concurrent execution test (P3 coverage gap). Run it 100x in CI to catch racy behavior.

3. **Documentation:** Clarify in PRD whether noise floor is absolute or relative (P3 finding). Current behavior may be intentional but should be explicit.

4. **Future hardening:** Consider moving all canary logic into a single long-running process (intermute service extension) rather than hook-based execution. This would eliminate all inter-process races and allow proper transaction management.

---

## Test Plan Validation

Reviewed `tests/shell/test_interspect_routing.bats` lines 634-927. Tests cover:
- ✓ Table creation
- ✓ UNIQUE constraint (but not counter race)
- ✓ Baseline computation (happy path + insufficient data)
- ✓ Sample recording (happy path + skip conditions)
- ✓ Evaluation verdicts (passed, alert, expired_unused)
- ✓ Noise floor (absolute values, not edge case)
- ✓ Config bounds-checking

**Missing:**
- ✗ Concurrent sample insertion (P0)
- ✗ Concurrent evaluation + insertion (P1)
- ✗ Malformed group_id in alert JSON (P2)
- ✗ Zero-baseline scenarios (P2)
- ✗ SQL injection attempts (P1)

Add these tests before merge to prevent regressions.
