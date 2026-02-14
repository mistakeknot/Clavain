# Clavain: Vision and Philosophy

## What Clavain Is

Clavain is a highly opinionated agent rig for building software from brainstorm to ship. It codifies product and engineering discipline into composable, token-efficient skills, agents, and workflows that orchestrate heterogeneous AI models into a reliable system for getting things built.

It is also a proving ground. Capabilities are built tightly integrated, battle-tested through real use, and then extracted into companion plugins when the patterns stabilize. The inter-* constellation (interphase, interflux, interline, and others) represents crystallized research outputs; each companion started as a tightly-coupled feature inside Clavain that earned its independence through repeated, successful use.

## Core Conviction

The point of agents isn't to remove humans from the loop; it's to make every moment in the loop count. Multi-agent engineering only works when it is measurable, reproducible, and reviewable. Clavain encodes this belief into a working system you can point at and learn from.

## Audience

Clavain serves three concentric circles, and the priority is explicit: inner circle first, others as byproducts.

1. **Inner circle.** A personal rig, optimized relentlessly for one product-minded engineer's workflow. The primary goal is to make a single person as effective as a full team without losing the fun parts of building.

2. **Middle circle.** A reference implementation for the Claude Code plugin community. Clavain shows what's possible with disciplined multi-agent engineering and sets conventions for plugin structure, skill design, and agent orchestration.

3. **Outer circle.** A research artifact for the broader AI-assisted development field. By solving real problems under real constraints and publishing the results, Clavain demonstrates what disciplined human-AI collaboration looks like in practice.

## Operating Principles

### 1. Refinement > production
The review phases matter more than the building phases. Every moment spent refining and reviewing is worth far more than the actual building itself. A core goal is to resolve all open questions before execution, because it is far more expensive to deal with ambiguity during execution than during planning.

### 2. Composition > integration
Small, focused tools composed together beat large integrated platforms. The inter-* constellation, Unix philosophy, modpack metaphor; it's turtles all the way down. Each companion does one thing well and composes with others through explicit interfaces.

### 3. Outcome efficiency enables scale
If you can't afford to run it, it doesn't matter how good it is. But cost alone is a vanity metric; the goal is outcomes per dollar: defects caught per token, merge-ready changes per session, time-to-first-signal per gate. Token efficiency is a means, not an end. 12 agents should cost less than 8 via orchestration optimization, *and* catch more bugs.

### 4. Human attention is the bottleneck
Optimize for the human's time, not the agent's. The human's focus, attention, and product sense are the scarce resource; agents are in service of that. Token efficiency does not equal attention efficiency; multi-agent output must be presented so humans can review quickly and confidently, not just cheaply.

### 5. Building builds building
Capability is forged through practice, not absorbed through reading. Like guitar, you can read all the theory books you want, but none of that matters as much as applied, active practice.

### 6. Discipline before automation
Encode judgment into checks before removing the human. Agents without discipline ship slop. Automation multipliers (adaptive routing, cross-project learning) should come after observability and measurement, not before.

### 7. Multi-AI > single-vendor
No one model is best at everything. The future is heterogeneous fleets of specialized models orchestrated by discipline, not loyalty to one vendor. Clavain is built on Claude Code and uses Codex and Oracle as complements; it is architecturally multi-model while remaining platform-native.

### 8. Observability is a feature, not a bolt-on
Every agent action should emit traceable events: inputs, outputs, cost, latency, decision rationale, and downstream outcomes. If it can't be traced, it can't be trusted. Measurement is the foundation for everything else; you can't refine what you can't see, and you can't extract what you can't measure.

### 9. Contracts > cleverness
Prefer typed interfaces, schemas, manifests, and declarative specs over prompt sorcery. Composition only works when boundaries are explicit. Agent definitions, plugin capabilities, and inter-plugin communication should be formally specifiable, not implicitly assumed.

## Scope

Clavain covers the full product development lifecycle, not just the code-writing phase:

| Phase | Capability |
|---|---|
| Problem discovery | Brainstorming, collaborative dialogue, repo research |
| Product specification | Strategy, PRD creation, beads prioritization |
| Planning | Write-plan, parallelization analysis, subagent delegation |
| Execution | Execute-plan, work, subagent-driven-development, cross-AI dispatch |
| Review | Quality-gates, flux-drive, interpeer, cross-AI peer review |
| Testing | TDD, smoke-test, verification-before-completion |
| Shipping | Landing-a-change, fixbuild, resolve |
| Learning | Compound, auto-compound, research agents, knowledge capture |

The brainstorm and strategy phases are real product capabilities, not engineering context-setting. Most agent tools pretend product work is prompt fluff; Clavain makes it first-class.

## Development Model

**Clavain-first, then generalize out.**

Tight coupling is a feature during the research phase, not a bug. Capabilities are built integrated, tested under real use, and only extracted when the pattern stabilizes enough to stand alone. This inverts the typical "design the API first" approach; Clavain builds too-tightly-coupled on purpose, discovers the natural seams through practice, and only then extracts. Each companion has been validated by production use before it becomes a standalone module.

### The inter-* constellation

| Companion | Crystallized Insight | Status |
|---|---|---|
| interphase | Phase tracking and gates are generalizable | Shipped |
| interflux | Multi-agent review is generalizable | Shipped |
| interline | Statusline rendering is generalizable | Shipped |
| interpath | Product artifact generation is generalizable | Shipped |
| interwatch | Doc freshness monitoring is generalizable | Shipped |
| intercraft | Claude Code meta-tooling is generalizable | Planned |
| intershift | Cross-AI dispatch is generalizable | Planned |
| interscribe | Knowledge compounding is generalizable | Planned |
| interarch | Agent-native architecture is generalizable | Planned |

The naming convention follows a consistent metaphor: each companion occupies the space *between* two things. Interphase (between phases), interline (between lines), interflux (between flows), interpath (between paths of artifacts), interwatch (between watches of freshness), intershift (between shifts of context). They are bridges and boundary layers, not monoliths.

## What Clavain Is Not

**Not a framework.** Clavain is an opinionated rig with opinions. The inter-* constellation offers composable pieces that anyone can adopt independently, but the system as a whole is not designed to be "framework-agnostic" or "configurable for any workflow." It is an opinionated rig that also happens to produce reusable components; the reusability is a byproduct of good design, not the goal.

**Not for non-builders.** Clavain is for people who build software with agents. It is not a no-code tool, not an AI assistant for non-technical users, not a chatbot framework.

**Platform-native, not vendor-neutral.** Clavain is built on Claude Code. It dispatches to Codex CLI, GPT-5.2 Pro (via Oracle), and other models as complements (and has a Codex port via install-codex.sh), but it is not trying to be a universal agent orchestrator for any LLM platform.

## Roadmap

The roadmap follows Oracle's prescription: build the truth engine first, then let everything else compete for survival under data.

### Phase 1: Measure (now)

**Build outcome-based agent analytics.** The foundation everything else depends on. A unified trace/event log for every workflow run; five discipline KPIs (defect escape rate, human override rate, cost per landed change, time-to-first-signal, redundant work ratio); and a measured feedback loop that changes behavior based on data, not intuition.

**Design agent evals as CI.** A small corpus of real tasks with expected properties, run as regression tests. Did a prompt change reduce bug-catching rate? Did tldrs integration reduce defects per token or just tokens? Proving-ground-grade evals for a proving ground.

**Run the topology experiment.** Same tasks with 2, 4, 6, and 8 agents. Plot quality vs. cost vs. time vs. human attention. Derive 2-3 topology templates to standardize. This answers: what is the coordination tax? When do more agents hurt?

### Phase 2: Integrate + extract

**Deep tldrs integration.** tldrs becomes the default token-efficient "eyes" of the system, with plan-aware context compression: each domain-specific agent gets domain-specific context. Measured against Phase 1 baselines.

**Companion extractions (analytics-informed).** intercraft first (zero coupling, safe), then intershift, interscribe, interarch. Each extraction is informed by analytics data showing which interfaces are stable.

### Phase 3: Advance

**Adaptive model routing.** Dynamic routing based on measured trust, not static tiers. Agents with low precision get smaller scope; expensive models are invoked only when screeners detect risk.

**Cross-project learning.** Knowledge compounding across projects, measured for ROI.

**MCP-native companion communication.** Migrate from file-based sideband to MCP servers, starting with interphase.

## Research Areas

Clavain is well-positioned to explore open questions at the intersection of multi-agent systems, product development, and engineering discipline. These are organized by proximity to current capabilities:

### Near-term (informed by current work)
- **Agent measurement and analytics** (Ashpool + tldrs integration)
- **Multi-agent failure taxonomy** (hallucination cascades, coordination tax, partial failures)
- **Cognitive load budgets and review UX** (progressive disclosure, time-to-first-signal)
- **Product-native agent orchestration** (Clavain's lfg pipeline is genuine whitespace)
- **Agent regression testing** (evals as CI, behavior drift detection)

### Medium-term (informed by Phase 1 data)
- **Optimal human-in-the-loop frequency** (how much attention per sprint?)
- **Multi-model composition theory** (principled framework for model selection)
- **Bias-aware product decision framework** (LLM judge bias in brainstorm/strategy)
- **Plan-aware context compression** (tldrs + domain profiles)
- **Transactional orchestration** (idempotency, rollback, conflict resolution)
- **Skill and discipline transfer** (TDD for code to TDD for product specs)

### Long-term (informed by Phase 2 data)
- **Knowledge compounding dynamics** (cross-project learning, stale insight pruning)
- **Emergent multi-agent behavior** (predicting interactions in 7+ agent constellations)
- **Guardian agent patterns** (formalizing quality-gates with instruction adherence metrics)
- **Agent Definition Language extensions** (ADL + discipline metadata)
- **MCP-native companion communication** (A2A protocol alignment)
- **Security model for tool access** (capability boundaries, prompt injection, supply chain)
- **Prompt/agent supply chain management** (versioning, checksums, behavior deltas)
- **Latency budgets** (time-to-feedback as first-class constraint alongside token cost)

### Deprioritized
- Speculative decoding (can't control inference stack from a plugin)
- Vision-centric token compression (overkill for code-centric workflows)
- Theoretical minimum token cost (empirical cost-quality curves are more useful)
- Deep capability negotiation formalism (manifests and capability maps are enough)
- Full marketplace/recommendation engine (not where Clavain wins)

## Origins

Clavain is named after one of the protagonists from Alastair Reynolds's Revelation Space series. The inter-* naming convention follows the same spirit: names that describe what the component does in the system (the space between things), not the implementation detail.

The project merges, modifies, and maintains updates from [superpowers](https://github.com/obra/superpowers), [superpowers-lab](https://github.com/obra/superpowers-lab), [superpowers-developing-for-claude-code](https://github.com/obra/superpowers-developing-for-claude-code), and [compound-engineering](https://github.com/EveryInc/compound-engineering-plugin).

---

*This document was formalized from a brainstorm session on 2026-02-14, with input from four parallel flux-research agents (Claude) and cross-review by Oracle (GPT-5.2 Pro). The brainstorm source is at `docs/brainstorms/2026-02-14-clavain-vision-philosophy-brainstorm.md`.*
