# Clavain Roadmap

> Version 0.6.216 | 17 skills, 6 agents, 49 commands, 10 hooks | Updated 2026-03-19
>
> Source of truth: `roadmap.json` (machine-readable, generated from beads)

## Overview

Clavain is the L2 OS layer of Sylveste — an autonomous software agency orchestrating the full development lifecycle. This roadmap covers work directly on Clavain and closely coupled Sylveste-level items (sprint system, prompt optimization, tool gating, progress tracking).

For companion plugin roadmaps (interflux, interphase, interspect, etc.), see each plugin's own `docs/roadmap.md`.

---

## Now (P0-P1) — Active / Next Up

| ID | Title | Status |
|----|-------|--------|
| Sylveste-fqb | Interrank power-up: task-based model recommendation | in_progress |
| Sylveste-6qb | Skaffen — sovereign agent runtime | in_progress |
| iv-w41fn | Expand sequencing hints in tool-composition.yaml from real failure data | open |
| iv-7h6tp | Adapt check_fn tool gating pattern from Hermes | open |

---

## Next (P2) — Planned

### Sprint system
- **Sylveste-oac8** Clavain prompt token optimization — phase 2 *(in_progress)*
- **Sylveste-ss15** F3: Progress tracker rollout to remaining 6 commands
- **Sylveste-7uko** F2: Wire artifact bus into all 10 sprint commands *(blocked)*
- **Sylveste-lcxa** F4: Graduated autonomy tier system for sprint *(blocked)*
- **Sylveste-lta9** Deep review + brainstorm of sprint lifecycle — phase coherence, OODARC alignment *(blocked)*
- **iv-6u3s** F4: Sprint Scan Release Visibility

### Infrastructure
- **iv-e8dg** flux-drive-spec Phase 4: Migrate Clavain to consume the library
- **iv-ho3** Epic: StrongDM Factory Substrate — validation-first infrastructure for Clavain

### Observability + routing
- **Sylveste-jly6** F2: /interspect:effectiveness command
- **Sylveste-6f5i** F1: Interspect effectiveness report function
- **iv-5ubkh** Evolve Interspect outcome data to drive adaptive routing
- **iv-jgdct** Apply complexity-aware routing across all subagents

### Research + coordination
- **Sylveste-dxzr** Epic: Interlab observability audit
- **Sylveste-2ik** Autoresearch: cross-campaign leaderboard and config adoption *(blocked)*
- **iv-i76wv** Research: Autonomy safety policy for auto-remediate and auto-ship
- **iv-fwwhl** Epic: WCM multi-agent coordination patterns
- **iv-qjwz** AgentDropout: dynamic redundancy elimination for flux-drive reviews
- **iv-quk4** Hierarchical dispatch: meta-agent for N-agent fan-out

### Ecosystem
- **iv-wjbex** Intercom: sprint status push notifications
- **iv-sdqv** Plan interscribe extraction (knowledge compounding)
- **iv-6ikc** Plan intershift extraction (cross-AI dispatch engine)

---

## Later (P3+) — Backlog

### Progress trackers (P3, 6 items)
Epic **Sylveste-01ew**: Add explicit phase names and hard-stop rules to resolve, reflect, quality-gates, write-plan, strategy commands.

### Sprint evolution (P3)
- **Sylveste-8hzt** F6: Multi-agent parallel execution windows *(blocked)*
- **Sylveste-5ump** F5: Sprint-level 10-step progress display *(blocked)*

### Performance (P3)
- **Sylveste-0pvp.5** Optimize composePlan — reduce map iteration allocs
- **Sylveste-0pvp.1** Optimize classifyComplexity — eliminate regex allocs

### Extractions + integrations (P3-P4)
- **iv-u2pd** Arbiter extraction Phase 2: spec sprint sequencing to Clavain skill
- **iv-d5hz** Extract Coldwine task orchestration to Clavain skills (v2)
- **iv-88cp2** Extract Interspect from Clavain into standalone plugin
- **iv-icqo** Research: ADL discipline extensions for Clavain agents
- **iv-spad** Deep tldrs integration into Clavain workflows

### Future vision (P4)
- **iv-sevis** clavain-cli Go migration implementation plan
- **iv-eqbo** Add Conductor-style project init wizard to /clavain:init
- **iv-d8yi** Add inherit model tier to Clavain model routing
- **iv-k1q4** Coldwine: intent submission to Clavain OS

---

## Research Agenda

- **Autonomy safety** — policy for auto-remediate and auto-ship (iv-i76wv)
- **Model routing** — Skaffen shadow experiments, haiku/sonnet/opus phase comparison (Sylveste-dk5)
- **Token efficiency** — prompt caching strategy from Hermes (iv-f8s9q), multi-strategy context estimation (iv-fv1f)
- **Coordination patterns** — WCM multi-agent patterns (iv-fwwhl), convergence-divergence detection (iv-goiyq)
- **ADL discipline extensions** for Clavain agents (iv-icqo)

---

## Recent Highlights

- **Go CLI pre-build fix** (issue #10) — resolved build failure in Clavain CLI toolchain
- **Brainstorm progress tracker** — added phase tracking and hard-stop to brainstorm command
- **Compose pre-indexing** — plugin discovery API centralized, cache-glob duplication removed (iv-1xtgd.1)
- **Unified Codex install path** — migration to ~/.agents/skills (iv-914cu)
- **ic build step** added to clavain:setup (iv-ttj6q)
- **Agency specs** (C1) shipped — declarative per-stage agent/model/tool config (iv-asfy)
- **Tool-time PreToolUse binding** removed, Task redirect extracted to Clavain (iv-iu31)
