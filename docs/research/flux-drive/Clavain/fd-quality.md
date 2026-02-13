# Code Quality & Hygiene Review: Clavain Plugin

**Review Date:** 2026-02-13
**Reviewer:** fd-quality (Quality & Style Reviewer)
**Project:** Clavain v0.5.7 — General-purpose engineering discipline plugin for Claude Code
**Scope:** Shell scripts, documentation freshness, test coverage, uncommitted changes, untracked files

---

## Findings Index

- P0 | P0-1 | "Uncommitted Changes" | 1,212 insertions across 16 files — unclear intent (feature in progress or forgotten cleanup)
- P0 | P0-2 | "hooks/auto-publish.sh" | Untracked auto-publish hook missing from hooks.json registration
- P1 | P1-1 | "Untracked Research Files" | 5 research docs untracked (3 valuable, 2 temp artifacts)
- P1 | P1-2 | "AGENTS.md Component Counts" | Documentation claims "17 agents" but consolidation reduced from 19 to 17 — verify accuracy
- P1 | P1-3 | "clodex Artifacts" | .claude/clodex-audit.log and clodex-toggle.flag are temp runtime artifacts (should be in /tmp or gitignored)
- P2 | P2-1 | "Shell Script Standards" | All shell scripts pass bash -n but lack shellcheck validation
- IMP | IMP-1 | "Research Documentation" | audit-flux-drive-token-flow.md and check-beads-issues-for-flux-drive.md should move to docs/research/flux-drive/ for discoverability
- IMP | IMP-2 | "Git Hygiene" | 3 deleted research docs (code-simplicity-reviewer.md, fd-code-quality.md, fd-user-experience.md) — clean deletion or need archiving
- IMP | IMP-3 | "Hook Discovery" | explore-posttooluse-hook-patterns.md is reference material, belongs in skills/working-with-claude-code/references/
- IMP | IMP-4 | "Test Coverage" | No smoke tests for new fd-quality.md and fd-user-product.md agents
- IMP | IMP-5 | "Documentation Drift" | CLAUDE.md and AGENTS.md modified but unclear what changed (version bump, count update, content)

Verdict: needs-changes

---

## Summary

The Clavain plugin has 1,212 lines of uncommitted changes across 16 files, including 3 deleted research docs and 5 new untracked files. The largest concern is hooks/auto-publish.sh — a complete PostToolUse hook (147 lines) that auto-increments plugin versions and syncs the marketplace after git push, but it's not registered in hooks.json. This creates a gap where the hook exists in the working tree but won't be installed or executed. Three research documents (audit-flux-drive-token-flow.md, check-beads-issues-for-flux-drive.md, explore-posttooluse-hook-patterns.md) are valuable reference material but sit untracked in the wrong directories. Two clodex runtime artifacts (.claude/clodex-audit.log, .claude/clodex-toggle.flag) should be in /tmp or gitignored to prevent commit pollution. All shell scripts pass syntax validation (bash -n) and no namespace contamination detected. Documentation counts are accurate (29 skills, 17 agents, 37 commands) but AGENTS.md and CLAUDE.md show uncommitted changes of unclear purpose.

---

## Issues Found

### P0-1: 1,212 insertions across 16 files — unclear intent (feature in progress or forgotten cleanup)

**Severity:** P0
**Location:** Working tree (git status shows 16 modified files, 3 deleted, 5 untracked)

**Evidence:**
```
 .beads/issues.jsonl                                |   4 +-
 AGENTS.md                                          |   2 +-
 CLAUDE.md                                          |   2 +-
 README.md                                          |   4 +-
 docs/catalog.json                                  |   4 +-
 .../flux-drive/SKILL/code-simplicity-reviewer.md   | 229 -------
 docs/research/flux-drive/SKILL/fd-architecture.md  | 648 ++++++++++++++-----
 docs/research/flux-drive/SKILL/fd-code-quality.md  | 216 -------
 docs/research/flux-drive/SKILL/fd-performance.md   | 701 ++++++++++++++++-----
 .../flux-drive/SKILL/fd-user-experience.md         | 194 ------
 docs/research/flux-drive/SKILL/summary.md          | 143 ++++-
 hooks/hooks.json                                   |  10 +
 skills/flux-drive/SKILL.md                         |   2 +-
 skills/flux-drive/phases/launch.md                 | 105 +--
 skills/flux-drive/phases/shared-contracts.md       |   8 +-
 skills/flux-drive/phases/synthesize.md             |   9 +
 16 files changed, 1,212 insertions(+), 1,069 deletions(-)
```

The diff shows:
1. **3 deleted research files** (code-simplicity-reviewer.md, fd-code-quality.md, fd-user-experience.md) — 639 deletions — these are old flux-drive agent reviews, likely superseded by fd-quality.md and fd-user-product.md
2. **2 expanded research files** (fd-architecture.md +648 lines, fd-performance.md +701 lines) — these look like new review outputs, not in-progress edits
3. **flux-drive orchestration changes** (launch.md -105 lines, shared-contracts.md +8, synthesize.md +9) — structural refactoring or fixes
4. **Documentation bumps** (AGENTS.md, CLAUDE.md, README.md, catalog.json) — likely version or count updates
5. **hooks.json** (+10 lines) — new hook registration

**Problem:** Without a commit message or plan context, it's impossible to determine:
- Is this a completed feature ready to commit?
- Is it in-progress work that should be stashed?
- Are the deletions intentional cleanup or accidental?

**User Impact:** Unclear git state creates risk:
- If these changes are committed as-is, the commit message will be generic without explaining WHY 1,212 lines changed
- If these changes are work-in-progress, other developers (or future sessions) may accidentally commit or revert them
- If the deletions are wrong, valuable research is lost

**Recommendation:**
1. Review each modified file's diff to determine intent
2. Group changes into logical commits:
   - Commit 1: Delete superseded research docs with message "chore: remove superseded flux-drive research (replaced by fd-quality and fd-user-product)"
   - Commit 2: Flux-drive orchestration fixes with descriptive message
   - Commit 3: Documentation updates with message "chore: update docs for v0.5.7"
3. Or: if this is incomplete work, stash it and document the stash purpose

---

### P0-2: Untracked auto-publish hook missing from hooks.json registration

**Severity:** P0
**Location:** hooks/auto-publish.sh (147 lines, complete implementation) but NOT in hooks/hooks.json

**Evidence:**

File exists:
```bash
$ wc -l hooks/auto-publish.sh
147 hooks/auto-publish.sh
```

Content summary:
```bash
#!/usr/bin/env bash
# PostToolUse hook: auto-publish plugin after git push
# Detects `git push` in plugin repos, auto-increments patch version if the
# developer forgot to bump, syncs marketplace, and pushes marketplace.
```

But `hooks/hooks.json` has no PostToolUse entry for auto-publish.sh. Current hooks.json structure:
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/clodex-audit.sh",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

**Problem:** auto-publish.sh is a complete, production-ready hook but it won't be installed or executed because it's not registered. The hook's purpose (auto-bump patch version after `git push`) is critical for plugin development hygiene, yet it's dormant.

**Root Cause:** The hook was likely developed in this session or a recent session but the registration step was forgotten.

**User Impact:**
1. Developers push plugin changes without version bumps → marketplace is out of sync
2. The hook's sentinel logic (60s TTL lock files) and loop prevention are wasted
3. The hook's marketplace sync logic never runs → manual `/interpub:release` required every time

**Recommendation:**

Add to hooks/hooks.json:
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/auto-publish.sh",
            "timeout": 10,
            "description": "Auto-publish plugin after git push"
          }
        ]
      },
      {
        "matcher": "Edit|Write|MultiEdit|NotebookEdit",
        ...
      }
    ]
  }
}
```

Then test:
1. Make a trivial change to plugin.json
2. `git commit -am "test: auto-publish hook"`
3. `git push`
4. Check if hook fires (should see marketplace commit)

---

### P1-1: 5 research docs untracked (3 valuable, 2 temp artifacts)

**Severity:** P1
**Location:** Untracked files in git status

**Evidence:**
```
?? docs/research/audit-flux-drive-token-flow.md
?? docs/research/check-beads-issues-for-flux-drive.md
?? docs/research/explore-posttooluse-hook-patterns.md
?? docs/research/flux-drive/SKILL/fd-quality.md
?? docs/research/flux-drive/SKILL/fd-user-product.md
```

**Analysis:**

1. **audit-flux-drive-token-flow.md** (494 lines, 14k words) — comprehensive token flow analysis of flux-drive orchestration. Valuable reference material.

2. **check-beads-issues-for-flux-drive.md** (636 lines) — beads query results for flux-drive improvements. Tracks implementation status.

3. **explore-posttooluse-hook-patterns.md** (325 lines) — research on Claude Code's PostToolUse hook system. Reference material, should move to skill references.

4. **fd-quality.md** (655 lines) — flux-drive agent output reviewing SKILL.md quality. P0 findings: 546-line SKILL.md violates plugin convention.

5. **fd-user-product.md** (583 lines) — flux-drive agent output reviewing UX. P0 findings: Missing escape hatch for triage disagreement loops.

**Problem:**
- 3 valuable research docs are at risk of loss if session crashes
- 2 agent outputs are not discoverable
- explore-posttooluse-hook-patterns.md is in the wrong directory

**Recommendation:**
1. **Commit valuable research:**
   ```bash
   git add docs/research/audit-flux-drive-token-flow.md
   git add docs/research/check-beads-issues-for-flux-drive.md
   git add docs/research/flux-drive/SKILL/fd-quality.md
   git add docs/research/flux-drive/SKILL/fd-user-product.md
   git commit -m "docs: add flux-drive token flow analysis and agent reviews"
   ```

2. **Move hook patterns to skill reference:**
   ```bash
   mv docs/research/explore-posttooluse-hook-patterns.md \
      skills/working-with-claude-code/references/posttooluse-patterns.md
   git add skills/working-with-claude-code/references/posttooluse-patterns.md
   git commit -m "docs: move PostToolUse hook patterns to skill reference"
   ```

---

### P1-2: Documentation claims "17 agents" but consolidation reduced from 19 to 17 — verify accuracy

**Severity:** P1
**Location:** AGENTS.md line 12, CLAUDE.md (modified but content not visible in diff stats)

**Evidence:**

From AGENTS.md:
```markdown
| Components | 29 skills, 17 agents, 37 commands, 6 hooks, 2 MCP servers |
```

From filesystem verification:
```bash
$ ls -la agents/review/*.md agents/research/*.md agents/workflow/*.md 2>/dev/null | grep -v references | wc -l
17
```

From project memory:
> Agent Consolidation (2026-02-10, updated 2026-02-12)
> Total: 17 agents (10 review + 5 research + 2 workflow)

**Analysis:**

The count is **correct** (17 agents), but the modified AGENTS.md and CLAUDE.md files suggest the documentation was updated. The diff stats show only 2 lines changed in each file.

**Problem:** Documentation accuracy is critical for plugin discovery and validation. Without seeing the actual diff, we can't confirm what changed.

**Recommendation:**

1. **Verify the diff:**
   ```bash
   git diff AGENTS.md CLAUDE.md
   ```

2. **If count was corrected:** Commit with message "chore: update agent count to 17 (post-consolidation)"

3. **If version was bumped:** Verify plugin.json also shows v0.5.7

---

### P1-3: .claude/clodex-audit.log and clodex-toggle.flag are temp runtime artifacts (should be in /tmp or gitignored)

**Severity:** P1
**Location:** .claude/clodex-audit.log, .claude/clodex-toggle.flag (untracked)

**Evidence:**

From git status:
```
?? .claude/clodex-audit.log
?? .claude/clodex-toggle.flag
```

From audit log contents:
```
[2026-02-13T09:09:25-08:00] VIOLATION: Edit/Write to source file: /root/projects/Clavain/docs/research/flux-drive/SKILL/fd-architecture.md.partial
[2026-02-13T09:12:32-08:00] VIOLATION: Edit/Write to source file: /root/projects/Clavain/docs/research/flux-drive/SKILL/fd-user-product.md.partial
```

From toggle flag:
```
2026-02-13T08:29:18-08:00
```

**Analysis:**

1. **clodex-audit.log** is a runtime log written by hooks/clodex-audit.sh. It tracks Edit/Write violations. This is ephemeral state.

2. **clodex-toggle.flag** is a timestamp file indicating when clodex mode was enabled. This is session-scoped state.

Both files live in `.claude/` which is NOT gitignored. This creates commit pollution risk.

**Problem:**
- Temp runtime artifacts in a non-gitignored directory create commit pollution risk
- No cleanup mechanism for audit logs (grows unbounded)
- Toggle flag should be session-scoped but isn't

**Recommendation:**

1. **Move to /tmp:**
   ```bash
   # In clodex-audit.sh
   AUDIT_LOG="/tmp/clavain-clodex-audit-${session_id}.log"

   # In clodex-toggle.sh
   TOGGLE_FLAG="/tmp/clavain-clodex-toggle-${session_id}.flag"
   ```

2. **Or: Add to .gitignore:**
   ```
   .claude/clodex-audit.log
   .claude/clodex-toggle.flag
   ```

3. **Delete current files:**
   ```bash
   rm .claude/clodex-audit.log .claude/clodex-toggle.flag
   ```

---

### P2-1: All shell scripts pass bash -n but lack shellcheck validation

**Severity:** P2
**Location:** All shell scripts (hooks/*.sh, scripts/*.sh)

**Evidence:**

Syntax validation passes:
```bash
$ for script in hooks/*.sh scripts/*.sh; do bash -n "$script" 2>&1 || echo "FAIL: $script"; done
[no output = all passed]
```

But no shellcheck validation in test suite. Project uses 3-tier testing (pytest, bats-core, smoke) but none run shellcheck.

**Analysis:**

bash -n only checks syntax. It doesn't check:
- Unquoted variable expansions
- Useless use of cat
- Missing error handling
- Deprecated syntax

**Problem:** Without shellcheck, subtle bugs can slip through.

**Recommendation:**

Add shellcheck to test suite:
```bash
# In tests/run-tests.sh
echo "Running shellcheck..."
shellcheck hooks/*.sh scripts/*.sh || exit 1
```

---

## Improvements Suggested

### IMP-1: audit-flux-drive-token-flow.md and check-beads-issues-for-flux-drive.md should move to docs/research/flux-drive/ for discoverability

**Location:** docs/research/ (top-level) should be docs/research/flux-drive/

**Rationale:**

Both files are flux-drive-specific research. They should be under `docs/research/flux-drive/` for discoverability and organizational consistency.

**Recommendation:**
```bash
mv docs/research/audit-flux-drive-token-flow.md docs/research/flux-drive/
mv docs/research/check-beads-issues-for-flux-drive.md docs/research/flux-drive/
git add docs/research/flux-drive/{audit-flux-drive-token-flow,check-beads-issues-for-flux-drive}.md
git commit -m "docs: move flux-drive research to skill directory"
```

---

### IMP-2: 3 deleted research docs — clean deletion or need archiving

**Location:** git status shows 3 deletions in docs/research/flux-drive/SKILL/

**Evidence:**
```
 D docs/research/flux-drive/SKILL/code-simplicity-reviewer.md (229 lines)
 D docs/research/flux-drive/SKILL/fd-code-quality.md (216 lines)
 D docs/research/flux-drive/SKILL/fd-user-experience.md (194 lines)
```

From project memory:
> Agent Consolidation (2026-02-10, updated 2026-02-12)
> 19 v1 review agents consolidated into 6 core fd-* agents

**Analysis:**

These 3 files are old flux-drive agent reviews, superseded by fd-quality.md and fd-user-product.md.

**Recommendation:**

Clean deletion is sufficient:
```bash
git add docs/research/flux-drive/SKILL/code-simplicity-reviewer.md
git add docs/research/flux-drive/SKILL/fd-code-quality.md
git add docs/research/flux-drive/SKILL/fd-user-experience.md
git commit -m "chore: remove superseded flux-drive reviews (replaced by fd-quality and fd-user-product)"
```

Git history already preserves the content.

---

### IMP-3: explore-posttooluse-hook-patterns.md is reference material, belongs in skills/working-with-claude-code/references/

**Location:** docs/research/ (top-level)

**Rationale:**

This file documents Claude Code's PostToolUse hook system — reference material for the working-with-claude-code skill.

**Recommendation:**
```bash
mv docs/research/explore-posttooluse-hook-patterns.md \
   skills/working-with-claude-code/references/posttooluse-patterns.md
git add skills/working-with-claude-code/references/posttooluse-patterns.md
git commit -m "docs: move PostToolUse hook patterns to skill reference"
```

---

### IMP-4: No smoke tests for new fd-quality.md and fd-user-product.md agents

**Location:** tests/smoke/ directory

**Analysis:**

The 2 new files (fd-quality.md, fd-user-product.md) were produced during this flux-drive run, but there are no corresponding smoke tests.

**Clarification:** These are research outputs (reviews OF the flux-drive skill), not agent definitions. They live in docs/research/flux-drive/SKILL/, not agents/review/. No smoke tests needed — they're not agents themselves, they're reviews produced BY agents.

**Recommendation:**

No action needed. But clarify with a comment:
```markdown
# fd-quality.md
<!-- This is a flux-drive agent review output, not an agent definition -->
```

---

### IMP-5: Documentation drift — CLAUDE.md and AGENTS.md modified but unclear what changed

**Location:** CLAUDE.md (2 lines changed), AGENTS.md (2 lines changed)

**Evidence:**

From git diff stats:
```
 AGENTS.md    |   2 +-
 CLAUDE.md    |   2 +-
```

**Problem:** Without seeing the actual diff, we can't verify the changes are intentional and consistent.

**Recommendation:**

1. **View the diff:**
   ```bash
   git diff AGENTS.md CLAUDE.md
   ```

2. **Commit with clear message:**
   ```bash
   git add AGENTS.md CLAUDE.md
   git commit -m "chore: update docs for v0.5.7 (agent count 19→17 post-consolidation)"
   ```

---

## Overall Assessment

The Clavain plugin is structurally sound — all shell scripts pass syntax validation, plugin.json is valid, no namespace contamination detected, and component counts are accurate (29 skills, 17 agents, 37 commands). The primary quality gaps are process-related, not code-related: 1,212 lines of uncommitted changes with unclear intent, a complete auto-publish hook that's not registered in hooks.json, 5 untracked research files that should be committed or moved, and 2 temp runtime artifacts that should be in /tmp or gitignored. The uncommitted state creates risk — if this session ends without a commit, the intent behind flux-drive orchestration changes is lost. The auto-publish hook is production-ready but dormant, wasting its version-bump and marketplace-sync automation. Shell script quality is solid (bash -n passes) but would benefit from shellcheck validation.

**Prioritize:**
1. **P0-1:** Review uncommitted changes, group into logical commits (or stash if incomplete)
2. **P0-2:** Register auto-publish.sh in hooks.json and test
3. **P1-1:** Commit valuable research (token flow analysis, beads tracking, agent reviews)
4. **P1-3:** Move clodex runtime artifacts to /tmp or add to .gitignore

**Cleanup is 90% "finish what was started" — commit the research, register the hook, move the temp files. The code quality underneath is solid.**

---

<!-- fd-quality:complete -->
