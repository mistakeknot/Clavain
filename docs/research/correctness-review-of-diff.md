# Correctness Review: Agent Memory Handoff System

**Date:** 2026-02-13
**Reviewer:** Julik (fd-correctness)
**Scope:** Session handoff lifecycle (session-handoff.sh writes, session-start.sh reads), doctor.md checks, test count update

## Executive Summary

Reviewed changes implement a handoff file system where Stop hooks write `.clavain/scratch/handoff.md` and next session's Start hook reads it. Found **3 P2 issues** (edge case brittleness, no P1 data corruption risks), **1 resolved test count fix**.

**Severity Key:**
- P1: Data corruption, race-induced corruption, production-fatal failure
- P2: Edge case failure, probabilistic error under load, correctness violation in uncommon scenarios
- P3: Observability gap, minor inconsistency, low-consequence edge case

---

## P2-1: head -40 with set -e fails silently when file < 40 lines

**Location:** `hooks/session-start.sh:135`

```bash
handoff_content=$(head -40 ".clavain/scratch/handoff.md" 2>/dev/null) || handoff_content=""
```

**Issue:**

When `.clavain/scratch/handoff.md` has fewer than 40 lines (expected case for 10-20 line handoff files), `head -40` succeeds and returns all content — **this is correct behavior**.

However, if the file is exactly 40 lines or less, `head` returns exit code 0. If more than 40 lines, `head` also returns 0 (truncates successfully). The `|| handoff_content=""` fallback only fires on command failure (file unreadable, permission denied, etc.).

The real risk is **not with head**, but with the subsequent JSON embedding. If `handoff_content` contains content that breaks `escape_for_json`, the session-start hook will output malformed JSON and **fail Claude Code's session initialization silently** (session starts with no injected context, no error surfaced to user).

**Failure scenario:**

1. User writes handoff with unusual characters (e.g., `\x00`, `\x1f`, Unicode control chars)
2. `head -40` succeeds, passes raw content to `escape_for_json`
3. `escape_for_json` uses bash parameter substitution loops (lines 35-41 in lib.sh) — if input contains null bytes or triggers bash edge cases, the loop may produce partial output
4. session-start outputs malformed JSON: `{"hookSpecificOutput": {"additionalContext": "...[broken escaping]..."}}`
5. Claude Code's hook parser rejects JSON → session starts with **no context injection** (no using-clavain skill, no handoff, no discovery state)
6. User gets a "clean" session that silently lost all cross-session memory

**Evidence from code:**

- session-start.sh runs under `set -euo pipefail` (line 4)
- If `escape_for_json` returns empty string due to edge case, `handoff_context` becomes empty → additionalContext loses handoff section but remains valid JSON (silent data loss, not crash)
- If `escape_for_json` produces invalid JSON (e.g., unclosed quote), Claude Code silently drops the entire hook output

**Fix:**

Add length validation and checksum verification:

```bash
if [[ -f ".clavain/scratch/handoff.md" ]]; then
    handoff_content=$(head -40 ".clavain/scratch/handoff.md" 2>/dev/null) || handoff_content=""
    if [[ -n "$handoff_content" ]]; then
        # Verify content is safe for JSON embedding (no null bytes, valid UTF-8)
        if echo "$handoff_content" | LC_ALL=C grep -q $'\x00'; then
            echo "WARN: handoff.md contains null bytes, skipping" >&2
            handoff_content=""
        elif ! echo "$handoff_content" | iconv -f UTF-8 -t UTF-8 >/dev/null 2>&1; then
            echo "WARN: handoff.md is not valid UTF-8, skipping" >&2
            handoff_content=""
        else
            handoff_context="\\n\\n**Previous session context:**\\n$(escape_for_json "$handoff_content")"
        fi
    fi
fi
```

Or add a JSON validation step before outputting:

```bash
# Build final JSON first, validate before output
FINAL_JSON=$(cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "...${handoff_context}"
  }
}
EOF
)

# Validate JSON before output
if ! echo "$FINAL_JSON" | jq empty 2>/dev/null; then
    echo "ERROR: session-start produced invalid JSON, dropping handoff context" >&2
    # Rebuild without handoff
    FINAL_JSON=$(cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "...${discovery_context}"
  }
}
EOF
    )
fi

echo "$FINAL_JSON"
```

**Impact:** Medium. Handoff files are user-written markdown (typically ASCII + basic markdown), so exotic characters are rare. But a malicious or corrupted handoff file could silently break context injection for all future sessions until `.clavain/scratch/handoff.md` is deleted.

---

## P2-2: ls | wc -l returns "0" with trailing space on some systems

**Location:** `commands/doctor.md:86`

```bash
learnings_count=$(ls .clavain/learnings/*.md 2>/dev/null | wc -l | tr -d ' ')
```

**Issue:**

When `.clavain/learnings/` is empty or does not exist, `ls .clavain/learnings/*.md` outputs nothing and exits 1 (glob expansion failure). The pipeline continues (`2>/dev/null` suppresses errors), `wc -l` reads empty stdin and outputs `0` (with possible leading spaces on some systems).

The `tr -d ' '` correctly strips spaces, producing `0`.

**However**, the real correctness issue is: **what if `.clavain/learnings/` exists but contains no .md files?**

- `ls .clavain/learnings/*.md` → exits 2 (no match), stderr: "ls: cannot access '.clavain/learnings/*.md': No such file or directory"
- `2>/dev/null` suppresses the error
- `wc -l` reads empty stdin → outputs `0`
- Output: `learnings: 0 entries` ← **Correct behavior**

**What if `.clavain/learnings/` contains a file named `foo.md\nbar.md`?** (newline in filename)

- `ls .clavain/learnings/*.md` outputs two lines: `foo.md`, `bar.md`
- `wc -l` counts 2 lines
- Output: `learnings: 2 entries` ← **Incorrectly counts one file as two**

**Fix:**

Use a more robust counting method:

```bash
if [ -d .clavain/learnings ]; then
    learnings_count=$(find .clavain/learnings -maxdepth 1 -name '*.md' -type f 2>/dev/null | wc -l | tr -d ' ')
else
    learnings_count=0
fi
echo "  learnings: ${learnings_count} entries"
```

Or use a null-terminated approach:

```bash
learnings_count=$(find .clavain/learnings -maxdepth 1 -name '*.md' -type f -print0 2>/dev/null | grep -zc '' || echo 0)
echo "  learnings: ${learnings_count} entries"
```

**Impact:** Low. Newlines in .md filenames are extremely rare (filesystem edge case), and this is a diagnostic command (no data mutation). But the pattern (`ls | wc -l`) is a known anti-pattern and should be fixed for correctness hygiene.

---

## P2-3: stat fallback chain assumes 0 on all failures, masks permission errors

**Location:** `commands/doctor.md:77`, `hooks/session-start.sh:99`

```bash
# doctor.md:77
mtime=$(stat -c %Y .clavain/scratch/handoff.md 2>/dev/null || stat -f %m .clavain/scratch/handoff.md 2>/dev/null || echo 0)

# session-start.sh:99
file_mtime=$(stat -c %Y "$VERSIONS_FILE" 2>/dev/null || stat -f %m "$VERSIONS_FILE" 2>/dev/null || echo 0)
```

**Issue:**

The fallback chain tries GNU stat (`-c %Y`), then BSD stat (`-f %m`), then defaults to `0` on any failure. This conflates three failure modes:

1. **File does not exist** → mtime=0 is semantically correct (treat as "never modified")
2. **Permission denied** → mtime=0 **silently hides access violation** (user should be warned)
3. **stat binary not found** → mtime=0 is a reasonable fallback (diagnostic degradation)

**Failure scenario (doctor.md:77):**

1. `.clavain/scratch/handoff.md` exists but is owned by root with mode 0600
2. Claude Code runs as claude-user (non-root)
3. `stat -c %Y` fails with EACCES, stderr suppressed by `2>/dev/null`
4. `stat -f %m` also fails (GNU/Linux system doesn't have `-f`)
5. Fallback `echo 0` executes → `mtime=0`
6. Age calculation: `age=$(( ($(date +%s) - 0) / 86400 ))` → age = current timestamp in days (e.g., 19751 days since epoch)
7. Doctor output: `WARN: stale handoff (19751 days old)` ← **Misleading error message**

**Correct behavior:** Should detect permission failure and report "handoff.md exists but is unreadable (check permissions)"

**Fix:**

Add explicit existence and readability checks:

```bash
if [ -f .clavain/scratch/handoff.md ]; then
    if [ ! -r .clavain/scratch/handoff.md ]; then
        echo "  WARN: handoff.md exists but is unreadable (check permissions)"
    else
        mtime=$(stat -c %Y .clavain/scratch/handoff.md 2>/dev/null || stat -f %m .clavain/scratch/handoff.md 2>/dev/null || echo 0)
        if [ "$mtime" -gt 0 ]; then
            age=$(( ($(date +%s) - mtime) / 86400 ))
            if [ "$age" -gt 7 ]; then
                echo "  WARN: stale handoff (${age} days old)"
            fi
        else
            echo "  WARN: could not determine handoff.md age (stat failed)"
        fi
    fi
fi
```

**Impact:** Low-Medium. Permission failures are rare on single-user systems, but the `cc` (claude-user) setup described in the CLAUDE.md context shows this is a **real multi-user scenario** where ACL drift can cause root-owned files to become unreadable by claude-user. The misleading "19751 days old" error would send users down the wrong debugging path.

---

## P3-1: Test count updated without adding new test coverage (RESOLVED)

**Location:** `tests/structural/test_commands.py:23`

```python
assert len(files) == 38, (
    f"Expected 38 commands, found {len(files)}: {[f.stem for f in files]}"
)
```

**Issue:**

The command count increased from 37 → 38, but no new `.md` file was added in this diff. This suggests `doctor.md` already existed and was modified (sections added), not created.

**Verification:**

```bash
$ ls /root/projects/Clavain/commands/*.md 2>/dev/null | wc -l
38
```

**Resolution:**

The test count change is **correct** — there are indeed 38 command files. The previous test was wrong (test said 37, actual was 38). This diff fixes a pre-existing test bug (false negative that would have failed on next test run).

**Verdict:** No action required. Test count fix is valid.

---

## Lifecycle Correctness Analysis

### Question 1: session-handoff writes, session-start reads — is the lifecycle correct?

**Answer:** Yes, with one edge case.

**Write path (session-handoff.sh):**

- Runs as Stop hook (line 2 comment: "Stop hook: auto-handoff when session ends")
- Detects incomplete work signals (uncommitted changes, in-progress beads)
- If `.clavain/` exists, creates `.clavain/scratch/` and sets `HANDOFF_PATH=".clavain/scratch/handoff.md"`
- **Blocks session stop** (outputs `{"decision":"block","reason":"..."}`) and asks Claude to write the handoff file
- Uses double sentinel pattern (lines 35-40, 43-46): `/tmp/clavain-stop-${SESSION_ID}` and `/tmp/clavain-handoff-${SESSION_ID}` to prevent re-triggering

**Read path (session-start.sh):**

- Runs as Start hook for the **next session** (different session ID)
- Reads `.clavain/scratch/handoff.md` if it exists (lines 132-139)
- Caps content at 40 lines (`head -40`)
- Embeds into `additionalContext` via `escape_for_json`

**Correctness:**

- **Time ordering:** Stop hook runs before session ends → file is written. Next session's Start hook runs on new session → file is read. ✓
- **File persistence:** `.clavain/scratch/handoff.md` lives in project directory (not `/tmp`), survives across sessions. ✓
- **No race between write/read:** Different sessions, sequential (Stop completes before next Start begins). ✓

**Edge case risk:**

If **two sessions** run concurrently in the same project (e.g., user runs `cc` in two terminals, both in same directory):

1. Session A's Stop hook writes `.clavain/scratch/handoff.md`
2. Session B's Stop hook **also** writes `.clavain/scratch/handoff.md` (clobbers A's file)
3. Next session reads B's handoff, loses A's context

**Mitigation:** Add session ID to filename:

```bash
HANDOFF_PATH=".clavain/scratch/handoff-${SESSION_ID}.md"
```

Then session-start reads all handoff files:

```bash
handoff_context=""
for f in .clavain/scratch/handoff-*.md; do
    [ -f "$f" ] || continue
    content=$(head -40 "$f" 2>/dev/null) || continue
    handoff_context="${handoff_context}\\n$(escape_for_json "$content")"
done
```

**Impact of current design:** Low. Concurrent sessions in the same directory are rare (user would need to explicitly `cd` to same path in two terminals and run `cc` in both). But the pattern is **not concurrency-safe** if this becomes common usage.

**Verdict:** Lifecycle is correct for single-session-per-project usage (expected case), **not safe for concurrent sessions** (edge case).

---

### Question 2: head -40 cap with escape_for_json — does it work correctly?

**Answer:** Yes for well-formed input, **no for malformed input** (covered in P2-1).

**Mechanics:**

1. `head -40 ".clavain/scratch/handoff.md"` reads first 40 lines (or fewer if file is shorter)
2. Output is stored in `handoff_content` variable (bash string)
3. `escape_for_json "$handoff_content"` processes the string:
   - Escapes backslashes, quotes, control chars
   - Converts `\n` (bash literal newline) to `\\n` (JSON escape sequence)
4. Embedded into JSON heredoc (line 146)

**Correctness verification:**

- **40-line cap:** Works. If file is 100 lines, only first 40 are read. If file is 10 lines, all 10 are read. ✓
- **Newline handling:** bash captures multi-line output into `handoff_content` with embedded newlines. `escape_for_json` replaces each `$'\n'` with `\\n` (line 31 of lib.sh). ✓
- **JSON embedding:** The escaped string is concatenated into `additionalContext` (line 146). Final JSON uses heredoc (lines 142-148), so no quote-escaping issues in the heredoc itself. ✓

**Edge case failure (P2-1):**

If `handoff_content` contains characters that `escape_for_json` mishandles (e.g., `\x00`, or triggers bash parameter substitution edge cases in the loop at lines 35-41), the output may be truncated or malformed.

**Example:**

```bash
# handoff.md contains:
Done: Fixed bug
Context: User said "use $SPECIAL_VAR" but meant literal text

# After head -40:
handoff_content='Done: Fixed bug\nContext: User said "use $SPECIAL_VAR" but meant literal text'

# After escape_for_json:
# If SPECIAL_VAR is unset and nounset is active, this COULD cause issues in naive implementations
# But escape_for_json uses ${s//old/new} which treats $SPECIAL_VAR as literal string data (already captured in variable), not variable expansion
# So this is SAFE. ✓
```

**Actual risk:** Not variable expansion, but **control characters** (`\x00` through `\x1f`) that the `for i in {1..31}` loop (lines 35-41) must handle. If the loop has bugs (e.g., off-by-one, missing case), some control chars might pass through unescaped.

**Verdict:** Works correctly for typical markdown content (ASCII + UTF-8 text). **Unvalidated for adversarial input** (embed binary data, null bytes, Unicode edge cases).

---

### Question 3: doctor.md ls | wc -l when no files exist

Covered in **P2-2**. Summary: works correctly (outputs `0`), but pattern is fragile for filenames with newlines.

---

### Question 4: stat portability fallback chain

Covered in **P2-3**. Summary: works for typical cases (file exists, readable), **fails to distinguish permission errors from missing files** (both default to `mtime=0`).

---

### Question 5: session-handoff mkdir -p with || true under set -euo pipefail

**Location:** `hooks/session-handoff.sh:81`

```bash
mkdir -p ".clavain/scratch" 2>/dev/null || true
```

**Context:** Script runs under `set -euo pipefail` (line 16).

**Question:** Does `|| true` correctly prevent `set -e` from aborting on mkdir failure?

**Answer:** Yes. ✓

**Mechanics:**

- `set -e`: Exit immediately if any command returns non-zero, **unless the command is part of a conditional** (e.g., in `if`, `while`, `||`, `&&` chains)
- `mkdir -p ".clavain/scratch" 2>/dev/null || true`:
  - If `mkdir` succeeds (exit 0), `|| true` doesn't execute (short-circuit)
  - If `mkdir` fails (e.g., permission denied, read-only filesystem), `|| true` executes and returns 0
  - The entire expression returns 0, so `set -e` does not abort
- `2>/dev/null` suppresses stderr (user won't see "Permission denied" warnings)

**Correctness:**

- If `.clavain/scratch/` already exists, `mkdir -p` is a no-op (exit 0). ✓
- If parent `.clavain/` does not exist, `mkdir -p` creates both (exit 0). ✓
- If filesystem is read-only or permission denied, `mkdir -p` fails, `|| true` catches it, script continues with `HANDOFF_PATH="HANDOFF.md"` (fallback to root). ✓

**Edge case: what if .clavain exists but is a regular file (not a directory)?**

```bash
touch .clavain  # Create file named .clavain
# Now try to mkdir -p .clavain/scratch
```

- `mkdir -p .clavain/scratch` → fails with "File exists" error (exit 1)
- `2>/dev/null` suppresses error
- `|| true` catches failure
- `HANDOFF_PATH` remains `HANDOFF.md`
- Script continues, outputs block message referencing `HANDOFF.md` (not `.clavain/scratch/handoff.md`)

**Result:** Script doesn't crash, but the behavior is **silent fallback** (no warning to user that `.clavain` is corrupted). This is acceptable for a Stop hook (crashing would be worse), but the doctor command should check for this:

```bash
if [ -e .clavain ] && [ ! -d .clavain ]; then
    echo "  ERROR: .clavain exists but is not a directory"
fi
```

**Verdict:** `|| true` pattern is correct. No crash risk. Silent fallback is acceptable for Stop hook context. **Recommend adding validation to doctor.md** (P3 observability gap).

---

## Additional Observations (No Action Required)

### 1. Handoff file not explicitly deleted after read

session-start.sh reads `.clavain/scratch/handoff.md` but does not delete it. This means:

- Handoff persists across multiple sessions until overwritten
- If a user starts 3 sessions in a row, all 3 see the same handoff (from the first Stop event)
- Stale handoff warning triggers after 7 days (doctor.md:80)

**Intent:** Likely intentional (handoff is "last known state" until next incomplete-work signal). User can manually delete if stale.

**Correctness implication:** Not a bug, but behavior should be documented. If intent is "one-time consumption", add deletion after read:

```bash
if [[ -f ".clavain/scratch/handoff.md" ]]; then
    handoff_content=$(head -40 ".clavain/scratch/handoff.md" 2>/dev/null) || handoff_content=""
    if [[ -n "$handoff_content" ]]; then
        handoff_context="\\n\\n**Previous session context:**\\n$(escape_for_json "$handoff_content")"
        # Mark as consumed
        mv ".clavain/scratch/handoff.md" ".clavain/scratch/handoff.md.consumed" 2>/dev/null || true
    fi
fi
```

### 2. No size cap on handoff file itself

session-handoff prompts Claude to write a "10-20 line" handoff, but doesn't enforce this. If Claude writes a 500-line file, `head -40` caps the read to 40 lines, but:

- The file remains 500 lines on disk
- Next session reads first 40 lines, loses lines 41-500
- No warning that content was truncated

**Mitigation:** Add size warning to doctor.md:

```bash
if [ -f .clavain/scratch/handoff.md ]; then
    line_count=$(wc -l < .clavain/scratch/handoff.md 2>/dev/null || echo 0)
    if [ "$line_count" -gt 40 ]; then
        echo "  WARN: handoff.md is ${line_count} lines (only first 40 will be read)"
    fi
fi
```

---

## Recommendations Summary

| ID | Severity | Action | Effort |
|----|----------|--------|--------|
| P2-1 | Medium | Add input validation before `escape_for_json` (check for null bytes, invalid UTF-8) or add JSON validation before output | 10 lines |
| P2-2 | Low | Replace `ls \| wc -l` with `find ... -type f \| wc -l` or null-delimited count | 3 lines |
| P2-3 | Medium | Add `-r` check before `stat` fallback, distinguish permission errors from missing files | 8 lines |
| P3-1 | N/A | ~~Verify test count~~ (resolved: test fix is valid, 38 commands confirmed) | N/A |
| Obs-1 | Info | Document handoff persistence behavior (or add `.consumed` rename pattern) | Doc or 2 lines |
| Obs-2 | Info | Add doctor.md check for oversized handoff files (>40 lines) | 5 lines |
| Obs-3 | Info | Add doctor.md check for `.clavain` file-vs-directory corruption | 3 lines |

**Total incremental effort:** ~30 lines of defensive code + 1 verification step.

---

## Conclusion

The handoff lifecycle is **correct for single-session usage** (the expected case). No data corruption or race-induced corruption risks in the primary flow. The P2 findings are **edge case brittleness** (malformed input, permission failures, concurrent sessions) that should be hardened but are unlikely to occur in typical development workflows.

**Approve for merge** with the recommendation to address P2-1 (input validation) and P2-3 (permission error clarity) in a follow-up commit, as these are observability/robustness improvements rather than blocking correctness failures.
