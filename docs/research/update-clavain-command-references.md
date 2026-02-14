# Update Clavain Command References: clavain:flux-* → interflux:flux-*

**Date:** 2026-02-14
**Status:** Complete

## Objective

Replace all flux-drive and flux-gen namespace references from `clavain:` to `interflux:` across command files and the using-clavain skill, reflecting the extraction of flux-drive into the Interflux companion plugin.

## Replacements Performed

### 1. Commands directory (`commands/*.md`)

All 9 replacement patterns applied via `sed -i`:

| Old Reference | New Reference |
|---|---|
| `clavain:flux-drive` | `interflux:flux-drive` |
| `clavain:flux-gen` | `interflux:flux-gen` |
| `clavain:review:fd-architecture` | `interflux:review:fd-architecture` |
| `clavain:review:fd-safety` | `interflux:review:fd-safety` |
| `clavain:review:fd-correctness` | `interflux:review:fd-correctness` |
| `clavain:review:fd-quality` | `interflux:review:fd-quality` |
| `clavain:review:fd-user-product` | `interflux:review:fd-user-product` |
| `clavain:review:fd-performance` | `interflux:review:fd-performance` |
| `clavain:review:fd-game-design` | `interflux:review:fd-game-design` |

**Files modified in commands/:**
- `plan-review.md` — 2 occurrences (fd-architecture, fd-quality subagent_type)
- `work.md` — 1 occurrence (gate-blocked message)
- `full-pipeline.md` — 1 occurrence (flux-drive invocation)
- `deep-review.md` — 1 occurrence (skill reference)
- `execute-plan.md` — 1 occurrence (gate-blocked message)
- `lfg.md` — 2 occurrences (flux-drive invocation + gate-blocked message)
- `strategy.md` — 1 occurrence (flux-drive invocation)
- `help.md` — 3 occurrences (flux-drive x2, flux-gen x1)

### 2. Skills: `using-clavain/SKILL.md`

2 replacements:
- Line 19: `/clavain:flux-drive` → `/interflux:flux-drive`
- Line 26: `/clavain:flux-gen` → `/interflux:flux-gen`

**Note:** The alias reference `/clavain:deep-review` on line 19 was intentionally NOT changed — it remains a Clavain-owned alias that delegates to interflux.

### 3. Skills: `using-clavain/references/routing-tables.md`

3 replacements:
- Line 51: `/clavain:flux-drive` → `/interflux:flux-drive`
- Line 55: `/clavain:flux-gen` → `/interflux:flux-gen`
- Line 57: `/clavain:flux-drive` → `/interflux:flux-drive` (default recommendation)

## Verification

Post-replacement grep for stale references:
```
grep -rn 'clavain:flux-drive\|clavain:flux-gen\|clavain:review:fd-' commands/ skills/using-clavain/
```
**Result:** Exit code 1 (no matches found). All 17 occurrences successfully updated.

Post-replacement grep for new references confirmed all 17 `interflux:` references are in place across 10 files.

## Files NOT Modified (by design)

The following were not in scope and may still contain `clavain:flux-drive` or related references:
- `skills/flux-drive/` — The skill content itself (will move to interflux plugin)
- `config/flux-drive/` — Configuration files (will move to interflux plugin)
- `agents/review/` — Agent definitions (will move to interflux plugin)
- `scripts/detect-domains.py` — Domain detection (will move to interflux plugin)
- `tests/` — Test files (should be updated when interflux extraction is complete)
- `docs/` — Historical documentation (may reference old namespace for context)
- `CLAUDE.md`, `AGENTS.md` — Project docs (separate update needed)

## Summary

- **17 total replacements** across **10 files**
- **0 stale references** remaining in target directories
- All `clavain:flux-drive`, `clavain:flux-gen`, and `clavain:review:fd-*` references in `commands/` and `skills/using-clavain/` now point to the `interflux:` namespace
