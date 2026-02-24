# Intermute: Commit and Push Analysis

**Date:** 2026-02-23
**Repository:** /home/mk/projects/Demarch/core/intermute
**Branch:** main

## Current State (`git status --short`)

```
 M .gitignore
 D docs/intermute-roadmap.md
 D docs/roadmap.md
?? docs/research/execute-task-2-interlock-register-sh.md
?? docs/research/execute-task-3-extend-list-agents-tool.md
?? intermute
```

## Analysis

### Group 1: Modified .gitignore — `chore: update gitignore`

The `.gitignore` has one addition: `.beads/` directory exclusion. This is a standard tooling cache exclusion, consistent with the existing `.auracoil/cache/` and `.auracoil/oracle/` entries.

**Diff:**
```diff
+
+.beads/
```

### Group 2: Deleted roadmap files — `docs: remove deprecated roadmap files`

Two roadmap files were deleted from the working tree:
- `docs/intermute-roadmap.md` — 80-line detailed roadmap with IMT-prefixed task IDs
- `docs/roadmap.md` — separate roadmap file

These were previously standardized (see commit `33b8057 chore: standardize module roadmap/vision docs`), and likely replaced by canonical versions or consolidated elsewhere.

### Group 3: Untracked files — `docs: add research artifacts`

Two new research documents in `docs/research/`:
- `execute-task-2-interlock-register-sh.md` (4,331 bytes, Feb 22)
- `execute-task-3-extend-list-agents-tool.md` (6,759 bytes, Feb 22)

**`intermute` symlink:**
```
lrwxrwxrwx 1 mk mk 40 Feb 23 18:01 intermute -> /home/mk/projects/Demarch/core/intermute
```
This is a self-referencing compatibility symlink (the repo directory points to itself). This matches the Demarch monorepo pattern where old project locations have symlinks back. It should be added since it's a symlink, not a binary.

## Execution Plan

1. `git add .gitignore` → commit "chore: update gitignore"
2. `git add docs/intermute-roadmap.md docs/roadmap.md` → commit "docs: remove deprecated roadmap files"
3. `git add docs/research/execute-task-2-interlock-register-sh.md docs/research/execute-task-3-extend-list-agents-tool.md intermute` → commit "docs: add research artifacts"
4. `git push origin main`
