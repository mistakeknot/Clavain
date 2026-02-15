# Flux-Drive Protocol Specification v1.0 — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Write 9 specification documents for the flux-drive multi-agent review protocol, extracted from the interflux reference implementation. Pure documentation — no code changes.

**Architecture:** 9 markdown files in `/root/projects/interflux/docs/spec/{core,extensions,contracts}/`. Each doc follows a consistent template: Overview → Specification → interflux Reference → Conformance. Contracts first (they define the output format other specs reference), then core (they reference contracts), then extensions, then README (indexes everything).

**Tech Stack:** Markdown only. Source verification against interflux Python/YAML/Markdown files.

**Bead:** Clavain-vsig
**Phase:** executing (as of 2026-02-14T17:17:46Z)

**PRD:** `docs/prds/2026-02-14-flux-drive-spec.md`

**Source material:**
- interflux implementation: `/root/projects/interflux/` (~2,982 lines across 9 source files)
- Core algorithm analysis: `/root/projects/Clavain/docs/research/analyze-flux-drive-core-algorithm.md` (512 lines, scaffolding only — verify against source)

---

## Document Template

Every spec document follows this structure. Do not deviate.

```markdown
# [Title]

> flux-drive-spec 1.0 | Conformance: Core|Extension

## Overview

[2-3 sentence summary. What this document specifies and why it matters.]

## Specification

[The protocol. Use decision tables, formulas, and examples. Be precise enough to implement against.]

### [Subsection]

[Detail with rationale callouts:]

> **Why this works:** [1-2 sentences explaining the design decision]

## interflux Reference

[How the reference implementation handles this. File paths, notable implementation choices, where the code lives.]

## Conformance

[What an implementation MUST do, SHOULD do, and MAY do to conform to this section.]
```

**Style rules:**
- Write in the author's voice — pragmatic, opinionated, clear. Not RFC-dry, not academic.
- Include inline rationale for every major design decision (scoring ranges, thresholds, stage percentages).
- Use decision tables for algorithms with multiple variables.
- Use JSON examples (not formal schemas) for data structures.
- Mermaid diagrams for lifecycle flows where they aid comprehension.
- Abstract protocol language: "agent runtime", "orchestrator", "findings collector" — not "Claude Code subagent", "Task tool", "background agent".
- Name interflux as the normative reference implementation in the interflux Reference section.

---

## Execution Order

Tasks are ordered by dependency: contracts first (other docs reference them), then core protocol, then extensions, then README.

**Parallelizable groups:**
- Group A (no deps): Task 1 + Task 2 (contracts)
- Group B (depends on A): Task 3 + Task 4 + Task 5 + Task 6 (core specs — conceptually protocol→scoring→staging→synthesis, but each reads from independent source files so execution can be parallel; add forward-references between docs during README assembly)
- Group C (depends on B): Task 7 + Task 8 (extensions, may reference core concepts)
- Group D (depends on all): Task 9 (README indexes everything)

---

### Task 1: Contract — Findings Index Format (F8)

**Files:**
- Create: `/root/projects/interflux/docs/spec/contracts/findings-index.md`

**Source files to read and verify against:**
- `/root/projects/interflux/skills/flux-drive/phases/shared-contracts.md` (69 lines — findings index section)
- `/root/projects/interflux/skills/flux-drive/phases/synthesize.md` (365 lines — how indices are parsed)

**Steps:**

1. Read `shared-contracts.md` and extract the findings index format specification
2. Read `synthesize.md` to understand how the index is parsed and what edge cases exist
3. Cross-reference with the core algorithm analysis section on synthesis
4. Write `contracts/findings-index.md` covering:
   - The pipe-delimited format: `SEVERITY | ID | "Section" | Title`
   - The Verdict line format: `Verdict: safe|needs-changes|risky`
   - Severity levels and their meanings (P0 = critical, P1 = important, P2 = moderate, P3 = minor)
   - ID format and uniqueness rules
   - At least 2 complete examples: one passing (no findings), one with mixed-severity findings
   - Edge cases: no findings, error verdicts, malformed output handling
   - Conformance section: MUST produce valid index, MUST include Verdict line

**Acceptance criteria from PRD:** F8

---

### Task 2: Contract — Completion Signal (F9)

**Files:**
- Create: `/root/projects/interflux/docs/spec/contracts/completion-signal.md`

**Source files to read and verify against:**
- `/root/projects/interflux/skills/flux-drive/phases/shared-contracts.md` (69 lines — completion section)
- `/root/projects/interflux/skills/flux-drive/phases/launch.md` (454 lines — monitoring/timeout logic)

**Steps:**

1. Read `shared-contracts.md` and extract the completion signaling protocol
2. Read `launch.md` to understand how the orchestrator monitors for completion (poll interval, timeout)
3. Write `contracts/completion-signal.md` covering:
   - The `.partial` → final rename flow
   - The `<!-- flux-drive:complete -->` sentinel comment
   - Error stub format (how agents signal failure: `Verdict: error`)
   - Timeout behavior: what happens when an agent doesn't complete (orchestrator timeout, graceful degradation)
   - Partial results: how the orchestrator handles agents that produce output but don't signal completion
   - Conformance section: MUST append sentinel before rename, MUST produce error stub on failure

**Acceptance criteria from PRD:** F9

---

### Task 3: Core Protocol Spec (F2)

**Files:**
- Create: `/root/projects/interflux/docs/spec/core/protocol.md`

**Source files to read and verify against:**
- `/root/projects/interflux/skills/flux-drive/SKILL.md` (415 lines — lifecycle overview, first ~100 lines + orchestration flow)
- `/root/projects/interflux/skills/flux-drive/phases/launch.md` (phase 2 entry/exit)
- `/root/projects/interflux/skills/flux-drive/phases/synthesize.md` (phase 3 entry/exit)
- `/root/projects/interflux/skills/flux-drive/phases/slicing.md` (366 lines — content routing, slicing thresholds, synthesis contracts)
- `/root/projects/Clavain/docs/research/analyze-flux-drive-core-algorithm.md` (scaffolding — verify claims)

**Steps:**

1. Read `SKILL.md` lines 1-100 for the lifecycle overview
2. Read launch.md and synthesize.md headers for phase entry/exit conditions
3. Cross-reference with the core algorithm analysis "Abstract Protocol" section
4. Write `core/protocol.md` covering:
   - Input classification: file, directory, diff — how the orchestrator determines input type
   - Workspace path derivation: INPUT_PATH → INPUT_DIR → PROJECT_ROOT → OUTPUT_DIR
   - Phase 1 (Triage): input profiling, agent roster compilation, scoring, stage assignment, user approval gate
   - Phase 2 (Launch): parallel dispatch, monitoring, Stage 2 expansion decision
   - Phase 3 (Synthesize): collect outputs, parse indices, deduplicate, compute verdict, produce summary
   - Entry/exit conditions for each phase
   - Mermaid lifecycle diagram showing the 3-phase flow with decision points
   - Content routing overview: slicing eligibility (diff ≥1000 lines, document ≥200 lines), how slicing affects Phase 2 dispatch and Phase 3 convergence (reference slicing.md for full details)
   - Rationale: why 3 phases (not 2, not 4), why static-then-dynamic, why structured contracts
   - References to other spec documents (scoring.md, staging.md, synthesis.md, contracts/)
   - Conformance section: MUST implement all 3 phases, MUST support all input types, SHOULD support content routing for large inputs, MAY add pre/post hooks

**Acceptance criteria from PRD:** F2

---

### Task 4: Core Scoring Spec (F3)

**Files:**
- Create: `/root/projects/interflux/docs/spec/core/scoring.md`

**Source files to read and verify against:**
- `/root/projects/interflux/skills/flux-drive/SKILL.md` (lines 225-332 — scoring algorithm)
- `/root/projects/interflux/skills/flux-drive/references/scoring-examples.md` (67 lines)
- `/root/projects/interflux/config/flux-drive/domains/index.yaml` (454 lines — domain list and signal scoring rules)
- `/root/projects/interflux/config/flux-drive/domains/*.md` (11 domain profiles — injection criteria that determine domain_boost scoring)

**Steps:**

1. Read `SKILL.md` lines 225-332 for the complete scoring algorithm
2. Read `scoring-examples.md` for worked examples
3. Read `index.yaml` and 2-3 domain profile `.md` files to understand how injection criteria bullet counts translate to domain_boost (0-2)
4. Cross-reference with the core algorithm analysis "Scoring & Selection" section
4. Write `core/scoring.md` covering:
   - Score formula: `total = base_score + domain_boost + project_bonus + domain_agent`
   - base_score (0-3): 0=irrelevant, 1=tangential, 2=adjacent, 3=core. How to assign.
   - domain_boost (0-2): from domain profile injection criteria. Scoring rules.
   - project_bonus (0-1): +1 if project has CLAUDE.md/AGENTS.md. Rationale.
   - domain_agent (0-1): +1 for generated agents (flux-gen). Rationale.
   - Pre-filtering: data/product/deploy/game category filters — which agents get eliminated before scoring
   - Dynamic slot ceiling formula: `base_slots + scope_slots + domain_slots + generated_slots`, hard maximum (12)
   - Stage assignment: top 40% (rounded up, min 2, max 5) → Stage 1, remainder → Stage 2 + expansion pool
   - Agent deduplication: project-specific > plugin > cross-AI priority
   - At least 2 worked scoring examples (e.g., web API project, game project)
   - Decision table showing score component ranges and their effects
   - Rationale for each range (why 0-3 not 0-5, why 40% cutoff, why hard max 12)
   - Conformance section: MUST implement base_score, SHOULD implement domain_boost, MAY use different ranges with equivalent semantics

**Acceptance criteria from PRD:** F3

---

### Task 5: Core Staging Spec (F4)

**Files:**
- Create: `/root/projects/interflux/docs/spec/core/staging.md`

**Source files to read and verify against:**
- `/root/projects/interflux/skills/flux-drive/phases/launch.md` (lines 146-220 — expansion logic)
- `/root/projects/interflux/skills/flux-drive/SKILL.md` (stage assignment references)

**Steps:**

1. Read `launch.md` lines 146-220 for the complete expansion logic
2. Read the adjacency map section and expansion scoring
3. Write `core/staging.md` covering:
   - Two-stage design: Stage 1 (immediate launch) vs. Stage 2 (conditional expansion)
   - Stage 1 launch: all assigned agents dispatched in parallel, all-at-once
   - Stage 2 expansion decision point: triggered after Stage 1 completes
   - Expansion scoring: severity signals (P0 → +3, P1 → +2, disagreement → +2) + domain signals (+1)
   - Expansion thresholds: ≥3 RECOMMEND expansion, =2 OFFER to user, ≤1 RECOMMEND STOP
   - Adjacency map concept: each agent has 2-3 "neighbors" it can trigger
   - How adjacency maps interact with expansion scoring (only neighbors of triggered agents are candidates)
   - Rationale: why two stages (cost control + diminishing returns), why these threshold values, why adjacency over full-mesh
   - Conformance section: MUST support Stage 1 parallel launch, MUST implement expansion decision, SHOULD use adjacency maps (MAY use full-mesh)

**Acceptance criteria from PRD:** F4

---

### Task 6: Core Synthesis Spec (F5)

**Files:**
- Create: `/root/projects/interflux/docs/spec/core/synthesis.md`

**Source files to read and verify against:**
- `/root/projects/interflux/skills/flux-drive/phases/synthesize.md` (365 lines)
- `/root/projects/interflux/skills/flux-drive/phases/slicing.md` (366 lines — convergence adjustment)
- `/root/projects/interflux/skills/flux-drive/phases/shared-contracts.md` (contracts context)

**Steps:**

1. Read `synthesize.md` for the complete synthesis algorithm
2. Read `slicing.md` for convergence adjustment rules
3. Read `shared-contracts.md` to understand the input format (findings index)
4. Write `core/synthesis.md` covering:
   - Findings collection: gather outputs from all completed agents
   - Index parsing: extract findings from the pipe-delimited index format (references `contracts/findings-index.md`)
   - Deduplication rules: same finding from multiple agents — how to detect and merge
   - Convergence tracking: count how many agents independently found each issue
   - Convergence adjustment: how slicing affects convergence (agents that didn't see relevant content)
   - Verdict computation: P0 → risky, P1 → needs-changes, all clear → safe. Threshold rules.
   - findings.json generation: structured output with agents_launched, agents_completed, findings array, verdict
   - Error handling: agent timeout (use partial results), malformed output (skip with warning), no agents completed (error verdict)
   - Rationale: why convergence matters (multi-agent agreement = higher confidence), why structured output (enables tooling)
   - Conformance section: MUST parse findings index format, MUST compute verdict, MUST handle agent failures gracefully

**Acceptance criteria from PRD:** F5

---

### Task 7: Extension — Domain Detection Spec (F6)

**Files:**
- Create: `/root/projects/interflux/docs/spec/extensions/domain-detection.md`

**Source files to read and verify against:**
- `/root/projects/interflux/scripts/detect-domains.py` (713 lines — detection algorithm)
- `/root/projects/interflux/config/flux-drive/domains/index.yaml` (454 lines — signal definitions)

**Steps:**

1. Read `detect-domains.py` for the complete detection algorithm
2. Read `index.yaml` for signal definitions and domain list
3. Write `extensions/domain-detection.md` covering:
   - 4 signal types with default weights: directories (0.3), files (0.2), frameworks (0.3), keywords (0.2)
   - Signal matching: glob patterns for directories/files, string matching for frameworks/keywords
   - Confidence scoring: weighted sum of matched signals per domain
   - Multi-domain support: a project can match multiple domains (e.g., "game server" = game + web-api)
   - Threshold for domain activation (minimum confidence to include)
   - Cache format: `.claude/flux-drive.yaml` with version, structural hash, git state, mtime
   - Staleness detection: when to re-scan (hash changed, git state changed, cache version mismatch)
   - Domain profile integration: how detected domains feed into scoring (domain_boost) and agent prompt injection
   - Current domains in interflux reference (11 domains listed)
   - Rationale: why these signal types, why these weights, why caching matters
   - Conformance section: MUST support weighted signal scoring, MUST support multi-domain, SHOULD implement caching, MAY use different signal types

**Acceptance criteria from PRD:** F6

---

### Task 8: Extension — Knowledge Lifecycle Spec (F7)

**Files:**
- Create: `/root/projects/interflux/docs/spec/extensions/knowledge-lifecycle.md`

**Source files to read and verify against:**
- `/root/projects/interflux/config/flux-drive/knowledge/README.md` (79 lines)
- Knowledge entry files in `/root/projects/interflux/config/flux-drive/knowledge/*.md` (frontmatter format)
- `/root/projects/interflux/skills/flux-drive/phases/slicing.md` (366 lines — knowledge retrieval and injection into agent prompts)

**Steps:**

1. Read `knowledge/README.md` for lifecycle rules
2. Read 2-3 knowledge entry files to understand the frontmatter format
3. Read `slicing.md` knowledge retrieval section to understand how knowledge entries are injected into agent prompts (semantic search, max 5 entries per agent)
3. Write `extensions/knowledge-lifecycle.md` covering:
   - Knowledge entry format: markdown files with YAML frontmatter (lastConfirmed, provenance)
   - Provenance types: `independent` (found without prompting) vs. `primed` (found because a prior review mentioned it)
   - Temporal decay: 10 reviews without independent confirmation → move to archive/
   - Accumulation: how synthesis extracts durable patterns from review findings
   - Retrieval: how agents access knowledge during review (semantic search, max 5 entries per agent)
   - Compounding workflow: post-synthesis background task that creates/updates knowledge entries
   - Rationale: why provenance matters (prevents echo chambers), why decay (prevents stale knowledge from biasing reviews)
   - Conformance section: MUST track provenance, MUST implement decay, SHOULD use semantic retrieval, MAY use different decay periods

**Acceptance criteria from PRD:** F7

---

### Task 9: Spec README (F1)

**Files:**
- Create: `/root/projects/interflux/docs/spec/README.md`

**Depends on:** All other tasks (indexes their output)

**Steps:**

1. Read all 8 spec documents created in Tasks 1-8
2. Write `docs/spec/README.md` covering:
   - Spec title: "Flux-Drive Protocol Specification"
   - Version: 1.0.0
   - One-paragraph overview: what flux-drive is, what this spec defines
   - Audience section: AI tool developers (framework-agnostic protocol) + interflux contributors (reference docs)
   - Document index table: each spec document with one-line description and conformance level
   - Conformance levels:
     - **Core**: protocol, scoring, staging, synthesis, findings-index, completion-signal
     - **Core + Domains**: adds domain-detection
     - **Core + Knowledge**: adds knowledge-lifecycle
   - Versioning policy: semver (major = core protocol changes, minor = extensions, patch = clarifications)
   - interflux reference: link to `/root/projects/interflux/` as the normative reference implementation
   - Directory structure diagram showing `core/`, `extensions/`, `contracts/`
   - Getting started: suggested reading order (README → protocol → contracts → scoring → staging → synthesis → extensions)

**Acceptance criteria from PRD:** F1

---

## Pre-flight Checklist

Before starting execution:
- [ ] Verify `/root/projects/interflux/` exists and is accessible
- [ ] Create directory structure: `docs/spec/{core,extensions,contracts}/`
- [ ] Verify all source files listed above exist and have expected content

## Post-execution Checklist

After all tasks complete:
- [ ] All 9 files created in correct locations
- [ ] All documents follow the template structure
- [ ] Cross-references between documents are valid (e.g., synthesis references contracts/findings-index)
- [ ] No interflux-specific terminology leaks into abstract protocol sections (check for "Claude Code", "subagent", "Task tool", "plugin cache")
- [ ] Each document has Overview, Specification, interflux Reference, and Conformance sections
- [ ] README document index matches actual files created
