# Commit and Push Analysis — Autarch

**Date:** 2026-02-23
**Repo:** `/home/mk/projects/Demarch/apps/autarch` (origin: `https://github.com/mistakeknot/Autarch.git`)
**Branch:** `main` (trunk-based development)

## Current State

10 modified files and 52+ new (untracked) files/directories.

### Modified Files

| File | Category | Notes |
|------|----------|-------|
| `.githooks/pre-commit` | config | +31 lines changed |
| `.gitignore` | config | +2 lines |
| `.serena/project.yml` | config | +4 lines |
| `bigend` | binary | ELF x86-64, 30MB (tracked, not gitignored) |
| `testui` | binary | ELF x86-64, 29MB (tracked, not gitignored) |
| `docs/autarch-vision.md` | docs | Minor edit (2 lines) |
| `docs/bigend/roadmap.md` | docs | Major rewrite (-392 lines) |
| `pkg/agenttargets/config.go` | Go source | +72 lines |
| `pkg/agenttargets/config_test.go` | Go source | +85 lines |
| `pkg/claude/run.go` | Go source | Refactored (~212 lines changed) |

### New (Untracked) Files

**Group 4 — New test files (2 files):**
- `pkg/agenttargets/backend_claude_test.go`
- `pkg/agenttargets/backend_codex_test.go`

**Group 5 — New docs (52 files):**
- 3 brainstorms (`docs/brainstorms/2026-02-{11,20,23}`)
- 7 plans (`docs/plans/2026-02-{05,06,07,11,20,23}`)
- 2 PRDs (`docs/prds/2026-02-{11,20}`)
- 38+ research files (`docs/research/`)
- `docs/roadmap.md`, `docs/vision.md`

**Group 6 — New config/scaffold directories:**
- `.claude/` (agents, scratchpad — settings.local.json is gitignored)
- `.clavain/` (interspect, quality-gates, scratch)
- `.gurgeh/` (sprints)
- `.githooks/` new files: post-checkout, post-merge, pre-commit.backup, pre-push, prepare-commit-msg
- `gurgeh-plugin/` (agents, commands, skills)

## Adjustments from Requested Plan

The user's Group 1 referenced files that do NOT appear in `git status`:
- `internal/pollard/insights/insight.go` — NOT modified
- `internal/tui/views/bigend.go` — NOT modified
- `pkg/autarch/client.go` — NOT modified

Actual Go source files in git status: `pkg/agenttargets/config.go`, `pkg/agenttargets/config_test.go`, `pkg/claude/run.go`

**Revised commit groupings:**

### Group 1: Modified Go source
Files: `pkg/agenttargets/config.go`, `pkg/agenttargets/config_test.go`, `pkg/claude/run.go`
Message: `feat: update agent targets config and claude runner`

### Group 2: Modified config/build files
Files: `.githooks/pre-commit`, `.gitignore`, `.serena/project.yml`, `bigend`, `testui`
Message: `chore: update git hooks, gitignore, serena config, and build artifacts`

### Group 3: Modified vision/roadmap docs
Files: `docs/autarch-vision.md`, `docs/bigend/roadmap.md`
Message: `docs: update autarch vision and bigend roadmap`

### Group 4: New test files
Files: `pkg/agenttargets/backend_claude_test.go`, `pkg/agenttargets/backend_codex_test.go`
Message: `test: add claude and codex backend tests`

### Group 5: All new docs
Files: `docs/brainstorms/`, `docs/plans/`, `docs/prds/`, `docs/research/`, `docs/roadmap.md`, `docs/vision.md`
Message: `docs: add brainstorms, plans, PRDs, and research artifacts`

### Group 6: New config/scaffold directories
Files: `.claude/`, `.clavain/`, `.gurgeh/`, `.githooks/post-checkout`, `.githooks/post-merge`, `.githooks/pre-commit.backup`, `.githooks/pre-push`, `.githooks/prepare-commit-msg`, `gurgeh-plugin/`
Message: `chore: add clavain config, gurgeh plugin scaffold, and git hooks`

## Risk Assessment

- **Binary files (bigend, testui):** 30MB each, already tracked in repo history. Committing updated versions is consistent with project convention.
- **`.claude/settings.local.json`:** Gitignored, will not be included.
- **Large doc volume:** 52 new doc files is substantial but they are all markdown artifacts from brainstorming/planning sessions.
- **No secrets detected** in the file list.
