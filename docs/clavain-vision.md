# Clavain: Vision and Philosophy

> **Reading context.** Cross-doc links in this document use relative paths within the [Interverse monorepo](https://github.com/mistakeknot/Interverse). If reading outside the repo, refer to the linked docs by name in their respective subprojects.
>
> **See also:** [Architecture diagram](../../../docs/architecture.md)

## What Clavain Is

Clavain is an autonomous software agency. It orchestrates the full development lifecycle — from problem discovery through shipped code — using heterogeneous AI models selected for cost, capability, and task fit. Each phase of development is a sub-agency with its own model routing, agent composition, and quality gates. The agency drives execution; the human decides direction.

Clavain runs on its own TUI (Autarch), backed by a durable orchestration kernel (Intercore) that persists every run, phase, gate, dispatch, and event in a crash-safe database. An adaptive profiler (Interspect) reads the kernel's event stream and proposes improvements to routing, agent selection, and gate policies based on outcome data. Companion plugins are drivers — each wraps one capability and extends the agency through kernel primitives.

It is also a proving ground. Capabilities are built tightly integrated, battle-tested through real use, and then extracted into companion plugins when the patterns stabilize. The inter-* constellation represents crystallized research outputs; each companion started as a tightly-coupled feature inside Clavain that earned its independence through repeated, successful use.

## Core Conviction

The point of agents isn't to remove humans from the loop; it's to make every moment in the loop count. Multi-agent engineering only works when it is measurable, reproducible, and reviewable. The agency drives the mechanics — sequencing, model selection, dispatch, review, advancement. The human drives the strategy — what to build, which tradeoffs to accept, when to ship. This separation of concerns at the attention level is Clavain's fundamental bet: strategic human intelligence combined with autonomous execution intelligence produces better software than either alone.

## Architecture

Clavain is the operating system in a layered stack:

```
Layer 3: Apps (Autarch)
├── Interactive TUI surfaces: Bigend, Gurgeh, Coldwine, Pollard
├── Renders OS opinions into interactive experiences
└── Swappable — Autarch is one set of apps, not the only possible set (see Autarch vision doc for transitional caveats)

Layer 2: OS (Clavain)
├── The autonomous software agency — macro-stages, quality gates, model routing
├── Orchestrates by calling kernel (state/gates/events) and companion plugins (capabilities)
├── Companion plugins (interflux, interlock, interject, etc.) are OS extensions — each wraps one capability
├── Provides the developer experience: slash commands, session hooks, routing tables
└── If the host platform changes, opinions survive; UX wrappers are rewritten

Layer 1: Kernel (Intercore)
├── Host-agnostic Go CLI + SQLite — works from any platform
├── Runs, phases, gates, dispatches, events — the durable system of record
├── If the UX layer disappears, the kernel and all its data survive untouched
└── Mechanism, not policy — the kernel doesn't know what "brainstorm" means

Interspect (Profiler) — cross-cutting
├── Reads kernel events (phase results, gate evidence, dispatch outcomes)
├── Correlates with human corrections and outcome data
├── Proposes changes to OS configuration (routing, agent selection, gate rules)
└── Never modifies the kernel — only the OS layer
```

The guiding principle: the system of record is in the kernel; the policy authority is in the OS; the interactive surfaces are swappable apps. If a host platform disappears, you lose UX convenience but not capability. For details on the apps layer, see the [Autarch vision doc](../../../apps/autarch/docs/autarch-vision.md). For term definitions, see the [shared glossary](../../../core/intercore/docs/product/glossary.md).

**Write-path contract.** The OS is the sole policy authority for kernel mutations. Companion plugins produce capability results (artifacts, evidence, telemetry) but do not create/advance runs or define gate rules. Apps submit intents to the OS — they do not call kernel primitives for policy-governing operations. See the [Intercore vision doc](../../../core/intercore/docs/product/intercore-vision.md) for the full write-path contract table.

> **Current state vs target state.** Today, Clavain ships as a Claude Code plugin (dozens of slash commands, hooks, and an MCP server) because that surface is available and productive now. Autarch's TUI tools exist but are not yet the primary interface. The kernel (Intercore) is in active development with gates, events, and dispatches working; the hook cutover from temp files to `ic` is the v1.5 milestone. The architecture above describes the target design — what each layer is converging toward. Where the target differs from today's reality, the gap is acknowledged in the relevant section.

## Audience

Clavain serves three concentric circles, and the priority is explicit: inner circle first, then prove it works, then open the platform.

1. **Inner circle.** A personal rig, optimized relentlessly for one product-minded engineer's workflow. The primary goal is to make a single person as effective as a full team without losing the fun parts of building.

2. **Proof by demonstration.** Build Clavain with Clavain. Use the agency to run its own development sprints — research improvements, brainstorm features, plan execution, write code, review changes, compound learnings. Every capability must survive contact with its own development process. This is the credibility engine: a system that autonomously builds itself is a more convincing proof than any benchmark.

3. **Platform play.** Once dogfooding proves the model works, open the Demarch platform — Intercore as infrastructure for anyone building autonomous software development agencies, and Clavain as the reference agency. AI labs get the kernel. Developers get the agency. Both are open source. The differentiation from general-purpose AI gateways is that this stack is purpose-built for building software.

## Operating Principles

### 1. Discipline enables speed
The review phases matter more than the building phases. Resolve all open questions before execution — ambiguity is far more expensive to handle during building than during planning. Encode judgment into checks before removing the human. Agents without discipline ship slop. Automation multipliers (adaptive routing, cross-project learning) should come after observability and measurement, not before. But discipline that slows without catching bugs is miscalibrated gates, not good practice. The goal is faster safe shipping, not more review. Match rigor to risk (PHILOSOPHY.md: "If review phases slow you down more than they catch bugs, the gates are miscalibrated").

### 2. Compose through contracts
Small, focused tools composed together beat large integrated platforms. The inter-* constellation, Unix philosophy, modpack metaphor; it's turtles all the way down. Each companion does one thing well and composes with others through explicit interfaces. Prefer typed interfaces, schemas, manifests, and declarative specs over prompt sorcery — composition only works when boundaries are explicit. Agent definitions, plugin capabilities, and inter-plugin communication should be formally specifiable, not implicitly assumed.

### 3. Measure what matters
If you can't afford to run it, it doesn't matter how good it is. But cost alone is a vanity metric; the goal is outcomes per dollar: defects caught per token, merge-ready changes per session, time-to-first-signal per gate. 12 agents should cost less than 8 via orchestration optimization, *and* catch more bugs. This requires pervasive observability — every agent action should emit traceable events: inputs, outputs, cost, latency, decision rationale, and downstream outcomes. If it can't be traced, it can't be trusted. The kernel's event bus is the backbone; every state change produces a typed, durable event. You can't refine what you can't see, and you can't extract what you can't measure.

### 4. Human attention is the bottleneck
Optimize for the human's time, not the agent's. The human's focus, attention, and product sense are the scarce resource; agents are in service of that. Token efficiency does not equal attention efficiency; multi-agent output must be presented so humans can review quickly and confidently, not just cheaply.

### 5. Self-building through practice
Capability is forged through practice, not absorbed through reading. Like guitar, you can read all the theory books you want, but none of that matters as much as applied, active practice. Every feature must be testable by Clavain building Clavain. Dogfooding is a design constraint, not a marketing exercise. If the agency can't use a capability to improve itself, the capability isn't ready. Self-building is the highest-fidelity eval: it tests the full stack under real conditions with real stakes.

### 6. Right model, right task
No one model is best at everything. The agency's intelligence includes knowing *which* intelligence to apply. Gemini's long context window for exploration and research. Opus for reasoning, strategy, and design. Codex for parallel implementation. Haiku for quick checks and linting. Oracle (GPT-5.2 Pro) for high-complexity cross-validation. Model selection is a first-class routing decision at every level — macro-stage, phase, agent, and individual tool call.

### 7. Agency drives, human decides where
The agency handles execution mechanics: which model, which agents, what sequence, when to advance, what to review. The human retains strategic control: what to build, which tradeoffs to make, when to ship, where to intervene. Quality gates surface issues; the human decides whether they're blockers. The sprint runs autonomously; the human decides whether to start it. This is not "human in the loop" — it's "human above the loop."

### 8. Push the frontier

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

## Day-1 Workflow

The minimum workflow a new user experiences on first install. Everything else is progressive enhancement.

**The core loop:** `brainstorm → plan → review plan → execute → test → quality gates → ship`. This is the Design → Build → Ship pipeline — the three macro-stages that are shipped and proven. A user types `/sprint "add user auth"` and the agency walks them through this sequence.

**What's available on Day 1:**
- Sprint workflow with complexity-aware phase skipping (trivial tasks skip brainstorm + strategy)
- Multi-agent plan review via flux-drive (7 review agents, parallel dispatch)
- Quality gates with automatic agent selection based on change risk
- Incremental commits on trunk with conventional commit messages
- Session checkpointing — resume where you left off across sessions

**What's NOT available on Day 1 (and shouldn't be promised):**
- Discovery pipeline (kernel primitives shipped in E5; OS integration with interject pending)
- Adaptive model routing (requires Interspect + outcome data)
- Cross-project portfolio runs (requires Intercore v4)
- Fully autonomous overnight sprints (requires Level 2 reactor + managed service deployment)

**First sprint experience target:** A user with a Go or TypeScript project can run `/sprint "fix the flaky test in auth_test.go"`, get a brainstorm, plan, plan-review, execution, tests, quality gates, and a landed commit — in under 30 minutes for a simple fix.

## Safety Posture by Macro-Stage

Each macro-stage has a different risk profile and corresponding safety controls:

| Stage | Risk Profile | Safety Controls |
|-------|-------------|-----------------|
| **Discover** | Low — read-only research, no mutations | No gates required. Outputs are proposals, not actions. |
| **Design** | Low-medium — generates plans, not code | Flux-drive plan review catches scope creep and architectural risks before execution. |
| **Build** | High — writes code, modifies files | Gate enforcement: plan must be reviewed before execution. Tests run continuously. Incremental commits enable rollback. Sandbox specs constrain agent file access (future). |
| **Ship** | Highest — pushes to remote, closes work items | Quality gates must pass. Human explicitly approves push. No auto-push without confirmation. Override audit trail. |

**Invariant (today):** The system never pushes code to a remote repository without human confirmation. This is a Level 1-2 safety control. As trust progresses through the ladder (PHILOSOPHY.md), auto-push becomes available under policy constraints (e.g., auto-push to staging branches, require confirmation for main). The constraint softens through gated processes, not removal.

## Collaboration Stance

Clavain is a **single-operator system through v2**. One human, one agency, one machine. The architecture does not prevent multi-user operation, but it is not designed for it and does not address:
- Concurrent human operators with conflicting intents
- Permission models for shared kernel databases
- Merge conflict resolution between parallel human-directed sprints

Multi-user collaboration is a v3+ concern, gated on Intercore's multi-project portfolio support and a proper permission model.

## Scope: Five Macro-Stages

Clavain covers the full product development lifecycle through five macro-stages. Each macro-stage is a sub-agency — a team of models and agents selected for the work at hand.

### Discover (Optional Until Core Loop Stabilizes)

Research, brainstorming, and problem definition. The agency scans the landscape, identifies opportunities, and frames the problem worth solving.

> **Current status:** The kernel discovery primitives are shipped (E5): `ic discovery` CLI with submit, score, promote, dismiss, feedback, decay, rollback, and embedding search. The interject plugin implements source adapters (arXiv, HN, GitHub, Anthropic docs, Exa) with embedding-based scoring. What's **not** shipped is the OS-level pipeline integration: interject emitting kernel events, event-driven scan triggers, automated backlog refinement, and confidence-tiered autonomy policy. Today, work discovery is manual (beads backlog + human input). The Design → Build → Ship loop is the core product; the full Discover pipeline extends it once the OS integration lands. A sprint can begin at any macro-stage — `--from-step brainstorm` or `--from-step plan` skips Discover entirely.

| Capability | Models / Agents |
|---|---|
| Long-context exploration and recon | Gemini (2M context window) |
| Ambient research and trend detection | Interject (source adapters + embedding scoring) |
| High-complexity analysis and cross-validation | Oracle (GPT-5.2 Pro) |
| Collaborative brainstorming | Opus (reasoning) |
| **Output** | Problem definition, opportunity assessment, research briefings |

#### Discovery → Backlog Pipeline

The Discover macro-stage includes an autonomous research pipeline that closes the loop between **what the world knows** and **what the system is working on**. The kernel provides the discovery primitives (scored records, confidence gates, events); Clavain provides the pipeline workflow.

```
Sources                     Scoring & Triage           Backlog Actions
─────────────────          ──────────────────         ──────────────────
arXiv (Atom feeds)    ┐
Hacker News (API)     │     Embedding-based           High confidence:
GitHub (releases,     │     relevance scoring    ──→    auto-create bead
  issues, READMEs)    ├──→  against learned             + briefing doc
Exa (semantic web     │     interest profile
  search)             │                               Medium confidence:
Anthropic docs        │     Confidence tiers:    ──→    propose to human
  (change detection)  │     high / medium /              (inbox review)
RSS/Atom feeds        │     low / discard
  (general)           │                               Low confidence:
User submissions      ┘     Adaptive thresholds  ──→    log only
                            (shift with feedback)

Internal signals                                      Backlog refinement:
─────────────────                                     ──────────────────
Beads history              Feedback loop:              merge duplicates
Solution docs        ──→   promotions strengthen ──→   update priorities
Error patterns             dismissals weaken           suggest dependencies
Session telemetry          source trust adapts          decay stale items
Kernel events              thresholds shift             link related work
```

**Source configuration (OS policy).** Which RSS feeds, arXiv categories, GitHub repos, and search queries to monitor. Sources are configured per-project with global defaults.

**Three trigger modes.** The pipeline can be triggered three ways, all producing the same kernel event stream:

- **Scheduled (background).** A managed timer runs the scanner at configurable intervals (default: 4x daily with randomized jitter). Each scan queries all configured sources, scores discoveries against the interest profile, and submits them to the kernel via `ic discovery add`. The kernel evaluates its confidence gate and emits the resulting events.
- **Event-driven (reactive).** The scanner registers as a kernel event bus consumer. Run completions trigger search for related prior art. Work item creation checks for existing research. Dispatch completions with novel techniques trigger prior art search. Event-driven scans are targeted (using triggering event context); scheduled scans cast a wide net.
- **User-initiated (on-demand).** The user triggers a full scan, submits a topic for triage, or searches stored discoveries via the kernel discovery API. User submissions receive a source trust bonus.

**Confidence-tiered autonomy policy.** The kernel enforces tier boundaries; the OS decides the policy at each tier:

| Tier | Score Range | OS Policy |
|---|---|---|
| **High** | ≥ 0.8 | Auto-create bead (P3 default), write briefing doc, notify in session inbox |
| **Medium** | 0.5 – 0.8 | Write briefing draft, surface in inbox for human promote/dismiss/adjust |
| **Low** | 0.3 – 0.5 | Log only, searchable via kernel discovery API |
| **Discard** | < 0.3 | Record with `discarded` status for negative signal |

**Adaptive thresholds.** Tier boundaries shift based on the promotion-to-discovery ratio. If humans consistently promote Medium items (>30% promotion rate — chosen as the point where manual triage cost exceeds auto-triage risk), the High threshold lowers by 0.02 per feedback cycle (small step to prevent oscillation). If humans consistently dismiss High items (<10% rate), the threshold rises. These defaults are tunable per-project. Convergence toward human judgment is tracked by Interspect.

**Backlog refinement rules.** The OS applies refinement policy using kernel primitives:
- **Deduplication** — kernel enforces cosine similarity threshold (default 0.85, empirically tuned against interject's all-MiniLM-L6-v2 embeddings — adjust per embedding model); duplicates link as evidence to existing beads
- **Priority escalation** — 3+ independent sources within 7 days triggers priority bump
- **Dependency suggestion** — cross-references between discoveries propose bead dependency links (human confirms)
- **Staleness decay** — kernel decays priority on inactive beads (default: one level per 30 days); fresh evidence reverses decay
- **Weekly digest** — periodic rollup of research activity, promotions, trends, and profile learning for human review

**The feedback loop.** Human actions feed back into the scoring model:

```
Discovery scored → Human promotes → Profile vector shifts toward discovery embedding
                                     Source trust for that source increases
                                     Adaptive threshold adjusts

Discovery scored → Human dismisses → Profile vector shifts away from discovery embedding
                                      Source trust for that source decreases
                                      If pattern: source deprioritized

Bead shipped     → Feedback signal → Discovery marked "validated"
                                      Source gets trust bonus
                                      Similar future discoveries score higher
```

Discovery is a capability track orthogonal to the autonomy ladder (see the [Demarch vision](../../../docs/demarch-vision.md) for the full ladder and capability track definitions). It operates at any autonomy level — the pipeline that finds work before it can be recorded.

**What already exists.** The interject plugin implements the core discovery engine: source adapters (arXiv, HN, GitHub, Anthropic docs, Exa), embedding-based scoring (all-MiniLM-L6-v2, 384 dims), adaptive thresholds, and bead/briefing output. The intersearch library provides shared embedding and Exa search infrastructure. What's missing is OS pipeline integration — feeding interject discoveries into the kernel event bus, event-driven scan triggers, and automated backlog refinement. The kernel primitives (discovery storage, confidence tiers, scoring, promotion/dismissal) shipped in E5.

### Design

Strategy, specification, planning, and plan review. The agency designs the solution and validates it through multi-perspective review before any code is written.

| Capability | Models / Agents |
|---|---|
| Strategy and system design | Opus (deep reasoning) |
| PRD generation and validation | Gurgeh (confidence-scored spec sprint) |
| Cross-AI design review | Oracle (GPT-5.2 Pro) |
| Multi-perspective plan review | Flux-drive with formalized cognitive lenses (e.g., security, resilience) to combat AI consensus bias |
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
| Final multi-agent review | Interflux fleet deploying explicit cognitive diversity lenses (combating consensus bias) |
| Critical path analysis | Oracle (GPT-5.2 Pro) |
| Landing and deployment | Landing discipline agents |
| Knowledge compounding | Auto-compound (learnings → memory) |
| **Output** | Landed change |

### Reflect

Capture what was learned. The agency documents patterns discovered, mistakes caught, decisions validated, and complexity calibration data. This closes the recursive learning loop — every sprint feeds knowledge back into the system.

| Capability | Models / Agents |
|---|---|
| C1-C2 lightweight learnings | Haiku (quick memory notes) |
| C3+ engineering documentation | Opus (full solution docs) |
| Complexity calibration | Automatic (estimated vs actual comparison) |
| **Output** | Learning artifacts (memory notes, solution docs, calibration data) |

Each macro-stage maps to sub-phases internally — Discover includes research and brainstorm; Design includes strategy, plan, and plan-review; Build includes execute and test; Ship includes review and deploy; Reflect includes learning capture and complexity calibration. The macro-stages provide the mental model; the sub-phases provide the granularity. Phase chains are configurable per-run via the kernel.

**Macro-stage handoff contracts.** Each macro-stage produces typed artifacts that become the next stage's input:
- **Discover → Design:** Problem definition doc, research briefings, opportunity assessment. Design reads these as context for strategy.
- **Design → Build:** Approved plan with gate-verified artifacts (PRD, architecture doc, task breakdown). Build reads the plan as its work order.
- **Build → Ship:** Tested code (passing CI), review artifacts (verdicts). Ship reads these for final validation.
- **Ship → Reflect:** Shipped code, review verdicts, agent telemetry. Reflect reads these as evidence for what worked and what didn't.
- **Reflect → (next cycle):** Compounded learnings, complexity calibration data, updated memory. Feed back into Discover for the next iteration.

The kernel enforces handoff via `artifact_exists` gates at macro-stage boundaries. The OS defines which artifact types satisfy each gate.

The brainstorm and strategy phases are real product capabilities, not engineering context-setting. Most agent tools pretend product work is prompt fluff; Clavain makes it first-class.

## Model Routing Architecture

Model routing operates at three stages, each building on the one below:

### Stage 1: Kernel Mechanism

All dispatches flow through the kernel dispatch primitive with an explicit model parameter. The kernel records which model was used, tracks token consumption, and emits events. This is the durable system of record for every model decision.

### Stage 2: OS Policy

Plugins declare default model preferences (fd-architecture defaults to Opus, fd-quality defaults to Haiku). Clavain's routing table can override these per-project, per-run, or per-complexity-level. Not everything needs Opus — a style-checking agent on Haiku catches the same issues at 1/20th the cost.

### Stage 3: Adaptive Optimization (The Meta-Learning Loop)

The agent fleet registry stores cost/quality profiles per agent×model combination. The composer optimizes the entire fleet dispatch within a budget constraint. "Run this review with $5 budget" → the composer allocates Opus to the 2 highest-impact agents and Haiku to the rest. Interspect's outcome data drives profile updates — models that consistently underperform for a task type get downweighted. Crucially, this meta-learning loop features manual routing overrides, counterfactual shadow evaluations, and circuit breakers as first-class citizens of the OS's safety model, ensuring the system learns safely from its own history.

These three stages are staged on the roadmap: static routing ships first, complexity-aware routing follows, adaptive optimization comes with measurement infrastructure. The kernel mechanism (Stage 1) is described fully in the [Intercore vision doc](../../../core/intercore/docs/product/intercore-vision.md) — the kernel records dispatch details, model selection, and token consumption; the OS configures routing policy on top.

**Routing precedence.** When multiple stages provide a model preference, higher stages override lower: adaptive override (Stage 3) > OS routing table (Stage 2) > plugin default (Stage 2) > kernel default (Stage 1, none — model is required). If adaptive routing has no data for a task type, it defers to the OS routing table.

**Failure handling.** If the selected model is unavailable (API error, rate limit), the OS retries with the next model in the routing table's fallback chain. If no fallback is configured, the dispatch fails. The kernel records the original model selection and the actual model used (if fallback occurred) for Interspect analysis.

**Budget semantics.** Token budgets on runs (`--token-budget`) are soft caps: the kernel emits `budget.warning` at the configured threshold percentage and `budget.exceeded` when the cap is crossed. The OS decides the response — kill, downgrade, or continue. Budgets are not hard enforcement in v1; they are observability signals.

## Development Model

**Clavain-first, then generalize out.**

Tight coupling is a feature during the research phase, not a bug. Capabilities are built integrated, tested under real use, and only extracted when the pattern stabilizes enough to stand alone. This inverts the typical "design the API first" approach; Clavain builds too-tightly-coupled on purpose, discovers the natural seams through practice, and only then extracts. Each companion has been validated by production use before it becomes a standalone module.

### The inter-* constellation

The ecosystem has three layers — kernel (infrastructure), OS (agency + companion plugins), and apps (Autarch TUI tools) — plus a cross-cutting profiler.

**Infrastructure (Layer 1)**

| Module | Role | Status |
|---|---|---|
| intercore | Orchestration kernel — runs, phases, gates, dispatches, events | Active development |
| interspect | Adaptive profiler — reads kernel events, proposes OS config changes | Active development |

**Companion Plugins (OS Extensions)**

| Companion | Crystallized Insight | Status |
|---|---|---|
| interflux | Multi-agent review + research dispatch is generalizable | Shipped |
| interphase | Phase tracking and gates are generalizable (shim — delegates to `ic`) | Shipped |
| interline | Statusline rendering is generalizable | Shipped |
| interpath | Product artifact generation is generalizable | Shipped |
| interwatch | Doc freshness monitoring is generalizable | Shipped |
| interlock | Multi-agent file coordination is generalizable | Shipped |
| interject | Ambient discovery + research engine is generalizable | Shipped |
| interdoc | Documentation generation is generalizable | Shipped |
| intermux | Agent visibility is generalizable | Shipped |
| tldr-swinton | Token-efficient code context is generalizable | Shipped |
| intercheck | Code quality guards + session health are generalizable | Shipped |
| interdev | MCP CLI + developer tooling is generalizable | Shipped |
| intercraft | Agent-native architecture patterns are generalizable | Shipped |
| interform | Design patterns + visual quality are generalizable | Shipped |
| interslack | Slack integration is generalizable | Shipped |
| internext | Work prioritization + tradeoff analysis is generalizable | Shipped |
| interpub | Plugin publishing is generalizable | Shipped |
| intersearch | Shared embedding + Exa search is generalizable | Shipped |
| interstat | Token efficiency benchmarking is generalizable | Shipped |
| intersynth | Multi-agent synthesis (verdict aggregation) is generalizable | Shipped |
| intermap | Project-level code mapping is generalizable | Shipped |
| intermem | Memory synthesis + tiered promotion is generalizable | Shipped |
| interkasten | Notion sync + documentation is generalizable | Shipped |
| interfluence | Voice profile + style adaptation is generalizable | Shipped |
| interlens | Cognitive augmentation lenses are generalizable | Shipped |
| interleave | Deterministic skeleton + LLM islands is generalizable | Shipped |
| interserve | Codex spark classifier + context compression is generalizable | Shipped |
| interpeer | Cross-AI peer review is generalizable | Shipped |
| intertest | Engineering quality disciplines are generalizable | Shipped |
| tool-time | Tool usage analytics is generalizable | Shipped |
| tuivision | TUI automation + visual testing is generalizable | Shipped |
| intershift | Cross-AI dispatch engine is generalizable | Planned |
| interscribe | Knowledge compounding is generalizable | Planned |

**Apps (Autarch)** — Bigend (monitoring), Gurgeh (PRD generation), Coldwine (task orchestration), Pollard (research intelligence). See the [Autarch vision doc](../../../apps/autarch/docs/autarch-vision.md).

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

#### Event Reactor Lifecycle (A3 Detail)

At Level 2 autonomy, the OS runs an event reactor that drives automatic phase advancement. The reactor is an OS component — not a kernel daemon. The kernel remains stateless between CLI calls.

**Process model.** The reactor runs as a long-lived process that tails the kernel event log via a consumer cursor. It filters for `dispatch.completed`, `gate.passed`, and `gate.failed` events, and invokes the kernel's run-advance operation when conditions are met. The OS does not poll state tables — it tails the event log.

**Lifecycle management.** The reactor can be deployed in three modes, each with increasing reliability:
- **Session-scoped** (simplest): A Clavain hook starts the reactor at session start; it dies when the session ends. Suitable for interactive development where overnight runs are not expected.
- **Managed service** (recommended for Level 2): A service unit with auto-restart. Survives session ends. Requires installation.
- **Hook-triggered** (hybrid): Each `dispatch.completed` event triggers a run-advance attempt from a Clavain hook. No persistent process. Reliable within sessions but no overnight advancement.

**Gate failure behavior.** When the reactor receives `gate.failed` for an automatic advancement attempt, it must:
1. Request the kernel to transition the run to `paused` state with gate failure evidence
2. The kernel emits a `run.paused` event (the kernel is the event authority, not the OS)
3. Surface the pause in the app layer (Bigend/TUI/inbox) as requiring human action

A paused run does not auto-resume. The human reviews the failure, resolves the issue, and manually advances the run via the kernel CLI. The reactor picks up from the advanced state on its next poll.

**Manual recovery.** If the reactor is down and runs are stuck, manual advancement via the kernel CLI always works from any terminal. The reactor automates advancement, but the kernel CLI is always the escape hatch.

**Stalled dispatch handling.** A dispatch killed without self-reporting (`kill -9`, OOM) remains in `running` state. The OS calls `ic dispatch reconcile` periodically (default: 60s — fast enough to catch most stalls within one phase transition, cheap enough to run continuously), which detects orphaned dispatches and emits `reconciliation.anomaly` events. The `agents_complete` gate must accept dispatches confirmed dead by reconciliation as terminal states.

**Operational contracts.**

- **Idempotency of advance calls.** The kernel's optimistic concurrency (`WHERE phase = ?`) makes `ic run advance` idempotent at the kernel level — a duplicate advance receives `ErrStalePhase` and no state changes. The reactor must handle `ErrStalePhase` as a benign race (log and continue), not an error requiring intervention.
- **Concurrent reactor safety.** Only one reactor instance per project should be active. Multiple reactors tailing the same event log would race on advance calls — the kernel prevents double-advancement, but the losing reactor wastes work. The managed service mode enforces single-instance via its service unit. Session-scoped mode is naturally single-instance per session.
- **Causal ordering.** The reactor processes events in `rowid` order (insertion order within the event log). The kernel guarantees that state mutations and their events are written in the same transaction, so a `dispatch.completed` event is never visible before its state table update. The reactor can rely on event ordering matching causal ordering.
- **Backoff and flapping prevention.** If the reactor receives repeated `gate.failed` events for the same run within a short window (e.g., 3 failures in 60 seconds), it must back off — stop attempting advancement for that run until a human intervenes or a qualifying event (new artifact, new dispatch completion) resets the failure count. Without backoff, a misconfigured gate could cause the reactor to spin on advance-fail-advance cycles.
- **Consumer checkpoint recovery.** On restart, the reactor resumes from its durable cursor position (`ic events tail --consumer=clavain-reactor --durable`). Events between the last checkpoint and the crash are replayed. Because advance calls are idempotent, replaying already-processed events is safe — the kernel rejects duplicate transitions. The reactor should checkpoint its cursor after each successfully processed event batch.
- **Reconciliation ownership.** The reconciliation loop (calling `ic dispatch reconcile`) runs in the same process as the reactor when deployed as a managed service, or as a periodic hook when deployed in session-scoped mode. It is an OS responsibility — the kernel provides the primitive, the OS schedules it.

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

## Success Metrics

Clavain's value is measurable. These metrics define what "working" means at each maturity level:

**Core loop metrics (measurable now):**
- **Sprint completion rate** — % of sprints that reach Ship without abandonment. Target: >70% for complexity ≤3.
- **Gate pass rate** — % of phase transitions that pass gates on first attempt. Low rates indicate miscalibrated gates or poor planning. *Caveat:* Gate pass rate is a calibration signal, not a quality signal. If agents optimize for pass rate directly (e.g., lowering thresholds), the metric becomes meaningless. Post-merge defect rate is the ground truth (PHILOSOPHY.md: anti-gaming by design).
- **Time-to-first-signal** — wall-clock time from sprint start to first quality gate result. Target: <15 min for simple, <45 min for complex.
- **Defect escape rate** — bugs found after Ship that were present during Build. Lower is better. Measured by Interspect once correction events are available.
- **Override rate** — % of gate failures that are manually overridden. High rates indicate gates are too strict or poorly calibrated. Tracked per gate type.

**Efficiency metrics (measurable with token tracking):**
- **Tokens per landable change** — total token spend for a sprint that produces a merged commit. Lower is better, but only meaningful when quality is held constant.
- **Agent utilization** — % of dispatched agents whose output contributes to the final change. Low utilization suggests over-dispatching.
- **Cost per finding** — token cost of quality gate findings that are actually actionable (not false positives).

**Maturity metrics (measurable with Interspect):**
- **Routing accuracy** — % of model selections that match the outcome-optimal model for that task type. Requires Interspect data.
- **Self-improvement rate** — frequency of OS configuration changes proposed by Interspect that improve metrics when applied. This is the "is the system actually learning?" metric.

## What Clavain Is Not

**Not the platform.** That's Demarch. Clavain is the opinionated reference agency built on the platform. The inter-* constellation offers composable pieces that anyone can adopt independently, but the agency as a whole is not designed to be "framework-agnostic" or "configurable for any workflow."

**Not a general AI gateway.** That's what projects like OpenClaw (general-purpose AI message routing) do. Clavain doesn't route arbitrary messages to arbitrary agents. It orchestrates software development — it has opinions about what "good" looks like at every phase, and those opinions are encoded in gates, review agents, and quality disciplines.

**Not a coding assistant.** That's what Cursor and similar tools do. Clavain doesn't help you write code; it *builds software* — the full lifecycle from problem discovery through shipped, reviewed, tested, compounded code. The coding is one phase of five.

**Not primarily a Claude Code plugin — but today, it is.** Clavain's identity is an autonomous software agency. Today it ships primarily as a Claude Code plugin because that surface is available and productive (PHILOSOPHY.md: "Claude Code first, multi-host near-term, host-agnostic long-term"). Autarch (TUI) is an alternative surface and a proving ground for the host-agnostic architecture, not a replacement target. The architecture is designed to outlive any single host platform — agent IDEs will commoditize; the value is in the infrastructure, not which editor runs the agents. Clavain dispatches to Claude, Codex, Gemini, GPT-5.2, and other models as execution backends. The Claude Code plugin interface is one driver among several — a UX adapter, not the identity.

**Not for non-builders.** Clavain is for people who build software with agents. It is not a no-code tool, not an AI assistant for non-technical users, not a chatbot framework.

## Origins

Clavain is named after one of the protagonists from Alastair Reynolds's Revelation Space series. The inter-* naming convention follows the same spirit: names that describe what the component does in the system (the space between things), not the implementation detail.

The project began by merging and evolving [superpowers](https://github.com/obra/superpowers), [superpowers-lab](https://github.com/obra/superpowers-lab), [superpowers-developing-for-claude-code](https://github.com/obra/superpowers-developing-for-claude-code), and [compound-engineering](https://github.com/EveryInc/compound-engineering-plugin). It has since grown beyond those roots into an autonomous agency with its own kernel, profiler, TUI, and companion ecosystem.

---

*This document was originally formalized from a brainstorm session on 2026-02-14, with input from four parallel flux-research agents (Claude) and cross-review by Oracle (GPT-5.2 Pro). Revised on 2026-02-19 to reflect the new identity as an autonomous software agency following the Intercore kernel vision.*
