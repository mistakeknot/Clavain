# PRD: P2 Quick Wins Batch

## Problem

Three independent friction points: (1) command names are memorable but not guessable — new users can't find `/flux-drive` without the catalog, (2) upstream-check makes 30 API calls when 12 would suffice, wasting rate limit and adding 2.4s latency, (3) using-clavain injects ~1100 tokens every session when only ~400 are needed for routing.

## Solution

Add guessable command aliases, consolidate redundant API calls, and slim down the session-start injection to a compact router card.

## Features

### F1: Command Aliases (Clavain-np7b)
**What:** Add `/deep-review`, `/full-pipeline`, `/cross-review` as guessable aliases for power commands.
**Acceptance criteria:**
- [ ] `commands/deep-review.md` exists and invokes `clavain:flux-drive` skill
- [ ] `commands/full-pipeline.md` exists and invokes `clavain:lfg` skill with arg passthrough
- [ ] `commands/cross-review.md` exists and invokes `clavain:interpeer` skill
- [ ] `commands/help.md` lists guessable names with alias references
- [ ] `bash -n` not needed (markdown files)
- [ ] Structural tests updated for new command count (33 → 36)

### F2: Consolidate upstream-check API calls (Clavain-4728)
**What:** Reduce `gh api` calls in `scripts/upstream-check.sh` from 5 per upstream to 2.
**Acceptance criteria:**
- [ ] Single `gh api repos/{repo}/commits?per_page=1` call replaces 3 separate calls
- [ ] SHA, message, and date extracted from stored JSON via `jq`
- [ ] Output format unchanged (same columns, same alignment)
- [ ] `bash -n scripts/upstream-check.sh` passes
- [ ] Manual test: `bash scripts/upstream-check.sh` produces same output as before

### F3: Split using-clavain injection (Clavain-p5ex)
**What:** Reduce session-start token cost by splitting `using-clavain/SKILL.md` into compact router + reference tables.
**Acceptance criteria:**
- [ ] `skills/using-clavain/SKILL.md` reduced to ~40 lines (compact router card)
- [ ] `skills/using-clavain/references/routing-tables.md` contains full routing tables
- [ ] Session-start hook still injects SKILL.md content (no hook changes needed)
- [ ] `/clavain:help` command still shows full catalog
- [ ] Routing accuracy maintained — commands still findable by stage/domain

## Non-goals

- Renaming existing commands (cool names stay, aliases are additive)
- Rewriting upstream-check.sh beyond API consolidation
- Changing session-start hook injection mechanism

## Dependencies

None — all three features are independent with no shared files.

## Open Questions

None.
