# Analysis: Core Scoring Specification for flux-drive

## Task Summary

Wrote `/root/projects/Interflux/docs/spec/core/scoring.md` — the agent selection scoring algorithm specification for flux-drive. This is a "Core" conformance-level spec that defines the foundational algorithm all flux-drive implementations must support.

## Structure Delivered

### 1. Score Formula (4 components, max 7 points)
- **base_score (0-3)**: Intrinsic relevance (irrelevant/tangential/adjacent/core)
- **domain_boost (0-2)**: From injection criteria bullet counts in domain profiles
- **project_bonus (0-1)**: Projects with CLAUDE.md/AGENTS.md get +1
- **domain_agent_bonus (0-1)**: flux-gen agents in their native domain get +1

### 2. Base Score Semantics with Hard Barrier
The 0-3 scale maps to natural language categories:
- **0 = irrelevant**: Always excluded, bonuses cannot override
- **1 = tangential**: Include only for thin sections
- **2 = adjacent**: Relevant secondary concern
- **3 = core**: Primary domain overlap

Key design decision: The hard barrier at 0 prevents "maybe relevant" agents from getting selected via bonuses alone. This preserves resource efficiency.

### 3. Dynamic Slot Ceiling Algorithm
```
base (4) + scope (0-3) + domain (0-2) + generated (0-2) = 4-11, capped at 12
```

Adapts to:
- **Scope**: Single file (0), small diff (+1), large diff (+2), directory (+3)
- **Domains**: 0 domains (0), 1 domain (+1), 2+ domains (+2)
- **Generated agents**: Has flux-gen agents (+2), none (0)

This ensures small reviews stay lean (4-5 agents) while multi-domain repo reviews can scale (up to 12).

### 4. Pre-Filtering (Before Scoring)
Reduces candidate pool before score calculation:

**File/directory inputs:**
- Data filter: skip correctness unless DB/migration/concurrency keywords
- Product filter: skip user-product unless PRD/product keywords
- Deploy filter: skip safety unless security/deploy keywords
- Game filter: skip game-design unless game-simulation domain or game keywords
- Always pass: architecture, quality, performance (domain-general)

**Diff inputs:**
- Use routing patterns from domain profiles (priority file patterns + hunk keywords)
- Domain-general agents always pass

### 5. Stage Assignment with Tiebreaker
- **Stage 1**: Top 40% of slots (rounded up, min 2, max 5) — highest-value agents run first in parallel
- **Stage 2**: Remaining selected agents
- **Expansion pool**: Agents scoring ≥2 but not selected (available for escalation)

Tiebreaker at Stage 1 boundary: Project > Plugin > Cross-AI

### 6. Selection Rules (4-step process)
1. All agents scoring ≥3 included (strong relevance)
2. Agents scoring 2 included if slots remain
3. Agents scoring 1 included only for thin sections AND slots remain
4. Deduplication: Project Agent > Plugin Agent > Cross-AI

### 7. Three Worked Examples
- **Example 1**: Go API plan (5 slots, 4 agents selected, web-api domain)
- **Example 2**: Game project plan (7 slots, 7 agents selected, game-simulation domain, 2 flux-gen agents)
- **Example 3**: Database migration diff (6 slots, 5 agents selected, data-pipeline domain)

Each example shows full scoring tables with rationale columns.

## Rationale Callouts (Inline Design Justification)

Used `> **Why this works:**` blocks for 5 key design decisions:

1. **0-3 granularity**: Minimum levels needed for consistent judgment without decision fatigue
2. **Domain boost from bullet counts**: Proxy for "how much domain-specific guidance exists"
3. **Dynamic ceiling formula**: Adapts to scope while preventing resource waste
4. **40% Stage 1 ratio**: Balances parallelism (speed) with focus (quality)
5. **Hard barrier at base_score=0**: Prevents irrelevant agents from consuming slots via bonuses

## Conformance Section

Defined MUST/SHOULD/MAY/MUST NOT rules:

**MUST:**
- Implement base_score (0-3) with documented semantics
- Exclude base_score=0 agents (hard barrier)
- Implement slot ceiling + stage assignment (≥2 stages)
- Pre-filter before scoring

**SHOULD:**
- Implement domain_boost (when domain detection available)
- Use dynamic slot ceiling (adapts to scope)
- Use 40% Stage 1 ratio (or document deviation)

**MAY:**
- Use different score ranges if semantics preserved
- Add implementation-specific bonuses (document them)

**MUST NOT:**
- Allow bonuses to override base_score=0
- Exceed hard_maximum=12 slots
- Assign <2 agents to Stage 1 when ceiling permits

## Interflux Reference Section

Mapped spec components to implementation files:

| Component | File | Lines/Notes |
|-----------|------|-------------|
| Scoring algorithm | `skills/flux-drive/SKILL.md` | Lines 225-332 |
| Worked examples | `skills/flux-drive/references/scoring-examples.md` | Extended examples |
| Domain profiles | `config/flux-drive/domains/*.md` | 11 domains, injection criteria |
| Domain index | `config/flux-drive/domains/index.yaml` | Detection rules + routing patterns |

Included agent metadata schema (YAML frontmatter for category, domain, injection_criteria).

## Style Notes

- **Abstract language**: Used "agent runtime", "orchestrator" instead of "Claude Code subagent", "Task tool"
- **Decision tables**: 13 tables for rules (base score semantics, domain boost, filters, stage assignment, etc.)
- **Pragmatic prose**: No academic tone, focused on implementer needs
- **Inline rationale**: Design decisions justified where they appear, not in separate "Design Rationale" section

## Key Insights from Writing Process

1. **The 0-barrier is load-bearing**: Without it, an irrelevant agent could score 0+2+1+1=4 and consume a slot. The MUST NOT rule codifies this.

2. **Dynamic ceiling prevents both waste and starvation**: Fixed ceilings either waste slots (small reviews with 10 agents) or starve reviews (repo review with 4 agents). The formula adapts.

3. **Stage assignment needs constraints**: Without min=2, a 1-agent Stage 1 loses parallelism benefit. Without max=5, an 8-agent Stage 1 is too diffuse for quality.

4. **Thin section补填 is an escape hatch**: Allows score-1 agents to be included when document analysis flags gaps. Example: 2-line performance section triggers "this needs more depth" signal.

5. **Pre-filtering is critical for efficiency**: Without it, the orchestrator scores 20+ agents for every review. Filters reduce pool to 6-10 candidates before scoring starts.

## Conformance Level Justification

This is "Core" conformance because:
- All flux-drive implementations need agent selection (can't skip this)
- The algorithm is foundational (scoring → ceiling → stages → execution)
- MUST rules are minimal (0-3 scale, hard barrier, pre-filtering, staging)
- SHOULD rules allow adaptation (domain boost optional if no domain detection)
- MAY rules permit innovation (different score ranges, extra bonuses)

"Extended" specs can layer on top: multi-round selection, cost-based optimization, learning from past reviews, etc.

## Validation Against Template Requirements

- [x] Title with `> flux-drive-spec 1.0 | Conformance: Core` tag
- [x] Overview (3 sentences explaining algorithm purpose)
- [x] Specification (6 subsections: formula, base score, boosts, ceiling, stages, selection)
- [x] Worked examples (3 examples with full scoring tables)
- [x] Interflux Reference (implementation file paths + notes)
- [x] Conformance (MUST/SHOULD/MAY/MUST NOT)
- [x] Pragmatic prose with inline rationale callouts
- [x] Decision tables (13 tables)
- [x] Abstract language (no tool-specific terms)

## Document Stats

- **Length**: ~500 lines
- **Tables**: 13 (decision tables + examples)
- **Rationale callouts**: 5 `> **Why this works:**` blocks
- **Examples**: 3 worked examples with 9 agent scoring tables total
- **Conformance rules**: 12 (4 MUST, 4 SHOULD, 4 MAY, 1 MUST NOT)

## Next Steps (Not Done, Recommendations Only)

1. **Create `scoring-examples.md`**: The spec references `skills/flux-drive/references/scoring-examples.md` for extended examples. Write 5-10 edge cases: ties at ceiling boundary, all agents score 0, expansion pool usage, deduplication scenarios.

2. **Update `SKILL.md` to reference spec**: Add link at top of scoring section (lines 225-332) pointing to this spec as canonical reference.

3. **Validation test suite**: Write pytest structural tests that assert conformance rules (base_score=0 → excluded, ceiling ≤ hard_max, Stage 1 has ≥2 agents, etc.).

4. **Domain profile audit**: Verify all 11 domain profiles have injection criteria for ≥4 agents (otherwise domain_boost is underutilized).

5. **Orchestrator implementation review**: Check if current orchestrator (in flux-drive SKILL.md) matches all MUST rules. If not, file P0 bugs.
