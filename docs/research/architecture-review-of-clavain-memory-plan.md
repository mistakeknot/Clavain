# Architecture Review: .clavain/ Memory Filesystem Implementation Plan

**Bead:** Clavain-d4ao
**Reviewer:** fd-architecture (flux-drive)
**Date:** 2026-02-13
**Plan:** [docs/plans/2026-02-13-clavain-memory-filesystem.md](../plans/2026-02-13-clavain-memory-filesystem.md)
**PRD:** [docs/prds/2026-02-13-clavain-memory-filesystem.md](../prds/2026-02-13-clavain-memory-filesystem.md)

## Executive Summary

The plan defines a sound v1 contract with appropriate boundaries and scope discipline. Two **critical correctness issues** must be fixed: session-handoff writes to the wrong path (hardcoded "handoff.md" instead of "scratch/handoff.md"), and the doctor check uses unsafe shell redirection precedence. One **architectural boundary violation** was found where session-start loads weather.md without a clear specification of its structure. No over-engineering detected — scope is appropriately minimal for v1.

**Recommendation:** Fix the three issues below, then proceed. The design is solid.

---

## 1. Boundaries & Coupling

### 1a. Module Boundaries — PASS with Advisory

The directory structure correctly separates ephemeral (`scratch/`) from durable (`learnings/`, `contracts/`) state. The gitignore contract is precise and enforceable.

**Boundary mapping:**
- `scratch/` — ephemeral, session-local, gitignored
- `learnings/` — durable, project-specific, committed
- `contracts/` — durable, review-injected, committed
- `weather.md` — semi-permanent config, committed

**Advisory:** The plan defers writing to `learnings/` (Phase 3) and reading from it (Phase 4), which is correct sequencing. However, the YAML schema specified in the PRD (lines 63-81) uses fields (`category`, `severity`, `provenance`) that are **not compatible with the existing knowledge format** in `config/flux-drive/knowledge/README.md` (lines 8-17, which uses `lastConfirmed` and `provenance` only). This schema mismatch is deferred to Phase 3, but it should be flagged in the plan's Risks section so implementers know they'll need a schema migration strategy.

**Fix:** Add to Step 6 verification: "Schema alignment TBD in Phase 3 — PRD learnings format differs from existing knowledge/ format."

---

### 1b. Hook Coupling — FAIL (Critical)

**Issue 1: session-handoff path construction is wrong**

Plan Step 2 (line 38) says:
> "change the handoff instruction to write to `.clavain/scratch/handoff.md`"

But the current `session-handoff.sh` (line 80) writes to:
```bash
1. Write a brief HANDOFF.md in the project root
```

This is a **string literal in the Stop hook output**. The plan says to "change the handoff instruction" but doesn't specify **what the new instruction text should be**. More critically, the path should be `.clavain/scratch/handoff.md`, not `.clavain/handoff.md` (which is what a naive implementer might write).

**Fix:** Step 2 must specify the **exact instruction text**:
```markdown
Change line 80 from:
  "1. Write a brief HANDOFF.md in the project root"
to:
  "1. Write a brief handoff file to .clavain/scratch/handoff.md"
```

**Impact if not fixed:** Handoff files end up in `.clavain/handoff.md` (not gitignored, wrong location) or session-start fails to find them.

---

**Issue 2: session-start and session-handoff are coupled via implicit contract**

The hooks share state via a file path (`.clavain/scratch/handoff.md`) but the plan doesn't specify:
- Who is responsible for **creating** `.clavain/scratch/` if it doesn't exist?
- What happens if `.clavain/` exists but `scratch/` was removed (e.g., `git clean -fdx`)?

Plan Step 2 (line 38) says:
> "Ensure `.clavain/scratch/` directory exists (create if needed)"

But Step 3 (session-start) doesn't mention this. If session-handoff creates `scratch/`, but session-start expects it to already exist, you have asymmetric initialization.

**Fix:** Add to Step 3 (session-start):
```markdown
Before reading .clavain/scratch/handoff.md, check that the directory exists.
Do not create it — only session-handoff creates scratch/ (to avoid auto-creating
gitignored dirs that confuse users who expect clean state).
```

**Fix:** Add to Risks section:
```markdown
- **Scratch dir lifecycle**: session-handoff creates scratch/, session-start reads it.
  If scratch/ is manually deleted, next session-start won't find handoff but will not fail.
  This is correct behavior — gitignored dirs can disappear.
```

---

### 1c. Dependency Direction — PASS

Hooks depend on `.clavain/` presence (filesystem), not vice versa. The contract is a **convention**, not a hard dependency. Hooks degrade gracefully when `.clavain/` is absent (Step 2 line 40, Step 3 line 52). No forbidden upward dependencies detected.

---

### 1d. Integration Seams — PASS with Advisory

The plan correctly isolates failure modes:
- If `.clavain/` doesn't exist → fallback to root `HANDOFF.md` (current behavior)
- If `scratch/handoff.md` is empty → session-start skips injection (Step 3 line 51)
- If `.gitignore` append fails → `/init` continues (idempotent, line 24)

**Advisory:** The doctor check (Step 4) calls `stat -c %Y` (GNU) with fallback to `stat -f %m` (BSD), but the **precedence is wrong**:

```bash
age=$(( ($(date +%s) - $(stat -c %Y .clavain/scratch/handoff.md 2>/dev/null || stat -f %m .clavain/scratch/handoff.md 2>/dev/null || echo $(date +%s))) / 86400 ))
```

If `stat -c` fails (BSD), the `2>/dev/null` suppresses the error, but the **exit code is non-zero**, so `||` fires the BSD stat. If **both** fail, `|| echo $(date +%s)` fires, returning **age 0** (file is "current").

**Problem:** On a system where the file doesn't exist, this returns age 0 instead of skipping the check.

**Fix:** Rewrite the doctor check logic:
```bash
if [ -f .clavain/scratch/handoff.md ]; then
  mtime=$(stat -c %Y .clavain/scratch/handoff.md 2>/dev/null || stat -f %m .clavain/scratch/handoff.md 2>/dev/null || echo 0)
  if [ "$mtime" -gt 0 ]; then
    age=$(( ($(date +%s) - mtime) / 86400 ))
    if [ "$age" -gt 7 ]; then
      echo "  WARN: stale handoff (${age} days old)"
    fi
  fi
fi
```

---

## 2. Pattern Analysis

### 2a. Existing Patterns — PASS

The plan reuses existing conventions:
- **YAML frontmatter + markdown body** — matches `config/flux-drive/knowledge/` format (line 63-81)
- **Hook-driven initialization** — matches session-start/session-handoff patterns
- **Opt-in via command** — matches `/setup`, `/doctor`, `bd init` precedent
- **Gitignore append** — common pattern (e.g., `bd init` does this)

No new patterns introduced. No drift from codebase conventions.

---

### 2b. Anti-Patterns — WARNING

**Duplication risk:** The plan creates a **parallel knowledge system** (`.clavain/learnings/`) alongside the existing global one (`config/flux-drive/knowledge/`). The PRD (line 39) says:
> "Compound writes: Project-local when `.clavain/` exists, global fallback otherwise"

But this creates a **split-brain problem**:
- Some learnings are global (apply to all projects)
- Some learnings are project-local (apply only here)
- Which takes precedence when both exist?

The plan defers this to Phase 3 (PRD line 29), but the PRD's "Design Decisions" table (line 39) says:
> "Different purposes: project gotchas vs. plugin review patterns"

This is **not a technical solution**, it's a **policy**. Without a concrete merge strategy or precedence rule, Phase 3 implementers will have to invent one, risking inconsistency.

**Not a blocker for v1** (Phase 3 is deferred), but flag it in the Risks section.

**Fix:** Add to Risks:
```markdown
- **Knowledge split-brain**: Phase 3 must define precedence rules for global vs.
  project-local learnings. Current plan assumes "different purposes" but doesn't
  specify how agents choose which to inject.
```

---

### 2c. Naming Consistency — PASS

- `scratch/` — clearly ephemeral (matches `.pytest_cache/`, `node_modules/`)
- `learnings/` — matches existing `knowledge/` terminology
- `contracts/` — clear ownership (matches `docs/solutions/` semantic level)
- `weather.md` — metaphor is consistent with Clavain's model-routing language

No naming drift detected.

---

## 3. Simplicity & YAGNI

### 3a. Scope Discipline — PASS (Excellent)

The plan **correctly defers**:
- Index generation (`/index:update`, `/genrefy`) — Phase 2
- Auto-compound writing to `.clavain/learnings/` — Phase 3
- Agent reading from `.clavain/learnings/` — Phase 4
- Downstream features (scenarios, pipelines, CXDB, provenance) — separate beads

**Only implements**:
1. Directory structure (empty scaffolding)
2. Session-handoff relocation (file path change)
3. Session-start reading (file read + inject)
4. Doctor check (file existence + staleness)

This is **the minimum viable contract**. No premature abstractions.

---

### 3b. Unnecessary Abstractions — WARNING (Non-Blocking)

**Issue:** The plan includes `weather.md` (Step 1 line 23, Step 3 line 52) but:
- Step 1 says "create weather.md with default model routing content (simple template)"
- Step 3 says "inject a one-line summary of model routing preferences if present"

**Problem:** The plan doesn't specify:
- What the template content is
- How to parse weather.md (is it YAML? Markdown? Plain text?)
- What "one-line summary" means (extract first line? generate a summary?)

This is an **underspecified feature**. If session-start is expected to parse and inject weather.md, the format must be defined. If it's just "read first line", say so.

**Current session-start** (line 48-138) injects structured context from hooks and companions. Adding weather.md without a clear schema creates a **leaky abstraction** — implementers won't know what to inject.

**Fix:** Either:
1. **Defer weather.md to Phase 2** (remove from Step 1 and Step 3), OR
2. **Specify the format** in Step 1:
   ```markdown
   Create .clavain/weather.md with:
   ```yaml
   # Model routing preferences
   - Reviews: opus-4
   - Refactoring: sonnet-4
   - Docs: sonnet-3.7
   ```
   Session-start extracts first 3 lines (after "# Model routing preferences").
   ```

Recommendation: **Defer to Phase 2**. weather.md is not needed for handoff (the core feature). The PRD lists it as "In Scope" (line 27), but the success criteria (line 101-108) **don't mention it**. This is scope creep.

**Fix:** Remove weather.md from Steps 1 and 3. Add to PRD Out of Scope (line 28):
```markdown
- weather.md (Phase 2 — requires model-routing command integration)
```

---

### 3c. Control Flow Complexity — PASS

The hook modifications are **linear checks**:
```bash
if [ -d .clavain ]; then
  # use .clavain/scratch/handoff.md
else
  # use root HANDOFF.md
fi
```

No nested branches, no clever indirection. The 40-line cap (Step 3 line 51) prevents context bloat. The doctor check uses simple stat + date arithmetic.

No unnecessary complexity detected.

---

## 4. Extension Points

### 4a. Extensibility — PASS

The contract defines **top-level directories** (`learnings/`, `contracts/`, `scratch/`) with clear ownership. Downstream beads can add:
- `.clavain/scenarios/` (Clavain-fz77)
- `.clavain/pipelines/` (Clavain-kvlq)
- `.clavain/blobs/` (CXDB-lite, Clavain-re7g)
- `.clavain/provenance/` (Clavain-lkji)

**No collision risk** — each downstream bead owns its subdirectory. The base contract doesn't hardcode a list of allowed subdirs, so it won't break when new ones are added.

**Gitignore contract is safe** — only `scratch/` is gitignored. New subdirs are committed by default unless downstream beads extend `.gitignore`.

---

### 4b. Breaking Change Risk — PASS

The contract is **additive only**:
- If `.clavain/` doesn't exist → current behavior (root HANDOFF.md)
- If `.clavain/` exists → new behavior (scratch/handoff.md)

No existing behavior is removed. No files are moved automatically. No forced migration.

**Risk:** If a project has both `.clavain/` (new) and root `HANDOFF.md` (old), **which one wins**?

Plan Step 2 (line 40) says:
> "If `.clavain/` doesn't exist: keep current behavior (root HANDOFF.md)"

This implies **precedence**: `.clavain/` > root. But it doesn't say **what to do if both exist**.

**Fix:** Add to Step 2:
```markdown
If both .clavain/ and root HANDOFF.md exist, session-handoff only writes to
.clavain/scratch/handoff.md (new behavior). Root HANDOFF.md is ignored.
```

---

## 5. Test Coverage Gaps

### 5a. Structural Tests — PASS

Plan Step 6 (line 122) hardcodes the command count bump (37 → 38). This will break tests, but the plan accounts for it:
> "Test count assertion: Structural tests hardcode command count at 37. Will need updating to 38."

The fix is straightforward (edit test assertion). No hidden gaps.

---

### 5b. Hook Behavior Tests — MISSING

The plan includes syntax checks (bash -n, line 101-102) but **no behavior tests** for:
- session-handoff creates `.clavain/scratch/` when `.clavain/` exists
- session-start reads `.clavain/scratch/handoff.md` and injects it
- session-start caps handoff content at 40 lines
- doctor check detects stale handoff (>7 days)

**Impact:** These are integration points with user-visible behavior. Syntax checks won't catch logic bugs (e.g., wrong path, off-by-one line count).

**Fix:** Add to Step 6:
```markdown
6. Manual integration test:
   a. Run /clavain:init in a test repo
   b. Trigger session-handoff (create uncommitted changes, stop session)
   c. Start new session, verify handoff content appears in additionalContext
   d. Verify handoff is at .clavain/scratch/handoff.md, not root HANDOFF.md
   e. Run /clavain:doctor, verify .clavain status reported correctly
```

This is a **5-minute smoke test**, not a full test suite. But it catches the most common implementation errors (wrong paths, missing mkdir).

---

## 6. Compliance with Project Conventions

### 6a. Trunk-Based Development — PASS

Plan says "commit directly to main" (implicit in Clavain conventions). No branch/worktree steps. Correct.

---

### 6b. Read Before Edit — PASS

Plan assumes existing files are read (hooks/session-handoff.sh, hooks/session-start.sh). No blind edits.

---

### 6c. No Heredocs in Bash — PASS

Plan Step 1 says "create .clavain/README.md documenting the directory contract" but doesn't specify **how**. Current Clavain pattern (from CLAUDE.md, global instructions) says:
> "Never use heredocs in Bash tool calls — Write the content first, then reference the file."

**Advisory:** Ensure implementers use the Write tool for README.md, not `cat <<EOF`.

---

## 7. Critical Issues Summary

| Issue | Severity | Step | Fix |
|-------|----------|------|-----|
| session-handoff path is underspecified | **CRITICAL** | 2 | Specify exact instruction text: `.clavain/scratch/handoff.md` |
| doctor stat fallback logic is broken | **CRITICAL** | 4 | Rewrite to check file existence first, avoid echo fallback |
| weather.md format is undefined | **HIGH** | 1, 3 | Defer to Phase 2 or specify YAML schema + injection logic |
| scratch/ creation responsibility is unclear | MEDIUM | 2, 3 | Document that session-handoff creates, session-start only reads |
| learnings split-brain not addressed | MEDIUM | Risks | Add to Risks: Phase 3 must define precedence rules |
| No integration smoke test | MEDIUM | 6 | Add manual test checklist |
| Both .clavain/ and root HANDOFF.md case | LOW | 2 | Document precedence: .clavain/ wins |

---

## 8. Recommendation

**Fix the three critical/high issues**, then proceed. The design is sound, scope is appropriate, and extension points are clean.

**Revised Step 2 (session-handoff integration):**
```markdown
### Step 2: Update session-handoff.sh

**File:** `hooks/session-handoff.sh`

Add `.clavain/scratch/` awareness:

1. After the existing signals detection (line 67), check if `.clavain/` directory exists
2. If it exists:
   - Ensure `.clavain/scratch/` directory exists (create if needed)
   - Change line 80 from:
     "1. Write a brief HANDOFF.md in the project root"
   to:
     "1. Write a brief handoff file to .clavain/scratch/handoff.md"
3. If `.clavain/` doesn't exist: keep current behavior (root HANDOFF.md)
4. If both .clavain/ and root HANDOFF.md exist, only write to .clavain/scratch/
   (new behavior takes precedence)

**Acceptance:** With `.clavain/` present, handoff goes to `.clavain/scratch/handoff.md`.
Without it, behavior is unchanged.
```

**Revised Step 3 (session-start integration):**
```markdown
### Step 3: Update session-start.sh

**File:** `hooks/session-start.sh`

Add `.clavain/scratch/handoff.md` reading:

1. After the companion detection block (around line 82), add a block that checks
   for `.clavain/scratch/handoff.md`
2. If the file exists and is non-empty:
   - Read at most the first 40 lines (prevent context bloat)
   - Append to additionalContext as "\n\nPrevious session context:\n<content>"
3. Do not create .clavain/scratch/ if it doesn't exist (only session-handoff
   creates it)

**Acceptance:** New sessions in projects with `.clavain/` get handoff context
automatically. Empty or missing handoff files are silently skipped.
```

**Revised Step 4 (doctor check):**
```markdown
### Step 4: Add doctor check

**File:** `commands/doctor.md`

Add section "3d. Agent Memory" between "3c. Statusline Companion" and "4. Conflicting Plugins":

```markdown
### 3d. Agent Memory

```bash
if [ -d .clavain ]; then
  echo ".clavain: initialized"

  # Check scratch/ is gitignored
  if grep -q '.clavain/scratch' .gitignore 2>/dev/null; then
    echo "  scratch gitignore: OK"
  else
    echo "  WARN: .clavain/scratch/ not in .gitignore"
  fi

  # Check for stale handoff (portable stat with fallback)
  if [ -f .clavain/scratch/handoff.md ]; then
    mtime=$(stat -c %Y .clavain/scratch/handoff.md 2>/dev/null || \
            stat -f %m .clavain/scratch/handoff.md 2>/dev/null || \
            echo 0)
    if [ "$mtime" -gt 0 ]; then
      age=$(( ($(date +%s) - mtime) / 86400 ))
      if [ "$age" -gt 7 ]; then
        echo "  WARN: stale handoff (${age} days old)"
      fi
    fi
  fi

  # Count learnings entries
  learnings_count=$(ls .clavain/learnings/*.md 2>/dev/null | wc -l | tr -d ' ')
  echo "  learnings: ${learnings_count} entries"
else
  echo ".clavain: not initialized (run /clavain:init to set up)"
fi
```

Add to output table: `.clavain     [initialized|not set up]`

**Acceptance:** Doctor reports `.clavain/` status with gitignore, staleness, and
learnings count.
```

**Revised Risks section:**
```markdown
## Risks

- **Count bump cascade**: New command (init.md) bumps 37→38 across 6 files.
  gen-catalog.py handles this automatically.
- **session-start context bloat**: Injecting handoff content could bloat
  additionalContext. Mitigated by 40-line cap.
- **Test count assertion**: Structural tests hardcode command count at 37.
  Will need updating to 38.
- **Scratch dir lifecycle**: session-handoff creates scratch/, session-start
  only reads. If scratch/ is manually deleted (e.g., git clean -fdx), next
  session-start won't find handoff but will not fail. This is correct behavior.
- **Knowledge split-brain**: Phase 3 must define precedence rules for global vs.
  project-local learnings. Current plan assumes "different purposes" but doesn't
  specify how agents choose which to inject.
```

**Remove from scope (defer to Phase 2):**
- weather.md creation (Step 1 line 23)
- weather.md injection (Step 3 line 52)

---

## Conclusion

The plan is **well-scoped** and **architecturally sound**. The boundary between ephemeral and durable state is clear. The hook modifications are minimal and fail-safe. Extension points are clean.

**Three critical fixes required** (handoff path, doctor stat, weather.md scope). After these, the plan is ready for execution.

The discipline shown here — deferring indexes, auto-compound, and downstream features to later phases — is exemplary. This is how you build a stable contract without overcommitting.

**Ship it** (after fixes).
