# Clavain Roadmap

**Version:** 0.6.5
**Last updated:** 2026-02-14
**Vision:** [`docs/vision.md`](vision.md)
**PRD:** [`docs/PRD.md`](PRD.md)

---

## Where We Are

Clavain is a general-purpose engineering discipline plugin for Claude Code — 27 skills, 5 agents, 37 commands, 7 hooks, 1 MCP server. Five companion plugins shipped (interflux, interphase, interline, interpath, interwatch); four more planned. 278 beads closed, 45 open.

### What's Working

- Full product lifecycle coverage: brainstorm, strategy, plan, execute, review, test, ship, learn
- 3-layer routing (Stage/Domain/Concern) injected every session via SessionStart hook
- Multi-agent review engine (interflux) with 7 fd-* review agents + 5 research agents, domain detection across 11 profiles, diff/document slicing, and knowledge compounding
- Phase-gated `/sprint` pipeline with work discovery via beads state tracking
- Cross-AI peer review via Oracle (GPT-5.2 Pro)
- Parallel dispatch to Codex CLI via `/clodex`
- Structural test suite (pytest + bats-core) guarding component counts, cross-references, namespace hygiene
- Companion plugin ecosystem with shim delegation (graceful degradation when companions absent)

### What's Not Working Yet

- **No measurement.** Agent output is qualitatively useful but unquantified. Can't answer: are 8 agents better than 4? Which agents have high override rates? What's the cost per landed change?
- **No evals.** Prompt changes, model updates, and agent consolidation happen without regression detection.
- **No project-local memory.** Knowledge compounding writes to global plugin state; per-project learnings don't exist.
- **Token costs are opaque.** No per-run cost reporting, no budget controls, no cost-quality tradeoff visibility.
- **Companion extractions are intuition-driven.** Interflux, interphase, and interline were extracted based on gut feel about stable interfaces, not analytics.

---

## Roadmap

The roadmap follows Oracle's prescription (2026-02-14 brainstorm cross-review): **build the truth engine first, then let everything else compete for survival under data.**

Three phases, sequenced by dependency. Each phase has a clear theme, concrete deliverables with linked beads, and trigger conditions for the next phase.

### Phase 1: Measure

**Theme:** Build outcome-based agent analytics. Without measurement, everything else is guesswork.

**Why first:** Every other roadmap item benefits from data. Companion extractions should be informed by interface stability metrics. Token optimization should target the highest-cost/lowest-value agents. Topology decisions should be empirical, not intuitive. Phase 1 creates the foundation that makes all subsequent work data-driven.

#### P1.1 — Outcome-Based Agent Analytics (v1)

**Bead:** Clavain-mb6u (P1, blocks: Clavain-spad, Clavain-7z28, Clavain-4xqu)

Build a unified trace/event system for every workflow run.

| Component | What it captures |
|-----------|-----------------|
| Per-agent trace | Tokens in/out, latency, model, context size, tool calls, findings count |
| Per-gate trace | Pass/fail, reasons, duration, human override (if any) |
| Per-human-touch | Override decision, time-to-decision, rationale |
| Per-run summary | Total cost, agent roster, topology, verdict |

**Five discipline KPIs** (from Oracle's recommendation):

1. **Defect escape rate** — findings caught in review that would have shipped
2. **Human override rate** — % of agent recommendations overridden, by agent and domain
3. **Cost per landed change** — total token cost for brainstorm-to-merge
4. **Time-to-first-signal** — seconds from `/flux-drive` to first actionable finding
5. **Redundant work ratio** — % of agent findings that are duplicates across agents

**Output:** Analytics data stored per-project (likely `.clavain/analytics/` — see P1.4). Dashboard via CLI commands, not GUI.

#### P1.2 — Agent Evals as CI

**Bead:** Clavain-705b (P1)

Design a small corpus of real tasks with expected properties (not exact text matches), run as regression tests.

| Task type | Example | Expected property |
|-----------|---------|-------------------|
| Code review | Intentional SQL injection in diff | fd-safety flags it |
| Plan review | Plan missing error handling | plan-reviewer catches it |
| Refactor review | Extract with broken interface | fd-architecture flags coupling |
| Docs review | Stale count in README | fd-quality catches drift |
| Bugfix | Off-by-one in pagination | fd-correctness flags it |

**Goal:** Answer "did this prompt change reduce bug-catching rate?" and "did tldrs integration reduce defects per token or just tokens?"

**Output:** Eval harness that runs as CI (or on-demand via command). Results feed into P1.1 analytics.

#### P1.3 — Topology Experiment

**Bead:** Clavain-7z28 (P1, blocked by: Clavain-mb6u)

Run the same tasks with 2, 4, 6, and 8 agents. Plot quality vs. cost vs. time vs. human attention.

| Topology | Agents | Hypothesis |
|----------|--------|-----------|
| Minimal | fd-architecture, fd-correctness | Catches structural bugs only |
| Core-4 | + fd-safety, fd-quality | Covers 80% of finding categories |
| Standard-6 | + fd-user-product, fd-performance | Current default |
| Full-8 | + fd-game-design + generated agent | Marginal value vs. marginal cost? |

**Output:** 2-3 topology templates to standardize. Empirical answer to "what is the coordination tax?" and "when do more agents hurt?"

**Depends on:** P1.1 (needs analytics to measure quality/cost).

#### P1.4 — Agent Memory Filesystem (`.clavain/`)

**Bead:** Clavain-d4ao (P2, but foundational)

Establish the per-project memory contract that analytics, learnings, and downstream features depend on.

```
.clavain/
├── index/                  # Auto-generated search indexes
├── learnings/              # Curated durable knowledge (per-project)
├── scratch/                # Ephemeral state (gitignored)
│   ├── handoff.md          # Session handoff (replaces root HANDOFF.md)
│   └── runs/               # Run manifests and checkpoints
├── contracts/              # API contracts and invariants
└── weather.md              # Model routing preferences
```

**Key changes:**
- `session-handoff.sh` writes to `.clavain/scratch/` (not root HANDOFF.md)
- `auto-compound.sh` writes project-local learnings when `.clavain/` exists
- `session-start.sh` injects `.clavain/index/` summary as context
- New `/clavain:init` command scaffolds the directory

**Why Phase 1:** Analytics (P1.1) needs a place to write per-project traces. Knowledge compounding (interflux) needs per-project storage. This is infrastructure, not a feature.

#### Phase 1 Exit Criteria

- [ ] Analytics trace emitted for every `/flux-drive` and `/sprint` run
- [ ] 5 KPIs computable from stored traces
- [ ] Eval corpus with 10+ tasks, runnable as CI
- [ ] Topology experiment completed, 2-3 templates documented
- [ ] `.clavain/` convention established and used by at least 2 hooks

---

### Phase 2: Integrate + Extract

**Theme:** Deep tldrs integration measured against Phase 1 baselines. Extract remaining companions — informed by analytics data showing which interfaces are stable.

**Trigger:** Phase 1 KPIs are computable and the topology experiment has results.

#### P2.1 — Deep tldrs Integration

**Bead:** Clavain-spad (P2, blocked by: Clavain-mb6u)

tldrs becomes the default token-efficient "eyes" of the system. Every skill/agent that reads code routes through tldrs.

| Integration point | Before | After |
|-------------------|--------|-------|
| Flux-drive triage | Reads full files/diffs | tldrs structural analysis + targeted reads |
| Agent context | Full file dumps | tldrs function-level extraction |
| Plan execution | Read-then-modify | tldrs call graph + targeted modification |
| Research agents | Full repo scans | tldrs semantic search |

**Measured against Phase 1 baselines:** Did tldrs integration reduce defects per token, or just tokens? Did time-to-first-signal improve? Did human override rate change?

#### P2.2 — Companion Extractions (Analytics-Informed)

Four planned companions, ordered by self-containment and risk:

| Priority | Companion | Theme | Bead | Coupling | Risk |
|----------|-----------|-------|------|----------|------|
| P2.2a | **intercraft** | Claude Code meta-tooling | Clavain-2ley | Very low (zero coupling) | Low — safe to extract first |
| P2.2b | **intershift** | Cross-AI dispatch engine | Clavain-6ikc | Moderate (flag file shim) | Medium — Oracle/Codex dispatch |
| P2.2c | **interscribe** | Knowledge compounding | Clavain-sdqv | Moderate (cross-plugin) | Medium — touches auto-compound |
| P2.2d | **interarch** | Agent-native architecture | Clavain-eff5 | Very low (zero coupling) | Low — standalone skill |

**Extraction criteria (from Oracle):** Don't extract before you have measurement. Each extraction is informed by analytics data showing:
- Interface stability (did the API between Clavain and this component change in the last N runs?)
- Usage frequency (is this component used enough to warrant standalone maintenance?)
- Coupling evidence (does the analytics trace show tight dependencies?)

**intercraft first** (zero coupling, safe even without full analytics). Then intershift, interscribe, interarch — sequenced by analytics evidence.

#### P2.3 — Flux-Drive Spec Library Extraction

**Beads:** Clavain-ia66, Clavain-0etu, Clavain-e8dg, Clavain-rpso (P2-P3, chained)

Extract the flux-drive protocol (already spec'd in `docs/spec/` in Interflux) into reusable libraries:

| Phase | Bead | Deliverable |
|-------|------|-------------|
| Spec Phase 1 | (done) | Protocol spec: 9 docs, 2,309 lines, 3 conformance levels |
| Spec Phase 2 | Clavain-ia66 | Extract domain detection Python library |
| Spec Phase 3 | Clavain-0etu | Extract scoring/synthesis Python library |
| Spec Phase 4 | Clavain-e8dg | Migrate Clavain to consume the library |
| Spec Phase 5 | Clavain-rpso | Claude Code adapter guide + publish |

#### P2.4 — Diff/Document Slicing Consolidation

**Bead:** Clavain-496k (P2)

Consolidate slicing logic from 4 files (~499 lines across 5 locations) into a single `phases/slicing.md` (~350 lines). This is a refactoring of markdown instructions — no runtime behavior changes. Clears technical debt before further interflux evolution.

#### P2.5 — Infrastructure Improvements

Smaller items that compound over Phase 2:

| Item | Bead | Priority | Description |
|------|------|----------|-------------|
| Split upstreams.json | Clavain-3w1x | P2 | Separate config from state, gitignore state |
| Consolidate upstream API calls | Clavain-4728 | P2 | 24 → 12 API calls per check |
| flux-gen UX improvements | Clavain-0d3a | P3 | Onboarding, integration, docs |
| flux-gen frontmatter | Clavain-ub8n | P3 | Move boilerplate to dispatch-time |
| `/describe-pr` command | Clavain-l8zk | P3 | Quick PR descriptions |

#### Phase 2 Exit Criteria

- [ ] tldrs integration measured: token reduction, defect rate, time-to-first-signal
- [ ] At least 2 companions extracted (intercraft + 1 more)
- [ ] Domain detection and scoring available as Python libraries
- [ ] Slicing logic consolidated
- [ ] Upstream sync infrastructure simplified

---

### Phase 3: Advance

**Theme:** Automation multipliers — adaptive routing, cross-project learning, MCP-native communication. Only safe to build on top of Phase 1 observability and Phase 2 integration.

**Trigger:** Phase 2 tldrs integration shows measured improvement. At least 2 companion extractions complete.

#### P3.1 — Adaptive Model Routing

**Bead:** Clavain-4xqu (P3, blocked by: Clavain-mb6u, Clavain-7z28)

Dynamic routing based on measured trust, not static tiers:
- Agents with low precision (high override rate) get smaller scope
- Expensive models invoked only when early screeners detect risk
- Topology templates from P1.3 inform default routing
- Per-project model preferences stored in `.clavain/weather.md`

**Depends on:** P1.1 (analytics for trust scores), P1.3 (topology templates).

#### P3.2 — Cross-Project Knowledge Compounding

**Bead:** Clavain-nv7f (P3)

Knowledge compounding across projects, measured for ROI:
- Patterns learned in project A inform project B
- Two-tier knowledge: project-local (`.clavain/learnings/`) and global
- Graduation pipeline: project-local → global when confirmed across 2+ projects
- Staleness pruning: archive entries not re-confirmed after configurable decay period

**Depends on:** P1.4 (`.clavain/` filesystem), interscribe extraction (P2.2c).

#### P3.3 — MCP-Native Companion Communication

**Bead:** Clavain-oijz (P3)

Migrate inter-* communication from file-based sideband (`/tmp/clavain-*.json`) to MCP servers:
- Start with interphase (phase state queries via MCP tool calls instead of file reads)
- Enables interoperability with non-Clavain tools
- Supports dynamic capability discovery
- Aligns with industry direction (MCP 97M+ SDK downloads, A2A protocol)

#### P3.4 — Interactive-to-Autonomous Boundary

**Bead:** Clavain-xweh (P3)

Formalize the shift-work boundary in workflows — when should the system ask for human input vs. proceed autonomously? Informed by P1.1 human override rate data and P3.1 adaptive routing.

#### P3.5 — Deferred Flux-Drive v2 Features

**Bead:** Clavain-9tq (P3, 8 items)

Trigger-gated features deferred from the v2 architecture redesign:

| Feature | Trigger |
|---------|---------|
| Two-tier knowledge | After 20+ reviews, if >30% entries are project-specific |
| Ad-hoc agent generation | Users report domains core agents consistently miss |
| Async deep-pass agent | After 50+ reviews, if cross-review patterns are being missed |
| Agent graduation pipeline | Only if two-tier knowledge is implemented |
| Dynamic agent cap | If token costs are a proven bottleneck |
| 7th core agent (reliability/deploy) | If deploy reviews show shallow coverage under Safety |
| Claim-level convergence | If convergence tracking becomes meaningless at 6-7 agents |
| Complex knowledge frontmatter | If qmd retrieval proves insufficiently precise |

These are not scheduled — they activate when their trigger condition is met, as detected by Phase 1 analytics.

#### Phase 3 Exit Criteria

- [ ] Model routing adapts based on measured agent trust scores
- [ ] Cross-project knowledge compounding operational, measured for ROI
- [ ] At least 1 companion communicates via MCP instead of file sideband
- [ ] Autonomous/interactive boundary documented and enforced

---

## Research Agenda

Research areas organized by proximity to current capabilities. These are not deliverables — they're open questions that Clavain is well-positioned to explore. Research outputs may inform roadmap additions.

### Near-Term (informed by Phase 1 work)

| Area | Key question | Connection |
|------|-------------|-----------|
| Agent measurement & analytics | What metrics predict human override? | P1.1 directly |
| Multi-agent failure taxonomy | How do hallucination cascades propagate? | P1.2 evals |
| Cognitive load budgets & review UX | How do you present multi-agent output for fast, confident review? | P1.1 time-to-first-signal |
| Product-native agent orchestration | Is sprint-style lifecycle orchestration genuine whitespace? | P1.3 topology |
| Agent regression testing | Did this prompt change degrade bug-catching? | P1.2 evals as CI |

**Beads:** Clavain-fzrn, Clavain-jk7q, Clavain-3kee, Clavain-705b

### Medium-Term (informed by Phase 1 data)

| Area | Key question | Connection |
|------|-------------|-----------|
| Optimal human-in-the-loop frequency | How much attention per sprint produces the best outcomes? | P1.1 override rate |
| Multi-model composition theory | When should you use Claude vs. Codex vs. GPT-5.2? | P3.1 adaptive routing |
| Bias-aware product decisions | LLM judges show 40-57% systematic bias — how to mitigate? | P1.2 evals |
| Plan-aware context compression | Give each agent domain-specific context, not everything | P2.1 tldrs integration |
| Transactional orchestration | How do you handle partial failures and conflicting edits? | P2.3 library extraction |

**Beads:** Clavain-exos, Clavain-l5ap

### Long-Term (informed by Phase 2+ data)

| Area | Key question | Connection |
|------|-------------|-----------|
| Knowledge compounding dynamics | Does cross-project learning improve outcomes or add noise? | P3.2 directly |
| Emergent multi-agent behavior | Can you predict interactions in 7+ agent constellations? | P1.3 topology |
| Guardian agent patterns | Can quality-gates be formalized with instruction adherence metrics? | P3.4 boundary |
| ADL discipline extensions | Can Clavain agents be formally specified via Agent Definition Language? | P3.3 MCP |
| Security model for tool access | Capability boundaries, prompt injection, supply chain risk | P2.2b intershift |
| Prompt/agent supply chain | Versioning, checksums, behavior deltas for agent definitions | P2.2 extractions |
| Latency budgets as constraints | Time-to-feedback alongside token cost as optimization target | P1.1 analytics |

**Beads:** Clavain-173y, Clavain-8nza, Clavain-icqo, Clavain-mkrh, Clavain-ve1n

### Deprioritized (per Oracle, 2026-02-14)

- Speculative decoding (can't control inference stack from a plugin)
- Vision-centric token compression (overkill for code-centric workflows)
- Theoretical minimum token cost (empirical cost-quality curves are more useful)
- Deep capability negotiation formalism (manifests + capability maps are enough)
- Full marketplace/recommendation engine (not where Clavain wins)

---

## Companion Constellation Status

| Companion | What it crystallized | Status | Location |
|-----------|---------------------|--------|----------|
| **interflux** | Multi-agent review is generalizable | Shipped | `/root/projects/Interflux/` |
| **interphase** | Phase tracking and gates are generalizable | Shipped | `/root/projects/interphase/` |
| **interline** | Statusline rendering is generalizable | Shipped | `/root/projects/interline/` |
| **interpath** | Product artifact generation is generalizable | Shipped | `/root/projects/interpath/` |
| **interwatch** | Doc freshness monitoring is generalizable | Shipped | `/root/projects/interwatch/` |
| **intercraft** | Claude Code meta-tooling is generalizable | Planned (P2.2a) | — |
| **intershift** | Cross-AI dispatch is generalizable | Planned (P2.2b) | — |
| **interscribe** | Knowledge compounding is generalizable | Planned (P2.2c) | — |
| **interarch** | Agent-native architecture is generalizable | Planned (P2.2d) | — |

---

## Open Beads Summary

### P1 — Must Do (3 beads, all Phase 1)

| Bead | Title | Blocks |
|------|-------|--------|
| Clavain-mb6u | Outcome-based agent analytics v1 (truth engine) | spad, 7z28, 4xqu |
| Clavain-705b | Design agent evals as CI harness | — |
| Clavain-7z28 | Topology experiment: 2/4/6/8 agents | Blocked by mb6u |

### P2 — Should Do (13 beads, Phase 1-2)

| Bead | Title | Phase |
|------|-------|-------|
| Clavain-spad | Deep tldrs integration | P2.1 |
| Clavain-sdqv | Plan interscribe extraction | P2.2c |
| Clavain-6ikc | Plan intershift extraction | P2.2b |
| Clavain-2ley | Plan intercraft extraction | P2.2a |
| Clavain-ia66 | [flux-drive-spec] Phase 2: domain detection library | P2.3 |
| Clavain-0etu | [flux-drive-spec] Phase 3: scoring/synthesis library | P2.3 |
| Clavain-e8dg | [flux-drive-spec] Phase 4: migrate Clavain | P2.3 |
| Clavain-496k | Diff/document slicing consolidation | P2.4 |
| Clavain-3w1x | Split upstreams.json config/state | P2.5 |
| Clavain-4728 | Consolidate upstream API calls | P2.5 |
| Clavain-l5ap | Research: transactional orchestration | Research |
| Clavain-jk7q | Research: cognitive load budgets | Research |
| Clavain-3kee | Research: product-native orchestration | Research |

### P3 — Nice to Have (15 beads, Phase 2-3)

| Bead | Title | Phase |
|------|-------|-------|
| Clavain-4xqu | Adaptive model routing | P3.1 |
| Clavain-nv7f | Cross-project knowledge compounding | P3.2 |
| Clavain-oijz | MCP-native companion communication | P3.3 |
| Clavain-xweh | Interactive-to-autonomous boundary | P3.4 |
| Clavain-9tq | Deferred flux-drive v2 features (8 items) | P3.5 |
| Clavain-eff5 | Plan interarch extraction | P2.2d |
| Clavain-rpso | [flux-drive-spec] Phase 5: adapter guide | P2.3 |
| Clavain-b683 | Auto-inject past solutions into /sprint execute | P3 |
| Clavain-l8zk | `/describe-pr` command | P2.5 |
| Clavain-0d3a | flux-gen UX improvements | P2.5 |
| Clavain-ub8n | flux-gen frontmatter overhaul | P2.5 |
| Clavain-173y | Research: guardian agent patterns | Research |
| Clavain-8nza | Research: latency budgets | Research |
| Clavain-icqo | Research: ADL extensions | Research |
| Clavain-mkrh | Research: prompt/agent supply chain | Research |

### P4 — Backlog (5 beads)

| Bead | Title |
|------|-------|
| Clavain-cam4 | Automated user testing via TUI/browser automation |
| Clavain-dm1a | Token budget controls + per-run cost reporting |
| Clavain-hbcw | `/semport` workflow for semantic code porting |
| Clavain-q703 | Model routing policy + consensus planning |
| Clavain-ve1n | Research: security model for disciplined tool access |

---

## Dependency Graph

```
Phase 1: Measure
  mb6u (analytics v1) ──┬──► 7z28 (topology experiment) ──► 4xqu (adaptive routing) [P3]
                        └──► spad (tldrs integration) [P2]
  705b (evals as CI) ────── independent
  d4ao (.clavain/ fs) ────── independent (infrastructure)

Phase 2: Integrate + Extract
  spad (tldrs) ──────────── depends on mb6u
  2ley (intercraft) ─────── independent (zero coupling)
  6ikc (intershift) ─────── independent
  sdqv (interscribe) ────── independent
  eff5 (interarch) ──────── independent
  ia66 → 0etu → e8dg → rpso (flux-drive spec library chain)
  496k (slicing consolidation) ── independent

Phase 3: Advance
  4xqu (adaptive routing) ── depends on mb6u + 7z28
  nv7f (cross-project) ──── depends on d4ao + sdqv
  oijz (MCP communication) ── independent
  9tq (deferred fd v2) ──── trigger-gated, no hard dependency
```

---

## Keeping This Roadmap Current

| Trigger | What to update |
|---------|---------------|
| Phase transition | Move items from current to completed, update exit criteria |
| New bead created with P1/P2 priority | Add to appropriate phase section |
| Bead completed | Mark in Open Beads Summary, update dependency graph |
| Research insight changes roadmap | Add/modify items, document rationale |
| Companion extraction completed | Update Constellation Status table |
| Trigger condition met for deferred feature | Move from P3.5 to active phase |

The `test_prd.py` structural test validates PRD component counts. This roadmap is not structurally tested — it's a living planning document updated when direction changes, not when files change.

---

*Synthesized from: [`docs/vision.md`](vision.md), [`docs/PRD.md`](PRD.md), 11 brainstorm docs (2026-02-08 through 2026-02-14), 3 flux-drive synthesis reports, 7 approved PRDs, 45 open beads, and Oracle cross-review (2026-02-14). Sources linked throughout.*
