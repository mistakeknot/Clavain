# Flux-Drive Improvements Brainstorm

**Date:** 2026-02-08
**Status:** Implemented (commit 3d02843) — post-implementation review below

## Flux Drive Enhancement Summary

Reviewed by 4 agents (3 codebase-aware, 1 generic) on 2026-02-08.

### Key Findings
- Model hints in Tier 3 table are non-functional — `model: haiku/sonnet` in SKILL.md has no runtime effect since agent files use `model: inherit` and orchestrator doesn't override (3/4 agents)
- Step 3.0.5 (validation) is physically placed after Step 3.1 in SKILL.md despite being numbered to run before it (2/4 agents)
- Token budget math claims 29% savings but actual optimizations yield ~18-21% (2/4 agents)
- Section trimming relies on prompt instructions with no enforcement mechanism (2/4 agents)

### Issues to Address
- [ ] Remove Model column from Tier 3 table — Opus-by-default policy (P0, 3/4 agents)
- [ ] Fix Step 3.0.5 ordering — move before Step 3.1 or renumber (P0, 2/4 agents)
- [ ] Correct token budget math in this brainstorm (P1, 2/4 agents)
- [ ] Consider trimming enforcement mechanism for future iteration (P1, 2/4 agents)
- [ ] Update brainstorm status — improvements 1, 3, 4 already implemented (P1, 1/4 agents)

## What We're Building

A comprehensive improvement pass on the flux-drive skill addressing six areas: output validation, token optimization, stale integration claims, qmd integration, triage calibration, and Phase 4 testing.

## Why This Approach

Flux-drive is Clavain's flagship multi-agent review skill. Two self-reviews (v1: 29 issues, v2: 28 issues) proved it works well for Phases 1-3 but revealed untested code paths, token waste from document duplication, and aspirational integration claims. The token budget analysis showed ~197K tokens per 6-agent review, with 38% (75K tokens) going to document duplication across agents.

## Key Decisions

1. **Full scope (Approach C)** — Surgical fixes + token optimization + Phase 4 validation
2. **Codex-first execution** — All code changes dispatched through Codex agents
3. **No subagent architecture changes** — Improvements are to the SKILL.md orchestration, not the agent markdown files
4. **YAML frontmatter is working** — Keep the structured output approach, just add validation

## Improvement Areas

### 1. Agent Output Validation (Reliability)
- Add validation step in Phase 3 before synthesis
- Check each output file starts with `---` and has `issues:`, `verdict:` keys
- Clear error reporting when agents don't follow output format
- Fallback behavior when frontmatter is malformed

### 2. Token Optimization (Cost)
- **Enforce section trimming**: Actually implement "1-line summary for out-of-domain sections" rule. Target: reduce per-agent document cost from ~12K to ~6K tokens (saves ~36K for 6 agents).
- **Add haiku model hint**: Tier 3 agents doing pattern/simplicity review can use haiku instead of inheriting opus. Add `model: haiku` suggestion in triage.

> **Flux Drive** (fd-architecture, fd-code-quality, fd-performance): Model hints in the roster table are advisory text only — agent `.md` files all declare `model: inherit`. The orchestrator must pass `model:` in the Task call for this to work. User policy is Opus-by-default, so remove the Model column entirely.
- **Compress prompt template**: Reduce from ~85 lines to ~50 lines by tightening instructions.
- **Domain-specific document slicing**: Phase 1 extracts per-domain section summaries that agents receive instead of full document.

### 3. Fix Stale Integration Claims
- Lines 540-541 claim flux-drive is "Called by writing-plans and brainstorming skills" — neither actually calls it
- Either implement the integration OR remove the claims
- Decision: Remove claims for now, add as future enhancement

### 4. qmd Integration (Step 1.0)
- Use qmd semantic search in Step 1.0 to find relevant project documentation
- Helps Tier 1 agents get better project context
- qmd is now an MCP server — tools available to all sessions

### 5. Triage Calibration
- Add concrete scoring examples (what's a 2 vs 1 vs 0 for different document types)
- Add quantitative thresholds for thin/adequate/deep sections
- Mine convergence data from past reviews to inform future scoring

### 6. Phase 4 Validation
- Test Oracle availability detection
- Test Oracle CLI invocation with DISPLAY/CHROME_PATH env vars
- Test splinterpeer auto-chain on disagreements
- Test winterpeer offer logic on critical decisions
- Fix any bugs found

## Open Questions

- Should we add a `--fast` flag that limits to 3 agents max for quick reviews?
- Should thin-section enrichment (Step 3.3) be tested now or deferred?
- What model should Tier 3 agents default to? (haiku saves tokens, sonnet is middle ground)

> **Flux Drive** (fd-performance): Resolved — user policy is Opus by default, inherit in clodex mode. Remove model hints from Tier 3 table.

## Token Budget Target

| Metric | Current | Target |
|--------|---------|--------|
| Per-agent document cost | ~12K tokens | ~6K tokens |
| 6-agent total | ~197K tokens | ~140K tokens |
| Savings | — | ~29% reduction |

> **Flux Drive** (fd-architecture, fd-performance): The 29% target is arithmetically inconsistent. Per-agent halving (12K→6K) across 6 agents saves 36K tokens, yielding 161K (18% reduction). Even with prompt compression (~4-6K), max plausible savings reach ~21%, not 29%. Rework with bottom-up estimates.

## Next Step

Run `/clavain:write-plan` to create implementation plan.
