# PRD: Upstream Sync Python Rewrite

## Problem

The upstream sync pipeline (sync-upstreams.sh) has grown to 1,019 lines of bash with 5 inline Python subprocess calls, creating shell/Python boundary fragility that's hard to test and debug. The three-way classification logic (7 outcomes) has no test coverage because it's embedded in bash.

This is a proactive refactor for testability and maintainability, not a reactive bugfix. The bash version works but is fragile to modify.

## Solution

Rewrite sync-upstreams.sh as a Python package (`scripts/clavain_sync/`) with testable modules, preserving all existing sync semantics. Keep `upstreams.json` schema unchanged.

## Feature

### F2: Python sync rewrite (Clavain-swio)

**What:** Port sync-upstreams.sh to a Python package preserving all 7 classification outcomes and existing sync semantics.

**Acceptance criteria:**
- [ ] Package structure: `__main__.py`, `config.py`, `state.py`, `classify.py`, `resolve.py`, `namespace.py`, `report.py`
- [ ] CLI entry: `python3 -m clavain_sync sync [--upstream NAME] [--dry-run] [--interactive]`
- [ ] All 7 classification outcomes preserved: SKIP, COPY, AUTO, KEEP-LOCAL, CONFLICT, REVIEW:new-file, REVIEW:unexpected-divergence
- [ ] Namespace replacement applied to upstream + ancestor (not local) — same as bash version
- [ ] Content blocklist filtering on AUTO files only
- [ ] AI conflict resolution via `claude -p` subprocess, falls back to needs_human on failure
- [ ] Protected files respected (commands/lfg.md)
- [ ] Atomic state file writes (tempfile + rename) for `lastSyncedCommit` updates in `upstreams.json`
- [ ] Markdown report generation matches existing format
- [ ] Unit tests for classify.py (all 7 paths), namespace.py, config.py schema validation
- [ ] Regression test: capture bash dry-run output for all 6 upstreams, verify Python output matches
- [ ] Old sync-upstreams.sh kept but marked deprecated in header comment
- [ ] `pull-upstreams.sh --sync` updated to call Python package (with `--legacy` flag to invoke bash version)

## Non-goals

- Splitting upstreams.json into config + state files (deferred — no proven need, adds complexity)
- Absorbing upstream-check.sh into the package (deferred — ship after Python sync proves stable)
- Rewriting pull-upstreams.sh (stays as bash — simple git fetch wrapper)
- Adding pydantic or other schema validation libraries (plain dict checks)
- Changing the AI conflict resolver from `claude -p` to SDK calls
- Changing CI workflow in this iteration (follow-up after Python rewrite proves stable)

## Dependencies

- Python 3.12+ (already available on server)
- `claude` CLI (already installed, used by AI conflict resolver)
- `git` (already available)
- No new pip dependencies required

## Rollback Plan

1. Old `sync-upstreams.sh` stays in place, marked deprecated but functional
2. `pull-upstreams.sh --sync --legacy` invokes the bash version directly
3. CI workflow continues to call bash version until Python version is validated over 1+ production cycle

## Deferred Work

| Bead | Feature | Status | Reason |
|------|---------|--------|--------|
| Clavain-3w1x | Split upstreams.json config/state | Deferred | Adds two-source-of-truth complexity without proven need |
| Clavain-4728 | Absorb upstream-check.sh | Deferred | Micro-optimization (3→2 API calls). Ship after F2 stable. |
| Clavain-p5ex | Split using-clavain router card | Closed | Already shipped |
| Clavain-np7b | Guessable command aliases | Closed | Already shipped |

## Flux-Drive Review Notes

Reviewed by fd-architecture and fd-user-product agents. Key findings incorporated:
- F4/F5 already shipped — removed from scope
- F1 (config split) creates unnecessary complexity — deferred
- F3 (API consolidation) is scope creep for first iteration — deferred
- Added regression test requirement (bash vs Python output parity)
- Added rollback mechanism (`--legacy` flag)
- Acknowledged this is proactive refactor, not reactive bugfix
