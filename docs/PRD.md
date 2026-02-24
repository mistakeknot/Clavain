# Clavain — Product Requirements Document

**Version:** 0.6.81
**Last updated:** 2026-02-19
**Vision:** [`docs/vision.md`](vision.md)
**Dev guide:** [`AGENTS.md`](../AGENTS.md)

---

## 1. Product Definition

Clavain is an autonomous software agency that orchestrates the full development lifecycle — from problem discovery through shipped code — using heterogeneous AI models selected for cost, capability, and task fit. Each phase of development is a sub-agency with its own model routing, agent composition, and quality gates. The agency drives execution; the human decides direction.

Clavain runs on its own TUI (Autarch), backed by a durable orchestration kernel (Intercore) and an adaptive profiler (Interspect). Companion plugins are drivers — each wraps one capability and extends the agency through kernel primitives. Capabilities are built tightly integrated, battle-tested through real use, and extracted into the inter-* constellation when patterns stabilize.

Clavain has an explicit frontier objective: advancing **agent orchestration**, **coding/reasoning quality**, and **token efficiency** together, not independently. New work should be judged by how it improves: coordination quality, confidence in correctness, and measurable quality-per-token outcomes.

```yaml
frontier_objective:
  title: "Clavain Frontier Scorecard"
  axes:
    - id: orchestration
      goal: "Faster, safer, more adaptive multi-agent coordination."
    - id: reasoning_quality
      goal: "Stronger correctness and defect-prevention outcomes."
    - id: token_efficiency
      goal: "Higher engineering impact per token consumed."
  accept_criteria:
    - "Improve at least one frontier axis."
    - "Avoid regression on the other two axes unless offset by clear, measurable gain."
    - "Prefer signals that are testable and observable."
```

### What Clavain Is Not

- **Not a platform.** That's Intercore. Clavain is the opinionated agency built on the platform.
- **Not a general AI gateway.** Clavain orchestrates software development with opinions about quality at every phase.
- **Not a coding assistant.** Clavain builds software — the full lifecycle from problem discovery through shipped code.
- **Not a Claude Code plugin.** Clavain runs on its own TUI (Autarch). Claude Code is one driver among several.
- **Not for non-builders.** For engineers who build software with agents.

## 2. Users

Three concentric circles, prioritized inner-out:

| Circle | Who | What they get |
|--------|-----|--------------|
| **Inner** | The author — one product-minded engineer | A personal rig optimized for maximum effectiveness without losing the fun |
| **Middle** | Claude Code plugin community | A reference implementation showing what disciplined multi-agent engineering looks like |
| **Outer** | AI-assisted development field | A research artifact demonstrating human-AI collaboration under real constraints |

## 3. Problem

AI coding assistants are powerful but undisciplined. Without structure:
- Work skips review phases and ships unrefined
- Agent output is unchecked — hallucinations, false positives, and redundant findings compound
- Context is lost between sessions — every conversation starts from scratch
- Multi-agent coordination has no measurement — you can't tell if 8 agents are better than 4
- Product work (brainstorming, strategy, PRDs) is treated as prompt fluff, not first-class capability

## 4. Solution

Clavain encodes engineering and product discipline into four component types that compose through a 3-layer routing system:

### 4.1 Component Architecture

| Type | Count | Purpose | Example |
|------|-------|---------|---------|
| **Skills** | 15 | Reusable discipline knowledge | `systematic-debugging`, `writing-plans`, `flux-drive` |
| **Agents** | 4 | Autonomous specialists (review + workflow) | `plan-reviewer`, `pr-comment-resolver` |
| **Commands** | 52 | User-invocable entry points | `/sprint`, `/interpeer`, `/write-plan` |
| **Hooks** | 21 | Event-driven automation | `session-start.sh`, `auto-compound.sh`, `interspect-evidence.sh` |
| **MCP Servers** | 1 | External tool integration | context7 (runtime doc fetching) |

### 4.2 Routing System

3-layer routing maps any user intent to the right component:

1. **Stage** — What phase? (explore / plan / execute / debug / review / ship / meta)
2. **Domain** — What kind of work? (code / data / deploy / docs / research / workflow)
3. **Concern** — What review concern? (architecture / safety / correctness / quality / performance)

Routing is injected into every session via the `SessionStart` hook, which loads the `using-clavain` skill as system context.

### 4.3 Lifecycle Coverage

| Phase | Capability | Key Components |
|-------|-----------|----------------|
| Problem discovery | Collaborative brainstorming, repo research | `brainstorming` skill, `flux-research` (interflux) |
| Product specification | Strategy, PRD creation, prioritization | `writing-strategy` skill, beads integration |
| Planning | Parallelization analysis, subagent delegation | `writing-plans` skill, `/write-plan` command |
| Execution | Plan execution, work, cross-AI dispatch | `executing-plans` skill, `/work`, `/sprint`, clodex |
| Review | Multi-agent review, cross-AI peer review | `flux-drive` (interflux), `/interpeer`, `/quality-gates` |
| Testing | TDD, smoke tests, verification | `test-driven-development` skill, `/fixbuild` |
| Shipping | Landing changes, resolving findings | `landing-a-change` skill, `/resolve` |
| Learning | Knowledge capture, auto-compounding | `compound` skill, `auto-compound` hook |

### 4.4 Companion Plugins (the inter-* constellation)

Capabilities extracted from Clavain when patterns stabilized:

| Companion | What it does | Status |
|-----------|-------------|--------|
| **intercore** | Orchestration kernel — durable state for runs, phases, gates, dispatches, events | Active development |
| **interspect** | Adaptive profiler — outcome analysis, routing optimization | Active development |
| **interflux** | Multi-agent review + research engine (7 fd-* agents, 5 research agents, 2 MCP servers) | Shipped |
| **interphase** | Phase tracking, gates, and work discovery | Shipped |
| **interline** | Statusline renderer (dispatch state, bead context, phase, clodex mode) | Shipped |
| **interpath** | Product artifact generation (roadmaps, PRDs, vision docs, changelogs, status reports) | Shipped |
| **interwatch** | Doc freshness monitoring (drift detection, confidence scoring, auto-refresh) | Shipped |
| **interlock** | Multi-agent file coordination (MCP server wrapping intermute) | Shipped |
| **interslack** | Slack integration | Shipped |
| **interform** | Design patterns + visual quality | Shipped |
| **intercraft** | Agent-native architecture patterns | Shipped |
| **interdev** | MCP CLI + developer tooling | Shipped |
| **intercheck** | Code quality guards + session health | Shipped |
| **interject** | Ambient discovery + research engine (MCP) | Shipped |
| **internext** | Work prioritization + tradeoff analysis | Shipped |
| **interpub** | Plugin publishing | Shipped |
| **intersearch** | Shared embedding + Exa search | Shipped |
| **interdoc** | AGENTS.md generator + Oracle critique | Shipped |
| **interstat** | Token efficiency benchmarking | Shipped |
| **intersynth** | Multi-agent synthesis engine (verdict aggregation) | Shipped |
| **intermap** | Project-level code mapping (MCP) | Shipped |
| **intermem** | Memory synthesis + tiered promotion | Shipped |
| **interkasten** | Notion sync + documentation | Shipped |
| **interfluence** | Voice profile + style adaptation | Shipped |
| **interlens** | Cognitive augmentation lenses | Shipped |
| **interleave** | Deterministic skeleton + LLM islands | Shipped |
| **interserve** | Codex spark classifier + context compression (MCP) | Shipped |
| **interpeer** | Cross-AI peer review (Oracle/GPT escalation) | Shipped |
| **intertest** | Engineering quality disciplines (TDD, debugging, verification) | Shipped |
| **tldr-swinton** | Token-efficient code context (MCP) | Shipped |
| **tool-time** | Tool usage analytics | Shipped |
| **tuivision** | TUI automation + visual testing (MCP) | Shipped |
| **intershift** | Cross-AI dispatch engine | Planned |
| **interscribe** | Knowledge compounding engine | Planned |

## 5. Key Workflows

### 5.1 `/sprint` — Full Pipeline (brainstorm → ship)

The flagship workflow. With no arguments, scans beads for work discovery. With a topic, drives the full lifecycle:

```
brainstorm → strategy/PRD → plan → flux-drive review → execute → test → quality-gates → resolve → ship
```

### 5.2 `/interpeer` — Cross-AI Peer Review

Dispatches to GPT-5.2 Pro (via Oracle) for independent second opinions. Four modes: `quick` (single pass), `deep` (focused analysis), `council` (multi-model deliberation), `mine` (find issues Claude missed).

### 5.3 `/flux-drive` — Multi-Agent Review (via interflux)

Triages up to 12 review agents based on content type and detected domains. Two-stage launch with severity-driven expansion. Synthesis deduplicates findings across agents and computes verdicts.

### 5.4 `/quality-gates` — Quick Diff Review

Lightweight review from `git diff` — faster than flux-drive, suitable for incremental changes.

### 5.5 Knowledge Compounding

`auto-compound` hook detects sessions with compoundable signals (commits, resolutions, insights) and prompts knowledge capture. `session-handoff` hook generates HANDOFF.md for incomplete work.

## 6. Non-Goals

- **No web GUI** — Autarch TUI is the target surface; no browser-based dashboard
- **No domain-specific components** — no Rails, Ruby, Every.to, Figma, Xcode
- **No vendor neutrality** — Claude Code native; multi-model via dispatch, not abstraction
- **No framework mode** — Clavain is a rig, not an SDK for building other rigs
- **No timeline estimation** — no Gantt charts, sprint velocity, or time predictions

## 7. Success Metrics

### 7.1 Current (qualitative, pre-analytics)

- All 8 lifecycle phases have working skills and commands
- Routing table covers every stage/domain combination
- Structural tests pass (component counts, cross-references, namespace hygiene)
- Shell tests pass (hook syntax, escape functions, shim delegation)
- Companion plugins installed and functional

### 7.2 Target (Track B/C — analytics + routing)

| Metric | Definition | Target |
|--------|-----------|--------|
| **Defect escape rate** | Findings caught in review that would have shipped | Baseline TBD |
| **Human override rate** | % of agent recommendations overridden | < 30% |
| **Cost per landed change** | Total token cost for brainstorm-to-merge | Trending down |
| **Time-to-first-signal** | Seconds from `/flux-drive` to first finding | < 45s |
| **Redundant work ratio** | % of agent findings that are duplicates | < 20% |

## 8. Roadmap

> Full detail in [`docs/roadmap.md`](roadmap.md) and [`docs/vision.md`](vision.md).

Three parallel tracks converge toward autonomous self-building sprints:

| Track | Focus | Next Step |
|-------|-------|-----------|
| **A: Kernel Integration** | Migrate from shell state to durable kernel-backed orchestration | A2: Sprint handover — sprint skill becomes kernel-driven (A1 hook cutover done) |
| **B: Model Routing** | Static → complexity-aware → adaptive model selection | B1: Static routing table |
| **C: Agency Architecture** | Declarative agency specs, fleet registry, composer, self-building loop | C1: Agency specs |

Convergence point: C5 (self-building loop) — Clavain uses its own agency specs to run its own development sprints, backed by kernel state and adaptive routing.

## 9. Dependencies

| Dependency | What it provides | Required? |
|-----------|-----------------|-----------|
| Intercore (`ic` CLI) | Durable orchestration kernel — runs, phases, gates, dispatches, events | Yes (Track A) |
| Claude Code | Plugin host, agent runtime (one of several UX drivers) | Yes (current primary) |
| Beads (`bd` CLI) | Issue tracking, state management | Yes |
| Oracle | GPT-5.2 Pro access for cross-AI review | For `/interpeer` |
| Codex CLI | Alternative agent dispatch | For `/clodex`, `/debate` |
| context7 MCP | Runtime documentation fetching | Yes |
| interflux | Multi-agent review engine | Yes (for flux-drive) |
| interphase | Phase tracking and gates | Yes (for phase-gated sprint) |
| interline | Statusline rendering | Recommended |
| interpath | Product artifact generation | Recommended |
| interwatch | Doc freshness monitoring | Recommended |

## 10. Risks

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Token cost grows faster than value | Rig becomes too expensive to run | Outcome-per-dollar metrics (Phase 1); tldrs integration (Phase 2) |
| Agent count inflates without measurement | Coordination tax exceeds benefit | Topology experiment (Phase 1); adaptive routing (Phase 3) |
| Companion extraction breaks Clavain | Shim delegation fails silently | Structural + shell tests; no-op stubs when companions absent |
| Single-user bias | Rig only works for author's workflow | Middle/outer circle feedback; reference implementation mindset |
| Upstream drift | Source repos diverge from Clavain's fork | Daily check workflow, weekly auto-merge, decision gate records |

---

## Appendix A: Keeping This PRD Current

This PRD is a living document. It tracks the state of the product, not a point-in-time specification.

### When to Update

| Trigger | What to update |
|---------|---------------|
| Component count changes (add/remove skill, agent, command) | Section 4.1 table, version header |
| Companion extracted or shipped | Section 4.4 table (status column) |
| Roadmap item completed or reprioritized | Section 8 tables |
| New success metric defined | Section 7 |
| Version bump (`scripts/bump-version.sh`) | Version header |

### Staleness Detection

The `gen-catalog.py` script already validates component counts against `using-clavain/SKILL.md`. The PRD and README are covered by `tests/structural/test_prd.py`:

1. **PRD version guard** — `**Version:**` header must match `plugin.json` version. Auto-updated by `bump-version.sh`.
2. **PRD component counts** — Section 4.1 skill/agent/command counts must match filesystem.
3. **README component counts** — Intro line and section header counts must match filesystem.
4. **Companion status** — verify Section 4.4 "Shipped" entries match installed plugins. Warning-level (companions are optional).

### What Lives Here vs. Elsewhere

| Document | Scope | Update frequency |
|----------|-------|-----------------|
| **This PRD** | What Clavain does, for whom, and how we know it's working | Every significant change |
| `README.md` | Public-facing intro, install, workflow overview, component catalog | When components or workflows change |
| `docs/vision.md` | Why Clavain exists, operating principles, research areas | Rarely (philosophical) |
| `AGENTS.md` | How to develop Clavain (architecture, conventions, validation) | Every structural change |
| `CLAUDE.md` | Quick reference for Claude Code sessions | Rarely (stable reference) |
| Feature PRDs (`docs/prds/`) | Scoped requirements for individual features | Write-once per feature |
