# Commit and Push: Interserve

**Date**: 2026-02-23
**Repository**: `/home/mk/projects/Demarch/interverse/interserve`
**Remote**: `https://github.com/mistakeknot/interserve.git`
**Branch**: `main`

## Summary

Created 3 logically grouped commits and pushed all to `origin main`.

## Pre-Commit State

`git status --short` output:

```
 M cmd/interserve-mcp/main.go
 M docs/research/fd-architecture-review-interserve.md
 M docs/research/fd-safety-review-interserve.md
 M hooks/pre-read-intercept.sh
?? docs/interserve-roadmap.md
?? docs/interserve-vision.md
?? docs/roadmap.md
?? docs/vision.md
```

4 modified files, 4 untracked files.

## Commits Created

### Commit 1: `28a4dca` — Source Changes

**Message**: `fix: update MCP server dispatch path and pre-read hook limit bypass`

**Files**:
- `cmd/interserve-mcp/main.go` — Updated default dispatch path from `hub/clavain` to `os/clavain` to reflect monorepo restructure
- `hooks/pre-read-intercept.sh` — Added `limit` parameter bypass alongside existing `offset` bypass. When Claude reads with a limit, it knows what it is looking for, so the pre-read intercept should allow it through (same logic as offset)

**Diff stats**: 2 files changed, 5 insertions, 2 deletions

### Commit 2: `5640fb7` — Research Docs

**Message**: `docs: update architecture and safety review for os/clavain path change`

**Files**:
- `docs/research/fd-architecture-review-interserve.md` — 1 path reference updated
- `docs/research/fd-safety-review-interserve.md` — 10 path references updated across code examples, attack scenario descriptions, and remediation recommendations

**Diff stats**: 2 files changed, 11 insertions, 11 deletions

### Commit 3: `498b2e7` — New Docs

**Message**: `docs: add roadmap and vision docs`

**Files**:
- `docs/interserve-roadmap.md` — New file (223 bytes)
- `docs/interserve-vision.md` — New file (217 bytes)
- `docs/roadmap.md` — New file (223 bytes)
- `docs/vision.md` — Symlink to `interserve-vision.md`

**Diff stats**: 4 files changed, 22 insertions (1 symlink)

## Post-Push State

```
498b2e7 docs: add roadmap and vision docs
5640fb7 docs: update architecture and safety review for os/clavain path change
28a4dca fix: update MCP server dispatch path and pre-read hook limit bypass
7a2d245 fix: remove redundant hooks declaration from plugin.json
04e08dc fix: declare undeclared hooks/skills/commands in plugin.json
```

All 3 commits pushed successfully to `origin main` (7a2d245..498b2e7).

## Key Findings

1. **Path migration**: The `hub/clavain` to `os/clavain` rename affected both source code and 10+ references in safety/architecture review docs. The source fix was a single line in `main.go`; the doc updates were more extensive.

2. **Pre-read hook enhancement**: The hook already allowed reads with an `offset` parameter to pass through (targeted reads). Adding the same bypass for `limit` is consistent — both indicate Claude knows what portion of the file it wants, so interception adds no value.

3. **Symlink pattern**: `docs/vision.md` is a symlink to `docs/interserve-vision.md`, following a naming convention where the canonical name includes the project prefix and the short name is a convenience alias.
