# Pyramid Mode for Flux-Drive Reviews

**Bead:** Clavain-5kea (P1)
**Inspired by:** StrongDM Software Factory — [Pyramid Summaries](https://factory.strongdm.ai/techniques/pyramid-summaries)

## Problem

Flux-drive review agents currently receive **full document content** in their prompts (launch.md Step 2.2, "Include the full document in each agent's prompt without trimming"). For large PRs, plans, or repo reviews, this burns significant context on content irrelevant to each agent's domain.

The synthesis phase (Step 3.2) already uses a pyramid-like approach — reading Findings Index first, then expanding to prose only when needed. But agents themselves don't get this optimization.

### Current Flow (wasteful)

```
Document (1000 lines) → fd-architecture gets all 1000 lines
                       → fd-safety gets all 1000 lines
                       → fd-quality gets all 1000 lines
                       → fd-performance gets all 1000 lines
```

### Proposed Flow (pyramid)

```
Document (1000 lines) → Pyramid scan produces 200-line overview
                       → Each agent gets: overview + expanded sections relevant to their domain
                       → Agents can request expansion of additional sections if needed
```

## Existing Precedent in Clavain

Flux-drive already has **diff slicing** for large diffs (>= 1000 lines) — domain-specific agents get priority hunks in full + compressed context summaries for the rest. Pyramid mode extends this same idea to **file and directory inputs**, not just diffs.

## Design

### Phase 1.5: Pyramid Scan (new step between Analysis and Launch)

**Trigger:** `INPUT_TYPE = file|directory` AND estimated document size > 500 lines.

For smaller documents, skip — full content is fine.

**Process:**

1. **Generate section-level summaries** (done by the orchestrator, not agents):
   - For each section identified in the document profile (Step 1.1), produce a 2-3 sentence summary
   - Include: section name, approximate line count, key topics, key symbols/functions mentioned
   - Format as a "pyramid overview" block

2. **Map sections to agent domains** using the same domain keywords from diff-routing:
   - fd-architecture → module boundaries, coupling, imports, dependencies
   - fd-safety → auth, credentials, encryption, permissions, deploy
   - fd-correctness → transactions, races, async, error handling
   - fd-quality → naming, style, tests, documentation
   - fd-user-product → user flows, UI, UX, onboarding
   - fd-performance → queries, loops, caching, memory, rendering

3. **Per-agent content assembly:**
   ```
   Agent receives:
   - Full pyramid overview (all section summaries — ~20% of original size)
   - Full text of sections mapped to their domain
   - Full text of sections with thin ratings from Step 1.1
   - Instruction: "If you need full text of a summarized section, note 'Request expansion: [section]' in findings"
   ```

### Changes to Existing Files

**SKILL.md (Phase 1):**
- After Step 1.2 (agent selection), add Step 1.2c: Pyramid Scan
- Only runs when document > 500 lines and INPUT_TYPE is file or directory
- Generate section summaries, map to agent domains

**phases/launch.md (Step 2.2):**
- Modify prompt template: instead of "[Trimmed document content]", use pyramid-assembled content
- Add "expansion request" instruction to prompt template
- Add handling for expansion requests in Step 2.2b (post-Stage 1): if an agent requested expansion, re-launch with expanded content

**phases/shared-contracts.md:**
- Add "Request expansion: [section]" to the Findings Index format as an optional annotation
- Add pyramid mode metadata line: `[Pyramid mode: N sections summarized, M sections expanded for this agent]`

### Edge Cases

| Case | Handling |
|------|----------|
| All sections map to one agent | That agent gets full content; others get overview only |
| No sections map to an agent | Agent gets overview only — may produce fewer findings (expected) |
| Agent requests expansion | Orchestrator re-launches with expanded content (like diff slicing re-run) |
| Very short document (< 500 lines) | Skip pyramid entirely — full content is cheap |
| Diff input type | Skip — diff slicing already handles this |

### Token Budget Estimate

For a 1000-line plan document with 8 sections:
- **Current:** 1000 lines × 6 agents = 6000 line-equivalents in prompts
- **Pyramid:** ~200 lines overview + ~250 lines domain-specific per agent × 6 = ~1700 line-equivalents
- **Savings:** ~70% context reduction

### Expansion Request Loop

To prevent infinite loops:
- Max 1 expansion request per agent per run
- If Stage 1 agent requests expansion, include it in the Stage 2 prompt (batch with Stage 2 launch)
- If a Stage 2 agent requests expansion, note it in findings but do NOT re-launch

## Implementation Order

1. Add pyramid scan logic to SKILL.md (Step 1.2c) — the section summarizer
2. Modify launch.md prompt template to accept pyramid content
3. Add expansion request handling to shared-contracts.md
4. Update synthesize.md convergence counting to account for pyramid mode
5. Test with a large plan document (e.g., the test-suite-design plan)

## Risk

- **False compression:** Summarizer misses critical detail in a section → agent can't find the issue. Mitigated by expansion requests.
- **Complexity:** Adding another conditional path to an already complex orchestration. Mitigated by only triggering for large documents.
- **Orchestrator overhead:** Generating section summaries takes time. Mitigated by doing it once (not per-agent) and reusing.
