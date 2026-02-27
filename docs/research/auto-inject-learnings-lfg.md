# Auto-Inject Past Solutions into /lfg Execute Phase

**Bead:** Clavain-b683 (P2)
**Inspired by:** StrongDM Software Factory — [Gene Transfusion](https://factory.strongdm.ai/techniques/gene-transfusion)

## Problem

The learnings-researcher agent exists and works well, but it's **opt-in** — you have to know it exists and manually invoke it. The agent's own docs say it integrates with `/clavain:lfg`, but the actual lfg command (`commands/lfg.md`) **never calls it**.

This means institutional knowledge in `docs/solutions/` and `config/flux-drive/knowledge/` sits passive. Engineers repeat mistakes that are already documented. StrongDM calls this "Gene Transfusion" — using working exemplars to seed new implementations.

### Current lfg Flow (no learnings injection)

```
brainstorm → strategy → write-plan → flux-drive → work → test → quality-gates → resolve → ship
                                                    ↑
                                                    No learnings check before coding
```

### Proposed Flow (learnings injected)

```
brainstorm → strategy → write-plan → flux-drive → [LEARNINGS CHECK] → work → test → quality-gates → resolve → ship
                                                    ↑
                                                    learnings-researcher runs automatically
                                                    results injected into plan context
```

## Design

### Option A: Add Step 4.5 to lfg.md (Recommended)

Add a new step between flux-drive review (Step 4) and execute (Step 5):

```markdown
## Step 4.5: Surface Institutional Knowledge

Before executing the plan, automatically search for relevant past solutions:

1. Launch the `clavain:research:learnings-researcher` agent with:
   - The plan file path from Step 3
   - Keywords extracted from the plan's title, technologies, and domains
2. If learnings are found:
   - Present them to the user as context before execution
   - Append a "## Relevant Learnings" section to the plan file
   - Note: these are advisory — not blockers
3. If no learnings found: proceed silently
```

**Why after flux-drive, not before?** Flux-drive reviews the plan for quality. Learnings inform the *implementation*, not the plan itself. You want learnings fresh in context when you start writing code, not when you're reviewing the plan.

### Option B: Inject into write-plan Skill (Alternative)

The `writing-plans` skill could auto-search learnings while drafting the plan, embedding relevant patterns directly into plan steps. This means learnings shape the plan itself, not just the execution.

**Trade-off:** Option A is simpler (one new step in lfg.md). Option B is deeper (learnings shape the plan structure) but requires modifying the more complex writing-plans skill.

### Option C: Inject into Both (Future)

Run learnings-researcher twice:
1. During write-plan → shapes the plan's approach
2. Before execute → reminds the implementer of gotchas

This is overkill for now but noted for completeness.

## Recommended: Option A

### Changes to commands/lfg.md

Add between Step 4 and Step 5:

```markdown
## Step 4.5: Surface Institutional Knowledge

Before execution, check for relevant past solutions that could inform implementation:

1. Launch the `clavain:research:learnings-researcher` agent with the plan file as context
2. If the agent returns relevant learnings:
   - Present key insights to the user (don't block — just inform)
   - Append a `## Relevant Learnings` section to the plan file with:
     - File references to relevant solutions
     - Key gotchas or patterns to follow
     - Applicable past mistakes to avoid
3. If no relevant learnings found: say "No prior learnings found for this domain" and proceed

This step is advisory — it never blocks execution. Treat learnings as context, not constraints.
```

### Changes to learnings-researcher.md

Update the Integration Points section to reflect that lfg actually calls it:

```markdown
## Integration Points

This agent is **automatically invoked** by:
- `/clavain:lfg` (Step 4.5) — Surfaces relevant learnings before plan execution
- `/clavain:write-plan` — Informs planning with institutional knowledge (planned)

It can also be **manually invoked** before starting work on any feature.
```

### Gene Transfusion Pattern Beyond docs/solutions/

StrongDM's Gene Transfusion is broader than just past bugs — it's about finding *working exemplars* in any codebase and using them as seeds. We could extend learnings-researcher to also search:

1. **`config/flux-drive/knowledge/`** — patterns from past reviews (already indexed by qmd)
2. **The project's own codebase** — find similar implementations as exemplars
3. **Upstream repos** — check if any upstream has solved a similar problem

For now, just docs/solutions/ and knowledge/ is enough. Codebase exemplar search is a future extension.

## Implementation Order

1. Add Step 4.5 to `commands/lfg.md`
2. Update Integration Points in `learnings-researcher.md`
3. Test with an lfg run on a feature that has relevant learnings

## Risk

- **Noise:** Learnings-researcher returns irrelevant results → clutters context before execution. Mitigated by the agent's existing grep-first filtering and relevance scoring.
- **Latency:** Adds ~15-30s to the lfg workflow. Mitigated by making it non-blocking (present results, don't wait for approval).
- **Empty results:** Most projects won't have a populated docs/solutions/. The step gracefully degrades ("No prior learnings found").

## Implementation (2026-02-27)

Implemented as a layered approach (Option B + AGENTS.md):

1. **Floor:** AGENTS.md Operational Guides table points to `docs/solutions/` with search instructions
2. **Ceiling:** `writing-plans` SKILL.md Step 0 spawns `learnings-researcher` before task writing
3. **Safety net:** `/work` Phase 1b checks for `## Prior Learnings` section; if missing, spawns learnings-researcher

Note: `/lfg` was replaced by `/sprint`. The injection happens at write-plan time (Option B), not between plan-review and execute (Option A), because learnings encoded into plan steps have higher leverage than learnings shown just before execution.
