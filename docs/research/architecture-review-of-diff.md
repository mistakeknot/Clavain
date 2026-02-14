# Architecture Review: .clavain/scratch/handoff.md Integration

**Date:** 2026-02-13
**Reviewer:** flux-drive-architecture
**Scope:** commands/doctor.md, hooks/session-handoff.sh, hooks/session-start.sh, tests/structural/test_commands.py

## Summary

This change introduces `.clavain/scratch/handoff.md` as a per-project session handoff mechanism, moving ephemeral state from the project root (`HANDOFF.md`) into a dedicated agent memory directory. The implementation crosses three hook boundaries (session-start, session-handoff) plus a diagnostic command, following the established plugin architecture patterns.

**Overall assessment:** Architecturally sound. Boundary integrity maintained. Minor P2 issues around missing gitignore coverage and lack of contract documentation.

---

## 1. Boundaries & Coupling

### 1.1 Hook Contract Integrity (PASS)

**Context:** Claude Code hooks are JSON-in/JSON-out boundary points. session-handoff.sh is a Stop hook that blocks session termination when incomplete work is detected. session-start.sh is a SessionStart hook that injects context via `additionalContext` field.

**Diff hunks:**
- session-handoff.sh lines 77-83: Path selection (`HANDOFF_PATH` variable)
- session-start.sh lines 130-139: Handoff content reading + injection

**Analysis:**

The diff correctly maintains hook contract boundaries:

1. **session-handoff.sh** generates user-facing instructions via the `reason` field in the block decision JSON. The handoff file path is now dynamic (`HANDOFF_PATH`) based on `.clavain/` presence, but the output contract remains unchanged.

2. **session-start.sh** reads stdin JSON, constructs additionalContext, and outputs hook JSON. The handoff reading is a pure data integration step — no side effects, no blocking behavior, fail-gracefully designed (`head -40` cap, `|| handoff_content=""` fallback).

3. **No cross-hook coupling:** session-handoff writes `.clavain/scratch/handoff.md`, session-start reads it. The only shared contract is the file path convention — both hooks independently check for `.clavain/` existence and derive the same path.

**Verdict:** Boundary integrity maintained. Each hook remains self-contained and fail-safe.

---

### 1.2 Directory Creation Responsibility (P2 — Ownership Ambiguity)

**Diff hunk:** session-handoff.sh lines 80-82

```bash
if [[ -d ".clavain" ]]; then
    mkdir -p ".clavain/scratch" 2>/dev/null || true
    HANDOFF_PATH=".clavain/scratch/handoff.md"
fi
```

**Issue:**

The session-handoff hook creates `.clavain/scratch/` on-demand if `.clavain/` exists. This is correct behavior (the hook shouldn't fail if scratch/ was cleaned), but it creates an **ownership ambiguity**:

- `/clavain:init` is documented as the scaffold command for `.clavain/`
- session-handoff.sh now also creates `scratch/` as a side effect
- session-start.sh reads but never creates directories

**Impact:**

- Users might end up with `.clavain/scratch/` created by the hook without ever running `/init`
- If someone creates `.clavain/` manually (e.g., `mkdir .clavain`), the hook will auto-create `scratch/`, but the rest of the contract (learnings/, contracts/, README.md) won't exist
- Diagnostic confusion: `/doctor` reports `.clavain: initialized` if the directory exists, even if it was only partially scaffolded

**Root cause:** The diff treats `.clavain/` as a boolean flag (exists = use it), but the directory contract has multiple components (learnings/, scratch/, contracts/, README.md). The hook only needs scratch/ but checks for the parent.

**Recommendation (P2):**

1. **Document the ownership split** in comments:
   - `/init` creates the full contract
   - session-handoff creates scratch/ on-demand (defensive)
   - session-start is read-only

2. **Update `/doctor` check** to distinguish "fully initialized" from "partially scaffolded":
   ```bash
   if [ -d .clavain ]; then
     if [ -d .clavain/learnings ] && [ -d .clavain/contracts ]; then
       echo ".clavain: initialized"
     else
       echo ".clavain: partially scaffolded (run /clavain:init to complete)"
     fi
   ```

3. **Consider making `/init` idempotent and defensive**: If `.clavain/` exists but is incomplete, `/init` should fill in missing pieces (learnings/, contracts/, README.md, gitignore entry).

**Severity:** P2 (minor UX inconsistency, no correctness impact)

---

### 1.3 Gitignore Coverage Gap (P2 — Missing Contract Entry)

**Context:** The diff adds `.clavain/scratch/handoff.md` as a new ephemeral file but doesn't update `.gitignore`.

**Current state:**
- `.gitignore` has no `.clavain/` entries
- `/init` command (commands/init.md lines 36-42) adds `.clavain/scratch/` to `.gitignore`
- session-handoff creates scratch/ but doesn't check gitignore

**Issue:**

If `.clavain/` exists (e.g., manually created or from an old init) but scratch/ is not gitignored, `handoff.md` becomes a tracked file. This violates the design intent (scratch/ is ephemeral).

**Risk scenario:**
1. User creates `.clavain/` manually or copies from another project
2. Forgets to run `/init`
3. session-handoff creates `scratch/handoff.md`
4. User commits everything → handoff.md gets committed
5. Multi-user repo: stale handoffs from other developers appear in session-start context

**Recommendation (P2):**

Add `.clavain/scratch/` to the project `.gitignore` as part of this PR. The doctor check already warns about missing gitignore entries (lines 70-73), but it's reactive. Proactive fix:

```bash
echo '.clavain/scratch/' >> .gitignore
```

**Severity:** P2 (won't break anything, but creates inconsistency between projects that ran `/init` vs projects that didn't)

---

### 1.4 Data Flow Integrity (PASS)

**Path:** session-handoff (Stop hook) → `.clavain/scratch/handoff.md` → session-start (SessionStart hook) → additionalContext JSON → Claude's system prompt

**Analysis:**

The data flow is unidirectional and explicit:

1. **Write path (session-handoff):** Generates markdown content via Claude, writes to disk, exits.
2. **Read path (session-start):** Reads file, escapes for JSON, injects into additionalContext.
3. **No feedback loops:** session-start never modifies handoff.md, session-handoff never reads it.
4. **Bounded size:** session-start caps at 40 lines (`head -40`), mitigating context bloat.
5. **Fail-safe:** If handoff.md is missing or empty, session-start silently skips it.

**Verdict:** Clean data pipeline. No coupling cycles.

---

## 2. Pattern Analysis

### 2.1 Consistent Hook Pattern (PASS)

**Pattern:** Clavain hooks follow a consistent structure:

1. Read JSON stdin
2. Guard clauses (early exit if preconditions not met)
3. Business logic (detection, transformation, file I/O)
4. Output JSON stdout
5. Exit 0 always (fail-open semantics)

**Diff conformance:**

- session-handoff.sh: Adds directory check (line 80) + path selection logic (lines 79-83) before existing signal detection. Fits the pattern.
- session-start.sh: Adds handoff reading (lines 130-139) in the same section as companion detection and sprint scanning. Consistent with existing context injection blocks.

**Verdict:** Follows established patterns. No deviation.

---

### 2.2 Fail-Open Error Handling (PASS)

**Analysis:**

Both hooks have appropriate fail-open guards:

- session-handoff: `mkdir -p ... 2>/dev/null || true` (line 81)
- session-start: `head -40 ... 2>/dev/null || handoff_content=""` (line 135)
- session-start: `if [[ -n "$handoff_content" ]]` (line 136) — only injects if non-empty

If `.clavain/scratch/` can't be created, session-handoff falls back to `HANDOFF_PATH="HANDOFF.md"`. If handoff.md can't be read, session-start skips injection.

**Verdict:** Error handling is defensive and appropriate.

---

### 2.3 Path Derivation Duplication (P3 — Minor DRY Violation)

**Observation:**

Both session-handoff.sh and session-start.sh use the same logic to derive the handoff path:

```bash
# session-handoff.sh
HANDOFF_PATH="HANDOFF.md"
if [[ -d ".clavain" ]]; then
    mkdir -p ".clavain/scratch" 2>/dev/null || true
    HANDOFF_PATH=".clavain/scratch/handoff.md"
fi

# session-start.sh (implicit)
if [[ -f ".clavain/scratch/handoff.md" ]]; then
    ...
fi
```

**Issue:**

The path derivation is duplicated. If the handoff file location changes in the future (e.g., `scratch/sessions/${SESSION_ID}.md`), both hooks need updating.

**Recommendation (P3):**

Extract path derivation to a shared function in `hooks/lib.sh`:

```bash
# hooks/lib.sh
clavain_handoff_path() {
    if [[ -d ".clavain" ]]; then
        echo ".clavain/scratch/handoff.md"
    else
        echo "HANDOFF.md"
    fi
}
```

Then both hooks call it:

```bash
HANDOFF_PATH=$(clavain_handoff_path)
```

**Severity:** P3 (low priority — only matters if path logic becomes more complex)

---

## 3. Simplicity & YAGNI

### 3.1 Minimal Abstraction (PASS)

**Analysis:**

The diff adds exactly what's needed:
- Directory check + path selection
- File read + JSON injection
- Doctor check + gitignore warning

No premature abstractions. No plugin hooks, no configuration files, no versioning scheme for handoff format.

**Verdict:** YAGNI compliance good.

---

### 3.2 Context Injection Size Cap (PASS)

**Diff hunk:** session-start.sh line 135

```bash
handoff_content=$(head -40 ".clavain/scratch/handoff.md" 2>/dev/null) || handoff_content=""
```

**Analysis:**

The 40-line cap is a pragmatic safety rail against context bloat. Handoff files are meant to be brief (10-20 lines per session-handoff instructions), but if someone accidentally writes a 500-line handoff, the cap prevents it from consuming the entire context window.

**Potential improvement (future):**

If handoff files grow structured (e.g., YAML frontmatter + sections), consider parsing instead of capping:
- Extract only "Pending" and "Next" sections
- Skip verbose "Done" logs

But this is speculative. Current solution is simple and sufficient.

**Verdict:** Appropriate guardrail.

---

### 3.3 Missing Contract Documentation (P2)

**Observation:**

The diff introduces a new file contract (`.clavain/scratch/handoff.md`) but doesn't document its schema:
- Is it freeform markdown?
- Does it have required sections (Done/Pending/Next)?
- Can it include YAML frontmatter?
- What's the intended lifespan (deleted after read? kept for N days?)

**Current state:**

- session-handoff.sh generates it via Claude with instructions: "Done / Pending / Next / Context" sections (lines 88-92)
- session-start.sh reads it as plain text (no parsing)
- doctor.md checks age > 7 days and warns

**Implicit schema:** Markdown with 4 sections, 10-20 lines, ephemeral (stale after 7 days).

**Issue:**

This schema is only documented in the session-handoff prompt text. If someone writes handoff.md manually or via another tool, they won't know the expected structure.

**Recommendation (P2):**

Add `.clavain/contracts/handoff-schema.md` (or document in `.clavain/README.md`):

```markdown
## handoff.md Schema

**Location:** `.clavain/scratch/handoff.md`

**Purpose:** Brief session handoff context for the next session.

**Format:** Markdown, 10-20 lines.

**Required sections:**
- **Done:** Bullet points of what was accomplished
- **Pending:** What's still in progress
- **Next:** Concrete next steps
- **Context:** Gotchas or decisions

**Lifespan:** Ephemeral. Stale after 7 days (doctor check warns).

**Auto-generated by:** session-handoff.sh (Stop hook).

**Consumed by:** session-start.sh (SessionStart hook).
```

**Severity:** P2 (missing documentation, not a correctness issue)

---

## 4. Test Coverage

### 4.1 Structural Test Update (PASS)

**Diff hunk:** tests/structural/test_commands.py

```python
-assert len(command_files) == 37, f"Expected 37 commands, found {len(command_files)}"
+assert len(command_files) == 38, f"Expected 38 commands, found {len(command_files)}"
```

**Analysis:**

The diff correctly updates the hardcoded count from 37 → 38 to account for the new `/init` command. This is the expected change per the plan (docs/plans/2026-02-13-clavain-memory-filesystem.md, Step 5).

**Verification:**

The plan states `init.md` is a new command. Counting commands:
- doctor.md (existing, modified in this diff)
- init.md (new, created separately, not shown in this diff)

Total: 38 commands.

**Verdict:** Test update correct.

---

### 4.2 Missing Hook Integration Tests (P2)

**Observation:**

The diff modifies two hooks (session-handoff, session-start) but doesn't add integration tests for the new handoff.md read/write cycle.

**Current test coverage:**
- tests/structural/ — file counts, metadata schema
- tests/shell/ — shim tests (interphase delegation)
- tests/smoke/ — end-to-end agent/command tests

**Gap:**

No tests verify:
1. session-handoff creates `.clavain/scratch/handoff.md` when `.clavain/` exists
2. session-handoff falls back to `HANDOFF.md` when `.clavain/` doesn't exist
3. session-start injects handoff content into additionalContext
4. session-start handles missing/empty handoff.md gracefully

**Recommendation (P2):**

Add shell tests in `tests/shell/handoff.bats`:

```bash
@test "session-handoff writes to scratch when .clavain exists" {
  mkdir -p /tmp/test-project/.clavain
  cd /tmp/test-project
  echo '{"session_id":"test","stop_hook_active":false}' | \
    bash hooks/session-handoff.sh
  [ -f .clavain/scratch/handoff.md ] || [ -f HANDOFF.md ]
}

@test "session-start reads handoff.md and injects context" {
  mkdir -p /tmp/test-project/.clavain/scratch
  echo "Test handoff content" > /tmp/test-project/.clavain/scratch/handoff.md
  cd /tmp/test-project
  output=$(echo '{"session_id":"test"}' | bash hooks/session-start.sh)
  [[ "$output" == *"Test handoff content"* ]]
}
```

**Severity:** P2 (missing test coverage, not a blocker for this diff)

---

## 5. Recommendations Summary

### P1 (Critical — Fix Before Merge)

None.

---

### P2 (Important — Address in Follow-Up)

1. **Gitignore coverage gap** (Section 1.3):
   - Add `.clavain/scratch/` to project `.gitignore` in this PR
   - Prevents accidental commits of handoff.md in projects that didn't run `/init`

2. **Directory ownership ambiguity** (Section 1.2):
   - Document in session-handoff.sh comments that it creates scratch/ defensively
   - Update `/doctor` to detect "partially scaffolded" .clavain/ dirs (has .clavain but missing learnings/contracts)

3. **Missing contract documentation** (Section 3.3):
   - Add handoff.md schema to `.clavain/README.md` or a new `contracts/handoff-schema.md`
   - Documents expected structure (Done/Pending/Next/Context sections, 10-20 lines)

4. **Missing hook integration tests** (Section 4.2):
   - Add bats tests for session-handoff + session-start handoff.md cycle
   - Verify both `.clavain/scratch/` and fallback `HANDOFF.md` paths

---

### P3 (Nice-to-Have — Future Refactor)

1. **Path derivation duplication** (Section 2.3):
   - Extract `clavain_handoff_path()` to `hooks/lib.sh`
   - Reduces duplication between session-handoff and session-start

---

## 6. Architectural Strengths

1. **Clean separation of concerns:**
   - session-handoff: write decision
   - session-start: read decision
   - doctor: health check
   - No cross-hook dependencies beyond file convention

2. **Fail-open semantics:**
   - All hooks have appropriate guards (`|| true`, `2>/dev/null`, existence checks)
   - Missing `.clavain/` → graceful fallback to root HANDOFF.md
   - Missing handoff.md → skip injection

3. **Bounded resource usage:**
   - 40-line cap on handoff content prevents context bloat
   - 7-day staleness warning in doctor prevents indefinite accumulation

4. **Consistent with existing patterns:**
   - Follows Clavain hook conventions (JSON I/O, sentinel files, fail-open)
   - Fits alongside existing context injection blocks (companions, sprint-scan, discovery)

---

## 7. Final Verdict

**Overall:** Architecturally sound. The change introduces a clean abstraction (`.clavain/scratch/` for ephemeral state) without breaking boundaries or coupling unrelated components.

**Blocking issues:** None.

**Follow-up work:**
- Add `.clavain/scratch/` to `.gitignore` (1 line)
- Document handoff.md schema (10 lines)
- Add bats tests for hook integration (20 lines)
- Update doctor check for partial scaffolding (5 lines)

**Recommendation:** Merge with P2 follow-ups tracked in a new bead (or added to the existing Clavain-d4ao bead).

---

## Appendix: Diff Hunk Reference

### A. session-handoff.sh (lines 77-83)

```bash
+HANDOFF_PATH="HANDOFF.md"
+if [[ -d ".clavain" ]]; then
+    mkdir -p ".clavain/scratch" 2>/dev/null || true
+    HANDOFF_PATH=".clavain/scratch/handoff.md"
+fi
+
-1. Write a brief HANDOFF.md in the project root with:
+1. Write a brief handoff file to ${HANDOFF_PATH} with:
```

**Impact:** Path selection logic + user-facing instruction update. No structural changes.

---

### B. session-start.sh (lines 130-139)

```bash
+handoff_context=""
+if [[ -f ".clavain/scratch/handoff.md" ]]; then
+    handoff_content=$(head -40 ".clavain/scratch/handoff.md" 2>/dev/null) || handoff_content=""
+    if [[ -n "$handoff_content" ]]; then
+        handoff_context="\\n\\n**Previous session context:**\\n$(escape_for_json "$handoff_content")"
+    fi
+fi
+
-    "additionalContext": "...${discovery_context}"
+    "additionalContext": "...${discovery_context}${handoff_context}"
```

**Impact:** Adds handoff reading + JSON injection. No changes to existing context injection logic.

---

### C. doctor.md (lines 64-91)

```markdown
+### 3d. Agent Memory
+
+```bash
+if [ -d .clavain ]; then
+  echo ".clavain: initialized"
+  if grep -qF '.clavain/scratch/' .gitignore 2>/dev/null; then
+    echo "  scratch gitignore: OK"
+  else
+    echo "  WARN: .clavain/scratch/ not in .gitignore"
+  fi
+  if [ -f .clavain/scratch/handoff.md ]; then
+    mtime=$(stat -c %Y .clavain/scratch/handoff.md 2>/dev/null || stat -f %m .clavain/scratch/handoff.md 2>/dev/null || echo 0)
+    if [ "$mtime" -gt 0 ]; then
+      age=$(( ($(date +%s) - mtime) / 86400 ))
+      if [ "$age" -gt 7 ]; then
+        echo "  WARN: stale handoff (${age} days old)"
+      fi
+    fi
+  fi
+  learnings_count=$(ls .clavain/learnings/*.md 2>/dev/null | wc -l | tr -d ' ')
+  echo "  learnings: ${learnings_count} entries"
+else
+  echo ".clavain: not initialized (run /clavain:init to set up)"
+fi
+```
```

**Impact:** New diagnostic check section. No changes to existing checks.

---

### D. test_commands.py (count update)

```python
-assert len(command_files) == 37, f"Expected 37 commands, found {len(command_files)}"
+assert len(command_files) == 38, f"Expected 38 commands, found {len(command_files)}"
```

**Impact:** Regression guard update for new `/init` command.
