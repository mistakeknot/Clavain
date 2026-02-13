## Flux Drive Self-Review — SKILL

**Reviewed**: 2026-02-13 | **Agents**: 4 launched, 4 completed | **Verdict**: needs-changes (unanimous)

### Critical Findings (P0)

| # | Finding | Convergence | Agents |
|---|---------|-------------|--------|
| 1 | **Progressive loading is illusory** — orchestrator must read all phase files upfront due to cross-references between phases | 4/4 | fd-architecture, fd-performance, fd-quality, fd-user-product |
| 2 | **Findings Index format duplicated in 3 places** without single source of truth (prompt template, shared-contracts, synthesis) | 3/4 | fd-architecture, fd-performance, fd-quality |
| 3 | **Document content multiplication** — same document sent inline to all N agents instead of file reference | 2/4 | fd-performance, fd-architecture |
| 4 | **Prompt template boilerplate** — 1050 tokens of format spec duplicated across all agents (7350 tokens for 7-agent review) | 2/4 | fd-performance, fd-quality |
| 5 | **546-line SKILL.md violates plugin convention** (should be under 100 lines with references) | 1/4 | fd-quality |
| 6 | **Diff slicing logic scattered across 4 files** — single feature split across config, launch, contracts, synthesis | 1/4 | fd-architecture |
| 7 | **Missing escape hatch in triage disagreement loop** — users stuck between Edit/Cancel lose all setup work | 1/4 | fd-user-product |
| 8 | **Expansion decisions made blind** — users don't see Stage 1 findings before choosing whether to continue | 1/4 | fd-user-product |

### Important Findings (P1)

| # | Finding | Convergence | Agents |
|---|---------|-------------|--------|
| 1 | Hidden coupling between triage and synthesis — convergence algorithm defined in wrong phase | 1/4 | fd-architecture |
| 2 | Domain boost calculation opaque — boost derived indirectly from bullet count in separate files | 2/4 | fd-architecture, fd-quality |
| 3 | Dynamic slot allocation formula fragile — hardcoded in narrative text | 1/4 | fd-architecture |
| 4 | Agent prompt template violates DRY — format duplicated across 3 locations | 2/4 | fd-architecture, fd-performance |
| 5 | Error stub format too minimal — loses debugging context | 1/4 | fd-architecture |
| 6 | Completion signal relies on filesystem state — racy rename contract | 1/4 | fd-architecture |
| 7 | Domain profile index weakly typed — no validation profiles exist and are well-formed | 1/4 | fd-architecture |
| 8 | Oracle integration brittle — heavy environmental coupling breaks agent abstraction | 1/4 | fd-architecture |
| 9 | Domain profiles multiply tokens — 921 words each, loaded per agent | 1/4 | fd-performance |
| 10 | Knowledge injection loads 134 lines per agent without dedup | 1/4 | fd-performance |
| 11 | Domain detection runs per-session even when cache exists | 1/4 | fd-performance |
| 12 | Scoring table lacks mental model anchor — users can't predict agent behavior | 1/4 | fd-user-product |
| 13 | Convergence counts mislead when Stage 2 skipped | 1/4 | fd-user-product |
| 14 | Silent domain detection failures create ghost state | 1/4 | fd-user-product |
| 15 | 30-second progress reporting gaps erode user confidence | 1/4 | fd-user-product |
| 16 | Oracle failure recovery undefined | 1/4 | fd-user-product |
| 17 | Inconsistent terminology (tiers/stages, launch/dispatch, document/file/input) | 1/4 | fd-quality |
| 18 | OUTPUT_DIR resolution scattered across 3 locations with conflicting guidance | 1/4 | fd-quality |
| 19 | Agent roster appears mid-skill instead of reference file | 1/4 | fd-quality |

### Improvements Suggested (top 10 by impact)

1. **O3 file reference** — write document to temp file, agents Read it (saves ~60% document tokens) — fd-performance
2. **Compress output format spec** — reduce from ~42 to ~20 lines per agent prompt — fd-performance, fd-quality
3. **Extract slicing as first-class module** — consolidate scattered logic into cohesive interface — fd-architecture
4. **Make domain boosts explicit in frontmatter** — prevents accidental triage changes — fd-architecture
5. **Extract scoring examples + roster to references/** — reduce SKILL.md from 546 to ~100 lines — fd-quality
6. **Create glossary** for tier/stage/phase/launch/dispatch — fd-quality
7. **Show "what you get" in triage table** — alongside scoring transparency — fd-user-product
8. **Add expansion score table** — so users can verify recommendation logic — fd-user-product
9. **Add domain profile validation to test suite** — catch config drift at deploy time — fd-architecture
10. **Instrument diff slicing for token metrics** — validate efficiency claims — fd-performance

### Section Heat Map

| Section | P0 | P1 | IMP | Agents Reporting |
|---------|----|----|-----|-----------------|
| Phase 2: Launch (prompt template) | 3 | 4 | 3 | all 4 |
| Phase File Organization | 1 | 1 | 1 | all 4 |
| Shared Contracts (Findings Index) | 1 | 1 | 1 | fd-architecture, fd-performance, fd-quality |
| Phase 1: Triage + Scoring | 0 | 4 | 3 | fd-architecture, fd-quality, fd-user-product |
| Phase 3: Synthesis | 0 | 1 | 1 | fd-performance, fd-user-product |
| Agent Roster / Oracle | 0 | 2 | 0 | fd-architecture, fd-user-product |
| SKILL.md Structure | 1 | 2 | 2 | fd-quality |
| UX: User Interactions | 2 | 3 | 5 | fd-user-product |

### Conflicts

No direct conflicts. Agents agree on diagnosis but differ on remediation priority:
- fd-architecture recommends consolidating slicing first; fd-performance recommends O3 file reference first. **Resolution**: O3 is lower risk and higher ROI — do it first (this plan).
- fd-quality flags SKILL.md length as P0; fd-architecture treats it as architectural but not blocking. **Resolution**: tracked separately (not in this plan's scope).

### Files

- Summary: `docs/research/flux-drive/SKILL/summary.md`
- Individual reports:
  - [`fd-architecture.md`](./fd-architecture.md) — needs-changes (2 P0, 8 P1, 5 P2, 7 IMP)
  - [`fd-performance.md`](./fd-performance.md) — needs-changes (3 P0, 4 P1, 1 P2, 3 IMP)
  - [`fd-quality.md`](./fd-quality.md) — needs-changes (2 P0, 5 P1, 1 P2, 5 IMP)
  - [`fd-user-product.md`](./fd-user-product.md) — needs-changes (2 P0, 5 P1, 0 P2, 8 IMP)

### Actions Taken

The three highest-convergence findings have been directly addressed:

| Finding | Convergence | Action | Status |
|---------|-------------|--------|--------|
| Progressive loading is illusory | 4/4 | Updated SKILL.md line 10 to honest "file organization" claim | Done |
| Findings Index duplicated in 3 places | 3/4 | Compressed output format in launch.md + shared-contracts.md | Done |
| Document content multiplication | 2/4 | O3 file reference pattern in launch.md Step 2.1c | Done |
| Prompt template boilerplate | 2/4 | O4 compressed output format (~42 → ~20 lines) | Done |
| Knowledge section noise for no-knowledge agents | 2/4 | O5 conditional skip in launch.md | Done |

### Remaining P0s (not addressed in this plan)

- **546-line SKILL.md** — requires structural refactoring (extract to references/). Tracked in Clavain-i1u6.
- **Diff slicing scattered across 4 files** — requires module extraction. Future work.
- **Missing escape hatch in triage** — UX improvement. Future work.
- **Blind expansion decisions** — UX improvement. Future work.

### Token Savings Estimate

| Optimization | Per Agent | ×5 Agents | Notes |
|-------------|----------|-----------|-------|
| O3: File reference | ~15,000 | ~75,000 → ~750 | 99% reduction in orchestrator output tokens |
| O4: Output compression | ~450 | ~2,250 | 44% reduction in format overhead |
| O5: Knowledge skip | ~150 | ~750 | Only for no-knowledge agents |
| **Total** | | **~77,000 saved** | ~84% reduction in orchestrator prompt cost |

*Note: O3 shifts cost from orchestrator output (expensive) to agent input (each reads once). Net agent tokens unchanged.*

<!-- flux-drive:complete -->
