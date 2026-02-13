# Correctness Review: F3 & F4 Implementation (Orphan Detection & Brief Scan)

**Reviewer:** fd-correctness
**Date:** 2026-02-13
**Files Reviewed:**
- `/root/projects/interphase/hooks/lib-discovery.sh` (lines ~189-288, ~295-387)
- `/root/projects/Clavain/commands/lfg.md` (lines 27-29, 37-47)
- `/root/projects/Clavain/hooks/session-start.sh` (lines 118-128)

---

## Executive Summary

The F3 (orphan detection) and F4 (brief scan) implementation introduces **6 correctness issues**, including:
- **1 critical race condition** (cache TOCTOU)
- **2 moderate race conditions** (orphan creation race, concurrent session cache corruption)
- **3 data consistency issues** (incomplete error handling, edge case bugs, missing validation)

**No immediate production-breaking issues**, but the cache TOCTOU race will cause 3am pages under concurrent session load. Recommend fixing before merge.

---

## 1. Critical Race Condition: Cache TOCTOU in `discovery_brief_scan()`

**Location:** `lib-discovery.sh` lines 312-326

**Issue:** Classic time-of-check to time-of-use (TOCTOU) race:

```bash
# Thread A checks cache freshness
if [[ -f "$cache_file" ]]; then
    cache_mtime=$(stat -c %Y "$cache_file" 2>/dev/null || ...)
    cache_age=$(( now - cache_mtime ))
    if [[ $cache_age -lt 60 ]]; then
        # Thread B truncates cache file here (line 346)
        cached=$(cat "$cache_file" 2>/dev/null) || cached=""
        # Thread A reads empty/partial content
        if [[ -n "$cached" ]]; then
            echo "$cached"
            return 0
        fi
    fi
fi
```

**Failure Narrative:**
1. Session A calls `discovery_brief_scan()` at T=0, reads `cache_mtime` → cache is fresh
2. Session B calls `discovery_brief_scan()` at T=0.1s (cache stale for B's query scope), proceeds to write at line 384: `echo "$summary" > "$cache_file"`
3. Session A executes `cat "$cache_file"` → reads empty string (B's write redirected to temp, not yet renamed) OR partial content (B's write in progress)
4. Session A sees `cached=""`, falls through to regeneration, queries `bd` again (wastes 100-500ms)
5. **If both sessions regenerate concurrently**, last writer wins → race on cache content itself

**Impact:**
- Cache thrashing under concurrent load (multiple sessions in same project)
- Wasted `bd list` queries (can be 200-500ms each for large backlogs)
- Potential for session-start timeout if 3+ sessions race during plugin load

**Recommendation:**
Use atomic write-then-rename pattern:
```bash
local temp_cache="${cache_file}.$$"
echo "$summary" > "$temp_cache" 2>/dev/null || true
mv -f "$temp_cache" "$cache_file" 2>/dev/null || true
```

Then `cat` sees either old complete content or new complete content, never partial writes. TTL check race remains (both sessions may regenerate), but content corruption is eliminated.

**Alternative (better):** Use `flock` for exclusive cache access:
```bash
(
    flock -n 200 || return 0  # Another session is regenerating; use stale or skip
    # TTL check + regeneration here
) 200>"${cache_file}.lock"
```

---

## 2. Moderate Race: Orphan Creation vs. Discovery Scan

**Location:** `lib-discovery.sh` lines 261-272 (orphan scan), `lfg.md` lines 44-48 (create_bead action)

**Issue:** No atomic guard between orphan detection and bead creation. The following interleaving causes duplicate beads:

**Failure Narrative:**
1. Session A invokes `/lfg`, runs `discovery_scan_beads()` at T=0
2. `discovery_scan_orphans()` finds file `docs/plans/foo.md` with no bead reference → returns orphan entry
3. Session A presents "Link orphan: foo.md" to user, user selects it at T=5s
4. **Between T=0 and T=5s**, Session B manually creates a bead and edits `foo.md` to add `**Bead:** Foo-abc123`
5. Session A executes lfg.md line 45: `bd create --title="foo" --type=task --priority=3` → creates **second bead** `Foo-xyz456`
6. Session A edits `foo.md` line 2, replacing B's `**Bead:** Foo-abc123` with `**Bead:** Foo-xyz456`
7. **Result:** Bead `Foo-abc123` is now orphaned (no file references it), `Foo-xyz456` is active but duplicates B's intent

**Impact:**
- Bead duplication (low frequency, requires manual user action during discovery latency window)
- Orphaned beads accumulate in `.beads/` database (pollutes backlog)
- Confusion when both sessions commit changes referencing different bead IDs for the same work

**Recommendation:**
Add pre-flight check in lfg.md between orphan selection and bead creation:
```bash
# After user selects orphan, before bd create:
if grep -q 'Bead.*[A-Za-z]+-[a-z0-9]+' "$artifact_path" 2>/dev/null; then
    echo "This artifact was linked to a bead by another session. Re-running discovery."
    # Re-run discovery from step 1
fi
```

**Alternative:** Make orphan scan check file mtime — if file modified since scan started, re-scan before creation.

---

## 3. Moderate Issue: Concurrent Session Cache Key Collision

**Location:** `lib-discovery.sh` lines 307-309

**Issue:** Cache key derivation is not session-aware:

```bash
local cache_key="${project_dir//\//_}"
local cache_file="/tmp/clavain-discovery-brief-${cache_key}.cache"
```

All sessions in the same project share **one cache file**. Under concurrent load:
- Session A writes summary for state at T=0
- Session B writes summary for state at T=0.1 (one bead closed between reads)
- Session A's statusline reads B's summary → shows work state that doesn't match A's actual discovery scan

**Failure Narrative:**
1. Session A starts, `discovery_brief_scan()` sees 5 open beads, caches "5 open beads. Top: Continue Foo-abc123"
2. User closes bead `Foo-abc123` via Session B (or external `bd` command) at T=10s
3. Session B (another Claude session) starts at T=11s, regenerates cache → "4 open beads. Top: Execute plan for Foo-xyz456"
4. Session A's statusline (via interline) reads cache at T=12s → shows "Top: Execute Foo-xyz456"
5. **But Session A's discovery_scan_beads() still returns Foo-abc123 as top bead** (no cache, always queries bd fresh)
6. User sees statusline mismatch: "Top: Foo-xyz" in status bar but "Top: Foo-abc" in discovery menu

**Impact:**
- Confusing UX when multiple sessions active (statusline shows wrong work state)
- Not a data corruption risk (discovery_scan_beads always queries bd fresh)
- Rare (requires 2+ concurrent sessions in same project)

**Recommendation:**
Include `CLAUDE_SESSION_ID` in cache key:
```bash
local cache_key="${project_dir//\//_}_${CLAUDE_SESSION_ID:-$$}"
local cache_file="/tmp/clavain-discovery-brief-${cache_key}.cache"
```

**Trade-off:** Increases cache churn (each session has its own cache), but eliminates cross-session contamination. Given 60s TTL and typical session duration (hours), negligible overhead.

---

## 4. Data Consistency: Incomplete Error Handling in Orphan Scan

**Location:** `lib-discovery.sh` lines 246-284

**Issue:** `find` command errors are silently suppressed:

```bash
while IFS= read -r -d '' file; do
    # ... processing ...
done < <(find "${project_dir}/${dir}" -name '*.md' -print0 2>/dev/null)
```

If `find` fails (permission denied, filesystem error, symlink loop), the loop gets zero input and orphan scan returns `[]`. Caller cannot distinguish "no orphans" from "scan failed".

**Failure Narrative:**
1. Filesystem ACL issue causes `find docs/plans/` to fail with EACCES
2. `discovery_scan_orphans()` returns `[]` (no orphans detected)
3. `discovery_scan_beads()` appends `[]` → user sees no orphan entries
4. **Actual orphaned artifact exists** but is invisible to discovery
5. User manually discovers orphan later, wonders why discovery didn't surface it

**Impact:**
- Silent failure hides orphaned work (user misses tasks)
- Low probability (requires filesystem permission issue), but high consequence (missed work)

**Recommendation:**
Track `find` exit status and emit sentinel on failure:
```bash
local find_status=0
while IFS= read -r -d '' file; do
    # ... processing ...
done < <(find "${project_dir}/${dir}" -name '*.md' -print0 2>/dev/null || { echo >&2; exit 1; })
find_status=$?
if [[ $find_status -ne 0 ]]; then
    echo "DISCOVERY_ERROR"  # Same sentinel as bd query failures
    return 0
fi
```

Caller (lfg.md) already handles `DISCOVERY_ERROR` by skipping discovery.

---

## 5. Edge Case: Empty Cache File Treated as Valid

**Location:** `lib-discovery.sh` lines 319-324

**Issue:** Cache validation only checks `[[ -n "$cached" ]]`, but an **empty string is valid output** when there are zero open beads (line 346):

```bash
if [[ "$total_count" -eq 0 ]]; then
    echo "" > "$cache_file" 2>/dev/null || true
    return 0
fi
```

However, the cache-read logic treats empty as invalid:
```bash
cached=$(cat "$cache_file" 2>/dev/null) || cached=""
if [[ -n "$cached" ]]; then  # Empty cache rejected
    echo "$cached"
    return 0
fi
```

**Failure Narrative:**
1. User closes all beads → `total_count=0`
2. `discovery_brief_scan()` writes empty string to cache
3. Next invocation reads cache, sees `cached=""`, rejects it
4. Re-queries `bd list` (wasted query), writes empty string again
5. **Cache never used when backlog is empty** → 60s TTL is meaningless

**Impact:**
- Wasted `bd` queries when backlog is empty (low cost, ~50ms)
- Violates caching contract (defeats the purpose of TTL)
- Not a correctness issue, but degrades performance for "inbox zero" users

**Recommendation:**
Use distinct sentinel for "zero beads" vs "invalid cache":
```bash
if [[ "$total_count" -eq 0 ]]; then
    echo "NO_WORK" > "$cache_file" 2>/dev/null || true
    return 0
fi

# Cache read:
cached=$(cat "$cache_file" 2>/dev/null) || cached=""
if [[ "$cached" == "NO_WORK" ]]; then
    return 0  # Valid "no work" state
elif [[ -n "$cached" ]]; then
    echo "$cached"
    return 0
fi
```

---

## 6. Data Consistency: Missing Null Check in Orphan Processing

**Location:** `lib-discovery.sh` lines 198-200

**Issue:** `jq -r` extracts can return literal `"null"` string if JSON field is null, but code only guards against empty string:

```bash
o_title=$(echo "$orphan_json" | jq -r '.title // "Untitled"')
o_path=$(echo "$orphan_json" | jq -r '.path // ""')
o_type=$(echo "$orphan_json" | jq -r '.type // ""')
```

If `discovery_scan_orphans()` emits malformed JSON (e.g., `{title: null, path: "foo.md"}`), then:
- `o_title="null"` (literal string)
- Results array contains: `{title: "null", ...}` instead of `"Untitled"`

**Failure Narrative:**
1. Orphan scan regex fails to extract title from malformed markdown (e.g., file starts with `## Heading` not `# Heading`)
2. `title=""` is set at line 250, then jq at line 267 stores `--arg title ""` → JSON field is `""` not `null`
3. **Actually, this case is safe** — the `// "Untitled"` fallback works for empty strings

**Re-analysis:** This is NOT a bug. `jq -r` with `// "Untitled"` handles both `null` and empty string correctly. The only risk is if `title` field is **missing entirely** from the orphan JSON (malformed upstream), but that can't happen because we construct the JSON ourselves with `--arg`.

**Verdict:** False alarm. No issue here.

---

## 7. Edge Case: Race-Free but Suboptimal Pre-Flight Check in lfg.md

**Location:** `lfg.md` lines 30-35

**Current logic:**
```markdown
4. Pre-flight check: Before routing, verify the selected bead still exists:
   bd show <selected_bead_id> 2>/dev/null
   If bd show fails, tell user "That bead is no longer available" and re-run discovery.
   Skip this check for orphan entries (action: "create_bead").
```

**Issue:** Check happens AFTER user selection, not before presentation. If bead was closed between scan (step 1) and selection (step 3), user sees:
1. Discovery menu: "Continue Foo-abc123 — Fix login bug (P0) (Recommended)"
2. User clicks option
3. "That bead is no longer available"
4. Re-run discovery → new menu appears

**Impact:**
- Poor UX (user's selection is rejected)
- Not a correctness issue (recovery is correct), but wastes user time

**Recommendation:**
Move pre-flight check to **before AskUserQuestion** presentation:
```bash
# After discovery_scan_beads, before presenting menu:
for bead in top 3 results; do
    if [[ "$bead.action" != "create_bead" ]]; then
        bd show "$bead.id" 2>/dev/null || {
            # Bead closed since scan — remove from results
            results=$(echo "$results" | jq "del(.[] | select(.id == \"$bead.id\"))")
        }
    fi
done
```

**Trade-off:** Adds 1-3 `bd show` calls (10-30ms total) to discovery latency. Buys better UX (no rejected selections).

---

## 8. Missing Validation: Bead Creation Can Fail Silently

**Location:** `lfg.md` line 45

**Issue:** No validation that `bd create` succeeded before proceeding:

```markdown
1. Run bd create --title="<artifact title>" --type=task --priority=3 and capture the new bead ID
2. Insert **Bead:** <new-id> on line 2 of the artifact file
```

If `bd create` fails (database lock, permission issue, invalid title), the script continues with an empty bead ID:
```bash
bead_id=$(bd create --title="foo" --type=task --priority=3)
# bead_id="" if bd create failed
# Edit tool inserts: **Bead:**
# Result: malformed bead reference in artifact
```

**Failure Narrative:**
1. User selects orphan "Link orphan: foo.md"
2. `bd create` fails (e.g., `.beads/beads.db` is locked by another session)
3. Bash captures empty string for `bead_id`
4. Edit tool inserts `**Bead:** ` (no ID) into `foo.md`
5. Next discovery scan sees malformed bead reference, treats file as orphan again
6. **Infinite loop:** orphan appears in every scan, user keeps selecting it, it keeps failing

**Impact:**
- User stuck in failure loop
- Database lock contention under concurrent load (multiple sessions creating beads)

**Recommendation:**
Add explicit error handling in lfg.md's create_bead branch:
```bash
bead_id=$(bd create --title="$artifact_title" --type=task --priority=3 2>&1)
if [[ ! "$bead_id" =~ ^[A-Za-z]+-[a-z0-9]+$ ]]; then
    echo "Failed to create bead: $bead_id"
    echo "Please try again or create manually with: bd create --title=\"$artifact_title\""
    exit 1
fi
```

Regex validation ensures we got a valid bead ID before proceeding to Edit.

---

## Summary Table

| # | Issue | Severity | Impact | Recommended Fix |
|---|-------|----------|--------|-----------------|
| 1 | Cache TOCTOU race | **Critical** | Cache thrashing, wasted queries, session-start timeout under concurrent load | Atomic write (temp+rename) or flock-based exclusive cache access |
| 2 | Orphan creation race | **Moderate** | Duplicate beads, orphaned work, user confusion | Pre-flight check before `bd create` |
| 3 | Cache key collision | **Moderate** | Statusline shows wrong work state in multi-session scenarios | Include `CLAUDE_SESSION_ID` in cache key |
| 4 | Silent orphan scan failure | **Moderate** | Missed orphaned work when filesystem errors occur | Propagate `find` exit status as `DISCOVERY_ERROR` |
| 5 | Empty cache rejected | **Low** | Wasted queries when backlog empty | Use `NO_WORK` sentinel |
| 6 | Null title handling | **None** | False alarm — jq `//` handles this correctly | No action needed |
| 7 | Post-selection pre-flight | **Low** | Poor UX (rejected selections) | Move validation before menu presentation |
| 8 | Silent bead creation failure | **Moderate** | Infinite orphan loop on database lock | Validate bead ID format after `bd create` |

---

## Recommended Merge Blockers

Fix **#1 (cache TOCTOU)** and **#8 (bead creation validation)** before merge. These will cause 3am pages under production load.

Issues #2-#7 can be addressed in follow-up PRs (not merge-blocking, but should be tracked).

---

## Test Coverage Recommendations

Add integration tests for:
1. **Concurrent cache access:** Spawn 2 sessions simultaneously, verify cache content is never corrupted
2. **Orphan creation race:** Mock scenario where file is edited between scan and create, verify duplicate detection
3. **Bead creation failure:** Mock `bd create` returning error, verify lfg.md aborts cleanly
4. **Empty backlog caching:** Close all beads, run `discovery_brief_scan()` twice within 60s, verify second call uses cache

---

## Closing Notes

The F3/F4 implementation is **structurally sound** — the async work discovery pattern is correct, and the JSON construction via `jq --arg` is injection-safe. The issues found are **classic concurrency bugs** (TOCTOU, missing atomicity, shared-state races) that will surface under load, not during single-session testing.

**Key lesson:** Any code that writes to `/tmp/` shared files must assume **concurrent writers**. Bash `>` redirection is not atomic. Use temp-then-rename or flock.

The pre-flight check pattern (lines 30-35 in lfg.md) is a **good defensive practice** — extend it to cover bead creation, not just selection.
