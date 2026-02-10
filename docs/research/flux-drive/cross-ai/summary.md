# Flux Drive Review Summary: cross-ai.md (Clavain-ne6)

Reviewed by 4 agents on 2026-02-09.

## Key Findings

1. **Auto-chain in Step 4.3 violates consent model** (P1, 4/4 agents) — The only unconsented action in all of flux-drive. Mine mode runs automatically when disagreements are found, breaking the established pattern where every consequential action has a gate.

2. **SKILL.md needs skip gate when Oracle absent** (P1, 4/4 agents) — Currently the orchestrator reads the entire Phase 4 file only to discover in Step 4.1 that it should stop. The skip condition should be in SKILL.md before the file-read instruction.

3. **Steps 4.3-4.5 are a 66-line pipeline that re-implements interpeer inline** (P1, 4/4 agents) — flux-drive tells interpeer how to do interpeer's job. Mine mode's workflow, council mode's trigger logic, and a 22-line summary template duplicate interpeer's own specs.

4. **Summary duplication** (P2, 3/4 agents) — Step 4.5 produces a second summary with a different format from Phase 3's report. The user receives two summaries in sequence with no defined relationship.

5. **Oracle failure unhandled in Phase 4** (P1, 2/4 agents) — If oracle-council.md exists but contains only the error notice, Step 4.2 attempts classification against an error message. No guard clause exists.

## Issues to Address

- [ ] Replace auto-chain with single AskUserQuestion consent gate (P1, 4/4 agents)
- [ ] Add SKILL.md skip gate: "If Oracle not in roster, skip Phase 4" (P1, 4/4 agents)
- [ ] Add guard clause for Oracle failure at start of Phase 4 (P1, 2/4 agents)
- [ ] Collapse 4-category classification to 2: blind spots + conflicts (IMP, 2/4 agents)
- [ ] Eliminate Step 4.5 duplicate summary — fold into Phase 3 report (P2, 3/4 agents)
- [ ] Compare against individual agent files, not merged synthesis (P1, 1/4 agents)
- [ ] Handle Oracle empty output (exit 0, 0 bytes) as failure (P2, 1/4 agents)
- [ ] Update SKILL.md Integration section to reflect decoupled interpeer relationship (IMP, 2/4 agents)

## Agreed Rewrite Structure (~30-35 lines)

All 4 agents converged on:

1. Guard clause — validate oracle-council.md (2-5 lines)
2. Classify — blind spots + conflicts (5-8 lines)
3. Present + consent gate — single AskUserQuestion (8-12 lines)
4. Execute chosen escalation — invoke interpeer if approved (4-5 lines)

## Agent Reports

- [fd-user-experience.md](fd-user-experience.md) — 8 UX issues, consent violations, terminal width
- [architecture-strategist.md](architecture-strategist.md) — Phase boundary, interpeer coupling, state dependencies
- [code-simplicity-reviewer.md](code-simplicity-reviewer.md) — YAGNI analysis, proposed 35-line structure
- [spec-flow-analyzer.md](spec-flow-analyzer.md) — 11 flow permutations, 14 gaps, edge cases checklist
