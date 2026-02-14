# PRD: Flux-Drive Protocol Specification v1.0

**Bead:** Clavain-vsig
**Brainstorm:** `docs/brainstorms/2026-02-14-flux-drive-spec-brainstorm.md`

## Problem

The flux-drive multi-agent review protocol exists only as implementation code scattered across Interflux's SKILL.md, phase files, and scripts. There's no standalone specification that someone could read to understand the protocol, implement a compatible system, or verify conformance. The existing core algorithm analysis is research, not spec.

## Solution

Write 9 specification documents (README + 4 core + 2 extensions + 2 contracts) in `docs/spec/` within the Interflux repo. Each document is a pragmatic spec with inline rationale, decision tables, and JSON schemas — precise enough to implement against, written in the author's voice, with Interflux as the normative reference implementation.

## Features

### F1: Spec README + Directory Scaffold
**What:** Create the `docs/spec/` directory structure and README with spec overview, versioning (semver), and conformance level definitions.
**Acceptance criteria:**
- [ ] `docs/spec/README.md` exists with spec version (1.0.0), conformance levels (Core, Core+Domains, Core+Knowledge), and Interflux reference link
- [ ] Directory structure: `docs/spec/{core,extensions,contracts}/` created
- [ ] README explains the layered audience (tool developers + contributors)
- [ ] README includes document index with one-line descriptions

### F2: Core Protocol Spec (protocol.md)
**What:** Specify the 3-phase review lifecycle (triage → launch → synthesize) as an abstract protocol.
**Acceptance criteria:**
- [ ] Defines input classification (file, directory, diff) and workspace path derivation
- [ ] Describes all 3 phases with entry/exit conditions
- [ ] Includes lifecycle diagram (Mermaid or ASCII)
- [ ] Rationale for 3-phase design vs. alternatives
- [ ] Verified against `skills/flux-drive/SKILL.md` lines 1-100

### F3: Core Scoring Spec (scoring.md)
**What:** Specify the agent selection algorithm: score components, dynamic slot ceiling, stage assignment.
**Acceptance criteria:**
- [ ] Documents score formula: base_score(0-3) + domain_boost(0-2) + project_bonus(0-1) + domain_agent(0-1)
- [ ] Documents pre-filtering rules (data/product/deploy/game)
- [ ] Documents dynamic slot ceiling: base_slots + scope_slots + domain_slots + generated_slots, hard max
- [ ] Documents stage assignment: top 40% → Stage 1, rest → Stage 2 pool
- [ ] Includes scoring examples (at least 2 scenarios)
- [ ] Rationale for score ranges and thresholds
- [ ] Verified against `SKILL.md` lines 225-332 + `references/scoring-examples.md`

### F4: Core Staging Spec (staging.md)
**What:** Specify Stage 1/2 expansion logic including adjacency maps and expansion thresholds.
**Acceptance criteria:**
- [ ] Documents Stage 1 launch (parallel, all-at-once)
- [ ] Documents Stage 2 expansion decision: severity signals (P0+3, P1+2, disagreement+2) + domain signals (+1)
- [ ] Documents expansion thresholds: ≥3 RECOMMEND, =2 OFFER, ≤1 STOP
- [ ] Documents adjacency map concept (which agents can trigger which neighbors)
- [ ] Rationale for two-stage design and threshold values
- [ ] Verified against `phases/launch.md` lines 146-220

### F5: Core Synthesis Spec (synthesis.md)
**What:** Specify findings synthesis: index parsing, deduplication, convergence tracking, verdict computation.
**Acceptance criteria:**
- [ ] Documents findings index parsing from agent outputs
- [ ] Documents deduplication rules (same finding from multiple agents)
- [ ] Documents convergence tracking (count agents per finding)
- [ ] Documents verdict computation (P0→risky, P1→needs-changes, thresholds)
- [ ] Documents error handling (agent timeout, malformed output, partial results)
- [ ] Rationale for convergence approach
- [ ] Verified against `phases/synthesize.md` (364 lines) + `phases/slicing.md`

### F6: Extension — Domain Detection Spec
**What:** Specify the optional domain detection system: signal types, weighted scoring, caching, multi-domain classification.
**Acceptance criteria:**
- [ ] Documents 4 signal types: directories (0.3), files (0.2), frameworks (0.3), keywords (0.2)
- [ ] Documents confidence scoring and multi-domain support
- [ ] Documents cache format and staleness detection (structural hash + git state + mtime)
- [ ] Marked as EXTENSION conformance level
- [ ] Rationale for signal weights
- [ ] Verified against `scripts/detect-domains.py` + `config/flux-drive/domains/index.yaml`

### F7: Extension — Knowledge Lifecycle Spec
**What:** Specify the optional knowledge management system: provenance tracking, temporal decay, accumulation from synthesis.
**Acceptance criteria:**
- [ ] Documents provenance types (independent vs. primed)
- [ ] Documents temporal decay: 10 reviews without independent confirmation → archive
- [ ] Documents accumulation: how synthesis extracts durable patterns
- [ ] Documents knowledge frontmatter format (lastConfirmed, provenance)
- [ ] Marked as EXTENSION conformance level
- [ ] Verified against `config/flux-drive/knowledge/README.md` + knowledge file frontmatter

### F8: Contract — Findings Index Format
**What:** Specify the required structured output format that agents must produce.
**Acceptance criteria:**
- [ ] Documents pipe-delimited findings format: `SEVERITY | ID | "Section" | Title`
- [ ] Documents Verdict line format
- [ ] Includes at least 2 complete examples (passing, with findings)
- [ ] Documents edge cases (no findings, error verdicts)
- [ ] Marked as CORE conformance level
- [ ] Verified against `phases/shared-contracts.md`

### F9: Contract — Completion Signal
**What:** Specify how agents signal they've finished producing output.
**Acceptance criteria:**
- [ ] Documents `.partial` → complete rename flow
- [ ] Documents `<!-- flux-drive:complete -->` sentinel
- [ ] Documents error stub format (Verdict: error)
- [ ] Documents timeout behavior
- [ ] Marked as CORE conformance level
- [ ] Verified against `phases/shared-contracts.md`

## Non-goals

- **No code changes** — Phase 1 is documentation only. No libraries, packages, or migrations.
- **No conformance test suite** — describing tests is fine, implementing them is Phase 2+.
- **No standalone repo** — spec lives in Interflux until adoption warrants extraction.
- **No formal grammar (BNF/ABNF)** — pragmatic schemas using JSON examples.
- **No governance process** — spec changes follow Interflux's normal workflow.
- **No multi-implementation compatibility matrix** — only Interflux exists today.

## Dependencies

- **Interflux source code** — the normative reference implementation at `/root/projects/Interflux/`
- **Existing core algorithm analysis** — `docs/research/analyze-flux-drive-core-algorithm.md` as scaffolding
- **Closed beads** — Clavain-o4ix (extraction) and Clavain-2mmc (clarifications) are both complete

## Open Questions

1. **Diagram format** — Include Mermaid diagrams for lifecycle and scoring flows? Adds comprehension, adds maintenance.
2. **Contract strictness** — Should findings index be formally specified (JSON schema) or stay as documented examples?
3. **Agent interface** — Should spec define a minimal abstract agent interface (inputs, outputs, lifecycle)?
4. **Extension registration** — Should spec describe how to register new extensions, or leave implicit?
