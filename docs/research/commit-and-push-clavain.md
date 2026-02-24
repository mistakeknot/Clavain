# Clavain Commit & Push Analysis

**Date:** 2026-02-23
**Branch:** main
**Pushed to:** `origin/main` (https://github.com/mistakeknot/Clavain.git)

## Summary

Three logically grouped commits were created and pushed to `origin main`:

| Commit | Message | Files Changed | Deletions | Additions |
|--------|---------|---------------|-----------|-----------|
| `a153b73` | `chore: remove beads artifacts` | 8 | 709 lines | 0 |
| `e838566` | `chore: update docs, setup command, and upstreams config` | 5 | 12 lines | 11 lines |
| `aea2ee0` | `docs: update catalog and roadmap` | 3 | 273 lines | 49 lines |

## Group 1: Remove Beads Artifacts (a153b73)

Deleted all files under `.beads/`:
- `.beads/.gitignore`
- `.beads/.jsonl.lock`
- `.beads/.migration-hint-ts`
- `.beads/README.md`
- `.beads/config.yaml`
- `.beads/interactions.jsonl`
- `.beads/issues.jsonl`
- `.beads/metadata.json`

709 lines removed. The beads tracking system has been superseded by Intercore kernel state management (completed in tracks A1-A3 and E3-E6 of the roadmap).

## Group 2: Update Docs, Setup Command, and Upstreams Config (e838566)

### Files Modified
- **AGENTS.md** — Updated component counts: 54 commands (was 53), 10 hooks (was 12). Updated directory tree and validation script comments.
- **CLAUDE.md** — Updated overview line: 10 hooks (was 12).
- **README.md** — Updated component counts throughout (54 commands, 10 hooks). Updated hooks section count.
- **commands/setup.md** — Fixed intermem description: "Memory synthesis — graduates auto-memory to AGENTS.md/CLAUDE.md" (was using parenthetical style).
- **upstreams.json** — Removed extraneous blank line, updated superpowers lastSyncedCommit from a98c5df to e4a2375.

### Key Changes
- Hook count reduced 12 to 10 (2 hooks removed/consolidated)
- Command count increased 53 to 54 (new /route command added, visible in catalog)
- Superpowers upstream synced to newer commit

## Group 3: Update Catalog and Roadmap (aea2ee0)

### Files Modified
- **docs/catalog.json** — Updated generation timestamp, command/hook counts, added new /route command entry ("Universal entry point — discovers work, resumes sprints, classifies tasks, and dispatches to /sprint or /work"), updated /sprint description to reference /route.
- **docs/clavain-roadmap.md** — Complete rewrite from 276-line detailed roadmap to 25-line auto-generated bead summary. Lists blocked items (7 beads: P2-P4), open items (3 beads: P0-P2), and recently closed items (2 beads).
- **docs/roadmap.md** — Changed from symlink to regular file (mode 120000 to 100644).

### Key Observations
- The roadmap was dramatically simplified — the detailed track-based roadmap (Tracks A/B/C with convergence diagrams, autonomy ladder mapping, supporting epics) has been replaced with a compact auto-generated view from the beads system.
- The new /route command serves as a universal entry point that dispatches to /sprint or /work, suggesting improved UX for task initiation.

## Post-Push State

- Working tree is clean (only pre-existing untracked docs/research/ files remain)
- HEAD is at aea2ee0 on main
- Remote origin/main is up to date

```
aea2ee0 docs: update catalog and roadmap
e838566 chore: update docs, setup command, and upstreams config
a153b73 chore: remove beads artifacts
16a1047 chore: bump version to 0.6.75
```
