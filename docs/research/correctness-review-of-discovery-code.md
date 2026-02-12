# Correctness Review: Discovery Code (lib-discovery.sh, lfg.md, discovery.bats)

**Reviewer:** Julik (fd-correctness)
**Date:** 2026-02-12
**Scope:** Data integrity, race conditions, edge cases, JSON parsing safety, grep reliability

---

## Executive Summary

**P0 Findings:** 1 (race condition causing incorrect recommendations)
**P1 Findings:** 3 (sorting bug, grep portability, stat error propagation)
**P2 Findings:** 4 (edge cases, error messages, test coverage gaps)

The discovery scanner has **one critical race condition** that can surface stale or incorrect work recommendations when bead state changes between scan and presentation. The sorting logic has a **determinism bug** that can reorder same-priority items unpredictably. Grep and stat error handling needs hardening against platform differences.

---

## P0: Critical Correctness Issues

### P0-1: TOCTOU Race — Scanner Output Stale Before Presentation

**Location:** `commands/lfg.md` lines 11-43 (discovery preamble)

**Failure Narrative:**

1. Discovery scanner runs at line 13: `discovery_scan_beads` queries bd and infers actions
2. Scanner finds bead `Project-abc1` with status `open`, plan exists, recommends action `execute`
3. **Before AskUserQuestion completes**, user (in parallel session) or automated process changes bead state:
   - Option A: Closes the bead via `bd close Project-abc1`
   - Option B: Deletes the plan file
   - Option C: Updates bead to `in_progress` and starts work
4. User selects "Execute plan for Project-abc1" from the stale options
5. Command routes to `/clavain:work <plan_path>` (line 30)
6. Outcomes:
   - **If bead closed:** Work proceeds on a bead marked done, creating duplicate effort or confusion
   - **If plan deleted:** `/work` fails with file-not-found, user gets cryptic error
   - **If bead now in_progress elsewhere:** Two sessions working on same bead concurrently, potential merge conflicts or wasted work

**Impact:** Medium-high frequency in active multi-session environments. Consequences range from wasted effort (duplicate work) to confusion (missing files) to silent data issues (two sessions modifying same code paths).

**Root Cause:** Check-then-act pattern with no validation barrier. Scanner runs, time passes (user reads menu, thinks), action executes against potentially stale state.

**Fix Strategy:**

Add a pre-flight validation step in `lfg.md` after user selection (line 29, before routing):

```bash
# After parsing user's selection, before routing:
# Validate bead still exists and is in expected state
if [[ "$selected_action" =~ ^(continue|execute|plan|strategize)$ ]]; then
    bead_current_status=$(bd get "$selected_bead_id" --json 2>/dev/null | jq -r '.status // empty')
    if [[ -z "$bead_current_status" ]]; then
        echo "Error: Bead $selected_bead_id no longer exists. State changed since scan."
        exit 1
    fi
    if [[ "$selected_action" == "continue" && "$bead_current_status" != "in_progress" ]]; then
        echo "Warning: Bead $selected_bead_id is no longer in_progress (now: $bead_current_status). Proceed anyway? (y/n)"
        # Handle user response
    fi
    if [[ -n "$plan_path" && ! -f "$plan_path" ]]; then
        echo "Error: Plan file $plan_path no longer exists. State changed since scan."
        exit 1
    fi
fi
```

**Alternative (lighter-weight):** Document the race as expected behavior and make commands idempotent. `/work`, `/write-plan`, etc. should validate bead state at start and fail gracefully with clear messages if state is unexpected. This pushes validation down to the command layer but accepts the UX friction of a failed command invocation.

**Test Coverage Gap:** `discovery.bats` does not test concurrent state changes. Need a test that:
1. Mocks `discovery_scan_beads` to return valid output
2. Deletes a plan file or changes bead status between scan and routing
3. Verifies `/lfg` detects the staleness and fails gracefully

---

## P1: High-Priority Correctness Issues

### P1-1: Sorting Non-Determinism — Same-Priority Beads Can Shuffle

**Location:** `lib-discovery.sh` line 126

**Code:**
```bash
sorted=$(echo "$merged" | jq 'sort_by(.priority, .updated_at) | reverse | sort_by(.priority)')
```

**Bug:** The sort is two-pass: (1) sort by priority + updated_at ascending, (2) reverse, (3) sort by priority ascending again. The second `sort_by(.priority)` is a **stable sort** in jq, so it preserves the relative order of items with the same priority from the reversed list. However, when two beads have the **same priority AND same updated_at timestamp** (possible if bd rounds timestamps or two beads are updated in the same second), the final order is undefined.

**Failure Scenario:**

1. Beads `Project-x` and `Project-y` both have `priority: 2`, `updated_at: "2026-02-12T10:00:00Z"`
2. First sort: both end up adjacent, order depends on JSON array order from bd
3. Reverse: order flips
4. Second `sort_by(.priority)`: both still priority 2, stable sort preserves reversed order
5. **But:** If bd returns them in different order across calls (e.g., due to internal hash map iteration), the final ranking changes between runs

**Impact:** Low frequency (requires timestamp collision), but high confusion when it happens. User sees work backlog reorder between invocations with no visible state change.

**Root Cause:** The two-pass sort is trying to achieve "priority ASC, updated_at DESC" but doing it in a fragile way. The second `sort_by(.priority)` is meant to undo the reversal for priority ordering, but it assumes no ties.

**Fix:**

Replace the two-pass sort with a single explicit multi-key sort:

```bash
sorted=$(echo "$merged" | jq 'sort_by(.priority, -.updated_at)')
```

Wait — jq `sort_by` does **not** support negation syntax for descending order on individual keys. The correct approach is:

```bash
sorted=$(echo "$merged" | jq 'sort_by(.priority, .updated_at) | reverse | group_by(.priority) | map(sort_by(.updated_at) | reverse) | flatten')
```

Or simpler (single-pass with explicit tie-breaking):

```bash
sorted=$(echo "$merged" | jq '[.[] | {priority, updated_at, id, title, status}] | sort_by(.priority, .updated_at) | reverse | unique_by(.priority) as $prios | [.[] | . as $item | {item: $item, prio_rank: ($prios | map(.priority) | index($item.priority))}] | sort_by(.prio_rank, -.item.updated_at) | map(.item)')
```

Actually, the cleanest fix is to use a custom sort expression that handles both keys correctly:

```bash
sorted=$(echo "$merged" | jq 'sort_by([.priority, .updated_at]) | group_by(.priority) | map(reverse) | flatten')
```

This groups by priority, reverses each group (most recent first within each priority), then flattens back to a single array.

**Test Coverage:** `discovery.bats` line 140-158 tests sorting but does NOT test tie-breaking behavior when `priority` and `updated_at` are identical. Add a test:

```bats
@test "discovery: sorts deterministically when priority and timestamp match" {
    mock_bd '[
        {"id":"Test-a","title":"First","status":"open","priority":2,"updated_at":"2026-02-12T10:00:00Z"},
        {"id":"Test-b","title":"Second","status":"open","priority":2,"updated_at":"2026-02-12T10:00:00Z"}
    ]'
    run discovery_scan_beads
    local first_run_order=$(echo "$output" | jq -r '[.[].id] | join(",")')

    # Run again — order should be stable
    run discovery_scan_beads
    local second_run_order=$(echo "$output" | jq -r '[.[].id] | join(",")')

    [[ "$first_run_order" == "$second_run_order" ]]
}
```

---

### P1-2: Grep Portability — EOL Boundary Matching Fails on Perl-Incapable Systems

**Location:** `lib-discovery.sh` lines 33-39 (grep fallback logic)

**Code:**
```bash
if grep -P "" /dev/null 2>/dev/null; then
    grep_flags="-rlP"
    pattern="Bead.*${bead_id}\b"
else
    pattern="Bead.*${bead_id}[^a-zA-Z0-9_-]"
fi
```

**Bug:** The portable fallback pattern `Bead.*${bead_id}[^a-zA-Z0-9_-]` does **not** match when the bead ID is at end-of-line. Example:

```markdown
**Bead:** Project-abc1
```

The pattern requires a character after `Project-abc1` to match. If the line ends after the ID, grep will not find it.

**Partial Mitigation:** Lines 43-45, 49-51, 55-57 add a second fallback grep with `Bead.*${bead_id}$` (EOL anchor). This catches the EOL case but **doubles the grep calls** on portable systems (two greps per directory, six total greps per bead).

**Impact:** Performance degradation on Alpine, BusyBox, macOS without gnu-grep. Six greps instead of three per bead. For a backlog of 20 beads, that's 120 greps instead of 60. On slow filesystems or large `docs/` directories, this adds seconds of latency.

**Root Cause:** Character class `[^a-zA-Z0-9_-]` cannot express "end of line" without alternation, which basic grep doesn't support in a single pattern.

**Fix:**

Use extended regex (`-E`) with alternation, which is more portable than Perl regex:

```bash
if grep -P "" /dev/null 2>/dev/null; then
    grep_flags="-rlP"
    pattern="Bead.*${bead_id}\b"
elif grep -E "" /dev/null 2>/dev/null; then
    grep_flags="-rlE"
    pattern="Bead.*${bead_id}([^a-zA-Z0-9_-]|$)"
else
    # Ultimate fallback: basic regex with two patterns combined via shell OR
    grep_flags="-rl"
    pattern="Bead.*${bead_id}"
    # Caller will need to post-filter with word boundary check
fi
```

If `-E` is available (POSIX-compliant, available on all modern systems including BusyBox), the alternation `([^a-zA-Z0-9_-]|$)` handles both cases in one grep. The ultimate fallback (basic grep) would match over-broadly and require post-filtering, but that's rare (systems without `-E` are very old).

**Test Coverage:** `discovery.bats` lines 220-229 test exact matching vs. substring false positives but do NOT test EOL boundary case explicitly. Add:

```bats
@test "infer_bead_action: matches bead ID at end of line" {
    mkdir -p "$TEST_PROJECT/docs/plans"
    echo "**Bead:** Test-eol1" > "$TEST_PROJECT/docs/plans/eol-plan.md"

    run infer_bead_action "Test-eol1" "open"
    assert_success
    [[ "$output" == "execute|"* ]]
}
```

---

### P1-3: Stat Error Propagation — Silent Staleness Failures

**Location:** `lib-discovery.sh` lines 162-163

**Code:**
```bash
plan_mtime=$(stat -c %Y "$plan_path" 2>/dev/null || stat -f %m "$plan_path" 2>/dev/null || echo 0)
[[ "$plan_mtime" -lt "$two_days_ago" ]] && stale=true
```

**Bug:** If both `stat` commands fail (e.g., plan file deleted between infer_bead_action and staleness check, or unsupported stat variant), `plan_mtime` is set to `0`. The comparison `[[ 0 -lt "$two_days_ago" ]]` is **always true** (epoch zero is before any real timestamp), so the bead is marked stale even though the file is missing.

**Failure Scenario:**

1. Bead has a plan file at scan time (line 154: `infer_bead_action` finds it)
2. Between line 154 and line 162, plan file is deleted (race) OR filesystem permissions change OR `stat` binary is missing
3. Both `stat` calls fail, `plan_mtime=0`
4. Bead is marked `stale=true` even though it should error (file missing)
5. User selects "Continue Test-xyz (stale)" from menu
6. `/work` is invoked with a missing plan file, fails with file-not-found
7. User gets confusing error: "file not found" when they expected "stale work, maybe refresh?"

**Impact:** Low-medium frequency. Requires file deletion race or stat unavailability. Consequences are UX confusion (stale flag is misleading) and potential wasted user action (selecting a bead that will immediately fail).

**Root Cause:** `|| echo 0` fallback conflates "stat failed" with "file is very old". Zero is a valid epoch timestamp (1970-01-01) but is used as a sentinel for "unknown".

**Fix:**

Distinguish between "stat failed" and "file is old":

```bash
if [[ -n "$plan_path" && -f "$plan_path" ]]; then
    local plan_mtime
    plan_mtime=$(stat -c %Y "$plan_path" 2>/dev/null || stat -f %m "$plan_path" 2>/dev/null)
    if [[ -n "$plan_mtime" && "$plan_mtime" != "0" ]]; then
        [[ "$plan_mtime" -lt "$two_days_ago" ]] && stale=true
    else
        # stat failed or returned zero — treat as not stale (can't determine)
        stale=false
    fi
fi
```

Or more conservatively, mark as stale only if stat succeeds and mtime is old:

```bash
if [[ -n "$plan_path" && -f "$plan_path" ]]; then
    local plan_mtime
    if plan_mtime=$(stat -c %Y "$plan_path" 2>/dev/null) || plan_mtime=$(stat -f %m "$plan_path" 2>/dev/null); then
        [[ "$plan_mtime" -lt "$two_days_ago" ]] && stale=true
    fi
    # If stat fails, stale remains false (default) — we can't determine age
fi
```

**Alternative:** Log a warning when stat fails and treat the bead as not stale (conservative). This way staleness is only marked when we have high confidence, not on ambiguous failures.

**Test Coverage:** `discovery.bats` lines 276-299 test staleness but assume `stat` always succeeds. Add a test where the plan file exists during `infer_bead_action` but is deleted before staleness check:

```bats
@test "discovery: does not mark stale when stat fails" {
    mkdir -p "$TEST_PROJECT/docs/plans"
    echo "**Bead:** Test-missing1" > "$TEST_PROJECT/docs/plans/temp-plan.md"
    mock_bd '[{"id":"Test-missing1","title":"Flaky file","status":"open","priority":2,"updated_at":"2026-02-12T10:00:00Z"}]'

    # Mock stat to fail
    stat() { return 1; }
    export -f stat

    run discovery_scan_beads
    assert_success
    [[ $(echo "$output" | jq '.[0].stale') == "false" ]]
}
```

---

## P2: Medium-Priority Issues

### P2-1: Date Parsing Portability — ISO 8601 with `date -d`

**Location:** `lib-discovery.sh` line 166

**Code:**
```bash
updated_epoch=$(date -d "$updated" +%s 2>/dev/null || echo 0)
```

**Issue:** `date -d` (GNU coreutils) is not available on macOS/BSD. The fallback `|| echo 0` makes all beads without plan files appear stale on macOS (same `echo 0` issue as P1-3).

**Current Mitigation:** Line 131 already has a dual-branch for `two_days_ago` calculation (`date -d` vs. `date -v`), but line 166 only uses `date -d`. This is inconsistent.

**Fix:** Add BSD fallback for ISO 8601 parsing:

```bash
updated_epoch=$(date -d "$updated" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%SZ" "$updated" +%s 2>/dev/null || echo 0)
```

Or extract to a helper function:

```bash
iso8601_to_epoch() {
    local iso="$1"
    date -d "$iso" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%SZ" "$iso" +%s 2>/dev/null || echo 0
}
```

**Test Coverage:** Tests run on Linux with GNU coreutils. Need CI matrix with macOS to catch BSD date issues, or mock `date` to simulate BSD behavior.

---

### P2-2: JQ Error Handling — Silent Failures in jq Pipeline

**Location:** `lib-discovery.sh` lines 171-179 (jq append to results array)

**Code:**
```bash
results=$(echo "$results" | jq \
    --arg id "$id" \
    --arg title "$title" \
    --argjson priority "${priority:-4}" \
    --arg status "$status" \
    --arg action "$action" \
    --arg plan_path "$plan_path" \
    --argjson stale "$stale" \
    '. + [{id: $id, title: $title, priority: $priority, status: $status, action: $action, plan_path: $plan_path, stale: $stale}]')
```

**Issue:** If any jq invocation in the loop fails (e.g., due to malformed JSON in `$results` from a previous iteration, or jq version incompatibility), the failure is silent. `$results` becomes empty or invalid, but the loop continues. The final output will be missing beads or will be `"DISCOVERY_ERROR"` only if the merge/sort steps fail (lines 114, 126).

**Scenario:**

1. Loop processes bead 1 successfully, `results='[{...}]'`
2. Loop processes bead 2, `priority` is non-numeric garbage (bd bug), `--argjson priority` fails
3. `results` becomes empty string (jq error output is to stderr, not captured)
4. Loop continues, all subsequent beads are appended to empty string
5. Final output is malformed or empty array

**Impact:** Low (requires bd to return malformed data, which is caught earlier by lines 104-110), but defense-in-depth is weak here.

**Fix:**

Check jq exit status in the loop:

```bash
local new_results
new_results=$(echo "$results" | jq \
    --arg id "$id" \
    --arg title "$title" \
    --argjson priority "${priority:-4}" \
    --arg status "$status" \
    --arg action "$action" \
    --arg plan_path "$plan_path" \
    --argjson stale "$stale" \
    '. + [{id: $id, title: $title, priority: $priority, status: $status, action: $action, plan_path: $plan_path, stale: $stale}]') || {
    echo "DISCOVERY_ERROR"
    return 0
}
results="$new_results"
```

Or validate `$results` after the loop:

```bash
if ! echo "$results" | jq empty 2>/dev/null; then
    echo "DISCOVERY_ERROR"
    return 0
fi
```

---

### P2-3: Grep False Positives — Markdown Bold and Case Variations

**Location:** `lib-discovery.sh` line 27-28 (pattern comment)

**Code:**
```bash
# Pattern: "Bead" (possibly markdown-bold) followed by the bead ID.
```

**Issue:** The pattern `Bead.*${bead_id}` matches both `Bead:` and `**Bead:**` (markdown bold) correctly due to `.*` wildcard, but it also matches:

- `bead Project-abc1` (lowercase, if someone writes "This bead is...")
- `Bead: some text Project-abc1` (if the ID appears later on the line but unrelated to "Bead:" marker)
- `BeadNecklace Project-abc1` (if a doc mentions beads in a different context)

The current pattern is case-sensitive (good), but the `.*` allows arbitrary text between "Bead" and the ID, which could cause false positives if docs mention the bead ID in unrelated paragraphs.

**Mitigation:** Word-boundary anchor on the bead ID (`\b` or `[^a-zA-Z0-9_-]`) prevents substring matches like `Test-abc12` matching `Test-abc1`, which is good. But the `Bead.*${bead_id}` prefix match is still broad.

**Recommended Pattern:**

Tighten the pattern to require "Bead" followed by zero or more `*` (markdown bold), then optional whitespace, then `:`, then the ID:

```bash
pattern="\*?\*?Bead\*?\*?[[:space:]]*:[[:space:]]*${bead_id}\b"
```

This matches:
- `Bead: Project-abc1`
- `**Bead:** Project-abc1`
- `Bead : Project-abc1` (with extra spaces)

But NOT:
- `Beads are cool Project-abc1`
- `This bead Project-abc1 is...`

**Test Coverage:** `discovery.bats` line 220-240 tests word boundaries but not false positive rejection for "Bead" in unrelated context. Add:

```bats
@test "infer_bead_action: does not match bead ID in unrelated paragraph" {
    mkdir -p "$TEST_PROJECT/docs/plans"
    echo "This document mentions Test-abc1 but is not tagged as a Bead." > "$TEST_PROJECT/docs/plans/unrelated.md"

    run infer_bead_action "Test-abc1" "open"
    assert_success
    assert_output "brainstorm|"  # Should NOT match the unrelated mention
}
```

---

### P2-4: Error Messages — DISCOVERY_ERROR is Opaque

**Location:** `lib-discovery.sh` lines 98, 105 (DISCOVERY_ERROR sentinel)

**Issue:** When bd fails or returns invalid JSON, the scanner emits `"DISCOVERY_ERROR"` to stdout and returns 0 (success). The caller (`lfg.md` line 18) interprets this as "skip discovery, proceed to manual prompt". The user has no visibility into why discovery failed (bd crash? database locked? JSON parse error?).

**Impact:** Low (discovery is best-effort, falling back to manual flow is acceptable), but debugging is harder when discovery silently fails.

**Recommendation:**

Emit the error to stderr (for logging/debugging) while still returning the sentinel to stdout:

```bash
echo "DISCOVERY_ERROR: bd command failed" >&2
echo "DISCOVERY_ERROR"
return 0
```

Or include error details in the JSON output:

```bash
jq -n '{error: "DISCOVERY_ERROR", reason: "bd command failed or returned invalid JSON"}'
return 0
```

Then `lfg.md` can parse the JSON and optionally show a non-blocking warning to the user:

```markdown
2. Parse the output:
   - `{"error": "DISCOVERY_ERROR", ...}` → show warning, proceed to Step 1
```

---

## Race Condition Analysis

### Concurrent State Change Scenarios

The discovery scanner reads from two sources:

1. **bd database** (via `bd list --status=...`)
2. **Filesystem** (via `grep` for artifact files)

Both sources can change concurrently:

| State Change | Impact | Detection |
|--------------|--------|-----------|
| Bead status changes (open → in_progress) | Scanner recommends "execute", should recommend "continue" | None (TOCTOU, P0-1) |
| Bead deleted | Scanner includes it, will fail on routing | None (TOCTOU, P0-1) |
| Plan file created (between grep calls) | Scanner misses it, recommends wrong action | None (scan-time snapshot) |
| Plan file deleted (between infer and staleness check) | Stale flag incorrect, routing fails (P1-3) | None |
| Plan file modified (content changes) | No impact (scanner only checks existence, not content) | None |
| New bead created | Not included in scan results (scan happened before creation) | Expected |

**Mitigation Strategy:**

1. **Short-term (for this PR):** Add pre-flight validation in `lfg.md` before routing (see P0-1 fix)
2. **Medium-term:** Cache bd query results and filesystem snapshot with a timestamp, show staleness warning in menu if scan is >30 seconds old
3. **Long-term:** Implement a file watcher or bd event hook to invalidate cached scan results when bead state changes

---

## JSON Parsing Correctness

### jq Edge Cases

**Priority field (line 142, 174):**
```bash
priority=$(echo "$bead_json" | jq -r '.priority // 4')
--argjson priority "${priority:-4}"
```

If bd returns `priority: null`, the first line sets `priority=""` (empty string). The second line expands to `--argjson priority ""`, which is **invalid JSON** (empty string is not a valid JSON literal). jq will fail.

**Fix:** Always provide a default when passing to `--argjson`:

```bash
priority=$(echo "$bead_json" | jq -r '.priority // 4')
--argjson priority "${priority:-4}"  # Shell parameter expansion catches empty string
```

Wait — this is already correct. The `// 4` in jq outputs `4` if `.priority` is null or missing, and `${priority:-4}` is redundant but harmless (adds shell-level fallback). The risk is only if `.priority` is present but invalid (e.g., `"not-a-number"`). Then jq `-r` will output `"not-a-number"`, and `--argjson priority "not-a-number"` will fail.

**Robust Fix:**

```bash
priority=$(echo "$bead_json" | jq -r '.priority // 4')
if ! [[ "$priority" =~ ^[0-9]+$ ]]; then
    priority=4
fi
```

Or use jq's `tonumber` filter:

```bash
priority=$(echo "$bead_json" | jq '.priority // 4 | tonumber')
```

This ensures numeric output even if bd sends string `"2"`.

---

### Test Coverage Analysis

**Coverage (by function):**

| Function | Structural Tests | Edge Cases | Error Handling | Race Conditions |
|----------|-----------------|------------|----------------|-----------------|
| `infer_bead_action` | ✅ (5 tests) | ✅ (word boundaries) | ❌ (missing dir) | ❌ |
| `discovery_scan_beads` | ✅ (8 tests) | ⚠️ (tie-breaking) | ✅ (bd fail, invalid JSON) | ❌ |
| `discovery_log_selection` | ✅ (2 tests) | ✅ (injection) | ⚠️ (file write fail) | N/A |

**Gaps:**

1. **No tests for file deletion races** (P0-1, P1-3)
2. **No tests for stat failure** (P1-3)
3. **No tests for date parsing failure on BSD** (P2-1)
4. **No tests for grep false positive rejection** (P2-3)
5. **No tests for concurrent bd state changes** (P0-1)
6. **No tests for malformed priority values** (jq numeric parsing)

**Recommendation:** Add 6 tests for the above gaps. Mocking concurrent changes is hard in bats (requires background processes or filesystem snapshots), so consider documenting the race as a known limitation and focus testing on error handling (stat failure, date parsing, grep edge cases).

---

## Summary of Recommendations

### Must Fix (P0)

1. **Add pre-flight validation in lfg.md** — validate bead state and plan file existence after user selection, before routing to commands. This closes the TOCTOU window from minutes to milliseconds.

### Should Fix (P1)

2. **Replace two-pass sort with single-pass group-by** — eliminates non-determinism when priority+timestamp are identical
3. **Use `grep -E` with alternation for portable word boundaries** — eliminates double-grep on non-Perl systems
4. **Check stat exit status before marking stale** — prevents "stale" flag on missing files

### Consider Fixing (P2)

5. **Add BSD date fallback for ISO 8601 parsing** — consistent with `two_days_ago` calculation
6. **Validate jq result in append loop** — catch malformed priority or JSON construction failures
7. **Tighten grep pattern** — require `Bead: <id>` format to reduce false positives
8. **Emit error details** — log reason for DISCOVERY_ERROR to stderr for debugging

### Test Coverage

9. **Add tests for:** stat failure, concurrent file deletion, date parsing portability, grep false positive rejection, malformed priority handling

---

## Conclusion

The discovery scanner is well-structured and handles most error cases gracefully. The critical issue is the **TOCTOU race** between scan and command execution, which can surface stale recommendations and confuse users when bead state changes mid-workflow. The **sorting non-determinism** and **stat error conflation** are high-priority bugs that impact correctness under specific conditions. Grep portability and date parsing are medium-priority polish for cross-platform reliability.

After these fixes, the scanner will be production-ready with deterministic ranking, robust error handling, and race-tolerant validation.
