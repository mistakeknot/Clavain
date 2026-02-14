# Plan: Add Success Criteria to flux-gen Template

**Bead:** Clavain-4cqy
**Phase:** executing (as of 2026-02-14T05:58:17Z)
**Date:** 2026-02-13
**Scope:** Small — single file edit (commands/flux-gen.md), ~30 lines added

## Context

Generated agents from `/flux-gen` have a "What NOT to Flag" section (lines 115-123) but no way to self-calibrate review quality. Core fd-* agents achieve this through specialized sections:
- fd-correctness: "Failure Narrative Method" (describe concrete interleavings)
- fd-architecture: "Focus Rules" (smallest viable change, no repeats)
- fd-correctness: "Communication Style" (step-by-step, reproducible)

Generated agents need an equivalent — a "Success Criteria" section in the template that tells the agent what a *good* review looks like for domain-specific work.

## Tasks

- [x] **Task 1: Add `## Success Criteria` section to the flux-gen template**
  - Location: `commands/flux-gen.md`, Step 4 template, after `## What NOT to Flag` and before `## Decision Lens`
  - Content: 5-6 bullets defining what a good domain-specific review looks like
  - Must be generic enough to work across all 11 domains but specific enough to be useful
  - Should reference the domain name via `{domain-name}` template variable
  - Pattern: draw from core agent quality bars (Failure Narrative, Focus Rules, Communication Style)

- [x] **Task 2: Add domain-specific success criteria hints to domain profiles**
  - Location: `config/flux-drive/domains/*.md` — each domain's Agent Specifications section
  - Add an optional `- **Success criteria hints**:` field to each agent spec
  - When present, these hints are appended to the generic Success Criteria section
  - When absent, the generic template stands alone (no fallback generation needed)
  - Only add hints to 2-3 domains as examples (game-simulation, web-api, claude-code-plugin) — others can be added later

- [x] **Task 3: Bump flux_gen_version to 3**
  - Update `flux_gen_version` references in flux-gen.md from `2` to `3`
  - Update the version description line at bottom to mention success criteria

## Template Design

```markdown
## Success Criteria

A good {domain-name} review:
- Ties every finding to a specific file, function, and line number — never a vague "consider X"
- Provides a concrete failure scenario for each P0/P1 finding — what breaks, under what conditions
- Recommends the smallest viable fix, not an architecture overhaul
- Distinguishes domain-specific expertise from generic code quality (defer the latter to core agents)
- Frames uncertain findings as questions: "Does this handle X?" not "This doesn't handle X"
{domain_success_hints — if present in profile, appended as additional bullets}
```

## Non-goals

- Not changing existing generated agents (users regenerate when ready)
- Not adding success criteria to domain profiles that don't have Agent Specifications sections
- Not modifying core fd-* agents (they already have their own quality calibration)

## Verification

```bash
# Template renders correctly
grep -c "Success Criteria" commands/flux-gen.md  # Should be 2+ (section + reference)

# Domain hints exist in example profiles
grep -l "Success criteria hints" config/flux-drive/domains/*.md  # Should be 2-3 files

# Version bumped
grep "flux_gen_version: 3" commands/flux-gen.md  # Should match

# Structural tests still pass
uv run --project tests pytest tests/structural/ -q
```
