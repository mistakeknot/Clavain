# Flux-Drive Protocol Specification Brainstorm

**Bead:** Clavain-vsig
**Phase:** brainstorm (as of 2026-02-14T11:33:34Z)
**Date:** 2026-02-14
**Status:** Complete

---

## What We're Building

A standalone protocol specification for the flux-drive multi-agent review orchestration system, extracted from its reference implementation in Interflux. The spec defines the abstract protocol — the 3-phase lifecycle, scoring algorithm, staging logic, synthesis rules, and structured contracts — in a way that's implementation-agnostic while pointing to Interflux as the normative reference.

This is **Phase 1** of a 5-phase extraction project. Phase 1 is documentation-only: no code changes, no library extraction, no migration. Pure specification writing.

### Deliverables

8 specification documents + 1 README, organized into `docs/spec/` within the Interflux repo:

| Document | Conformance | Purpose |
|----------|-------------|---------|
| `core/protocol.md` | Core | 3-phase review lifecycle (triage → launch → synthesize) |
| `core/scoring.md` | Core | Agent selection: base_score + domain_boost + project_bonus, slot ceiling |
| `core/staging.md` | Core | Stage 1/2 assignment, adjacency maps, expansion thresholds |
| `core/synthesis.md` | Core | Index parsing, deduplication, convergence, verdict computation |
| `extensions/domain-detection.md` | Extension | Signal → confidence scoring, caching, staleness |
| `extensions/knowledge-lifecycle.md` | Extension | Provenance tracking, 60-day decay, accumulation rules |
| `contracts/findings-index.md` | Core | Required structured output format (~30 lines) |
| `contracts/completion-signal.md` | Core | How agents signal completion (.partial → complete) |
| `README.md` | — | Spec overview, versioning, conformance levels, Interflux reference |

## Why This Approach

### Audience: Layered

The spec serves two audiences with different needs:

1. **Other AI tool developers** — building their own multi-agent review systems. They need framework-agnostic protocol docs they can implement against, even if their agent runtime is completely different (Cursor extensions, VSCode agents, custom CLIs).

2. **Clavain/Interflux contributors** — extending the existing system. They benefit from clear protocol docs that separate "what the protocol requires" from "how Interflux implements it."

The layered approach handles both: abstract protocol in the spec, Interflux details in the reference implementation. Phase 5 (a separate bead) adds a Claude Code adapter guide for the second audience.

### Positioning: Reference Architecture → Interoperability Standard

Today, this is a **reference architecture**: a well-documented pattern for multi-agent review orchestration. Others can learn from it and adapt. Strict conformance isn't the immediate goal.

The trajectory is toward an **interoperability standard**: a protocol that enables shared domain profiles, portable findings, and compatible agent rosters across different AI tools. The spec is written with that future in mind — clean abstractions, conformance levels, and versioned contracts — so the path from "reference doc" to "real standard" is incremental, not a rewrite.

### Spec Style: Pragmatic + Opinionated

- **Clear prose in the author's voice** — not dry RFC language, not academic formalism
- **Decision tables and JSON schemas** for algorithms and contracts — precise enough to implement against
- **Inline rationale** for every major design decision — explains *why*, not just *what*
- Think Stripe API docs meets 12-factor app manifesto

### Location: Inside Interflux

The spec lives at `/root/projects/Interflux/docs/spec/` rather than a standalone repo. Co-locating with the reference implementation:
- Keeps spec and implementation in sync during rapid evolution
- Reduces maintenance burden (one repo to update, not two)
- Can be extracted to a standalone repo later if external adoption warrants it

### Source Material: Hybrid Approach

The existing core algorithm analysis (`docs/research/analyze-flux-drive-core-algorithm.md`, 512 lines) covers much of the protocol. The plan:
1. Use the analysis as scaffolding for structure and coverage
2. Verify every claim against the actual Interflux source code
3. Write the spec documents fresh, grounded in verified source truth

This avoids both "writing from scratch when good analysis exists" and "rubber-stamping analysis that might have drifted from implementation."

## Key Decisions

1. **Conformance levels** — Core (6 docs: protocol, scoring, staging, synthesis, findings-index, completion-signal) vs. Extension (2 docs: domain-detection, knowledge-lifecycle). Implementations can claim "flux-drive-spec 1.0 core" or "flux-drive-spec 1.0 core + domains."

2. **Versioning: Semver** — The spec gets its own version (flux-drive-spec 1.0.0), independent of Interflux's version. Core protocol changes bump major, extensions bump minor, clarifications bump patch.

3. **Abstraction level** — Abstract protocol concepts (agent runtime, orchestrator, findings collector) with Interflux named as the normative reference implementation. Not a line-by-line description of Interflux code.

4. **Inline rationale** — Each major design decision (scoring ranges, expansion thresholds, stage assignment percentages) includes a brief "why this works" explanation. Adds ~30% to document length but makes the spec educational.

5. **Directory structure** — `docs/spec/{core,extensions,contracts}/` mirrors the conformance levels. Makes the layering tangible in the filesystem.

6. **No code in Phase 1** — Pure documentation. No library extraction, no Python packages, no test suites against the spec. Those are Phases 2-5.

## Approach: Layered Conformance Spec

### Directory Structure

```
/root/projects/Interflux/docs/spec/
├── README.md                        # Spec overview, versioning, conformance
├── core/
│   ├── protocol.md                  # 3-phase lifecycle
│   ├── scoring.md                   # Agent selection algorithm
│   ├── staging.md                   # Stage expansion logic
│   └── synthesis.md                 # Findings synthesis
├── extensions/
│   ├── domain-detection.md          # Domain signal scoring
│   └── knowledge-lifecycle.md       # Knowledge decay + accumulation
└── contracts/
    ├── findings-index.md            # Agent output format
    └── completion-signal.md         # Completion signaling
```

### Source Mapping

Each spec document maps to specific Interflux source files:

| Spec Document | Primary Sources |
|---------------|----------------|
| `core/protocol.md` | `skills/flux-drive/SKILL.md` (lines 1-100, lifecycle overview) |
| `core/scoring.md` | `skills/flux-drive/SKILL.md` (lines 225-332, scoring algorithm) + `references/scoring-examples.md` |
| `core/staging.md` | `skills/flux-drive/phases/launch.md` (lines 146-220, expansion logic) |
| `core/synthesis.md` | `skills/flux-drive/phases/synthesize.md` (364 lines) + `phases/slicing.md` |
| `extensions/domain-detection.md` | `scripts/detect-domains.py` + `config/flux-drive/domains/index.yaml` |
| `extensions/knowledge-lifecycle.md` | `config/flux-drive/knowledge/README.md` + knowledge/*.md frontmatter |
| `contracts/findings-index.md` | `skills/flux-drive/phases/shared-contracts.md` (findings index section) |
| `contracts/completion-signal.md` | `skills/flux-drive/phases/shared-contracts.md` (completion section) |

### Document Template

Each spec document follows a consistent structure:

```markdown
# [Title]

> flux-drive-spec 1.0 | Conformance: Core|Extension

## Overview
[2-3 sentence summary of what this document specifies]

## Specification
[The actual protocol — algorithms, decision tables, schemas]

### [Section]
[Precise description with rationale callouts]

> **Why this works:** [Brief explanation of design decision]

## Interflux Reference
[How the reference implementation handles this — file paths, notable choices]

## Conformance
[What an implementation MUST/SHOULD/MAY do to conform to this section]
```

### Conformance Levels

**flux-drive-spec 1.0 Core** — An implementation that:
- Implements the 3-phase lifecycle (triage → launch → synthesize)
- Uses the scoring algorithm for agent selection (or a compatible alternative)
- Supports Stage 1/2 expansion with configurable thresholds
- Produces findings in the specified index format
- Uses the completion signaling protocol

**flux-drive-spec 1.0 Core + Domains** — Additionally:
- Implements domain detection with weighted signal scoring
- Supports multi-domain classification
- Provides domain-specific scoring boosts

**flux-drive-spec 1.0 Core + Knowledge** — Additionally:
- Tracks finding provenance (independent vs. primed)
- Implements temporal decay (configurable period, default 60 days)
- Supports knowledge accumulation from synthesis results

## Open Questions

1. **Spec testing** — Should Phase 1 include conformance test descriptions (even without implementing them)? Or defer test specs to Phase 2?

2. **Diagram format** — Should the spec include Mermaid diagrams for the lifecycle and scoring flows? Good for comprehension but adds maintenance burden.

3. **Contract strictness** — The findings index format is currently loosely specified (pipe-delimited text). Should the spec tighten it with a formal grammar or JSON schema? Tighter contracts enable better tooling but reduce flexibility.

4. **Agent abstraction** — How abstract should the "agent" concept be? Current Interflux agents are Claude Code subagents, but the protocol could work with any callable that produces findings. Should the spec define a minimal agent interface?

5. **Extension mechanism** — Should the spec describe how to add new extensions beyond domains and knowledge? Or keep the extension surface implicit until Phase 2-3?

## Not Building (YAGNI)

- **No standalone repo** — spec lives in Interflux until adoption warrants extraction
- **No conformance test suite** — that's Phase 2+ work
- **No migration tooling** — no code changes in Phase 1
- **No formal grammar** — pragmatic spec, not BNF. Schemas use JSON examples, not formal notation
- **No multi-implementation compatibility matrix** — only one implementation exists today
- **No governance process** — spec changes follow Interflux's normal PR process for now
