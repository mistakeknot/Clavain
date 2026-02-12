# Correctness Review: Work Discovery Plan (2026-02-12)

**Reviewer:** Julik (fd-correctness)
**Document:** `/root/projects/Clavain/docs/plans/2026-02-12-work-discovery.md`
**Date:** 2026-02-12

## Summary

Reviewed implementation plan for beads-based work discovery scanner (`lib-discovery.sh`) and LFG discovery mode. Found **5 high-severity correctness issues** and **3 medium-severity issues** across edge cases, race conditions, pattern matching reliability, output format safety, and injection risks.

## Critical Findings

### 1. Edge Case: `infer_bead_action()` — Incorrect JSON Parsing (HIGH)

**Location:** Lines 62-96, `infer_bead_action()` function

**Issue:** The function uses `jq -r '.notes // ""'` to extract notes, but if `jq` fails (malformed JSON, missing field), the pipeline returns an empty string **and continues execution**. This can cause:

- All three `has_*` flags to remain `false` even when artifacts exist in notes
- Fallback filesystem scan to be triggered unnecessarily
- Wrong action to be returned

**Failure scenario:**
```bash
# If bead_json is malformed or bd show returns error JSON:
local notes=$(echo "$bead_json" | jq -r '.notes // ""')  # jq exits 0, returns ""
[[ "$notes" == *"Plan:"* ]] && has_plan=true  # Always false, even if notes had "Plan: docs/plans/..."
# Result: returns "brainstorm" when should return "execute"
```

**Interleaving:**
1. `bd show --json <bead>` returns `{"error": "database locked"}` (race with concurrent `bd` call)
2. `jq -r '.notes'` returns `"null"`, exit code 0
3. All string pattern matches fail
4. Filesystem fallback also fails if plan file not committed yet
5. Function returns `"brainstorm"` for an in-progress bead with a plan

**Fix:**
```bash
infer_bead_action() {
    local bead_id="$1"
    local bead_json="$2"

    # Validate JSON first
    if ! echo "$bead_json" | jq -e . >/dev/null 2>&1; then
        echo "error:invalid_json" >&2
        return 1
    fi

    local status=$(echo "$bead_json" | jq -r '.status // "unknown"')
    local notes=$(echo "$bead_json" | jq -r '.notes // ""')
    local title=$(echo "$bead_json" | jq -r '.title // "untitled"')

    # Fail if essential fields are missing
    if [[ "$status" == "unknown" || "$status" == "null" ]]; then
        echo "error:missing_status" >&2
        return 1
    fi

    # ... rest of function
}
```

**Impact:** Scanner can return wrong action, routing user to `/brainstorm` when they should go to `/work`. This wastes time and breaks the "smart discovery" promise.

---

### 2. Race Condition: Scanner vs. Concurrent Bead Mutations (HIGH)

**Location:** Lines 31-43, `discovery_scan_beads()` function description

**Issue:** The plan doesn't specify atomicity guarantees. The scanner calls:
1. `bd list --status=open --json` → gets list of beads
2. For each bead, calls `bd show <id> --json` → gets details
3. For each bead, runs filesystem scans (`grep -rl`)

**Race scenarios:**

#### Race A: Bead status changes between list and show
```
Time  Scanner Thread              User/Other Session
----  --------------------------  --------------------------
T0    bd list → [Clavain-abc]
T1    bd show Clavain-abc        bd update Clavain-abc --status=done
T2    infer_action → "execute"
T3    Present to user
T4    User selects bead          Bead is already closed
```

**Result:** User selects a bead that's no longer open. When routed to `/work`, the command may fail or operate on stale state.

#### Race B: Filesystem artifact appears after scan
```
Time  Scanner Thread                   User/Other Session
----  -------------------------------  --------------------------
T0    bd list → [Clavain-abc]
T1    grep docs/plans/ (no match)
T2    infer_action → "plan"           git commit -m "add plan"
T3    Present "Write plan" option     Plan now exists
T4    User selects, expects to write  /write-plan fails: plan exists
```

**Result:** User is prompted to write a plan that already exists. The command should either skip duplicate work or refresh state.

#### Race C: Concurrent scanner runs (session-start + manual /lfg)
The plan mentions the scanner will be used by:
- `commands/lfg.md` (on-demand)
- `hooks/session-start.sh` (future F4)
- `hooks/sprint-scan.sh` (full scan, existing)

If a user runs `/lfg` while session-start is still scanning:
```bash
# Both processes may call bd simultaneously
bd list --status=open --json  # Process 1
bd list --status=open --json  # Process 2 (race)
```

Dolt's storage layer is ACID-compliant, so concurrent reads are safe, but the **combined read-infer-present flow is not atomic**. The scanner doesn't lock state, so the presented options may be stale by the time the user selects.

**Fix recommendations:**
1. **Timestamp the scan:** Include scan timestamp in output, and when routing to a command, have the command re-validate bead state before starting work.
2. **Idempotency:** Ensure all routed commands (`/work`, `/write-plan`, etc.) check for duplicate work and fail gracefully if the precondition is no longer met.
3. **Session-start deduplication:** Add a lockfile or PID check so only one scanner runs at a time:
   ```bash
   discovery_scan_beads() {
       local lockfile="${HOME}/.clavain/discovery.lock"
       if [[ -f "$lockfile" ]] && kill -0 $(cat "$lockfile" 2>/dev/null) 2>/dev/null; then
           echo "# Scanner already running" >&2
           return 1
       fi
       echo $$ > "$lockfile"
       trap "rm -f '$lockfile'" EXIT
       # ... actual scan logic
   }
   ```

**Impact:** Scanner can present stale or invalid options, breaking user trust. In a multi-session environment (tmux, multiple Claude sessions), this becomes probabilistic corruption.

---

### 3. Pattern Matching: `grep -rl "Bead.*${bead_id}"` — Substring False Positives (MEDIUM-HIGH)

**Location:** Lines 77-82, filesystem fallback in `infer_bead_action()`

**Issue:** The pattern `"Bead.*${bead_id}"` will match:
- The target bead ID (`Clavain-abc`)
- Any bead ID that contains it as a substring (`Clavain-abc1`, `Clavain-abc-v2`)
- Any bead ID that shares a prefix (`Clavain-abcd`)

**Failure scenario:**
```bash
# Bead IDs: Clavain-abc, Clavain-abc1
# File docs/plans/2026-02-12-fix.md contains:
#   "**Bead:** Clavain-abc1"
# But NOT Clavain-abc

bead_id="Clavain-abc"
grep -rl "Bead.*${bead_id}" docs/plans/  # Matches the file (false positive)
# Function returns has_plan=true for Clavain-abc, even though the plan is for Clavain-abc1
```

**Why this happens:**
- Bead IDs follow the format `{project}-{4char}` (e.g., `Clavain-a3hp`)
- The 4-char suffix is hex, so `abc` is a valid substring of `abc1`, `abcd`, `abce`, etc.
- The regex `Bead.*abc` is too greedy — the `.*` matches any characters between "Bead" and "abc"

**Fix:**
```bash
# Anchor the bead ID with word boundaries or whitespace
if ! $has_plan; then
    # Match "Bead: Clavain-abc" or "Bead:Clavain-abc" but not "Bead:Clavain-abc1"
    grep -rl "Bead[: ]${bead_id}\b" docs/plans/ 2>/dev/null | head -1 | grep -q . && has_plan=true
fi
if ! $has_prd; then
    grep -rl "Bead[: ]${bead_id}\b" docs/prds/ 2>/dev/null | head -1 | grep -q . && has_prd=true
fi
```

Or use a more precise pattern:
```bash
# Match "**Bead:** Clavain-abc" (the actual Clavain markdown convention)
grep -rl "\*\*Bead:\*\* ${bead_id}\b" docs/plans/ 2>/dev/null | head -1 | grep -q . && has_plan=true
```

**Alternative fix:** Use `bd show --json` to get the plan/PRD references from notes field ONLY, and skip filesystem fallback entirely. Filesystem scans should be a last resort, not a primary detection method.

**Impact:** Scanner can assign wrong action to a bead because it thinks a plan exists when it doesn't (or vice versa). This breaks routing and wastes user time.

---

### 4. Structured Output Format: Pipe-Delimited Fields — Injection Risk (HIGH)

**Location:** Lines 99-107, output format specification

**Issue:** The output uses pipe (`|`) as a field delimiter:
```
bead:Clavain-abc|title:Fix auth timeout|priority:1|action:execute|stale:no
```

If a bead title contains a pipe character, this format is ambiguous:
```
bead:Clavain-abc|title:Fix auth|timeout issue|priority:1|action:execute|stale:no
                              ^-- Is this a delimiter or part of the title?
```

**Failure scenario:**
```bash
# User creates bead with title: "Migrate | Refactor | Test"
bd create --title "Migrate | Refactor | Test" --priority 1

# Scanner outputs:
# bead:Clavain-xyz|title:Migrate | Refactor | Test|priority:1|action:brainstorm|stale:no

# LLM parser in lfg.md splits on |, gets:
# ["bead:Clavain-xyz", "title:Migrate ", " Refactor ", " Test", "priority:1", ...]
# Parser breaks, can't find "priority:" field, crashes or skips bead
```

**Why pipes in titles are realistic:**
- Common in technical writing: "Component A | Component B"
- Shell examples: "ps aux | grep process"
- Path separators: "src/module1 | src/module2"

**Fix options:**

#### Option A: Use a more obscure delimiter
```bash
# Use ASCII 0x1E (record separator) or 0x1F (unit separator)
# Extremely unlikely to appear in bead titles
printf 'bead:%s\x1Ftitle:%s\x1Fpriority:%d\x1Faction:%s\x1Fstale:%s\n' \
    "$bead_id" "$title" "$priority" "$action" "$stale"
```

#### Option B: JSON output (recommended)
```bash
# Output valid JSON, let LLM parse with jq
printf '{"bead":"%s","title":"%s","priority":%d,"action":"%s","stale":"%s"}\n' \
    "$bead_id" "$(echo "$title" | jq -Rs .)" "$priority" "$action" "$stale"
```

JSON escaping handles pipes, quotes, newlines, etc. The LLM can parse with `jq` (which Claude Code already uses extensively).

#### Option C: Escape pipes in titles
```bash
# Replace | with \| in title before output
local title_escaped="${title//|/\\|}"
printf 'bead:%s|title:%s|priority:%d|action:%s|stale:%s\n' \
    "$bead_id" "$title_escaped" "$priority" "$action" "$stale"
```

**Recommendation:** Use JSON output (Option B). The plan already uses `jq` for parsing `bd` output, so the LLM can handle JSON input as well.

**Impact:** Parser failures cause beads to be silently dropped from discovery results. User never sees the option, assumes no work is available, wastes time.

---

### 5. Telemetry Logging: `printf` Injection Risk (MEDIUM)

**Location:** Lines 160-173, `discovery_log_selection()` function

**Issue:** The function uses `printf` with user-controlled data (bead ID, action):
```bash
printf '{"event":"discovery_select","bead":"%s","action":"%s","recommended":%s,"timestamp":"%s"}\n' \
    "$bead_id" "$action" "$was_recommended" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

If `$bead_id` or `$action` contain format specifiers (`%s`, `%d`, etc.), `printf` will interpret them:
```bash
bead_id='Clavain-abc%s%s%s'
action='execute%n%n'
printf '{"bead":"%s","action":"%s"}\n' "$bead_id" "$action"
# printf interprets %s as format spec, expects more arguments, crashes or prints garbage
```

**Failure scenario:**
1. User creates bead with title containing `%s` (rare but possible in technical titles)
2. Scanner logs the selection
3. `printf` misinterprets the format string, writes malformed JSON
4. Telemetry file becomes unparseable
5. If any future code tries to parse `telemetry.jsonl`, it fails

**Why this is realistic:**
- Technical bead titles might include format strings: "Fix printf %s bug in logger"
- Bead IDs are generated, so less risk, but action strings are derived from notes/titles

**Fix:**
```bash
discovery_log_selection() {
    local bead_id="$1"
    local action="$2"
    local was_recommended="$3"
    local telemetry_file="${HOME}/.clavain/telemetry.jsonl"
    mkdir -p "$(dirname "$telemetry_file")" 2>/dev/null || return 0

    # Escape JSON strings properly
    local bead_json=$(printf '%s' "$bead_id" | jq -Rs .)
    local action_json=$(printf '%s' "$action" | jq -Rs .)
    local timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    # Use echo with pre-escaped JSON values
    echo "{\"event\":\"discovery_select\",\"bead\":${bead_json},\"action\":${action_json},\"recommended\":${was_recommended},\"timestamp\":\"${timestamp}\"}" \
        >> "$telemetry_file" 2>/dev/null || true
}
```

Or use `jq` to construct the JSON:
```bash
jq -n \
    --arg event "discovery_select" \
    --arg bead "$bead_id" \
    --arg action "$action" \
    --argjson rec "$was_recommended" \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{event: $event, bead: $bead, action: $action, recommended: $rec, timestamp: $ts}' \
    >> "$telemetry_file" 2>/dev/null || true
```

**Impact:** Low likelihood (requires user to create bead with format-string title), but high consequence if it happens (telemetry becomes corrupt, future analytics break).

---

## Additional Findings

### 6. Error Handling: No Validation of `bd list` Output (MEDIUM)

**Location:** Lines 31-43, `discovery_scan_beads()` description

**Issue:** The plan doesn't specify what happens if:
- `bd list --status=open --json` returns empty array `[]`
- `bd list` fails (exit code != 0)
- `bd` is not installed (command not found)

The plan mentions "Handle `bd` unavailable gracefully" in Task 1, but doesn't specify the exact behavior.

**Fix:**
```bash
discovery_scan_beads() {
    # Check if bd is available
    if ! command -v bd >/dev/null 2>&1; then
        echo "# DISCOVERY_UNAVAILABLE: bd not installed" >&2
        return 1
    fi

    # Get bead list
    local beads_json=$(bd list --status=open --json 2>&1)
    local bd_exit=$?

    if [[ $bd_exit -ne 0 ]]; then
        echo "# DISCOVERY_ERROR: bd list failed (exit $bd_exit)" >&2
        return 1
    fi

    # Validate JSON
    if ! echo "$beads_json" | jq -e . >/dev/null 2>&1; then
        echo "# DISCOVERY_ERROR: invalid JSON from bd list" >&2
        return 1
    fi

    # Check if empty
    local bead_count=$(echo "$beads_json" | jq 'length')
    if [[ "$bead_count" -eq 0 ]]; then
        echo "# DISCOVERY_EMPTY: no open beads" >&2
        return 0  # Not an error, just empty
    fi

    # ... rest of function
}
```

The `lfg.md` command should check the exit code and stderr output to decide whether to fall through to normal pipeline.

---

### 7. Staleness Check: Date Comparison Edge Case (LOW)

**Location:** Line 44, staleness check description

**Issue:** "if bead updated >2 days ago" — the plan doesn't specify:
- How to parse the `updated` timestamp from `bd show --json`
- How to compare timestamps in bash (which lacks native date arithmetic)
- What timezone to use (beads uses UTC, system clock might be local)

**Failure scenario:**
```bash
# bd returns ISO8601: "2026-02-10T14:30:00Z"
# bash date command behavior varies by platform (GNU vs BSD)
# Naive comparison:
local updated="2026-02-10T14:30:00Z"
local now_epoch=$(date +%s)
local updated_epoch=$(date -d "$updated" +%s 2>/dev/null)  # Fails on BSD (macOS)
```

**Fix (GNU coreutils, Linux only):**
```bash
is_stale() {
    local updated_iso="$1"  # "2026-02-10T14:30:00Z"
    local now_epoch=$(date +%s)
    local updated_epoch=$(date -d "$updated_iso" +%s 2>/dev/null)

    if [[ -z "$updated_epoch" ]]; then
        # Parsing failed, assume not stale (fail open)
        return 1
    fi

    local age_seconds=$((now_epoch - updated_epoch))
    local two_days=$((2 * 24 * 60 * 60))

    [[ $age_seconds -gt $two_days ]]
}
```

**Recommendation:** Document that staleness check requires GNU date (available in Linux, not macOS). Or use a more portable approach:
```bash
# Extract date portion, compare lexicographically (works for ISO8601)
local updated_date="${updated_iso%%T*}"  # "2026-02-10"
local today=$(date -u +%Y-%m-%d)
# If date is before (today - 2 days), it's stale
# Requires date arithmetic... still platform-dependent
```

**Alternative:** Move staleness logic to beads CLI itself (`bd list --stale-threshold=2d`) so the shell script doesn't need to parse dates.

**Impact:** Staleness marker may be wrong on some platforms, but this is cosmetic (doesn't affect routing).

---

### 8. Concurrency: Filesystem Scan Race with Git Operations (LOW)

**Location:** Lines 77-82, filesystem fallback

**Issue:** The scanner runs `grep -rl` on `docs/plans/` and `docs/prds/` while git operations may be in progress:
- Another session is committing a new plan
- A git pull is in progress
- A file is being edited (Write tool creates temp file, renames)

**Race scenario:**
```
Time  Scanner Thread                   Git/Other Process
----  -------------------------------  --------------------------
T0    grep -rl docs/plans/
T1    stat docs/plans/foo.md          Write creates foo.md.tmp
T2    grep reads foo.md               Write renames to foo.md
T3    grep completes                  grep may miss foo.md
```

**Why this is unlikely to cause issues:**
- `grep -rl` only needs to see file content, not atomic writes
- If a file is added/removed during scan, worst case is scanner misses it (fallback to notes field)
- Git operations lock `.git/index`, not the worktree files

**Impact:** Very low. Filesystem scan is already a fallback. If it misses a file due to race, the primary detection method (notes field) should still work.

---

## Recommendations

### Priority 1 (Must Fix Before Merge)
1. **Fix `infer_bead_action()` JSON validation** — always validate `jq` output before using it
2. **Change output format to JSON** — pipe-delimited format is unsafe
3. **Add word-boundary anchors to grep patterns** — prevent substring false positives
4. **Fix telemetry printf injection** — use `jq` to construct JSON

### Priority 2 (Should Fix Before Release)
5. **Add timestamp to scanner output** — so routed commands can detect stale state
6. **Add lockfile to prevent concurrent scans** — deduplicate session-start + manual invocations
7. **Document error handling for bd unavailable** — specify exact fallback behavior

### Priority 3 (Nice to Have)
8. **Move staleness check to beads CLI** — avoid platform-specific date parsing
9. **Add integration test for concurrent scanner calls** — verify no data corruption

---

## Failure Narrative: Worst-Case Scenario

**Setup:**
- User has 3 open beads: `Clavain-abc` (P0, has plan), `Clavain-abc1` (P1, no plan), `Clavain-abd` (P2, no plan)
- Bead `Clavain-abc` was updated 3 days ago (stale)
- User runs `/lfg` in one tmux pane
- Another session is running `bd update Clavain-abc --status=done` concurrently
- Bead `Clavain-abc1` title is: "Migrate auth | Add SSO | Test"

**Timeline:**
```
T0  Scanner: bd list --status=open --json → [Clavain-abc, Clavain-abc1, Clavain-abd]
T1  Scanner: bd show Clavain-abc --json → gets bead details (still open)
T2  Other session: bd update Clavain-abc --status=done
T3  Scanner: infer_bead_action(Clavain-abc) → finds no plan in notes (corrupted JSON from concurrent update)
T4  Scanner: grep "Bead.*Clavain-abc" docs/plans/ → matches plan for Clavain-abc1 (substring match)
T5  Scanner: has_plan=true, action="execute"
T6  Scanner: bd show Clavain-abc1 --json → gets bead details
T7  Scanner: infer_bead_action(Clavain-abc1) → notes has "Plan: docs/plans/foo.md"
T8  Scanner: action="execute"
T9  Scanner: formats output with pipe delimiters
T10 Scanner: outputs "bead:Clavain-abc1|title:Migrate auth | Add SSO | Test|priority:1|action:execute|stale:no"
T11 LLM in lfg.md: splits on | → ["bead:Clavain-abc1", "title:Migrate auth ", " Add SSO ", " Test", ...]
T12 LLM: can't find priority field, skips Clavain-abc1
T13 LLM: presents only Clavain-abd (wrong recommendation)
T14 User selects Clavain-abd, starts brainstorm
T15 User wastes 30 minutes brainstorming when they should be executing the plan for Clavain-abc1
```

**Root causes:**
1. Race between scanner and concurrent bead update → wrong action for Clavain-abc
2. Substring grep match → false positive for Clavain-abc
3. Pipe in title → parser corruption for Clavain-abc1
4. No validation of scanner output → silent failure

**Consequences:**
- Scanner returns wrong recommendation
- User works on wrong bead
- Trust in discovery system is broken
- User falls back to manual `bd list`, defeating the purpose of the feature

---

## Testing Recommendations

### Unit Tests (Shell)
```bash
# test_discovery.bats

@test "infer_bead_action handles malformed JSON" {
    bead_json='{"error": "database locked"}'
    run infer_bead_action "Clavain-abc" "$bead_json"
    [[ "$status" -ne 0 ]]
}

@test "infer_bead_action rejects missing status field" {
    bead_json='{"notes": "Plan: foo.md", "title": "Test"}'
    run infer_bead_action "Clavain-abc" "$bead_json"
    [[ "$status" -ne 0 ]]
}

@test "grep pattern does not match substring bead IDs" {
    # Create fake plan file with Clavain-abc1
    echo "**Bead:** Clavain-abc1" > /tmp/test-plan.md

    # Run infer_bead_action for Clavain-abc (not abc1)
    bead_json='{"status":"open","notes":"","title":"Test"}'
    run infer_bead_action "Clavain-abc" "$bead_json"

    # Should NOT find the plan
    [[ "$output" != "execute" ]]
}

@test "output format handles pipe in title" {
    bead_json='{"status":"open","notes":"","title":"Fix | Test | Deploy"}'
    run format_discovery_output "$bead_json"

    # Output should be valid JSON
    echo "$output" | jq -e . >/dev/null
}

@test "telemetry printf handles format specifiers in bead ID" {
    run discovery_log_selection "Clavain-%s%s%s" "execute" "true"
    [[ "$status" -eq 0 ]]

    # Telemetry file should contain valid JSON
    tail -1 ~/.clavain/telemetry.jsonl | jq -e . >/dev/null
}
```

### Integration Tests
```bash
@test "concurrent scanner calls do not corrupt output" {
    # Run two scanners in parallel
    discovery_scan_beads > /tmp/scan1.txt &
    discovery_scan_beads > /tmp/scan2.txt &
    wait

    # Both outputs should be valid JSON
    jq -e . /tmp/scan1.txt >/dev/null
    jq -e . /tmp/scan2.txt >/dev/null
}

@test "scanner detects bead closed between list and show" {
    # Start scanner
    discovery_scan_beads > /tmp/scan.txt &
    sleep 0.1

    # Close a bead mid-scan
    bd update Clavain-test --status=done

    wait

    # Scanner should not include the closed bead
    ! grep -q "Clavain-test" /tmp/scan.txt
}
```

---

## Conclusion

The plan is architecturally sound but has **5 high-severity correctness issues** that will cause failures in production:
1. Wrong action inference due to JSON validation gaps
2. Race conditions between scanner and concurrent state changes
3. Substring false positives in grep patterns
4. Parser corruption from pipe characters in titles
5. Printf injection in telemetry logging

All issues have concrete fixes. Priority 1 fixes should be applied before merge. Priority 2 fixes should be applied before the feature is released to users.

The scanner is read-heavy, so database locking is not a concern, but the **lack of atomicity in the read-infer-present flow** means the presented options may be stale. The fix is to add validation at routing time (when the command is invoked) rather than trying to lock the scanner.

**Final recommendation:** Apply Priority 1 fixes, add the recommended unit tests, and document the staleness behavior in `lfg.md` so users understand that discovery is a point-in-time snapshot.
