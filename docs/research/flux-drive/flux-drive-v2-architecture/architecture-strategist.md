---
agent: architecture-strategist
tier: adaptive
issues:
  - id: P0-1
    severity: P0
    section: "5-Core-Agent Merge"
    title: "Safety & Correctness agent merges four unrelated domains into one prompt, risking shallow coverage where v1 had depth"
  - id: P0-2
    severity: P0
    section: "Phase 5: Compound"
    title: "Phase 5 Compound agent is tightly coupled to the output format of Phases 3-4, creating a fragile contract chain"
  - id: P1-1
    severity: P1
    section: "Ad-hoc Agent Lifecycle"
    title: "Graduation path from project-local to Clavain-global crosses repository boundaries without a defined sync mechanism"
  - id: P1-2
    severity: P1
    section: "Two-Tier Knowledge Architecture"
    title: "Compounding agents can write to both tiers simultaneously, creating potential for circular reinforcement of incorrect findings"
  - id: P1-3
    severity: P1
    section: "Knowledge Layer + qmd"
    title: "qmd retrieval depends on document content at query time — agents reviewing the same file get the same knowledge regardless of their focus area"
  - id: P1-4
    severity: P1
    section: "Immediate Compounding Agent"
    title: "The Immediate Compounding Agent creates a Phase 3.5 that extends the critical path without a skip/timeout mechanism"
  - id: P2-1
    severity: P2
    section: "Triage Changes"
    title: "Ad-hoc agent generation during triage introduces unbounded latency in what should be a fast scoring phase"
  - id: P2-2
    severity: P2
    section: "Knowledge Format"
    title: "Knowledge entry schema lacks a version field, making schema evolution painful across the two tiers"
improvements:
  - id: IMP-1
    title: "Split Safety & Correctness into two agents (Safety and Correctness) to preserve v1 depth"
    section: "5-Core-Agent Merge"
  - id: IMP-2
    title: "Define a minimal contract interface between Phase 3 output and Phase 5 input, decoupled from synthesis prose format"
    section: "Phase 5: Compound"
  - id: IMP-3
    title: "Make Phase 5 Compound fully optional with a timeout and user consent gate"
    section: "Phase 5: Compound"
  - id: IMP-4
    title: "Add a version field to knowledge entry schema from day one"
    section: "Knowledge Format"
  - id: IMP-5
    title: "Separate qmd queries by agent focus area rather than relying solely on document content"
    section: "Knowledge Layer + qmd"
verdict: needs-changes
---

## Architecture Assessment

### Components Affected

This plan touches the following Clavain components and boundaries:

1. **Agent roster** (`/root/projects/Clavain/agents/review/`) — 19 existing agents collapsed to 5 core agents plus ad-hoc generation. This is the largest structural change in the plan.
2. **Flux-drive skill** (`/root/projects/Clavain/skills/flux-drive/SKILL.md` and `phases/`) — All four phase files must be rewritten. A new Phase 5 file is added.
3. **Knowledge storage** — Two new directory trees: `.claude/flux-drive/knowledge/` (project-local) and `config/flux-drive/knowledge/` (Clavain-global). The latter is a new `config/` convention that currently only holds `config/CLAUDE.md` for the behavioral layer.
4. **qmd MCP server** — Promoted from optional triage helper (Step 1.0) to the primary retrieval engine for all knowledge injection.
5. **Output directory** (`docs/research/flux-drive/`) — Consumed by the new Async Deep-Pass Agent, which reads across run directories.
6. **Routing table** (`/root/projects/Clavain/skills/using-clavain/SKILL.md`) — The agent roster referenced in Layer 1/Layer 3 tables must shrink from 19 named agents to 5 core + "ad-hoc."

### Boundary Compliance

The plan mostly respects Clavain's established boundaries:

- **Skills remain orchestration, agents remain execution.** Phase 5 is implemented as an agent, not skill logic — consistent with how Phases 2-4 dispatch agents.
- **`config/` directory convention.** The behavioral layer plan already established `config/` for cross-project Clavain config (`config/CLAUDE.md`). Adding `config/flux-drive/knowledge/` is consistent.
- **Plugin manifest unchanged.** The plan does not require changes to `/root/projects/Clavain/.claude-plugin/plugin.json` or the MCP server list, since qmd is already registered.
- **Output directory convention preserved.** Research output stays under `docs/research/flux-drive/`.

However, there are boundary violations:

- **Ad-hoc agent files written to `.claude/flux-drive/agents/` in the target project.** This is a new convention that overlaps with the existing `.claude/agents/fd-*.md` convention documented in the v1 flux-drive SKILL.md. The plan says it replaces static project agents but doesn't address migration — what happens to existing `fd-*.md` files?
- **The Deep-Pass Agent reads across run output directories** (`docs/research/flux-drive/`), creating a coupling between the output format of individual runs and a new cross-run consumer. Any change to run output format now has two consumers to satisfy.

### Coupling Analysis

The plan introduces three new coupling relationships that do not exist in v1:

1. **Phase 5 --> Phase 3-4 output format.** The Immediate Compounding Agent reads "the synthesis summary + cross-AI delta." This means the synthesis output (currently specified in `phases/synthesize.md`, Step 3.4) becomes a contract, not just a user-facing report.

2. **Knowledge layer --> qmd availability.** In v1, qmd was optional enrichment (Step 1.0: "If qmd MCP tools are available"). In v2, qmd is the retrieval engine for Phase 2 knowledge injection. If qmd is unavailable, knowledge injection fails silently and agents run without context — which is the v1 behavior, but now feels like degraded mode rather than normal mode.

3. **Deep-Pass Agent --> historical run outputs.** The async agent reads across `docs/research/flux-drive/` directories from multiple past runs. This creates a temporal coupling: old run outputs must remain stable and parseable for future deep-pass analysis.

---

## Specific Issues

### P0-1: Safety & Correctness Agent Merges Four Unrelated Domains

**Location:** "Agent Roster (5 Core + Oracle + Ad-hoc)" table

**Problem:** The "Safety & Correctness" agent merges security-sentinel, data-integrity-reviewer, concurrency-reviewer, and deployment-verification-agent. These four domains have almost no overlap:

- **Security** requires threat modeling, input validation analysis, credential handling review — a distinct analytical frame.
- **Data integrity** requires transaction analysis, migration safety, schema evolution — a database-oriented frame.
- **Concurrency** requires race condition detection, goroutine lifecycle analysis, channel deadlock reasoning — a runtime behavior frame.
- **Deployment** requires pre/post-deploy checklists, rollback planning, migration sequencing — an operations frame.

The existing agent files confirm this separation. Compare `/root/projects/Clavain/agents/review/security-sentinel.md` (focused on trust boundaries, attack surface, credential handling) with `/root/projects/Clavain/agents/review/concurrency-reviewer.md` (focused on race conditions, async bugs, goroutine lifecycle). These are fundamentally different analytical modes. A single agent prompt covering all four will either be too long (diluting focus) or too short (losing the specialized heuristics each v1 agent carried).

The plan acknowledges this risk in Open Question 5 ("Will 5 merged agents actually perform as well as 19 specialists?") and offers knowledge injection as mitigation. But knowledge injection adds domain facts, not analytical discipline. Knowing that "auth middleware swallows context cancellation errors" does not teach an agent how to reason about race conditions.

**Suggestion:** Split into two agents: "Safety" (security + deployment — both concern trust and operational risk) and "Correctness" (data integrity + concurrency — both concern state consistency). This gives 6 core agents, still well within the reduced cap of 6, while preserving analytical depth where it matters most. The Architecture & Design and Quality & Style merges are more defensible because their constituent domains share analytical frames.

### P0-2: Phase 5 Compound Is Tightly Coupled to Phases 3-4 Output Format

**Location:** "Phase Structure (Updated)" table and "Compounding System" section

**Problem:** The Immediate Compounding Agent "reads the synthesis summary + cross-AI delta (not raw agent outputs)." This makes Phase 5 a direct consumer of Phase 3's prose output and Phase 4's classification output. But Phase 3 output is currently specified as a user-facing document (Step 3.4 in `/root/projects/Clavain/skills/flux-drive/phases/synthesize.md`). It was never designed as a machine-consumable contract.

This creates a fragile three-phase chain: Phase 3 output format --> Phase 4 cross-AI classification --> Phase 5 compounding input. Any change to how Phase 3 presents findings to the user (e.g., switching from inline annotations to a summary-only format, as suggested by the v1 self-review at P1 priority) breaks Phase 5.

The v1 self-review (`/root/projects/Clavain/docs/research/flux-drive/flux-drive-self-review/summary.md`) already identified the YAML frontmatter contract as "the system's Achilles heel" (P0, 3/5 agents). Adding another downstream consumer of output format doubles the exposure.

**Suggestion:** Define a minimal structured interface between Phase 3 and Phase 5. The Compounding Agent should read the individual agent output files in `{OUTPUT_DIR}/` (which have YAML frontmatter) directly, not the synthesized prose. This decouples compounding from synthesis presentation format. Phase 5 would consume the same structured data Phase 3 already validates in Step 3.1, adding no new format contracts. The cross-AI delta can be passed as a structured addendum (Oracle blind spots + conflicts list) rather than relying on Phase 4's prose classification.

### P1-1: Ad-hoc Agent Graduation Crosses Repository Boundaries

**Location:** "Ad-hoc Agents" description and "Clavain-Global Knowledge" section

**Problem:** The ad-hoc agent lifecycle is: generate in triage --> save to `.claude/flux-drive/agents/` in project repo --> reuse in future runs --> graduate to `config/flux-drive/` in Clavain repo when "used across multiple projects."

The graduation step moves a file from a target project's repository to the Clavain plugin repository. The plan does not specify how this happens mechanically. When flux-drive runs on Project A and observes an ad-hoc agent that was also used in Project B, who creates the file in the Clavain repo? The flux-drive skill runs in the context of the target project. It would need write access to the Clavain plugin repo, which is a different directory tree (possibly a different machine for users who install Clavain via marketplace, not local checkout).

This is the same class of problem the behavioral layer plan addressed for `config/CLAUDE.md`: distinguishing between content that lives in the plugin repo vs content that lives in the target project. The behavioral layer solved it by using agent-rig as the install mechanism. Ad-hoc agent graduation has no equivalent transport.

**Suggestion:** Define graduation as an explicit command (`/clavain:graduate-agent`) rather than automatic promotion. The command would present the user with ad-hoc agents that meet criteria and, upon approval, create a PR against the Clavain repo (or use agent-mail to propose it). This keeps the lifecycle well-bounded: project-local agents are automatic, cross-project promotion is human-gated. It also avoids flux-drive needing write access to the Clavain repo at runtime.

### P1-2: Circular Reinforcement Risk in Two-Tier Knowledge

**Location:** "Compounding System" section, specifically "Extracts findings into knowledge entries (both project-local and global)"

**Problem:** The Immediate Compounding Agent writes to both project-local and Clavain-global knowledge tiers. In a subsequent run, the Launch phase injects knowledge from both tiers via qmd. If a finding was incorrectly promoted to global, every future flux-drive run on every project receives it as context. Agents may "re-confirm" the finding (it was injected into their context, so they naturally agree with it), which increases its `lastConfirmed` date and prevents decay.

This is a positive feedback loop: write finding --> inject finding --> agent confirms finding --> update lastConfirmed --> finding never decays. The Async Deep-Pass Agent performs decay ("archives findings not re-confirmed across recent reviews"), but if confirmation is self-reinforcing, the decay mechanism is defeated.

**Suggestion:** Add a `source` provenance tag to knowledge entries tracking whether confirmation came from an independent agent analysis or from knowledge-primed context. Only independent confirmations (where the finding was NOT in the agent's injected knowledge) should update `lastConfirmed`. This is the difference between "the agent discovered this independently" and "the agent agreed with something we told it." The knowledge format already has a `source` field; extend it to distinguish `source: independent` from `source: primed`.

### P1-3: qmd Retrieval Does Not Differentiate Agent Focus Areas

**Location:** "Retrieval via qmd" section

**Problem:** The plan states "qmd semantic search retrieves relevant knowledge entries based on the document being reviewed and the agent's focus area." But qmd is a semantic search engine over file content — it matches queries against indexed documents. If the query is constructed from the document being reviewed, all agents reviewing the same document get approximately the same knowledge entries. The "agent's focus area" would need to be part of the query, but the plan does not specify how.

Looking at qmd's MCP interface (registered in `/root/projects/Clavain/.claude-plugin/plugin.json` as `qmd mcp`), it supports search, vsearch, and query operations. A search query like "security vulnerabilities in auth middleware" would return different results than "concurrency issues in auth middleware." But who constructs these differentiated queries? If the orchestrator constructs them, it needs to map agent focus areas to query terms. If the agents construct their own queries, they run qmd themselves during Phase 2 execution — but the plan says knowledge is "prepended" at launch time, implying the orchestrator does it.

**Suggestion:** The orchestrator should construct agent-specific queries by combining the document summary (from Phase 1 profile) with the agent's domain keywords. Define a `queryTemplate` field in the core agent definitions, e.g., Architecture & Design queries with "boundaries coupling dependencies {document_summary}" while Safety queries with "threats vulnerabilities credentials {document_summary}". This makes differentiation explicit rather than hoping semantic search disambiguates.

### P1-4: Immediate Compounding Agent Extends Critical Path Without Skip Mechanism

**Location:** "Immediate Compounding Agent (runs after each synthesis)"

**Problem:** The v1 flux-drive pipeline is: Triage --> Launch --> Synthesize --> Cross-AI (optional). Phase 5 adds a mandatory step after synthesis. The Immediate Compounding Agent "reads the synthesis summary + cross-AI delta" and "decides what's worth remembering permanently." This is useful for learning, but it adds latency to every flux-drive run.

The user experience concern from the v1 self-review was already "3-5 minute silent wait is unacceptable UX" (P0). Adding Phase 5 extends this. Unlike Phase 4 (which is skippable when Oracle is absent), Phase 5 has no skip condition — it always runs.

The plan also does not specify what happens if the Compounding Agent fails or times out. A failure in Phase 5 should not invalidate the synthesis from Phase 3, which is the primary deliverable.

**Suggestion:** Make Phase 5 fire-and-forget: dispatch the Compounding Agent in background after presenting the Phase 3/4 results to the user. The user gets their review immediately; knowledge extraction happens asynchronously. If it fails, the review is still complete — only the learning is lost. This also means Phase 5 does not need to block on Phase 4 completion; it can wait for both independently.

### P2-1: Ad-hoc Agent Generation During Triage Adds Unbounded Latency

**Location:** "Triage Changes" section

**Problem:** Triage is described as: "Scores 5 core agents... Checks saved ad-hoc agents... If unmatched domain detected, generates new ad-hoc agent prompt on the fly." Generating a new agent prompt is a generative task that takes non-trivial time and tokens. Triage in v1 is a fast scoring step (the orchestrator does it inline, no subagents). Adding prompt generation makes triage latency unpredictable.

**Suggestion:** Defer ad-hoc agent generation to Phase 2. Triage detects the unmatched domain and flags it. Phase 2 generates the prompt and launches the ad-hoc agent alongside the core agents. This keeps triage fast and predictable.

### P2-2: Knowledge Entry Schema Lacks Version Field

**Location:** "Knowledge Format" section

**Problem:** The knowledge entry YAML frontmatter has `domain`, `source`, `confidence`, `convergence`, `origin`, `lastConfirmed` — but no `schemaVersion`. Since these entries will persist across many flux-drive runs and potentially graduate between tiers, schema evolution is inevitable. Without a version field, the compounding agents must handle all historical formats without a discriminator.

**Suggestion:** Add `schemaVersion: 1` to the knowledge format from day one. This costs nothing now and prevents painful migrations later.

---

## Summary

**Overall architecture fit:** Needs changes.

The plan's core thesis — fewer core agents plus dynamic generation plus compounding — is architecturally sound. Reducing from 19 to a small core set addresses real maintenance and triage complexity problems. The two-tier knowledge architecture is well-motivated. Using qmd as the retrieval engine is pragmatic (zero new infrastructure, already in the stack).

However, the plan has structural issues that need resolution before implementation:

### Top 3 Changes

1. **Split "Safety & Correctness" into two agents.** The four-domain merge is the highest-risk decision in the plan. Security analysis and concurrency analysis are fundamentally different reasoning modes. A 6-core-agent roster (splitting Safety from Correctness) preserves depth without compromising the simplification goal. The cap of 6 already accommodates this.

2. **Decouple Phase 5 from Phase 3 prose output.** The Compounding Agent should read structured agent output files (YAML frontmatter) directly, not the synthesized summary. This prevents the synthesis presentation format from becoming a contract with two consumers (user and compounding system). Run Phase 5 in background after presenting results to the user to avoid extending the critical path.

3. **Add provenance tracking to knowledge confirmations.** Without distinguishing "agent discovered this independently" from "agent agreed with injected context," the compounding system risks positive feedback loops where incorrect findings self-reinforce. This is the plan's most subtle architectural risk and the hardest to fix retroactively.
