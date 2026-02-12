# P2 Quick Wins Brainstorm

**Date:** 2026-02-12
**Scope:** 3 independent P2 beads — all single-session, parallelizable via Codex

## What We're Building

### F1: Command Aliases (Clavain-np7b)
Add guessable aliases for power commands:
- `/clavain:deep-review` → invokes `clavain:flux-drive` skill
- `/clavain:full-pipeline` → invokes `clavain:lfg` skill (passes through args)
- `/clavain:cross-review` → invokes `clavain:interpeer` skill

Commands are markdown files in `commands/`. Each alias is a thin wrapper that invokes the target skill. Pattern: copy the target command's content but keep the alias name.

Update `commands/help.md` to list guessable names as primary, cool names as "(alias: flux-drive)".

### F2: Consolidate upstream-check API calls (Clavain-4728)
`scripts/upstream-check.sh` makes 3 redundant `gh api` calls per upstream to the same `/commits?per_page=1` endpoint with different `--jq` filters. Consolidate into 1 call, parse 3 fields locally.

Before: 5 API calls × 6 upstreams = 30 calls
After: 2 API calls × 6 upstreams = 12 calls
Saves ~2.4s and 50% rate limit.

### F3: Split using-clavain injection (Clavain-p5ex)
`skills/using-clavain/SKILL.md` (117 lines, ~1100 tokens) is injected every session. It tries to be router + catalog + docs. Split into:
- **Compact router card** (~40 lines): stage detection heuristic + top commands per stage
- **Full routing tables** in `skills/using-clavain/references/routing-tables.md`

The `/clavain:help` command already exists as the full catalog. The injected SKILL.md just needs to route correctly, not enumerate everything.

## Why This Approach

- All 3 items are independent — no shared files, no ordering dependencies
- Each is well-scoped: 1-3 files touched, clear acceptance criteria
- Perfect for parallel Codex delegation

## Key Decisions

- Aliases are commands (not skill aliases) because Claude Code doesn't support skill-level aliasing
- upstream-check.sh consolidation is pure performance — no behavioral change
- using-clavain split keeps the SKILL.md as the injected file, just shrinks it

## Open Questions

None — requirements clear from bead descriptions and repo research.
