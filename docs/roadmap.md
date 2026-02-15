# Clavain Roadmap

**Version:** 0.6.22
**Last updated:** 2026-02-15
**Vision:** [`docs/vision.md`](vision.md)
**PRD:** [`docs/PRD.md`](PRD.md)

---

## Where We Are

Clavain is a recursively self-improving multi-agent rig for Claude Code — 23 skills, 4 agents, 41 commands, 19 hooks, 1 MCP server. 19 companion plugins shipped. 364 beads closed, 0 open. Average lead time: 8.8 hours.

### What's Working

- Full product lifecycle coverage: brainstorm, strategy, plan, execute, review, test, ship, learn
- 3-layer routing (Stage/Domain/Concern) injected every session via SessionStart hook
- Multi-agent review engine (interflux) with 7 fd-* review agents + 5 research agents, domain detection across 11 profiles, diff/document slicing, and knowledge compounding
- Phase-gated `/sprint` pipeline with work discovery, sprint bead lifecycle, and session claim atomicity
- Cross-AI peer review via Oracle (GPT-5.2 Pro) with quick/deep/council/mine modes
- Parallel dispatch to Codex CLI via `/clodex` with clodex-toggle mode switching
- Structural test suite: 165 tests (pytest + bats-core) guarding component counts, cross-references, namespace hygiene, routing overrides, sprint lifecycle
- 19 companion plugins covering review, phase tracking, statusline, artifacts, drift detection, coordination, Slack, design patterns, agent-native architecture, dev tooling, code quality, ambient research, work prioritization, publishing, search, code context, tool analytics, and TUI testing
- Multi-agent file coordination via interlock (MCP server wrapping intermute Go service)
- Self-healing documentation system via interdoc (structural auto-fix, convergence loops, marker system)
- Signal-based drift detection via interwatch (auto-drift-check Stop hook, lib-signals shared library)
- Interspect analytics system: SQLite evidence store, 3-tier analysis (evidence → patterns → routing overrides), confidence thresholds, blacklist protection, flock-based atomic commits
- Sprint resilience: lib-sprint.sh with bead lifecycle CRUD, session claims via mkdir atomicity, phase routing, discovery integration

### What's Not Working Yet

- **No outcome measurement.** Agent output is qualitatively useful but unquantified. Can't answer: are 8 agents better than 4? Which agents have high override rates? What's the cost per landed change?
- **No evals.** Prompt changes, model updates, and agent consolidation happen without regression detection.
- **Token costs are opaque.** No per-run cost reporting, no budget controls, no cost-quality tradeoff visibility.
- **Interspect has data but no action.** Evidence collection and routing eligibility checks are built, but no override has been applied yet — the system needs real-world signal accumulation.

---

## Shipped Since Last Roadmap

Major features that landed since the 0.6.13 roadmap:

| Feature | Description |
|---------|-------------|
| **Interspect routing overrides** | Producer-consumer flow: interspect collects agent override evidence → confidence thresholds → routing-overrides.json → flux-drive reads at Step 1.2a.0 and excludes agents. Includes blacklist protection, SQL safety, 27 shell tests. |
| **Sprint bead lifecycle** | lib-sprint.sh (408 lines) — sprint beads as type=epic with sprint=true state, session claims via mkdir atomicity, phase routing, discovery integration. 23 shell tests. |
| **13 new companion plugins** | interslack, interform, intercraft, interdev, intercheck, interject, internext, interpub, intersearch, tldr-swinton, tool-time, tuivision, interdoc |
| **Monorepo consolidation** | Physical monorepo at /root/projects/Interverse with compat symlinks, each subproject keeping own .git |
| **Auto-drift-check** | Stop hook detecting shipped-work signals and triggering interwatch scans |
| **Interspect Phase 1-2** | SQLite evidence store, protected paths, confidence thresholds, session tracking |
| **Interlock + intermute** | Full multi-agent file coordination — MCP server, advisory hooks, git pre-commit enforcement |
| **Version 0.6.13 → 0.6.22** | 9 version bumps |

---

## Roadmap

The original 3-phase roadmap (Measure → Integrate + Extract → Advance) remains the strategic direction. All execution beads from the previous roadmap are closed. The next wave of work requires creating new beads.

### Phase 1: Measure (unchanged priority — infrastructure gap)

**Theme:** Build outcome-based agent analytics. Without measurement, everything else is guesswork.

**Status:** The interspect system provides the _evidence collection_ layer but not the _analytics_ layer. Interspect records per-agent override events; what's missing is per-run cost tracking, KPI computation, and eval harness.

| Item | What it needs | Blocked by |
|------|--------------|------------|
| Outcome-based analytics v1 | Per-agent token traces, per-gate pass/fail, per-run cost summaries | — |
| Agent evals as CI | Corpus of tasks with expected properties, regression harness | — |
| Topology experiment | Run 2/4/6/8 agents on same tasks, measure quality vs. cost | Analytics v1 |
| `.clavain/` filesystem | Per-project memory contract for analytics, learnings, scratch state | — |

**Five discipline KPIs** (from Oracle's 2026-02-14 recommendation):

1. **Defect escape rate** — findings caught in review that would have shipped
2. **Human override rate** — % of agent recommendations overridden, by agent and domain
3. **Cost per landed change** — total token cost for brainstorm-to-merge
4. **Time-to-first-signal** — seconds from `/flux-drive` to first actionable finding
5. **Redundant work ratio** — % of agent findings that are duplicates across agents

### Phase 2: Integrate + Extract

**Theme:** Deep tldrs integration measured against Phase 1 baselines. Extract remaining planned companions.

| Item | What it needs | Depends on |
|------|--------------|------------|
| Deep tldrs integration | Route all code-reading through tldrs, measure token/defect impact | Analytics v1 |
| Flux-drive spec library | Extract domain detection + scoring as Python libraries | — |
| Companion extractions | intershift (cross-AI dispatch), interscribe (knowledge compounding) — the two remaining planned companions not yet shipped | Analytics data |

**Note:** intercraft and interarch (previously planned P2.2a/P2.2d) have already been shipped as companion plugins.

### Phase 3: Advance

**Theme:** Automation multipliers — adaptive routing, cross-project learning, MCP-native communication.

| Item | What it needs | Depends on |
|------|--------------|------------|
| Adaptive model routing | Dynamic routing based on measured agent trust scores | Analytics + topology |
| Cross-project knowledge | Patterns learned in project A inform project B | `.clavain/` + interscribe |
| MCP-native communication | Replace file-based sideband with MCP tool calls | — |
| Interactive-to-autonomous boundary | Formalize when to ask human vs. proceed | Analytics override rate |
| Deferred flux-drive v2 | 8 trigger-gated features (two-tier knowledge, ad-hoc agents, etc.) | Various triggers |

---

## Research Agenda

Research areas organized by proximity to current capabilities. These are open questions, not deliverables.

### Near-Term

| Area | Key question |
|------|-------------|
| Agent measurement & analytics | What metrics predict human override? |
| Multi-agent failure taxonomy | How do hallucination cascades propagate? |
| Cognitive load budgets | How to present multi-agent output for fast, confident review? |
| Agent regression testing | Did this prompt change degrade bug-catching? |

### Medium-Term

| Area | Key question |
|------|-------------|
| Optimal human-in-the-loop frequency | How much attention per sprint produces the best outcomes? |
| Multi-model composition theory | When should you use Claude vs. Codex vs. GPT-5.2? |
| Bias-aware product decisions | LLM judges show 40-57% systematic bias — how to mitigate? |
| Plan-aware context compression | Give each agent domain-specific context, not everything |

### Long-Term

| Area | Key question |
|------|-------------|
| Knowledge compounding dynamics | Does cross-project learning improve outcomes or add noise? |
| Emergent multi-agent behavior | Can you predict interactions in 7+ agent constellations? |
| Guardian agent patterns | Can quality-gates be formalized with instruction adherence metrics? |
| Security model for tool access | Capability boundaries, prompt injection, supply chain risk |

### Deprioritized (per Oracle, 2026-02-14)

- Speculative decoding (can't control inference stack from a plugin)
- Vision-centric token compression (overkill for code-centric workflows)
- Theoretical minimum token cost (empirical cost-quality curves are more useful)
- Full marketplace/recommendation engine (not where Clavain wins)

---

## Companion Constellation

| Companion | Version | What it crystallized | Location |
|-----------|---------|---------------------|----------|
| **interflux** | 0.2.0 | Multi-agent review + research engine | `plugins/interflux/` |
| **interphase** | 0.3.2 | Phase tracking + gate validation | `plugins/interphase/` |
| **interline** | 0.2.1 | Statusline rendering | `plugins/interline/` |
| **interpath** | 0.1.1 | Product artifact generation | `plugins/interpath/` |
| **interwatch** | 0.1.1 | Doc freshness monitoring | `plugins/interwatch/` |
| **interlock** | 0.1.1 | Multi-agent file coordination (MCP) | `plugins/interlock/` |
| **interslack** | 0.1.0 | Slack integration | `plugins/interslack/` |
| **interform** | 0.1.0 | Design patterns + visual quality | `plugins/interform/` |
| **intercraft** | 0.1.0 | Agent-native architecture patterns | `plugins/intercraft/` |
| **interdev** | 0.1.0 | MCP CLI developer tooling | `plugins/interdev/` |
| **intercheck** | 0.1.0 | Code quality guards + session health | `plugins/intercheck/` |
| **interject** | 0.1.2 | Ambient discovery + research engine (MCP) | `plugins/interject/` |
| **internext** | 0.1.0 | Work prioritization + tradeoff analysis | `plugins/internext/` |
| **interpub** | 0.1.0 | Plugin publishing | `plugins/interpub/` |
| **intersearch** | — | Shared embedding + Exa search | `plugins/intersearch/` |
| **interdoc** | 5.1.0 | AGENTS.md generator + Oracle critique | `plugins/interdoc/` |
| **tldr-swinton** | 0.7.6 | Token-efficient code context (MCP) | `plugins/tldr-swinton/` |
| **tool-time** | 0.3.1 | Tool usage analytics | `plugins/tool-time/` |
| **tuivision** | 0.1.2 | TUI automation + visual testing (MCP) | `plugins/tuivision/` |
| **intershift** | — | Cross-AI dispatch engine | Planned |
| **interscribe** | — | Knowledge compounding | Planned |

---

## Open Beads Summary

**All 364 beads are closed.** The backlog is empty. The next wave of work requires creating new beads from the Phase 1-3 roadmap items above.

| Metric | Value |
|--------|-------|
| Total beads | 364 |
| Closed | 364 |
| Open | 0 |
| In progress | 0 |
| Avg lead time | 8.8 hours |

---

## Keeping This Roadmap Current

Run `/interpath:roadmap` to regenerate from current project state.

| Trigger | What to update |
|---------|---------------|
| New bead created | Add to appropriate phase section |
| Companion extraction completed | Update Constellation table |
| Phase 1 analytics built | Move items to "shipped", create Phase 2 beads |
| Research insight changes direction | Add/modify items, document rationale |

---

*Synthesized from: [`docs/vision.md`](vision.md), [`docs/PRD.md`](PRD.md), 7 brainstorm docs (2026-02-14 through 2026-02-15), 13 plan docs, 364 closed beads, 19 companion plugins, and Oracle cross-review (2026-02-14). Sources linked throughout.*
