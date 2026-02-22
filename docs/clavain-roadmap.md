# Clavain Roadmap

**Version:** 0.6.60
**Last updated:** 2026-02-21
**Vision:** [`docs/clavain-vision.md`](clavain-vision.md)
**PRD:** [`docs/PRD.md`](PRD.md)

---

## Where We Are

Clavain is an autonomous software agency — 16 skills, 4 agents, 53 commands, 22 hooks, 1 MCP server. 35 companion plugins in the inter-* constellation (33 shipped/active, 2 planned). 1419 beads tracked, 1098 closed, 321 open. Runs on its own TUI (Autarch), backed by Intercore kernel and Interspect profiler.

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

- **No adaptive model routing.** Static routing (B1) and complexity-aware routing (B2) shipped. Next: Interspect outcome data driving model selection (B3).
- **Agency architecture is implicit.** Sub-agencies (Discover/Design/Build/Ship) are encoded in skills and hooks, not in declarative specs or a fleet registry.
- **Outcome measurement limited.** Interspect collects evidence but no override has been applied. Cost-per-change and quality metrics are unquantified.

---

## Shipped Since Last Roadmap

Major features that landed since the 0.6.22 roadmap:

| Feature | Description |
|---------|-------------|
| **A2 Sprint handover** | Sprint skill fully kernel-driven — hybrid → handover → kernel-driven pipeline. |
| **A3 Event-driven advancement** | Schema v14 `phase_actions` table, action CRUD, CLI, template resolution, `sprint_next_step()` queries kernel actions, default actions registered at sprint creation. |
| **B1 Static routing** | Phase→model mapping declared in config, applied at dispatch. |
| **B2 Complexity-aware routing** | C1-C5 classification, zero-cost bypass, shadow mode, enforce mode. 22 new routing tests. |
| **E3 Hook cutover** | Sprint state management migrated from beads-only to ic-primary with beads fallback. |
| **E4 Interspect kernel integration** | Evidence events flow through Intercore event bus. |
| **E5 Discovery pipeline** | Kernel primitives for research intake — submit, score, promote, dismiss, decay, semantic search. |
| **E6 Rollback and recovery** | Three-layer revert — workflow state, code query, completed run rollback. |
| **E7 Autarch Phase 1** | Bigend TUI migration — dashboard, run pane, activity feed, aggregator dedup. |
| **Intercore kernel (E1-E2)** | Go CLI + SQLite — runs, phases, gates, dispatches, events as durable state. |
| **Vision rewrite** | Autonomous software agency with three-layer architecture (Kernel/OS/Drivers). |
| **35 companion plugins** | intermap, intermem, intersynth, interlens, interleave, interserve, interpeer, intertest, interkasten, interstat, interfluence, interphase v2, and more (33 shipped/active, 2 planned) |
| **Version 0.6.22 → 0.6.60** | 38 version bumps |

---

## Roadmap: Three Parallel Tracks

The roadmap progresses on three independent tracks that converge toward autonomous self-building sprints.

### Track A: Kernel Integration

Migrate Clavain from ephemeral state management to durable kernel-backed orchestration.

| Step | What | Bead | Status | Depends On |
|------|------|------|--------|------------|
| A1 | **Hook cutover** — all Clavain hooks call `ic` instead of temp files. ic-primary with beads fallback across sprint CRUD, agent tracking, and phase advancement. | iv-ngvy | **Done** | Intercore E1-E2 (done) |
| A2 | **Sprint handover** — sprint skill becomes kernel-driven (hybrid → handover → kernel-driven) | iv-kj6w | **Done** | A1 (done) |
| A3 | **Event-driven advancement** — phase transitions trigger automatic agent dispatch. Schema v14: `phase_actions` table, action CRUD store, CLI (`ic run action`), template resolution (`${artifact:*}`, `${run_id}`, `${project_dir}`), advance output includes resolved actions, `sprint_next_step()` queries kernel first, default actions registered at sprint creation. | iv-r9j2 | **Done** | A2 (done) |

### Track B: Model Routing

Build the multi-model routing infrastructure from static to adaptive.

| Step | What | Bead | Status | Depends On |
|------|------|------|--------|------------|
| B1 | **Static routing table** — phase→model mapping declared in config, applied at dispatch | iv-dd9q | **Done** | — |
| B2 | **Complexity-aware routing** — C1-C5 classification, zero-cost bypass (disabled = static path), shadow mode, enforce mode. 22 new tests. | iv-k8xn | **Done** | B1 (done) |
| B3 | **Adaptive routing** — Interspect outcome data drives model/agent selection | iv-i198 | Open (P3) | B2 (done), Interspect E4 (done) |

### Track C: Agency Architecture

Build the agency composition layer that makes Clavain a fleet of specialized sub-agencies.

| Step | What | Bead | Status | Depends On |
|------|------|------|--------|------------|
| C1 | **Agency specs** — declarative per-stage config: agents, models, tools, artifacts, gates. Include companion capability declarations (`capabilities` field in manifests). See [pi_agent_rust lessons](brainstorms/2026-02-19-pi-agent-rust-lessons-brainstorm.md) §2. | iv-asfy | Open (P2) | — |
| C2 | **Agent fleet registry** — capability + cost profiles per agent×model combination | iv-lx00 | Open (P2) | B1 (done), C1 |
| C3 | **Composer** — matches agency specs to fleet registry within budget constraints | iv-240m | Open (P3) | C1, C2 |
| C4 | **Cross-phase handoff** — structured protocol for how Discover's output becomes Design's input | iv-1vny | Open (P3) | C1 |
| C5 | **Self-building loop** — Clavain uses its own agency specs to run its own development sprints | iv-6ixw | Open (P3) | C3, C4, A3 (done) |

### Convergence

The three tracks converge at C5: a self-building Clavain that autonomously orchestrates its own development sprints using kernel-backed state, multi-model routing, and fleet-optimized agent dispatch.

```
Track A (Kernel)      Track B (Routing)     Track C (Agency)
    A1 ✓                  B1 ✓                  C1
    │                     │                     │
    A2 ✓                  B2 ✓─────────────→    C2
    │                     │                     │
    A3 ✓                  B3                    C3
    │                                           │
    └───────────────────────────────────────→   C4
                                                │
                                               C5 ← convergence
                                          (self-building)
```

### Autonomy Ladder Mapping

The three tracks map to the [Demarch Autonomy Ladder](../../../docs/demarch-vision.md#the-autonomy-ladder) (L0 Record, L1 Enforce, L2 React, L3 Auto-remediate, L4 Auto-ship):

| Steps | Track | Autonomy Level | Rationale |
|-------|-------|---------------|-----------|
| A1-A3 (done) | Kernel Integration | Enabled L0-L2 (Record, Enforce, React) | Hook cutover gives durable state (L0), sprint handover adds gate enforcement (L1), event-driven advancement enables automatic reactions (L2). |
| B1-B2 (done) | Model Routing | Supports L2 (React) | Routing decisions applied automatically at dispatch time — the system reacts to task complexity without human model selection. |
| B3 (open) | Model Routing | Prerequisite for L3 (Auto-remediate) | Interspect-driven model selection means the system adjusts its own routing based on outcome data, a form of self-remediation. |
| C1-C4 (open) | Agency Architecture | Foundation for L3 (Auto-remediate) | Agency specs, fleet registry, composer, and cross-phase handoff give the system the vocabulary to retry with different agents, substitute models, and adjust parameters autonomously. |
| C5 (open) | Agency Architecture | Gateway to L4 (Auto-ship) | The self-building loop — Clavain using its own agency specs to run its own sprints — is the entry point to fully autonomous shipping. |

### Supporting Epics (Intercore)

These Intercore epics are prerequisites for the tracks above:

| Epic | What | Bead | Status |
|------|------|------|--------|
| E3 | Hook cutover — big-bang Clavain migration | iv-ngvy | **Done** |
| E4 | Level 3 Adapt — Interspect kernel event integration | iv-thp7 | **Done** |
| E5 | Discovery pipeline — kernel primitives for research intake | iv-fra3 | **Done** |
| E6 | Rollback and recovery — three-layer revert | iv-0k8s | **Done** |
| E7 | Autarch Phase 1 — Bigend migration + `ic tui` | iv-ishl | **Done** |

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
| Total beads | 1419 |
| Closed | 1098 |
| Open | 321 |
| In progress | 0 |

Key completed epics:
- **iv-66so** — Vision refresh: autonomous software agency (P1, done)
- **iv-ngvy** — E3: Hook cutover — big-bang Clavain migration to `ic` (P1, done)
- **iv-kj6w** — A2: Sprint handover — kernel-driven sprint pipeline (P1, done)
- **iv-lype** — A3: Event-driven advancement — phase actions (P2, done)
- **iv-thp7** — E4: Interspect kernel integration (P1, done)
- **iv-fra3** — E5: Discovery pipeline (P2, done)
- **iv-0k8s** — E6: Rollback and recovery (P1, done)
- **iv-ishl** — E7: Autarch Phase 1 — Bigend TUI (P1, done)

Key active work:
- **iv-asfy** — C1: Agency specs — declarative per-stage config (P2)
- **iv-i198** — B3: Adaptive routing — Interspect-driven model selection (P3)

Recently closed:
- **iv-r9j2** — A3: Event-driven advancement — kernel-driven routing with fallback (P2, done)
- **iv-k8xn** — B2: Complexity-aware routing with zero-cost bypass (P2, done)
- **iv-dd9q** — B1: Static routing table (P2, done)

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

*Synthesized from: [`docs/clavain-vision.md`](clavain-vision.md), [`docs/PRD.md`](PRD.md), 1419 beads, 35 companion plugins, and the Intercore kernel vision. Sources linked throughout.*

## From Interverse Roadmap

Items from the [Interverse roadmap](../../../docs/roadmap.json) that involve this module:

- **iv-zyym** [Next] Evaluate Claude Hub for event-driven GitHub agent dispatch
- **iv-wrae** [Next] Evaluate Container Use (Dagger) for sandboxed agent dispatch
- **iv-quk4** [Next] Hierarchical dispatch — meta-agent for N-agent fan-out
