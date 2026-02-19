# Clavain: Vision and Philosophy

## What Clavain Is

Clavain is an autonomous software agency. It orchestrates the full development lifecycle — from problem discovery through shipped code — using heterogeneous AI models selected for cost, capability, and task fit. Each phase of development is a sub-agency with its own model routing, agent composition, and quality gates. The agency drives execution; the human decides direction.

Clavain runs on its own TUI (Autarch), backed by a durable orchestration kernel (Intercore) that persists every run, phase, gate, dispatch, and event in a crash-safe database. An adaptive profiler (Interspect) reads the kernel's event stream and proposes improvements to routing, agent selection, and gate policies based on outcome data. Companion plugins are drivers — each wraps one capability and extends the agency through kernel primitives.

It is also a proving ground. Capabilities are built tightly integrated, battle-tested through real use, and then extracted into companion plugins when the patterns stabilize. The inter-* constellation represents crystallized research outputs; each companion started as a tightly-coupled feature inside Clavain that earned its independence through repeated, successful use.

## Core Conviction

The point of agents isn't to remove humans from the loop; it's to make every moment in the loop count. Multi-agent engineering only works when it is measurable, reproducible, and reviewable. The agency drives the mechanics — sequencing, model selection, dispatch, review, advancement. The human drives the strategy — what to build, which tradeoffs to accept, when to ship. This separation of concerns at the attention level is Clavain's fundamental bet: strategic human intelligence combined with autonomous execution intelligence produces better software than either alone.

## Architecture

Clavain is the operating system in a three-layer stack:

```
Layer 3: Drivers (Companion Plugins)
├── Each wraps one capability (review, coordination, code mapping, research)
├── Call the kernel directly for shared state — no Clavain bottleneck
└── Examples: interflux (review), interlock (coordination), interject (research)

Layer 2: OS (Clavain)
├── The autonomous software agency — macro-stages, quality gates, model routing
├── Orchestrates by calling kernel (state/gates/events) and drivers (capabilities)
├── Provides the developer experience: TUI, slash commands, session hooks
└── If the host platform changes, opinions survive; UX wrappers are rewritten

Layer 1: Kernel (Intercore)
├── Host-agnostic Go CLI + SQLite — works from any platform
├── Runs, phases, gates, dispatches, events — the durable system of record
├── If the UX layer disappears, the kernel and all its data survive untouched
└── Mechanism, not policy — the kernel doesn't know what "brainstorm" means

Profiler: Interspect
├── Reads kernel events (phase results, gate evidence, dispatch outcomes)
├── Correlates with human corrections and outcome data
├── Proposes changes to OS configuration (routing, agent selection, gate rules)
└── Never modifies the kernel — only the OS layer
```

The guiding principle: the real magic is in the agency logic and the kernel beneath it. Drivers are swappable. The OS is portable. The kernel is permanent. If a host platform disappears, you lose UX convenience but not capability.

## Audience

Clavain serves three concentric circles, and the priority is explicit: inner circle first, then prove it works, then open the platform.

1. **Inner circle.** A personal rig, optimized relentlessly for one product-minded engineer's workflow. The primary goal is to make a single person as effective as a full team without losing the fun parts of building.

2. **Proof by demonstration.** Build Clavain with Clavain. Use the agency to run its own development sprints — research improvements, brainstorm features, plan execution, write code, review changes, compound learnings. Every capability must survive contact with its own development process. This is the credibility engine: a system that autonomously builds itself is a more convincing proof than any benchmark.

3. **Platform play.** Once dogfooding proves the model works, open Intercore as infrastructure for anyone building autonomous coding agents, and position Clavain as the reference OS. AI labs get the kernel. Developers get the agency. Both are open source. The differentiation from general-purpose AI gateways is that this stack is purpose-built for building software.

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

### 7. Right model, right task
No one model is best at everything. The agency's intelligence includes knowing *which* intelligence to apply. Gemini's long context window for exploration and research. Opus for reasoning, strategy, and design. Codex for parallel implementation. Haiku for quick checks and linting. Oracle (GPT-5.2 Pro) for high-complexity cross-validation. Model selection is a first-class routing decision at every level — macro-stage, phase, agent, and individual tool call.

### 8. Agency drives, human decides where
The agency handles execution mechanics: which model, which agents, what sequence, when to advance, what to review. The human retains strategic control: what to build, which tradeoffs to make, when to ship, where to intervene. Quality gates surface issues; the human decides whether they're blockers. The sprint runs autonomously; the human decides whether to start it. This is not "human in the loop" — it's "human above the loop."

### 9. The system builds itself
Every feature must be testable by Clavain building Clavain. Dogfooding is a design constraint, not a marketing exercise. If the agency can't use a capability to improve itself, the capability isn't ready. Self-building is the highest-fidelity eval: it tests the full stack under real conditions with real stakes.

### 10. Observability is a feature, not a bolt-on
Every agent action should emit traceable events: inputs, outputs, cost, latency, decision rationale, and downstream outcomes. If it can't be traced, it can't be trusted. Measurement is the foundation for everything else; you can't refine what you can't see, and you can't extract what you can't measure. The kernel's event bus is the backbone — every state change produces a typed, durable event.

### 11. Contracts > cleverness
Prefer typed interfaces, schemas, manifests, and declarative specs over prompt sorcery. Composition only works when boundaries are explicit. Agent definitions, plugin capabilities, and inter-plugin communication should be formally specifiable, not implicitly assumed.

### 12. Push the frontier

Clavain is not just a stable workflow stack; it is an active platform for advancing what AI-assisted engineering can do. That includes:
- **Agent orchestration frontier**: robust multi-model topology, adaptive selection, and context-sensitive dispatch across heterogeneous AI backends.
- **Reasoning and coding quality frontier**: stronger review signals, measurable defect prevention, and repeatable collaboration patterns that improve correctness over time.
- **Token-efficiency frontier**: reducing token spend *and* improving outcomes per token through intelligent model routing, plan-aware context compression, and quality-aware automation.

All roadmap decisions should be filtered by these three outcomes before adding new modules or changing core flows.

### Frontier Compass (Structured)

```yaml
frontier_objective:
  primary_axes:
    - orchestration
    - reasoning_quality
    - token_efficiency
  decision_rule: "Prioritize initiatives that improve at least two frontier axes without materially weakening the third."
  scoring_targets:
    orchestration:
      preferred_signals:
        - coordination_quality
        - adaptive_routing_success
        - dispatch_reliability
        - model_selection_accuracy
    reasoning_quality:
      preferred_signals:
        - defect_escape_reduction
        - review_signal_precision
        - repeatable_validation_coverage
    token_efficiency:
      preferred_signals:
        - tokens_per_impact
        - cost_per_landable_change
        - duplicate_work_ratio
        - model_cost_optimization_ratio
```

## Scope: Four Macro-Stages

Clavain covers the full product development lifecycle through four macro-stages. Each macro-stage is a sub-agency — a team of models and agents selected for the work at hand.

### Discover

Research, brainstorming, and problem definition. The agency scans the landscape, identifies opportunities, and frames the problem worth solving.

| Capability | Models / Agents |
|---|---|
| Long-context exploration and recon | Gemini (2M context window) |
| Ambient research and trend detection | Interject (source adapters + embedding scoring) |
| High-complexity analysis and cross-validation | Oracle (GPT-5.2 Pro) |
| Collaborative brainstorming | Opus (reasoning) |
| **Output** | Problem definition, opportunity assessment, research briefings |

### Design

Strategy, specification, planning, and plan review. The agency designs the solution and validates it through multi-perspective review before any code is written.

| Capability | Models / Agents |
|---|---|
| Strategy and system design | Opus (deep reasoning) |
| PRD generation and validation | Gurgeh (confidence-scored spec sprint) |
| Cross-AI design review | Oracle (GPT-5.2 Pro) |
| Multi-perspective plan review | Flux-drive (7 review agents, model-per-agent optimized) |
| **Output** | Approved plan with gate-verified artifacts |

### Build

Implementation and testing. The agency writes code, runs tests, and verifies correctness through parallel execution.

| Capability | Models / Agents |
|---|---|
| Parallel implementation | Codex (sandboxed, parallelizable) |
| Complex reasoning during execution | Claude Opus / Sonnet (context-dependent) |
| Quick checks and linting | Haiku (fast, cheap) |
| Test-driven development | TDD discipline agents |
| **Output** | Tested, reviewed code |

### Ship

Final review, deployment, and knowledge capture. The agency validates the change, lands it, and compounds what was learned.

| Capability | Models / Agents |
|---|---|
| Final multi-agent review | Interflux fleet (model-per-agent optimized) |
| Critical path analysis | Oracle (GPT-5.2 Pro) |
| Landing and deployment | Landing discipline agents |
| Knowledge compounding | Auto-compound (learnings → memory) |
| **Output** | Landed change + compounded learnings |

Each macro-stage maps to sub-phases internally — Discover includes research and brainstorm; Design includes strategy, plan, and plan-review; Build includes execute and test; Ship includes review, deploy, and learn. The macro-stages provide the mental model; the sub-phases provide the granularity. Phase chains are configurable per-run via the kernel.

The brainstorm and strategy phases are real product capabilities, not engineering context-setting. Most agent tools pretend product work is prompt fluff; Clavain makes it first-class.

## Model Routing Architecture

Model routing operates at three layers, each building on the one below:

### Layer 1: Kernel Mechanism

All dispatches flow through `ic dispatch spawn` with an explicit model parameter. The kernel records which model was used, tracks token consumption, and emits events. This is the durable system of record for every model decision.

### Layer 2: OS Policy

Plugins declare default model preferences (fd-architecture defaults to Opus, fd-quality defaults to Haiku). Clavain's routing table can override these per-project, per-run, or per-complexity-level. Not everything needs Opus — a style-checking agent on Haiku catches the same issues at 1/20th the cost.

### Layer 3: Adaptive Optimization

The agent fleet registry stores cost/quality profiles per agent×model combination. The composer optimizes the entire fleet dispatch within a budget constraint. "Run this review with $5 budget" → the composer allocates Opus to the 2 highest-impact agents and Haiku to the rest. Interspect's outcome data drives profile updates — models that consistently underperform for a task type get downweighted.

These three layers are staged on the roadmap: static routing ships first, complexity-aware routing follows, adaptive optimization comes with measurement infrastructure.

## Development Model

**Clavain-first, then generalize out.**

Tight coupling is a feature during the research phase, not a bug. Capabilities are built integrated, tested under real use, and only extracted when the pattern stabilizes enough to stand alone. This inverts the typical "design the API first" approach; Clavain builds too-tightly-coupled on purpose, discovers the natural seams through practice, and only then extracts. Each companion has been validated by production use before it becomes a standalone module.

### The inter-* constellation

| Companion | Crystallized Insight | Status |
|---|---|---|
| intercore | Orchestration state is a kernel concern | Active development |
| interspect | Self-improvement needs a profiler, not ad-hoc scripts | Active development |
| interflux | Multi-agent review is generalizable | Shipped |
| interphase | Phase tracking and gates are generalizable | Shipped |
| interline | Statusline rendering is generalizable | Shipped |
| interpath | Product artifact generation is generalizable | Shipped |
| interwatch | Doc freshness monitoring is generalizable | Shipped |
| interlock | Multi-agent file coordination is generalizable | Shipped |
| interject | Ambient research is generalizable | Shipped |
| interdoc | Documentation generation is generalizable | Shipped |
| intermux | Agent visibility is generalizable | Shipped |
| tldr-swinton | Token-efficient code context is generalizable | Shipped |
| intershift | Cross-AI dispatch is generalizable | Planned |
| interscribe | Knowledge compounding is generalizable | Planned |

The naming convention follows a consistent metaphor: each companion occupies the space *between* two things. interphase (between phases), interline (between lines), interflux (between flows), interpath (between paths of artifacts), interwatch (between watches of freshness), intershift (between shifts of context). They are bridges and boundary layers, not monoliths.

## Roadmap: Three Parallel Tracks

The roadmap progresses on three independent tracks that converge toward autonomous self-building sprints.

### Track A: Kernel Integration

Migrate Clavain from ephemeral state management to durable kernel-backed orchestration.

| Step | What | Depends On |
|---|---|---|
| A1 | **Hook cutover** — all Clavain hooks call `ic` instead of temp files | Intercore E1-E2 |
| A2 | **Sprint handover** — sprint skill becomes kernel-driven (hybrid → handover → kernel-driven) | A1 |
| A3 | **Event-driven advancement** — phase transitions trigger automatic agent dispatch and advancement | A2 |

### Track B: Model Routing

Build the multi-model routing infrastructure from static to adaptive.

| Step | What | Depends On |
|---|---|---|
| B1 | **Static routing table** — phase→model mapping declared in config, applied at dispatch | — |
| B2 | **Complexity-aware routing** — task complexity drives model selection within phases | Intercore token tracking (E1) |
| B3 | **Adaptive routing** — Interspect outcome data drives model/agent selection | Interspect kernel integration (E4) |

### Track C: Agency Architecture

Build the agency composition layer that makes Clavain a fleet of specialized sub-agencies.

| Step | What | Depends On |
|---|---|---|
| C1 | **Agency specs** — declarative per-stage config: agents, models, tools, artifacts, gates | — |
| C2 | **Agent fleet registry** — capability + cost profiles per agent×model combination | B1 |
| C3 | **Composer** — matches agency specs to fleet registry within budget constraints | C1, C2 |
| C4 | **Cross-phase handoff** — structured protocol for how Discover's output becomes Design's input | C1 |
| C5 | **Self-building loop** — Clavain uses its own agency specs to run its own development sprints | C3, C4, A3 |

### Convergence

The three tracks converge at C5: a self-building Clavain that autonomously orchestrates its own development sprints using kernel-backed state, multi-model routing, and fleet-optimized agent dispatch. This is the proof point for the platform play.

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

## Research Areas

Clavain is well-positioned to explore open questions at the intersection of multi-agent systems, product development, and engineering discipline. These are organized by proximity to current capabilities:

### Near-term (informed by current work)
- **Multi-model composition theory** — principled framework for which model to use when, informed by cost/quality/latency tradeoffs
- **Agent measurement and analytics** — what metrics predict human override? What signals indicate an agent is wasting tokens?
- **Multi-agent failure taxonomy** — hallucination cascades, coordination tax, partial failures, model mismatch
- **Cognitive load budgets and review UX** — progressive disclosure, time-to-first-signal, attention-efficient output formatting
- **Agent regression testing** — evals as CI, behavior drift detection across model versions

### Medium-term (informed by Track B data)
- **Optimal human-in-the-loop frequency** — how much attention per sprint produces the best outcomes?
- **Bias-aware product decision framework** — LLM judge bias in brainstorm/strategy phases
- **Plan-aware context compression** — each domain-specific agent gets domain-specific context via tldrs
- **Transactional orchestration** — idempotency, rollback, conflict resolution across distributed agent execution
- **Fleet topology optimization** — how many agents per phase? Which combinations produce the best outcomes?

### Long-term (informed by Track C data)
- **Knowledge compounding dynamics** — cross-project learning, stale insight pruning, when does shared memory help vs hurt?
- **Emergent multi-agent behavior** — predicting interactions in 7+ agent constellations across multiple models
- **Guardian agent patterns** — formalizing quality-gates with instruction adherence metrics
- **Self-improvement feedback loops** — how to prevent reward hacking ("skip reviews because it speeds runs")?
- **Security model for autonomous agents** — capability boundaries, prompt injection, supply chain risk, sandbox compliance
- **Latency budgets** — time-to-feedback as first-class constraint alongside token cost

### Deprioritized
- Speculative decoding (can't control inference stack from outside)
- Vision-centric token compression (overkill for code-centric workflows)
- Theoretical minimum token cost (empirical cost-quality curves are more useful)
- Full marketplace/recommendation engine (not where Clavain wins)

## What Clavain Is Not

**Not a platform.** That's Intercore. Clavain is the opinionated agency built on the platform. The inter-* constellation offers composable pieces that anyone can adopt independently, but the agency as a whole is not designed to be "framework-agnostic" or "configurable for any workflow."

**Not a general AI gateway.** That's what OpenClaw does. Clavain doesn't route arbitrary messages to arbitrary agents. It orchestrates software development — it has opinions about what "good" looks like at every phase, and those opinions are encoded in gates, review agents, and quality disciplines.

**Not a coding assistant.** That's what Cursor and similar tools do. Clavain doesn't help you write code; it *builds software* — the full lifecycle from problem discovery through shipped, reviewed, tested, compounded code. The coding is one phase of four.

**Not a Claude Code plugin.** Clavain runs on its own TUI (Autarch). It dispatches to Claude, Codex, Gemini, GPT-5.2, and other models as execution backends. The Claude Code plugin interface is one driver among several — a UX adapter, not the identity.

**Not for non-builders.** Clavain is for people who build software with agents. It is not a no-code tool, not an AI assistant for non-technical users, not a chatbot framework.

## Origins

Clavain is named after one of the protagonists from Alastair Reynolds's Revelation Space series. The inter-* naming convention follows the same spirit: names that describe what the component does in the system (the space between things), not the implementation detail.

The project began by merging and evolving [superpowers](https://github.com/obra/superpowers), [superpowers-lab](https://github.com/obra/superpowers-lab), [superpowers-developing-for-claude-code](https://github.com/obra/superpowers-developing-for-claude-code), and [compound-engineering](https://github.com/EveryInc/compound-engineering-plugin). It has since grown beyond those roots into an autonomous agency with its own kernel, profiler, TUI, and companion ecosystem.

---

*This document was originally formalized from a brainstorm session on 2026-02-14, with input from four parallel flux-research agents (Claude) and cross-review by Oracle (GPT-5.2 Pro). Revised on 2026-02-19 to reflect the new identity as an autonomous software agency following the Intercore kernel vision.*
