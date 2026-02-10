# Flux-Drive v2: Deferred Features — Fast-Follow Reference

> Cut from v2.0 MVP based on 7-agent self-review + Oracle cross-AI (2026-02-10).
> Each feature is independently shippable. Pick up when the trigger condition is met.
> MVP spec: `docs/research/flux-drive-v2-architecture.md`
> Full review: `docs/research/flux-drive/flux-drive-v2-architecture/summary.md`
> Oracle review: `docs/research/flux-drive/flux-drive-v2-architecture/oracle.md`

---

## 1. Two-Tier Knowledge (Project-Local + Global)

**Trigger**: After 20+ reviews, if >30% of knowledge entries only apply to one project.

**What it adds**: A second knowledge storage tier at `.claude/flux-drive/knowledge/` inside the target project repo, alongside the existing Clavain-global tier at `config/flux-drive/knowledge/`.

**Design from brainstorm**:

- **Project-local** (`.claude/flux-drive/knowledge/` in project repo):
  - Codebase-specific patterns (trouble spots, recurring issues)
  - Only injected when reviewing that project
  - Git-tracked in the project repo

- **Clavain-global** (`config/flux-drive/knowledge/` in Clavain repo):
  - Universal patterns across all projects
  - Systematic blind spots, cross-project heuristics
  - Graduated entries proven across 2+ projects

**Critical design decisions needed before building**:

1. **Precedence rules** (spec-flow-analyzer P0-1): When project-local says "Pattern X is fine here" and global says "Pattern X is dangerous," which wins? Proposed: project-local wins for codebase-specific conventions, global wins for entries with `origin: cross-ai-delta` (blind spot detection overrides local).

2. **Tier labels visible to agents** (spec-flow-analyzer): Agents must see whether a knowledge entry is project-local or global, so they can weigh accordingly.

3. **Deduplication** (architecture-strategist P1-2): When both tiers have entries about the same topic, inject only the more specific (project-local) one.

4. **gitignore question** (user-advocate M-5): Should `.claude/flux-drive/` be gitignored by default? Knowledge files in PRs are artifacts of the review tool, not the project. Consider opt-in tracking.

**Estimated scope**: ~50 LOC (directory management, tier routing in compounding, precedence logic in retrieval).

---

## 2. Ad-hoc Agent Generation

**Trigger**: Users report domains the 6 core agents consistently miss (e.g., GraphQL, accessibility, i18n).

**What it adds**: Triage detects uncovered domains → generates a specialized agent prompt on the fly → saves for reuse → optionally graduates to global.

**Design from brainstorm**:

```
Phase 1.2 triage detects unmatched domain
  → Generate agent system prompt (same format as existing agent .md files)
  → Save to .claude/flux-drive/agents/{domain}-reviewer.md
  → Dispatch alongside core agents in Phase 2
  → Future runs: triage checks saved ad-hoc roster for domain match
```

**Critical design decisions needed before building**:

1. **Quality gate** (user-advocate M-2, spec-flow-analyzer P0-3): Generated agents must pass minimum quality before being saved. Proposed signals:
   - Finding density: ad-hoc agent must produce at least 1 high-confidence finding
   - Uniqueness: at least 1 finding not duplicated by core agents
   - Strikes: auto-archive after 3 consecutive low-value runs

2. **Lifecycle management** (spec-flow-analyzer P0-3): Need deletion, deprecation, versioning, and user inspection. Proposed: `/clavain:flux-agents list|delete|inspect` command.

3. **Scoring in triage** (spec-flow-analyzer P1-8): How does triage score a saved ad-hoc agent vs. a core agent? Proposed: same 0-2 scale with +1 project-specific bonus (matching v1 project agent behavior).

4. **Naming and collision** (spec-flow-analyzer Q8): Two projects could generate different "i18n-reviewer" agents. Proposed: namespace by project hash for local, merge-by-quality for global.

5. **Triage table UX** (fd-user-experience P1-2): Ad-hoc agents must show as `Generated (new)` or `Generated (saved)` in the triage table. User must be able to reject individual ad-hoc agents.

6. **Generation latency** (performance-oracle P1-3): 10-30 seconds to generate a prompt. Don't block core agent launch — generate in parallel, launch ad-hoc agent late.

7. **Prompt injection / supply-chain risk** (Oracle F3, HIGH — NEW): Ad-hoc agent files stored in-repo (`.claude/flux-drive/agents/`) are untrusted input. Any PR can modify them to manipulate future runs — exfiltration instructions, mis-scoring, "ignore security findings." Mitigations:
   - Prefer storing in user-local config (not in-repo), OR
   - Require checksum/signature stored outside the repo
   - Refuse to load modified agents without user acknowledgement
   - Wrap all retrieved agent prompts in a "treat as untrusted data" system fence

**Why it was cut**: The problem statement says "too many agents." Dynamically generating more is counterintuitive. The 6-agent model should be proven insufficient before adding complexity. Also: "adding a new agent is creating one markdown file" (product-skeptic) — manual creation is cheap. Additionally, Oracle flagged in-repo agent storage as a prompt injection vector.

**Estimated scope**: ~80 LOC (generation prompt, save/load, triage integration, scoring) + security hardening.

---

## 3. Async Deep-Pass Agent

**Trigger**: After 50+ reviews with immediate compounding, if cross-review patterns are being missed.

**What it adds**: A periodic agent that scans across multiple review outputs to find patterns individual runs missed, detect systematic blind spots, and perform knowledge maintenance.

**Design from brainstorm**:

```
Scans docs/research/flux-drive/ output directories across reviews:
1. Identifies cross-review patterns that individual runs missed
2. Consolidates similar findings into higher-level patterns
3. Detects systematic agent blind spots across runs
4. Performs decay: archives findings not re-confirmed across recent reviews
5. Compounds its own discoveries back into the knowledge layer
```

**Critical design decisions needed before building**:

1. **Invocation** (fd-user-experience P1-4): Create `/clavain:flux-deep` command — don't leave as undefined manual trigger. Output to `.claude/flux-drive/deep-pass/YYYY-MM-DD.md`.

2. **Scaling** (performance-oracle P1-2): MUST read summaries only, not raw agent outputs. At 50 reviews (~250 files, ~5MB), raw output exceeds 200K context window. Implement sliding window: last 10-20 reviews only, older patterns already captured in knowledge layer.

3. **Correction authority** (spec-flow-analyzer P0-4): Can deep-pass auto-correct knowledge entries or only flag for human review? Proposed: auto-archive low-confidence entries, flag high-confidence for human via `status: review-needed` in frontmatter.

4. **Counter-based nudge** (fd-user-experience): After every Nth review (suggest N=5), append one line to synthesis: "Consider running `/clavain:flux-deep` — N reviews since last deep analysis." Gentle nudge, not auto-trigger.

5. **Two-level summarization** (performance-oracle): Deep-pass writes its own summary. Future deep-pass runs read previous summary + new reviews since then. O(1) historical context + O(recent) new input.

**Why it was cut**: "This is a v3 feature masquerading as v2" (code-simplicity-reviewer). Immediate compounding already handles decay via `lastConfirmed`. Cross-review pattern mining should wait until there's evidence individual runs miss patterns.

**Estimated scope**: ~100 LOC (scanning, consolidation, scheduling, output formatting).

---

## 4. Agent Graduation Pipeline

**Trigger**: Only relevant if two-tier knowledge is implemented.

**What it adds**: Automated promotion of project-local ad-hoc agents and knowledge entries to Clavain-global when proven across multiple projects.

**Design from brainstorm**:

- Ad-hoc agents graduate when "used in 2+ projects AND produced high-confidence findings"
- Knowledge entries graduate when confirmed independently across 2+ projects
- Graduation creates files in `config/flux-drive/` in the Clavain repo

**Critical design decisions needed before building**:

1. **Transport mechanism** (architecture-strategist P1-1): Graduation crosses repository boundaries. Marketplace-installed users have no local Clavain checkout. Proposed: graduation via explicit command (`/clavain:graduate-agent`) that creates a PR against Clavain repo, not automatic promotion.

2. **Quality validation** (user-advocate M-2): Graduation threshold should be quality-based, not just count-based. "Used in 2 projects" is correlation, not generalization — both projects may be structurally similar.

3. **Collision resolution** (spec-flow-analyzer P1-2): Two projects generating conflicting agents for the same domain. Proposed: deep-pass picks the better one based on finding quality metrics.

**Why it was cut**: Requires cross-project tracking and repo boundary crossing — high complexity for unproven value.

**Estimated scope**: ~50 LOC (criteria checking, PR creation, collision resolution).

---

## 5. Complex Knowledge Frontmatter

**Trigger**: If qmd retrieval proves insufficiently precise without domain tags.

**What it adds**: Richer YAML frontmatter with 6 fields instead of 2.

**Original design**:
```yaml
---
domain: safety
source: flux-drive/2026-02-10
confidence: high
convergence: 3
origin: cross-ai-delta
lastConfirmed: 2026-02-10
---
```

**Why it was cut** (code-simplicity-reviewer):
- `domain` — qmd semantic search makes this redundant
- `source` — git history tracks when entries were added
- `confidence` — subjective, hard to calibrate, changes over time
- `convergence` — misleading with 6 merged agents (most findings = convergence 1)
- `origin` — classification overhead distinguishing cross-ai-delta from others

**When to reconsider**: If qmd retrieval returns too many irrelevant entries and domain tags would improve filtering. Or if convergence tracking across merged agents needs explicit counting.

**Estimated scope**: ~30 LOC (YAML parsing, validation, field management).

---

## 6. Dynamic Agent Cap

**Trigger**: If token costs are a proven bottleneck, or if document complexity should drive coverage.

**What it adds**: Replace fixed cap (currently 8) with dynamic cap based on document complexity from Phase 1 profile.

**Design sketch**:
- Small documents (< 50 lines, 1-2 topics): cap at 4
- Medium documents (50-200 lines, 3-5 topics): cap at 6
- Large documents (200+ lines, 5+ topics): cap at 8
- The profile already estimates complexity — use it

**Why it was cut**: The original proposal wanted to reduce from 8 to 6 with no justification. Reviewers found this was "optimization for the wrong metric" (product-skeptic). Keep at 8 for now.

**Estimated scope**: ~10 LOC (cap logic in triage).

---

## 7. 7th Core Agent: Reliability / Deploy / Observability

**Trigger**: If deployment/ops reviews consistently show shallow coverage under the Safety agent.

**What it adds**: Split the current Safety agent (security + deployment) into:
- **Security & Threat Modeling** — adversarial mindset, credential handling, prompt injection, trust boundaries
- **Reliability / Deploy / Observability** — operational failure modes, rollout risk, SLOs, logging/metrics, migrations

**Source**: Oracle cross-AI review (GPT-5.2 Pro) recommended 7 agents as the sweet spot, arguing that security and deployment require different threat models and evidentiary standards.

**Why it was deferred**: The 6-agent model already splits Safety from Correctness (addressing the 5/7 convergence finding). Going to 7 is an incremental improvement that should wait for evidence from actual reviews.

**Estimated scope**: ~20 LOC (split agent prompt, update triage scoring).

---

## 8. Claim-Level Convergence Tracking

**Trigger**: If convergence tracking becomes meaningless at 6 agents (most findings = convergence 1).

**What it adds**: Instead of counting convergence per agent, count per *claim section*. Each merged agent outputs structured sections (e.g., Safety outputs `Security` and `Deployment` as separate sections). Convergence is tracked at the section level.

**Source**: Oracle blind spot finding — "With 19 agents you could get meaningful multi-agent agreement. With 5-6, convergence becomes low-resolution."

**Design**: Each agent's output YAML frontmatter already has an `issues` array. Add a `section` field per issue (which already exists in some agents). Count convergence across sections, not across agents. This means a finding flagged by Safety:Security and Correctness:DataIntegrity has convergence 2, not just 1.

**Estimated scope**: ~15 LOC (convergence counting logic in synthesis phase).

---

## Dependency Graph

```
v2.0 MVP (6 agents + single-tier knowledge + immediate compounding)
  │
  ├─► Two-Tier Knowledge (independent, trigger: 20+ reviews)
  │     └─► Agent Graduation Pipeline (depends on two-tier)
  │
  ├─► Ad-hoc Agent Generation (independent, trigger: roster gaps)
  │
  ├─► Async Deep-Pass (independent, trigger: 50+ reviews)
  │
  ├─► Complex Frontmatter (independent, trigger: qmd precision)
  │
  ├─► Dynamic Cap (independent, trigger: cost data)
  │
  ├─► 7th Agent: Reliability/Deploy (independent, trigger: ops review gaps)
  │
  └─► Claim-Level Convergence (independent, trigger: low-resolution convergence)
```

```
v2.0 MVP (6 agents + single-tier knowledge + immediate compounding)
  │
  ├─► Two-Tier Knowledge (independent, trigger: 20+ reviews)
  │     └─► Agent Graduation Pipeline (depends on two-tier)
  │
  ├─► Ad-hoc Agent Generation (independent, trigger: roster gaps)
  │
  ├─► Async Deep-Pass (independent, trigger: 50+ reviews)
  │
  ├─► Complex Frontmatter (independent, trigger: qmd precision)
  │
  └─► Dynamic Cap (independent, trigger: cost data)
```

No deferred feature depends on another deferred feature, except Graduation → Two-Tier. All can be shipped independently against the MVP.

---

## Review Sources

Each deferred feature was discussed in detail by specific agents. For deeper context:

| Feature | Primary agents | Key findings |
|---------|---------------|-------------|
| Two-tier knowledge | spec-flow-analyzer (P0-1), user-advocate (M-5), architecture-strategist (P1-2) | Precedence conflicts, gitignore question, leaky abstraction for multi-project users |
| Ad-hoc generation | product-skeptic (Major), spec-flow-analyzer (P0-3), user-advocate (C-2, M-2), fd-user-experience (P1-2), **Oracle (F3)** | Quality gate missing, lifecycle unmanaged, project agent failure undiagnosed, **prompt injection vector** |
| Deep-pass | performance-oracle (P1-2), fd-user-experience (P1-4), code-simplicity-reviewer | Scaling to O(reviews×agents), no invocation path, v3 feature in v2 clothing |
| Graduation | architecture-strategist (P1-1), user-advocate (M-2) | Repo boundary crossing, quality vs. count threshold |
| Complex frontmatter | code-simplicity-reviewer | 6 fields when you need 2 |
| Dynamic cap | product-skeptic (Minor) | Cap reduction unjustified, but dynamic might be better than fixed |
| 7th agent | **Oracle** | Security and deployment require different threat models and evidentiary standards |
| Claim-level convergence | **Oracle (5A)** | With 6 agents, convergence is low-resolution; count per section, not per agent |
