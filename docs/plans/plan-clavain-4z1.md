# Plan: Clavain-4z1 — Pre-filter triage table to domain-relevant agents only

## Context
The triage step (Phase 1, Step 1.2 in SKILL.md) currently scores all 19+ agents against the document profile, including obviously irrelevant ones. For a Python CLI tool, the orchestrator still scores go-reviewer, rust-reviewer, typescript-reviewer, etc. — all of which will be 0. This wastes ~800 tokens of orchestrator context on zero-score rows.

## Current State
- `skills/flux-drive/SKILL.md` Step 1.2 presents a scoring table with ALL agents in the roster
- Scoring: 2 (relevant), 1 (maybe), 0 (irrelevant) + category bonuses
- The orchestrator fills in scores for every agent, then selects those scoring 2+
- Language-specific reviewers (Go, Python, TypeScript, Shell, Rust) are always in the table even when their language isn't in the document

## Implementation Plan

### Step 1: Add pre-filter rules to Step 1.2
**File:** `skills/flux-drive/SKILL.md`

Before the scoring table, add a pre-filter step:

> **Step 1.2a: Pre-filter agents**
> 
> Before scoring, eliminate agents that cannot score ≥1 based on the document profile:
> 
> 1. **Language filter**: Skip language-specific reviewers (go-reviewer, python-reviewer, typescript-reviewer, shell-reviewer, rust-reviewer) unless their language appears in the document profile's Languages field.
> 2. **Data filter**: Skip data-integrity-reviewer, data-migration-expert, deployment-verification-agent unless the document profile mentions databases, migrations, or deployment.
> 3. **Product filter**: Skip product-skeptic, strategic-reviewer, user-advocate unless the document type is PRD, proposal, or strategy document.
>
> **All domain-general agents pass the filter** (architecture-strategist, security-sentinel, performance-oracle, code-simplicity-reviewer, pattern-recognition-specialist, concurrency-reviewer, fd-user-experience, fd-code-quality, spec-flow-analyzer).
>
> Present only passing agents in the scoring table.

### Step 2: Update scoring table header
Same file, update the Step 1.2 table instruction to note that only pre-filtered agents appear:

> Score the following agents (pre-filtered for domain relevance):

## Design Decisions
- **Conservative filter**: Only eliminates agents that are OBVIOUSLY irrelevant (wrong language, wrong domain). Domain-general agents always pass.
- **Profile-based, not content-based**: Uses the structured document profile from Step 1.1 (Languages, type), not raw content scanning. Fast and reliable.
- **No false negatives risk for general agents**: architecture-strategist, security-sentinel, etc. always pass because they apply to any domain.
- **Saves orchestrator work, not agent tokens**: The savings are in the orchestrator's triage context, not in agent dispatch. ~300-500 tokens per run.

## Files Changed
1. `skills/flux-drive/SKILL.md` — Add Step 1.2a pre-filter before scoring table

## Estimated Scope
~15-20 lines of new instructional content. Single file change.

## Acceptance Criteria
- [ ] Language-specific reviewers are skipped when their language isn't in the document
- [ ] Data/deployment agents are skipped for non-data documents
- [ ] Product agents are skipped for non-product documents
- [ ] Domain-general agents always appear in the scoring table
- [ ] Pre-filter uses document profile fields, not raw content scanning
- [ ] Scoring table only shows passing agents
