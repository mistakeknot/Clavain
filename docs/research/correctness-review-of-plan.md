# Correctness Review: .clavain/ Agent Memory Filesystem Contract

**Plan:** [docs/plans/2026-02-13-clavain-memory-filesystem.md](../plans/2026-02-13-clavain-memory-filesystem.md)
**Reviewer:** Julik (fd-correctness)
**Date:** 2026-02-13

## Executive Summary

Overall assessment: **HIGH CONFIDENCE** — plan is robust with minor improvements needed.

The plan correctly handles the session lifecycle non-concurrency guarantee. Four correctness issues identified:

1. **MEDIUM** — Gitignore append lacks duplicate protection (idempotency gap)
2. **LOW** — Path resolution assumptions not documented for multi-directory workflows
3. **LOW** — TOCTOU race in session-start is benign but should be documented
4. **INFO** — Stat command portability already handled correctly

All issues have clear mitigation strategies. No blocking concerns.

---

## Finding 1: Gitignore Append Lacks Duplicate Protection (MEDIUM)

### Invariant Violation

**Step 1.3** states: "Append `.clavain/scratch/` to `.gitignore` (if not already present)"

The plan does not specify HOW to check "if not already present." Running `/clavain:init` twice could create:

```gitignore
.clavain/scratch/
.clavain/scratch/
```

### Failure Narrative

1. User runs `/clavain:init` — writes `.clavain/scratch/` to `.gitignore` (line 10)
2. User accidentally runs `/clavain:init` again (via command history, typo, or forgotten first run)
3. Implementation does `echo '.clavain/scratch/' >> .gitignore` without `grep -F` check
4. Result: `.gitignore` now has duplicate entries

**Impact:** LOW runtime consequence (gitignore deduplicates internally), but violates idempotency contract and creates file hygiene issues. The doctor check at **Step 4 line 69** uses `grep -q '.clavain/scratch'` which would still PASS with duplicates, hiding the problem.

### Root Cause

Plan says "must be idempotent" (Step 1.5) but doesn't specify the duplicate-check implementation for gitignore appending.

### Recommendation

**In Step 1.3**, replace:

```markdown
3. Append `.clavain/scratch/` to `.gitignore` (if not already present)
```

With:

```markdown
3. Append `.clavain/scratch/` to `.gitignore` using duplicate-safe pattern:
   ```bash
   if ! grep -qF '.clavain/scratch/' .gitignore 2>/dev/null; then
       echo '.clavain/scratch/' >> .gitignore
   fi
   ```
   (Uses `-F` for literal match to avoid regex edge cases with `/` characters)
```

**Why `-F`:** Without it, `grep -q '.clavain/scratch/'` treats `.` as regex wildcard — `_clavain/scratch/` would match incorrectly. `-F` forces literal string matching.

---

## Finding 2: Path Resolution Assumptions Not Documented (LOW)

### Issue

The plan assumes hooks and commands run from the project root directory, but this is not explicitly stated or enforced.

**Evidence:**
- **Step 2** session-handoff.sh line 36: checks `if [[ -d .clavain/ ]]`
- **Step 3** session-start.sh line 49: checks `if [[ -f .clavain/scratch/handoff.md ]]`
- **Step 4** doctor.md line 66: checks `if [ -d .clavain ]`

All use relative paths starting with `.clavain/`.

### Failure Scenario

**Hooks are safe** — Claude Code's hook system sets CWD to project root before invoking hooks.

**Commands may not be safe** — if a user runs `/clavain:init` from a subdirectory:

1. User is in `/root/projects/MyProject/src/`
2. Runs `/clavain:init`
3. Creates `.clavain/` at `/root/projects/MyProject/src/.clavain/` instead of project root
4. session-handoff.sh still runs from project root, checks `.clavain/` there (not found)
5. Handoff goes to root `HANDOFF.md` instead of `.clavain/scratch/handoff.md`
6. State split across two locations — confusion

### Current Behavior

Claude Code commands do NOT automatically run from project root. The `Bash` tool uses Claude's current working directory, which can be a subdirectory if the user `cd`'d there or if files were opened from a subfolder.

### Recommendation

**Add to Step 1 (init.md) before the directory creation logic:**

```markdown
1. Determine the git repository root:
   ```bash
   GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
   if [[ -z "$GIT_ROOT" ]]; then
       echo "ERROR: Not in a git repository. /clavain:init requires git."
       exit 1
   fi
   cd "$GIT_ROOT"
   ```
2. Proceed with directory creation (now guaranteed to be at project root)
```

**Add to Step 2 (session-handoff.sh) before line 36:**

```markdown
# Determine project root for .clavain/ check
if command -v git &>/dev/null && git rev-parse --is-inside-work-tree &>/dev/null 2>&1; then
    PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || PROJECT_ROOT="$PWD"
    CLAVAIN_DIR="${PROJECT_ROOT}/.clavain"
else
    CLAVAIN_DIR=".clavain"  # Fallback to CWD-relative
fi

if [[ -d "$CLAVAIN_DIR" ]]; then
    # Use ${CLAVAIN_DIR}/scratch/handoff.md
fi
```

**Justification:** Git root is the canonical project boundary. Using relative `.clavain/` works ONLY if CWD is already the project root, which is true for hooks but not guaranteed for commands.

---

## Finding 3: Session-Start TOCTOU Race is Benign (LOW - Documentation Issue)

### User Question

"session-start reads handoff.md while session-handoff writes it. Is there a TOCTOU issue?"

### Analysis

**No exploitable TOCTOU** because session-start and session-handoff **never run concurrently within the same session lifecycle.**

#### Hook Execution Model (from Claude Code internals)

1. **SessionStart hook** runs when a new session begins (before first user message)
2. User interacts with Claude
3. **Stop hook** runs when session is terminating (on `/exit`, `/stop`, or timeout)

**Key guarantee:** A session's Stop hook and the NEXT session's SessionStart hook are separated by:
- Stop hook completes → session teardown → new session spawned → SessionStart runs

They are **sequential events across different session instances**, not concurrent events.

#### The TOCTOU That Doesn't Exist

**Hypothetical race (doesn't happen):**
1. Session A's Stop hook writes `handoff.md` (Step 2)
2. Session B's SessionStart hook reads `handoff.md` (Step 3)
3. Race: if both run at same time, read could see partial write

**Why it can't happen:**
- Session A's Stop hook must COMPLETE before Session A terminates
- Session B can only START after Session A terminates
- Therefore: write finishes → file is stable → read begins

**Sentinel file timing (lines 43-46 in session-handoff.sh):**
```bash
SENTINEL="/tmp/clavain-handoff-${SESSION_ID}"
if [[ -f "$SENTINEL" ]]; then
    exit 0
fi
```

This ensures the hook only fires once per session. The sentinel check happens BEFORE any `.clavain/` directory checks, so even if a user manually triggered two sessions in rapid succession, only one would write the handoff.

### Different Session IDs = No Collision

**Step 2** will write to `.clavain/scratch/handoff.md` for Session A.
**Step 3** will read the SAME `.clavain/scratch/handoff.md` for Session B.

There is NO per-session file naming (no `handoff-${SESSION_ID}.md`). This is **intentional** — the handoff is session-agnostic state for "the next session."

**Cross-session race (also doesn't happen):**
- User opens two Claude sessions (A and B) in the same project simultaneously
- Session A's Stop hook writes `handoff.md`
- Session B's SessionStart hook reads `handoff.md`

**Mitigation:** Session IDs are unique, so sentinels are distinct (`/tmp/clavain-handoff-${SESSION_A}`, `/tmp/clavain-handoff-${SESSION_B}`). Both Stop hooks could fire, but the LAST one to finish would overwrite `handoff.md`. The next new session would read that final state. This is **correct behavior** — the most recent session's context is what matters.

### Recommendation

**Add to Step 2 (session-handoff.sh) documentation:**

```markdown
**Concurrency note:** This hook may run from multiple simultaneous sessions in the same project. The last session to complete overwrites `.clavain/scratch/handoff.md`, which is correct — the most recent context is preserved for the next session.
```

**Add to Step 3 (session-start.sh) documentation:**

```markdown
**Concurrency note:** SessionStart reads handoff.md AFTER the previous session's Stop hook completes (sequential lifecycle). No TOCTOU risk. If multiple sessions were active, the last one to finish writing handoff.md "wins" — this is expected behavior.
```

**No code changes needed.** This is a documentation clarification, not a bug.

---

## Finding 4: Stat Command Portability Correctly Handled (INFO)

### User Question

The plan's doctor.md check (Step 4, line 76) uses:

```bash
stat -c %Y .clavain/scratch/handoff.md 2>/dev/null || stat -f %m .clavain/scratch/handoff.md 2>/dev/null
```

Is this portable?

### Analysis

**YES — already correct.**

The pattern `stat -c %Y ... || stat -f %m ...` is the standard cross-platform idiom for getting file modification timestamps:

- **GNU stat** (Linux): `-c %Y` outputs Unix timestamp
- **BSD stat** (macOS): `-f %m` outputs Unix timestamp
- **Fallback chain:** try GNU, fall back to BSD, then fall back to `echo $(date +%s)` (current time) if both fail

**Evidence from existing Clavain code:**

- `hooks/session-start.sh:99` uses identical pattern
- `hooks/auto-publish.sh:58` uses identical pattern
- `hooks/auto-compound.sh:57` uses identical pattern
- `hooks/sprint-scan.sh:243` uses identical pattern

This is an established convention in the codebase.

### Recommendation

**No changes needed.** The plan correctly follows existing portability patterns.

**Optional clarity improvement for Step 4, line 76:**

Add a comment in the code snippet:

```bash
# Portable: stat -c (GNU) || stat -f (BSD)
age=$(( ($(date +%s) - $(stat -c %Y .clavain/scratch/handoff.md 2>/dev/null || stat -f %m .clavain/scratch/handoff.md 2>/dev/null || echo $(date +%s))) / 86400 ))
```

---

## Additional Observations

### Non-Git Projects (from brainstorm line 165)

The brainstorm asks: "What about projects that aren't git repos?"

**Current plan behavior:**
- **Step 1** (init.md) has no git requirement specified
- **Step 2** (session-handoff.sh line 52) checks `git rev-parse --is-inside-work-tree` and only processes git repos
- **Step 4** (doctor.md) checks `.clavain/` existence but not git

**Consequence:**
- User can run `/clavain:init` in a non-git directory — creates `.clavain/` successfully
- session-handoff.sh will skip handoff logic (exits early at line 52's git check)
- `.clavain/scratch/handoff.md` never gets written, but directory exists
- **No corruption risk** — graceful degradation

**Recommendation:** If non-git support is desired, **Step 2 needs refactoring**. Currently the git check is line 52, which is BEFORE the `.clavain/` check (line 36 in the plan). To support non-git projects:

1. Move git-specific checks (lines 52-57) INSIDE the `.clavain/` conditional
2. Change from "is this a git repo with uncommitted changes" to "is there ANY signal of incomplete work"
3. Non-git signals: existence of `.clavain/scratch/*.tmp` files, uncommitted learnings, etc.

**If non-git is NOT a goal:** Add explicit check to Step 1 (see Finding 2 recommendation) to require git.

### Test Count Assertion Update (Step 6)

Plan correctly notes (line 122): "Structural tests hardcode command count at 37. Will need updating to 38."

**Verification needed:**
```bash
grep -r "37" tests/structural/
```

Likely locations:
- `tests/structural/test_structure.py` has assertion like `assert len(commands) == 37`

**Action after implementing Step 1:** Update the hardcoded count AND verify test passes:

```bash
uv run --project tests pytest tests/structural/test_structure.py::test_command_count -xvs
```

### gen-catalog.py Auto-Detection (Step 5)

Plan states: "gen-catalog.py will auto-detect and propagate this."

**Verify the count pattern expectation:**

From MEMORY.md:
> gen-catalog.py expects pattern `\d+ skills, \d+ agents, and \d+ commands` in SKILL.md

After creating `commands/init.md`, running `python3 scripts/gen-catalog.py` should:
1. Detect 38 command files (currently 37)
2. Update all locations with the new count
3. Update `using-clavain/SKILL.md` line 7's count summary

**Test the propagation:**
```bash
python3 scripts/gen-catalog.py --dry-run  # Check what would change
python3 scripts/gen-catalog.py            # Apply changes
git diff                                   # Verify updates
```

---

## Correctness Checklist

| Concern | Status | Severity | Mitigation |
|---------|--------|----------|------------|
| Gitignore duplicate append | ISSUE | MEDIUM | Add `grep -qF` guard before append |
| Path resolution from subdirs | ISSUE | LOW | Add git root resolution to init.md |
| Session-start/handoff TOCTOU | BENIGN | INFO | Document sequential lifecycle, no code change |
| Stat portability | CORRECT | INFO | Already using portable pattern |
| Idempotency of init command | AT-RISK | MEDIUM | Fixed by gitignore duplicate guard |
| Non-git project support | UNDEFINED | INFO | Clarify scope: require git or refactor handoff |
| Test count assertion | TRACKED | INFO | Update after Step 1 implementation |

---

## Final Recommendations

### MUST FIX (Before Implementation)

1. **Step 1.3** — Add `grep -qF` duplicate guard for gitignore append
2. **Step 1** — Add git root resolution logic (or explicitly document "must run from project root")

### SHOULD ADD (For Clarity)

3. **Step 2 & 3** — Add concurrency notes about sequential lifecycle and multi-session behavior
4. **Step 4** — Optional: add portability comment to stat command

### NICE TO HAVE (For Future Iterations)

5. **PRD clarity** — Document whether non-git projects are in scope (affects session-handoff logic)
6. **Verification steps** — Add explicit test commands to Step 6 for count assertions

---

## Failure Mode Summary

**Most likely failure:** User runs `/clavain:init` from a subdirectory, creates `.clavain/` in wrong location, state split across root and subdir.

**Mitigation:** Add git root resolution (Finding 2).

**Second most likely failure:** Duplicate gitignore entries from repeated init runs.

**Mitigation:** Add grep guard (Finding 1).

**Least likely failure:** TOCTOU race on handoff.md read/write.

**Reality:** Can't happen due to sequential session lifecycle (Finding 3).

---

## Correctness Verdict

**APPROVED with minor fixes.**

The plan demonstrates strong correctness reasoning:
- Idempotency is a stated requirement
- Portability patterns match existing code
- Session lifecycle isolation is correctly assumed
- File structure is simple (no complex state machines)

The two MEDIUM issues (gitignore duplicates, path resolution) are straightforward fixes with clear implementation guidance above.

After applying Findings 1 and 2 recommendations, the plan is production-ready.
