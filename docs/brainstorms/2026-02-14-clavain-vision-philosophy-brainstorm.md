# Clavain Vision, Philosophy, and Roadmap Brainstorm

**Date:** 2026-02-14
**Status:** Captured
**Participants:** Human (product owner), Claude Code (brainstorm facilitator)

## What We're Building

A comprehensive vision document for Clavain and its inter-* companion constellation, covering identity, conviction, vision, mission, philosophy, roadmap, non-goals, and research areas of interest.

## Core Identity

Clavain is a **highly opinionated flagship of the state of the art** in token efficiency, agentic workflows, and AI/human collaboration in product research, management, and execution.

It is not just a tool or a plugin; it is a **proving ground** where capabilities are built tightly integrated, battle-tested through real use, and then extracted into generalizable companion plugins (the inter-* constellation) when patterns stabilize.

**Audience (concentric circles):**
1. **Inner circle:** Personal rig for the author; optimized relentlessly for their own workflow
2. **Middle circle:** Reference implementation for the Claude Code plugin community, showing what's possible and setting conventions
3. **Outer circle:** Research artifact for the broader AI-assisted development field, demonstrating what disciplined human-AI collaboration looks like

## Core Conviction

The point of agents isn't to remove humans from the loop; it's to make every moment in the loop count. Clavain is a highly opinionated agent rig that codifies the discipline, orchestration, and token efficiency needed to make multi-agent engineering actually reliable. Not as a theory, but as a working system you can point at and learn from.

## Vision

**Personal:** Clavain makes a single product-minded engineer as effective as a full team, without losing the fun parts of building.

**Community:** Clavain becomes the reference implementation for how disciplined, multi-agent engineering should work. Other tools learn from it.

**Ecosystem:** The inter-* constellation becomes a composable standard for Claude Code; anyone can use pieces without buying the whole philosophy.

## Mission

Clavain codifies product and engineering discipline into composable, token-efficient skills, agents, and workflows that orchestrate heterogeneous AI models into a reliable, fun-to-use system for building software from brainstorm to ship.

## Philosophy (Operating Principles)

1. **Refinement > production.** The review phases matter more than the building phases. Every moment spent refining and reviewing is worth far more than the actual building itself.

2. **Composition > integration.** Small, focused tools composed together beat large integrated platforms. The inter-* constellation, Unix philosophy, modpack metaphor; it's turtles all the way down.

3. **Token efficiency enables scale.** If you can't afford to run it, it doesn't matter how good it is. 12 agents should cost less than 8 via orchestration optimization.

4. **Human attention is the bottleneck.** Optimize for the human's time, not the agent's. The human's focus, attention, and product sense are the scarce resource; agents are in service of that.

5. **Building builds building.** Capability is forged through practice, not absorbed through reading. Like guitar, you can read all the theory books you want, but none of that matters as much as applied, active practice.

6. **Discipline before automation.** Encode judgment into checks before removing the human. Agents without discipline ship slop.

7. **Multi-AI > single-vendor.** No one model is best at everything. The future is heterogeneous fleets of specialized models orchestrated by discipline, not loyalty to one vendor.

## Non-Goals

- **Not a framework.** Clavain is an opinionated rig, not a reusable library or SDK. You use it as-is or extract pieces, but it's not designed to be "framework-agnostic" or "configurable for any workflow."

- **Not for non-builders.** Clavain is for people who build software with agents. It is not a no-code tool, not an AI assistant for non-technical users, not a chatbot framework.

- **Claude Code native, not vendor-neutral.** Clavain is built on Claude Code. It uses Codex and Oracle as complements (and has a Codex port via install-codex.sh), but it's not trying to be a universal agent orchestrator that works with any LLM platform.

## Scope: Full Product Lifecycle

Clavain covers the full product development lifecycle, not just the code-writing phase:

| Phase | Clavain Capability |
|---|---|
| Problem discovery | Brainstorming (collaborative dialogue, repo research) |
| Product specification | Strategy (PRD creation, beads prioritization) |
| Planning | Write-plan (bite-sized tasks, parallelization analysis) |
| Execution | Execute-plan, work, subagent-driven-development, clodex dispatch |
| Review | Quality-gates, flux-drive (interflux), interpeer, cross-AI review |
| Testing | TDD, smoke-test, verification-before-completion |
| Shipping | Landing-a-change, fixbuild, resolve |
| Learning | Compound (knowledge capture), auto-compound, research agents |

The aspiration is full lifecycle coverage, with the brainstorm/strategy phases as real product capabilities (not just engineering context-setting), expanding toward richer product research tools over time.

## Development Model

**Clavain-first, then generalize out.**

Capabilities are built tightly integrated into Clavain, battle-tested through actual use, and then extracted into companion plugins when the pattern stabilizes. The tight coupling is a feature, not a bug, until extraction is warranted.

Each inter-* companion is a crystallized research output:
- **interphase** crystallized: "phase tracking and gates are generalizable"
- **interflux** crystallized: "multi-agent review is generalizable"
- **interline** crystallized: "statusline rendering is generalizable"
- **intercraft** (planned) will crystallize: "Claude Code meta-tooling is generalizable"
- **intershift** (planned) will crystallize: "cross-AI dispatch is generalizable"
- **interscribe** (planned) will crystallize: "knowledge compounding is generalizable"
- **interarch** (planned) will crystallize: "agent-native architecture is generalizable"

## Roadmap

### Structural (Plugin Extractions)

| Priority | Companion | Theme | Self-containment | File reduction |
|---|---|---|---|---|
| P1 | intercraft | Claude Code meta-tooling | Very high (zero coupling) | ~68 files |
| P2 | intershift | Cross-AI dispatch engine | Moderate-high (flag file shim) | ~27 files |
| P3 | interscribe | Knowledge compounding | Moderate (cross-plugin agents) | ~13 files |
| P4 | interarch | Agent-native architecture | Very high (zero coupling) | ~17 files |

### Capability (New Features)

| Priority | Capability | Description |
|---|---|---|
| P1 | Agent performance analytics | Token cost per outcome, agent accuracy/override rate, workflow bottleneck detection. What you can't measure, you can't optimize. Ashpool should contribute measurement capabilities here. |
| P2 | Deep tldrs integration | tldrs becomes the default token-efficient "eyes" of the system. Every skill/agent that reads code routes through tldrs. Code analysis feeds into analytics. Clavain as flagship demo of tight tldrs integration, with generalizable patterns extracted into inter-* modules. |
| P3 | Adaptive model routing | Dynamically route subagent tasks to the cheapest model that can handle them based on task complexity signals. Token efficiency taken to its logical conclusion. |
| P4 | Cross-project learning | Knowledge compounding across projects. Patterns learned in project A inform project B. |
| P5 | Automated user testing | Beyond smoke tests; simulate user journeys with TUI/browser automation and report UX issues. |

## Research Areas of Interest

### 1. Optimal Human-in-the-Loop Frequency
How much human attention per agent sprint produces the best outcomes? Too little leads to slop. Too much creates a bottleneck. Where is the sweet spot and how does it vary by task type, domain, and project maturity?

### 2. Multi-Model Composition Theory
When should you use Claude vs. Codex vs. GPT-5.2? Is there a principled framework for model selection beyond "try it and see"? Can you predict which model will perform best on a task category based on characteristics of the task?

### 3. Knowledge Compounding Dynamics
Does cross-project learning actually improve outcomes, or does it introduce noise? How do you prune stale learnings? What is the half-life of a documented insight before it becomes misleading? How do you measure the ROI of knowledge compounding?

### 4. Token Efficiency Frontiers
What is the theoretical minimum token cost for reliable multi-agent review? How close can you get with orchestration optimization vs. waiting for model improvements? tldrs is the primary research vehicle here, with Clavain as the integration testbed.

### 5. Emergent Multi-Agent Behavior
When you compose 7+ specialized agents, unexpected interactions emerge. How do you predict, detect, and harness (or prevent) emergent behavior in agent constellations? What are the failure modes of multi-agent systems that don't appear in single-agent testing?

### 6. Skill and Discipline Transfer
Can disciplines codified for one domain (e.g., TDD for code) transfer to non-code domains (e.g., TDD for product specs, TDD for design docs)? What is the right abstraction layer that makes engineering disciplines portable across domains?

### 7. Agent Measurement (via Ashpool + tldrs)
How do you build calibrated confidence in different agents for different task types? What metrics predict whether an agent's output will need human override? Can you create feedback loops where measurement data automatically improves agent selection and routing?

### 8. Multi-Agent Failure Taxonomy & Hallucination Cascades
When one agent hallucinates and another builds on that hallucination, errors compound exponentially (the "17x error trap"). How do you detect and prevent hallucination cascades in multi-agent pipelines? What are the failure modes specific to multi-agent systems that don't appear in single-agent testing? Research shows reflection mechanisms (like Clavain's fd-* review agents) improve benign-case performance but can fail catastrophically under adversarial conditions, with 20% increased attack success vs. base agents.

Sources: [Bag of Agents 17x Error Trap](https://towardsdatascience.com/why-your-multi-agent-system-is-failing-escaping-the-17x-error-trap-of-the-bag-of-agents/), [Multi-Agent Hallucination Coordination](https://galileo.ai/blog/multi-agent-coordination-failure-creates-hallucinations), [Adversarial Robustness of Multimodal LM Agents (ICLR 2025)](https://proceedings.iclr.cc/paper_files/paper/2025/file/460a1d8eac34125dad453b28d6d64446-Paper-Conference.pdf)

### 9. Agent Definition Language (ADL) Discipline Extensions
Next Moca released ADL (Feb 2026) as "OpenAPI for agents"; a declarative spec for what an agent is, what tools it can call, what data it can touch. Clavain could extend ADL with discipline metadata: instruction adherence scores, autonomy bounds, measurement criteria, review requirements. This would make Clavain agents formally specifiable, auditable, and governance-compliant.

Sources: [ADL - InfoQ](https://www.infoq.com/news/2026/02/agent-definition-language/), [Declarative Language for LLM Agent Workflows - arXiv](https://arxiv.org/html/2512.19769)

### 10. Bias-Aware Product Decision Framework
LLM judges exhibit 40-57% systematic bias rates across 8 categories: position bias, verbosity bias, authority bias, anchoring, cognitive biases (omission, framing, status quo). Clavain's brainstorm/strategy phases use LLM judgment for product decisions (prioritization, scope, strategy) but have no bias mitigation. Research opportunity: review agents that explicitly test for bias categories and flag high-risk product decisions for human escalation.

Sources: [LLM-as-a-Judge Survey (ACL 2025)](https://arxiv.org/abs/2411.15594), [Quantifying Biases in LLM-as-a-Judge](https://openreview.net/forum?id=3GTtZFiajM), [Amplified Cognitive Biases in LLMs (PNAS)](https://www.pnas.org/doi/10.1073/pnas.2412015122)

### 11. Plan-Aware Context Compression (tldrs Integration)
Rather than generic context pruning, compress context based on the agent's plan. If the agent is reviewing security, compress away performance-related context. PAACE (Plan-Aware Automated Context Engineering) and Cluster-Based Adaptive Retrieval achieve 40-60% token reduction with preserved relevance. Direct integration point for tldrs: instead of giving all agents the same context, give each domain-specific agent domain-specific context.

Sources: [PAACE - arXiv](https://arxiv.org/html/2512.16970), [Cluster-Based Adaptive Retrieval - arXiv](https://arxiv.org/html/2511.14769), [Google ADK Context Management](https://developers.googleblog.com/architecting-efficient-context-aware-multi-agent-framework-for-production/)

### 12. MCP-Native Companion Communication
File-based sideband (`/tmp/clavain-*.json`) works but doesn't align with where the industry is going. MCP (97M SDK downloads, 5800+ servers) and A2A (50+ launch partners including Salesforce, PayPal, Atlassian) are becoming the standard. Migrating inter-* communication to MCP servers would future-proof the architecture, enable interoperability with non-Clavain tools, and support dynamic capability discovery. Complementary roles: MCP for vertical integration (agent to tools), A2A for horizontal integration (agent to agent).

Sources: [MCP vs A2A Protocols 2026](https://onereach.ai/blog/guide-choosing-mcp-vs-a2a-protocols/), [A2A Protocol](https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/), [Open Protocols for Agent Interoperability - AWS](https://aws.amazon.com/blogs/opensource/open-protocols-for-agent-interoperability-part-1-inter-agent-communication-on-mcp/)

### 13. Product-Native Agent Orchestration
Generic agent frameworks (LangGraph, CrewAI, AutoGen) handle workflow sequencing but don't model product-specific workflows. Nobody models the full product lifecycle (discovery, strategy, planning, execution, review, ship) as a first-class concept with documented failure modes, cross-phase learning, or product-specific risk modeling. Clavain's lfg pipeline already does this. 72% of enterprise AI projects now use multi-agent architectures (up from 23% in 2024), but none are product-native. This is a genuine whitespace opportunity.

Sources: [Multi-Agent Orchestration Enterprise Strategy 2025-2026](https://www.onabout.ai/p/mastering-multi-agent-orchestration-architectures-patterns-roi-benchmarks-for-2025-2026), [Deloitte AI Agent Orchestration](https://www.deloitte.com/us/en/insights/industry/technology/technology-media-and-telecom-predictions/2026/ai-agent-orchestration.html), [Agentic Workflow Architectures 2026](https://www.stack-ai.com/blog/the-2026-guide-to-agentic-workflow-architectures)

### 14. Guardian Agent Patterns
Agents supervising other agents for reliability. Formalize guardian agent design: bidirectional supervision (agent reviews human work, human reviews agent review), instruction adherence monitoring, autonomy bounds enforcement. Clavain's quality-gates command already does this informally; making it formal and quantified would be a discipline contribution. Singapore IMDA and WEF governance frameworks (2025-2026) are converging on instruction adherence scoring as a key metric.

Sources: [Guardian Agent Solutions 2026](https://www.wayfound.ai/post/top-10-guardian-agent-solutions-to-evaluate-in-2026), [IMDA AI Governance Framework for Agentic AI](https://www.imda.gov.sg/-/media/imda/files/about/emerging-tech-and-research/artificial-intelligence/mgf-for-agentic-ai.pdf), [WEF AI Agents in Action](https://www.weforum.org/publications/ai-agents-in-action-foundations-for-evaluation-and-governance/)

### 15. Agent Regression Testing / Evals as CI (Oracle)
"Did this workflow silently degrade?" There is no harness to answer: did a prompt change reduce bug-catching rate? Did a new model routing heuristic increase slop escapes? Did tldrs integration reduce defects per token or just tokens? If Clavain is a proving ground, it needs proving-ground-grade evals. Concrete deliverable: a small corpus of real tasks (planning, code review, refactor, docs, bugfix) with expected properties (not exact text), run as CI.

### 16. Transactional Orchestration / Error Recovery (Oracle)
Partial failures are the mundane killer: tool call writes wrong file, two agents make conflicting edits, retry behavior doubles side effects. Need idempotency keys, rollback plans, "two-phase commit" for edits, conflict resolution protocols. Hallucination cascades (#8) are exotic; partial failures are everyday.

### 17. Security Model for Disciplined Tool Access (Oracle)
Secrets handling (API keys, env vars, tokens in logs), prompt injection via repo content/docs/issue templates, data exfiltration boundaries, supply-chain risk from plugins calling MCP servers. If "discipline before automation," then capability boundaries are discipline too, not just review checklists.

### 18. Cognitive Load Budgets / Review UX (Oracle)
Token efficiency ≠ attention efficiency. How do you present multi-agent output so humans can review quickly and confidently? Progressive disclosure: one-sentence verdict, then expandable evidence, then diffs, then raw traces. Fewer review decisions, clearer escalation, less duplicated disagreement across agents. "Time-to-first-signal" as a metric.

### 19. Prompt/Agent Supply Chain Management (Oracle)
Versioning for prompts/skills/agents (not just plugins). Signed or checksummed agent bundles. Change logs with behavior deltas. Compatibility constraints across agents (like lockfiles, but for behaviors). The plugin ecosystem report covers dependency hell for plugins but not for agent definitions themselves.

### 20. Latency Budgets as First-Class Constraints (Oracle)
Token economics are covered; time-to-feedback isn't. "12 agents cheaper than 8" doesn't matter if it's 3x slower and breaks flow. Need "time per gate" and "time-to-first-signal" optimization as a research track. Latency budgets should be as explicit as token budgets.

## Oracle Cross-Review (GPT-5.2 Pro, 2026-02-14)

### Strongest Parts of the Vision
1. **"Discipline before automation" is the right hill to die on.** This is the differentiator vs. agent-framework land.
2. **The proving ground → extract development model is structurally sound.** Use first, generalize second.
3. **"Human attention is the bottleneck" is the correct central framing.** More insightful than "agents replace developers."
4. **Full lifecycle aspiration (not just coding) is genuinely distinctive.** Most agent tools pretend product work is prompt fluff.

### Weakest Parts / Tensions Identified
1. **Identity trying to be three things at once.** Personal rig, community reference, and research artifact can work, but only if inner-circle outcomes are explicitly prioritized first. Others are byproducts.
2. **"Not a framework" conflicts with "becoming a composable standard."** That's framework behavior with opinions. Messaging is muddy.
3. **Token efficiency risks becoming a vanity metric.** Without anchoring to outcomes (defects caught per token, not just cost reduction), you'll optimize the wrong thing.
4. **"Refinement > production" is under-instrumented.** You have the slogan; you don't yet have the system design that makes refinement cheap and delightful.

### Contradictions / Tensions in the Roadmap
1. **Structure before truth.** Top roadmap items are plugin extractions (meta-work). If you extract before you have measurement, you calcify wrong interfaces. Roadmap should put analytics alongside or before extraction.
2. **Composition > integration vs. Clavain-first tight coupling.** Reasonable, but companions will keep inheriting hidden coupling until extraction is informed by data.
3. **More agents can increase attention burn.** Scaling agents without topology discipline and output compression means more noise and more review fatigue. Contradicts "human attention is the bottleneck."
4. **Autonomy before observability.** Adaptive routing and cross-project learning are automation multipliers. Doing them before discipline telemetry creates an un-debuggable system.
5. **"Multi-AI > single-vendor" vs. "Claude Code native."** Not inherently contradictory (dispatch to other models while Claude Code-native), but messaging is muddy.

### Proposed Principle Additions
- **Principle 8: Observability is a feature, not a bolt-on.** Every agent action emits traceable events: inputs, outputs, cost, latency, decision rationale, downstream outcomes. If it can't be traced, it can't be trusted.
- **Principle 9: Contracts > cleverness.** Prefer typed interfaces, schemas, manifests, and declarative specs (ADL-style) over prompt sorcery. Composition only works when boundaries are explicit.
- **Modify Principle 3:** From "token efficiency enables scale" to **"outcome efficiency enables scale."** Token efficiency is a component. The goal metric is defects caught per token, merge-ready change per dollar.

### Proposed Core Conviction Sharpening
Oracle proposed a more falsifiable version: "Multi-agent engineering only works when it is measurable, reproducible, and reviewable. The point isn't to remove humans; it's to convert human attention into maximum correctness-per-minute with disciplined gates, explicit contracts, and audited traces."

### Research Areas Oracle Would Deprioritize
- **Speculative decoding** — can't control inference stack from a plugin
- **Vision-centric token compression** — overkill for code-centric workflows
- **Theoretical minimum token cost** — replace with empirical cost-quality curves
- **Deep capability negotiation formalism** — manifests + capability maps are enough
- **"Intuition-guided opportunity detection"** — unfalsifiable, easy to fool yourself
- **Full marketplace/recommendation engine** — not where Clavain wins

### Oracle's #1 Priority: Outcome-Based Agent Analytics (v1 Deliverable)
1. **Unified trace/event log** — per-agent (tokens, latency, model, context size, tool calls), per-gate (pass/fail + reasons), per-human-touch (overrides, time-to-decision)
2. **5 Clavain Discipline KPIs** — defect escape rate, human override rate by agent/domain, cost per landed change, time-to-first-signal, redundant work ratio
3. **Measured feedback loop** — agents with low precision get smaller scope; domains with high defect escapes get stricter gates; expensive agents invoked only if early screeners detect risk
4. **One empirical experiment** — run same tasks with 2/4/6/8 agents, plot quality vs. cost vs. time vs. attention, derive 2-3 topology templates to standardize

> "Make the discipline measurable and reproducible before you scale the constellation. Build the truth engine, then let everything else compete for survival under data."

## Research Documents

Full research reports saved by flux-research agents (2026-02-14):
- `docs/research/research-ai-agent-orchestration-patterns.md` — failure modes, coordination tax, ADL, hallucination cascades, adversarial robustness, governance metrics
- `docs/research/research-token-efficiency-and-context-optimization.md` — context compression, code representation, adaptive strategies, cost modeling, speculative decoding
- `docs/research/research-product-management-ai-workflows.md` — AI-assisted discovery, PRD generation, prioritization, LLM judgment bias, design critique, product sense, A/B testing
- `docs/research/research-plugin-ecosystem-and-composability.md` — MCP/A2A protocols, plugin manifests, modpack patterns, dependency management, marketplace evolution

## Key Decisions Made

1. **Core identity:** Highly opinionated flagship, not a neutral framework
2. **Audience:** Concentric circles (self, community, field) — inner circle explicitly prioritized first
3. **Development model:** Build tightly in Clavain first, extract when stable
4. **Lifecycle scope:** Full product lifecycle (brainstorm to ship), expanding toward richer product research
5. **All seven principles confirmed** as operating philosophy
6. **Non-goals:** Not a framework, not for non-builders, Claude Code native
7. **Companion name:** "intershift" (not "intercodex") for cross-AI dispatch
8. **tldrs integration:** Deep, not optional; Clavain is the flagship demo of tldrs
9. **Agent analytics (P1 capability):** Most urgently needed new capability — Oracle strongly agrees, proposes specific v1 deliverable (trace log + 5 KPIs + feedback loop + topology experiment)
10. **Ashpool:** Should contribute to agent measurement research
11. **Oracle review (2026-02-14):** Proposed 2 new principles (observability, contracts > cleverness), 6 new research areas (#15-20), identified 5 tensions to resolve, recommended deprioritizing 6 research threads, and argued analytics must come before or alongside extraction (not after)

## Open Questions

1. What does the Codex port of Clavain look like as it grows? Is it a first-class citizen or a read-only mirror?
2. How should Ashpool's measurement capabilities integrate with Clavain's analytics roadmap?
3. Should interarch merge with intercraft, or stay standalone?
4. What is the right boundary between "Clavain core" and "companion" as the system evolves?
5. How do you version/release a constellation of 7+ tightly-related plugins without coordination hell?
6. (Oracle) Should the roadmap reorder to put analytics before/alongside extraction, rather than after?
7. (Oracle) Should Principle 3 change from "token efficiency" to "outcome efficiency"? Or keep both as separate principles?
8. (Oracle) Should the core conviction be sharpened to include "measurable, reproducible, and reviewable"?
9. (Oracle) How do you resolve "not a framework" vs. "composable standard" messaging tension?
10. (Oracle) What is the right topology for multi-agent review? Need empirical data (2/4/6/8 agent experiment).

## Next Steps

**Priority 1 (Oracle-endorsed): Build the truth engine**
- Create bead for outcome-based agent analytics v1 (trace log + 5 KPIs + feedback loop)
- Design unified trace/event schema (per-agent, per-gate, per-human-touch)
- Run topology experiment: same tasks with 2/4/6/8 agents, measure quality vs. cost vs. time
- Research Ashpool's current capabilities for measurement integration

**Priority 2: Formalize the vision**
- Resolve open questions #6-10 (Oracle tensions)
- Decide on principle additions (observability, contracts > cleverness, outcome efficiency)
- Formalize this brainstorm into a standing vision document (e.g., `docs/vision.md`)

**Priority 3: Structural extractions (analytics-informed)**
- `/clavain:write-plan` for extraction beads (Clavain-2ley, Clavain-6ikc, Clavain-sdqv, Clavain-eff5)
- Consider reordering: analytics alongside intercraft extraction (zero-coupling makes it safe)

**Priority 4: Research beads**
- Create beads for high-priority new research areas (#8 hallucination cascades, #10 bias-aware decisions, #11 plan-aware compression, #13 product-native orchestration, #15 agent evals as CI, #18 cognitive load budgets)
- Evaluate ADL spec (#9) for Clavain discipline extensions
- Prototype MCP-native companion communication (#12) starting with interphase

**Deprioritized (per Oracle):**
- Speculative decoding, vision-centric compression, theoretical token minima, deep capability negotiation formalism, intuition-guided opportunity detection, marketplace/recommendation engine
