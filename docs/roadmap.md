# Clavain Roadmap

**Version:** 0.6.42
**Last updated:** 2026-02-19
**Vision:** [`docs/vision.md`](vision.md)
**PRD:** [`docs/PRD.md`](PRD.md)

---

## Where We Are

Clavain is an autonomous software agency — 15 skills, 4 agents, 52 commands, 21 hooks, 1 MCP server. 31 companion plugins in the inter-* constellation. 925 beads tracked, 590 closed, 334 open. Runs on its own TUI (Autarch), backed by Intercore kernel and Interspect profiler.

### What's Working

- Full product lifecycle: Discover → Design → Build → Ship, each a sub-agency with model routing
- Three-layer architecture: Kernel (Intercore) → OS (Clavain) → Drivers (companion plugins)
- Multi-agent review engine (interflux) with 7 fd-* review agents + 5 research agents
- Phase-gated `/sprint` pipeline with work discovery, bead lifecycle, session claim atomicity
- Cross-AI peer review via Oracle (GPT-5.2 Pro) with quick/deep/council/mine modes
- Parallel dispatch to Codex CLI via `/clodex` with mode switching
- Structural test suite: 165 tests (pytest + bats-core)
- Multi-agent file coordination via interlock (MCP server wrapping intermute Go service)
- Signal-based drift detection via interwatch
- Interspect analytics: SQLite evidence store, 3-tier analysis, confidence thresholds
- Intercore kernel: Go CLI + SQLite, runs/phases/gates/dispatches/events as durable state

### What's Not Working Yet

- **Intercore integration incomplete.** Kernel primitives are built (E1-E2 done), but Clavain still uses shell-based state management. Hook cutover (E3) is the critical next step.
- **No adaptive model routing.** Static routing exists (stage→model mapping), but no complexity-aware or outcome-driven selection.
- **Agency architecture is implicit.** Sub-agencies (Discover/Design/Build/Ship) are encoded in skills and hooks, not in declarative specs or a fleet registry.
- **Outcome measurement limited.** Interspect collects evidence but no override has been applied. Cost-per-change and quality metrics are unquantified.

---

## Shipped Since Last Roadmap

Major features that landed since the 0.6.22 roadmap:

| Feature | Description |
|---------|-------------|
| **Intercore kernel (E1-E2)** | Go CLI + SQLite — runs, phases, gates, dispatches, events as durable state. Kernel primitives and event reactor shipped. |
| **Vision rewrite** | New identity: autonomous software agency with three-layer architecture (Kernel/OS/Drivers) |
| **12 new companions** | intermap, intermem, intersynth, interlens, interleave, interserve, interpeer, intertest, interkasten, interstat, interfluence, interphase v2 |
| **Monorepo consolidation** | Physical monorepo at /root/projects/Interverse with 31 companion plugins |
| **Hierarchical dispatch plan** | Meta-agent for N-agent fan-out (planned, iv-quk4) |
| **tldrs LongCodeZip** | Block-level compression for token-efficient code context (planned, iv-2izz) |
| **Version 0.6.22 → 0.6.42** | 20 version bumps |

---

## Roadmap: Three Parallel Tracks

The roadmap progresses on three independent tracks that converge toward autonomous self-building sprints.

### Track A: Kernel Integration

Migrate Clavain from ephemeral state management to durable kernel-backed orchestration.

| Step | What | Bead | Status | Depends On |
|------|------|------|--------|------------|
| A1 | **Hook cutover** — all Clavain hooks call `ic` instead of temp files | iv-ngvy | Open (P1) | Intercore E1-E2 (done) |
| A2 | **Sprint handover** — sprint skill becomes kernel-driven (hybrid → handover → kernel-driven) | — | Not yet created | A1 |
| A3 | **Event-driven advancement** — phase transitions trigger automatic agent dispatch | — | Not yet created | A2 |

### Track B: Model Routing

Build the multi-model routing infrastructure from static to adaptive.

| Step | What | Bead | Status | Depends On |
|------|------|------|--------|------------|
| B1 | **Static routing table** — phase→model mapping declared in config, applied at dispatch | — | Not yet created | — |
| B2 | **Complexity-aware routing** — task complexity drives model selection within phases | — | Not yet created | Intercore token tracking (E1) |
| B3 | **Adaptive routing** — Interspect outcome data drives model/agent selection | — | Not yet created | Interspect kernel integration (iv-thp7) |

### Track C: Agency Architecture

Build the agency composition layer that makes Clavain a fleet of specialized sub-agencies.

| Step | What | Bead | Status | Depends On |
|------|------|------|--------|------------|
| C1 | **Agency specs** — declarative per-stage config: agents, models, tools, artifacts, gates | — | Not yet created | — |
| C2 | **Agent fleet registry** — capability + cost profiles per agent×model combination | — | Not yet created | B1 |
| C3 | **Composer** — matches agency specs to fleet registry within budget constraints | — | Not yet created | C1, C2 |
| C4 | **Cross-phase handoff** — structured protocol for how Discover's output becomes Design's input | — | Not yet created | C1 |
| C5 | **Self-building loop** — Clavain uses its own agency specs to run its own development sprints | — | Not yet created | C3, C4, A3 |

### Convergence

The three tracks converge at C5: a self-building Clavain that autonomously orchestrates its own development sprints using kernel-backed state, multi-model routing, and fleet-optimized agent dispatch.

```
Track A (Kernel)      Track B (Routing)     Track C (Agency)
    A1                    B1                    C1
    │                     │                     │
    A2                    B2───────────────→    C2
    │                     │                     │
    A3                    B3                    C3
    │                                           │
    └───────────────────────────────────────→   C4
                                                │
                                               C5 ← convergence
                                          (self-building)
```

### Supporting Epics (Intercore)

These Intercore epics are prerequisites for the tracks above:

| Epic | What | Bead | Status |
|------|------|------|--------|
| E3 | Hook cutover — big-bang Clavain migration | iv-ngvy | Open (P1) |
| E4 | Level 3 Adapt — Interspect kernel event integration | iv-thp7 | Open (P2) |
| E5 | Discovery pipeline — kernel primitives for research intake | iv-fra3 | Open (P2) |
| E6 | Rollback and recovery — three-layer revert | iv-0k8s | Open (P2) |
| E7 | Autarch Phase 1 — Bigend migration + `ic tui` | iv-ishl | Open (P2) |

---

## Research Agenda

Research areas organized by proximity to current capabilities and aligned with the [Frontier Compass](vision.md#frontier-compass-structured). These are open questions, not deliverables.

### Near-Term (informed by current work)

| Area | Key question | Frontier axes |
|------|-------------|---------------|
| Multi-model composition theory | Principled framework for which model to use when | Token efficiency, Orchestration |
| Agent measurement & analytics | What metrics predict human override? What signals indicate token waste? | Reasoning quality |
| Multi-agent failure taxonomy | How do hallucination cascades, coordination tax, and model mismatch propagate? | Orchestration |
| Cognitive load budgets | How to present multi-agent output for fast, confident review? | Reasoning quality |
| Agent regression testing | Evals as CI — did this prompt change degrade bug-catching? | Reasoning quality |

### Medium-Term (informed by Track B data)

| Area | Key question | Frontier axes |
|------|-------------|---------------|
| Optimal human-in-the-loop frequency | How much attention per sprint produces the best outcomes? | Orchestration |
| Bias-aware product decisions | LLM judges show systematic bias — how to mitigate in brainstorm/strategy? | Reasoning quality |
| Plan-aware context compression | Give each agent domain-specific context via tldrs, not everything | Token efficiency |
| Transactional orchestration | Idempotency, rollback, conflict resolution across distributed agent execution | Orchestration |
| Fleet topology optimization | How many agents per phase? Which combinations produce the best outcomes? | Orchestration, Token efficiency |

### Long-Term (informed by Track C data)

| Area | Key question | Frontier axes |
|------|-------------|---------------|
| Knowledge compounding dynamics | Does cross-project learning improve outcomes or add noise? | Reasoning quality |
| Emergent multi-agent behavior | Can you predict interactions in 7+ agent constellations across multiple models? | Orchestration |
| Guardian agent patterns | Can quality-gates be formalized with instruction adherence metrics? | Reasoning quality |
| Self-improvement feedback loops | How to prevent reward hacking ("skip reviews because it speeds runs")? | Orchestration |
| Security model for autonomous agents | Capability boundaries, prompt injection, supply chain risk, sandbox compliance | All axes |
| Latency budgets | Time-to-feedback as first-class constraint alongside token cost | Token efficiency |

### Deprioritized

- Speculative decoding (can't control inference stack from outside)
- Vision-centric token compression (overkill for code-centric workflows)
- Theoretical minimum token cost (empirical cost-quality curves are more useful)
- Full marketplace/recommendation engine (not where Clavain wins)

---

## Companion Constellation

| Companion | Version | What it crystallized | Status |
|-----------|---------|---------------------|--------|
| **intercore** | — | Orchestration state is a kernel concern | Active development |
| **interspect** | — | Self-improvement needs a profiler, not ad-hoc scripts | Active development |
| **interflux** | 0.2.16 | Multi-agent review + research engine | Shipped |
| **interphase** | 0.3.2 | Phase tracking + gate validation | Shipped |
| **interline** | 0.2.4 | Statusline rendering | Shipped |
| **interpath** | 0.2.2 | Product artifact generation | Shipped |
| **interwatch** | 0.1.2 | Doc freshness monitoring | Shipped |
| **interlock** | 0.2.1 | Multi-agent file coordination (MCP) | Shipped |
| **interject** | 0.1.6 | Ambient discovery + research engine (MCP) | Shipped |
| **interdoc** | 5.1.1 | AGENTS.md generator + Oracle critique | Shipped |
| **intermux** | 0.1.1 | Agent visibility (MCP) | Shipped |
| **interslack** | 0.1.0 | Slack integration | Shipped |
| **interform** | 0.1.0 | Design patterns + visual quality | Shipped |
| **intercraft** | 0.1.0 | Agent-native architecture patterns | Shipped |
| **interdev** | 0.2.0 | MCP CLI + developer tooling | Shipped |
| **intercheck** | 0.1.4 | Code quality guards + session health | Shipped |
| **internext** | 0.1.2 | Work prioritization + tradeoff analysis | Shipped |
| **interpub** | 0.1.2 | Plugin publishing | Shipped |
| **intersearch** | 0.1.1 | Shared embedding + Exa search | Shipped |
| **interstat** | 0.2.2 | Token efficiency benchmarking | Shipped |
| **intersynth** | 0.1.2 | Multi-agent synthesis engine | Shipped |
| **intermap** | 0.1.3 | Project-level code mapping (MCP) | Shipped |
| **intermem** | 0.2.1 | Memory synthesis + tiered promotion | Shipped |
| **interkasten** | 0.4.2 | Notion sync + documentation | Shipped |
| **interfluence** | 0.2.3 | Voice profile + style adaptation | Shipped |
| **interlens** | 2.2.4 | Cognitive augmentation lenses | Shipped |
| **interleave** | 0.1.1 | Deterministic skeleton + LLM islands | Shipped |
| **interserve** | 0.1.1 | Codex spark classifier + context compression (MCP) | Shipped |
| **interpeer** | 0.1.0 | Cross-AI peer review (Oracle/GPT escalation) | Shipped |
| **intertest** | 0.1.1 | Engineering quality disciplines | Shipped |
| **tldr-swinton** | 0.7.14 | Token-efficient code context (MCP) | Shipped |
| **tool-time** | 0.3.2 | Tool usage analytics | Shipped |
| **tuivision** | 0.1.4 | TUI automation + visual testing (MCP) | Shipped |
| **intershift** | — | Cross-AI dispatch engine | Planned |
| **interscribe** | — | Knowledge compounding | Planned |

---

## Bead Summary

| Metric | Value |
|--------|-------|
| Total beads | 925 |
| Closed | 590 |
| Open | 334 |
| In progress | 1 |

Key active epics:
- **iv-66so** — Vision refresh: autonomous software agency (P1, in progress)
- **iv-ngvy** — E3: Hook cutover — big-bang Clavain migration to `ic` (P1)
- **iv-yeka** — Update roadmap.md for new vision + parallel tracks (P1)

---

## Keeping This Roadmap Current

Run `/interpath:roadmap` to regenerate from current project state.

| Trigger | What to update |
|---------|---------------|
| Track step completed | Update status in track table |
| New bead created for a track step | Add bead ID to track table |
| Companion extraction completed | Update Constellation table |
| Research insight changes direction | Add/modify items, document rationale |
| Vision doc updated | Re-align tracks and research agenda |

---

*Synthesized from: [`docs/vision.md`](vision.md), [`docs/PRD.md`](PRD.md), 925 beads, 31 companion plugins, and the Intercore kernel vision. Sources linked throughout.*

## From Interverse Roadmap

Items from the [Interverse roadmap](../../../docs/roadmap.json) that involve this module:

- **iv-zyym** [Next] Evaluate Claude Hub for event-driven GitHub agent dispatch
- **iv-wrae** [Next] Evaluate Container Use (Dagger) for sandboxed agent dispatch
- **iv-quk4** [Next] Hierarchical dispatch — meta-agent for N-agent fan-out
