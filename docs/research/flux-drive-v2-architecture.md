# Flux-Drive v2: Agent Architecture Redesign

> **Status**: MVP scope validated by 7-agent self-review + Oracle cross-AI (2026-02-10).
> Full review: `docs/research/flux-drive/flux-drive-v2-architecture/summary.md`
> Oracle review: `docs/research/flux-drive/flux-drive-v2-architecture/oracle.md`

## Problem Statement

The current flux-drive architecture has several pain points:

1. **Bloated roster** — 19 plugin agents, many rarely selected, high maintenance burden
2. **Wrong granularity** — 5 separate language reviewers (Go, Python, TypeScript, Shell, Rust) while other agents are too broad
3. **No learning** — each review starts from zero, findings don't compound across runs
4. **Project agents are dead** — optional `fd-*.md` project agents rarely get created by users

## Architecture: 6 Core Agents + Knowledge + Compounding

### Agent Roster (6 Core + Oracle)

Replace 19 specialized agents with 6 core agents that cover the same domains through merging:

| Agent | Merges | Focus |
|-------|--------|-------|
| **Architecture & Design** | architecture-strategist, pattern-recognition, code-simplicity | Boundaries, patterns, coupling, unnecessary complexity |
| **Safety** | security-sentinel, deployment-verification | Threats, credential handling, deploy risk, trust boundaries |
| **Correctness** | data-integrity-reviewer, concurrency-reviewer | Data consistency, race conditions, transaction safety, async bugs |
| **Quality & Style** | fd-code-quality, all 5 language reviewers | Naming, conventions, test approach — auto-detects language from context |
| **User & Product** | fd-user-experience, product-skeptic, user-advocate, spec-flow-analyzer | User flows, value prop, UX friction, missing flows |
| **Performance** | performance-oracle | Bottlenecks, resource usage, scaling concerns |

**Oracle** (cross-AI): GPT-5.2 Pro perspective via Oracle CLI. Gets diversity bonus in triage.

**Why 6 instead of 5**: The self-review (5/7 agents converging) found that merging security + data-integrity + concurrency + deployment into one agent is too aggressive — these are four fundamentally different analytical modes. Splitting Safety from Correctness preserves depth while still cutting from 19 to 6.

**Static project agents removed**: `fd-*.md` bootstrapped by Codex — dead feature, never adopted.

### Triage Changes

Current triage scores each of 19 agents on a 0-2 scale with bonuses, caps at 8. New triage:

- Scores 6 core agents (most runs select 3-6 of them)
- Oracle always offered if available
- Cap stays at 8 (no reduction — reviewer consensus was that reducing coverage to save tokens is wrong metric)

### Knowledge Layer (Single-Tier with qmd)

**Location:** `config/flux-drive/knowledge/` in the Clavain repo

All knowledge entries live in one place. qmd semantic search handles relevance — no manual tier separation needed.

Contents:
- Patterns discovered during reviews (codebase trouble spots, recurring issues)
- Systematic blind spots ("Oracle consistently catches X that Claude misses")
- Cross-project heuristics ("convergence=1 from Performance agent is correct 80% for N+1 queries")

**Sanitization rule** (Oracle cross-AI finding): Global entries must be phrased as **generalized heuristics with no codebase-specific nouns**. Never store: file paths to specific repos, hostnames, internal endpoints, org names, customer identifiers, secrets, or vulnerability details with exploitable specifics. The compounding agent must redact before writing. Example: "Auth middleware often swallows context cancellation errors — check for ctx.Err() after upstream calls" (good) vs "middleware/auth.go in Project X has a bug at line 47" (bad — too specific for global).

**Why single-tier**: The self-review (4/7 agents) found zero evidence that project-specific knowledge differs meaningfully from global knowledge. Starting single-tier avoids: two storage locations, graduation logic, precedence conflicts, and migration between tiers. If after 20+ reviews evidence shows the split is needed, add project-local tier then.

#### Knowledge Format

Minimal structured markdown:

```yaml
---
lastConfirmed: 2026-02-10
provenance: independent
---
Auth middleware in middleware/auth.go swallows context cancellation errors.
Both Safety agent and Oracle flagged this independently.

Evidence: middleware/auth.go:47-52, handleRequest() — context.Err() not checked after upstream call.
Verify: grep for ctx.Err() after http.Do() calls in middleware/*.go.
```

Three metadata fields + inline evidence:
- `lastConfirmed` — needed for decay (entries not confirmed in 10 reviews get archived)
- `provenance` — `independent` or `primed` (whether the confirming agent had this entry in its context)
- **Evidence anchors** (in body) — file paths, symbol names, line ranges. Without these, entries rot into unverifiable folklore (Oracle cross-AI finding).
- **Verification steps** (in body) — 1-3 steps to confirm the finding is still valid

**Why minimal metadata + rich body**: The self-review found that `domain`, `source`, `confidence`, `convergence`, and `origin` YAML fields are either redundant with qmd search (domain), tracked by git (source), subjective (confidence), misleading with merged agents (convergence), or classification overhead (origin). Oracle agreed on minimal metadata but stressed that the *body* must include concrete evidence anchors — not just claims. The compounding agent must extract file paths and verification steps, not just findings.

#### Provenance Tracking

The self-review's strongest finding (6/7 convergence) was the **false-positive feedback loop**:

```
Finding compounded → injected into next review → agent re-confirms (primed)
→ lastConfirmed updated → entry never decays → false positive permanent
```

**Fix**: The `provenance` field distinguishes:
- `independent` — agent flagged this without seeing the knowledge entry (genuine re-confirmation)
- `primed` — agent had this entry in its context when it re-flagged it (not a true confirmation)

Only `independent` confirmations update `lastConfirmed`. Primed confirmations are ignored for decay purposes. This breaks the self-reinforcing loop.

#### Retrieval via qmd

qmd semantic search retrieves relevant knowledge entries based on the document being reviewed and the agent's focus area.

- **Cap**: 5 entries per agent (not 10 — marginal value of entries 6-10 is low if qmd ranking is good)
- **Timing**: Retrieval is pipelined with agent launch, NOT during triage (avoids 15-35s of serial qmd latency)
- **Per-agent queries**: Orchestrator constructs agent-specific queries by combining document summary with agent domain keywords (e.g., Safety queries "threats vulnerabilities credentials {summary}")
- **Fallback**: If qmd unavailable, agents run without knowledge injection — effectively v1 behavior

### Compounding (Silent Post-Synthesis Hook)

After Phase 3 synthesis (and Phase 4 cross-AI if Oracle participated), a compounding agent runs **silently in the background**:

1. Reads structured agent output files (YAML frontmatter), NOT synthesis prose
2. Decides what's worth remembering permanently vs. what's review-specific
3. Writes knowledge entries to `config/flux-drive/knowledge/`
4. Updates `lastConfirmed` on re-observed findings (respecting provenance)
5. Handles decay: archives entries not independently confirmed in 10 reviews

**Model**: Sonnet (this is classification/extraction, not deep analysis — ~$0.025/run)

**Key design decisions**:
- **Silent**: No user-visible output. The user's last interaction is Phase 3/4 results, same as v1. If compounding fails, the review is still complete.
- **Reads YAML, not prose**: Decoupled from synthesis presentation format. The v1 self-review flagged YAML frontmatter as "the system's Achilles heel" — adding another prose consumer would double that exposure.
- **Single-tier writes**: All entries go to Clavain-global. No graduation logic, no cross-repo writes.

### Phase Structure

| Phase | What | Changes from v1 |
|-------|------|-----------------|
| **1. Triage** | Profile document, score 6 core agents, offer Oracle | Simpler scoring (6 vs 19) |
| **2. Launch** | Inject knowledge context (pipelined), dispatch agents in parallel | Each agent gets up to 5 relevant knowledge entries prepended |
| **3. Synthesize** | Validate, deduplicate, convergence tracking, summary | Unchanged |
| **4. Cross-AI** | Oracle delta analysis | Unchanged |
| **Post-synthesis** | Silent compounding hook | NEW — runs in background, no user interaction |

**Why not "Phase 5"**: The user should perceive the same 3-step flow as v1 (triage → wait → read results). Compounding is infrastructure, not a user-facing phase.

### First-Run Bootstrap

On a project's first flux-drive v2 run:
- No knowledge entries exist — qmd returns nothing
- Agents run without knowledge injection (effectively v1 behavior with merged agents)
- Compounding hook creates `config/flux-drive/knowledge/` directory and writes initial entries
- User sees: "First review on this project — building knowledge base for future reviews."

The first run is strictly a 6-agent review. The "getting smarter" benefit starts on run 2.

### Retraction Mechanism

When a knowledge entry is wrong:
- **Automatic**: If a file is reviewed and the entry's finding is NOT re-flagged in 3 consecutive reviews of the same file, confidence degrades and the entry is archived
- **Manual**: Users can delete files from `config/flux-drive/knowledge/` directly (they're just markdown)
- **Future**: `/clavain:flux-knowledge review` command to inspect, confirm, or retract entries

---

## Validation Plan

Before shipping, run a controlled comparison:

1. Pick 3 recent flux-drive reviews with known findings
2. Re-run with 6 merged agent prompts instead of 19 specialized
3. Compare: do merged agents find 90%+ of what specialists found?
4. If merged agents miss >20%, the merge destroys value — adjust agent boundaries

---

## Deferred to v2.x / v3

These features were cut based on the self-review. Each can be added independently later if data supports it.

| Feature | Why Deferred | Trigger to Reconsider |
|---------|-------------|----------------------|
| **Two-tier knowledge** (project-local + global) | Zero evidence project-specific patterns differ from global | After 20+ reviews, if >30% of entries only apply to one project |
| **Ad-hoc agent generation** | Problem: too many agents. Solution shouldn't be: dynamically generate more. | If users report domains the 6 core agents consistently miss |
| **Async deep-pass** | Prove immediate compounding works first. Deep-pass scaling hits context limits at ~100 reviews. | After 50+ reviews with immediate compounding, if cross-review patterns are being missed |
| **Agent graduation pipeline** | Requires cross-project tracking, repo boundary crossing. | Only relevant if two-tier knowledge is implemented |
| **Complex frontmatter** (domain, source, confidence, convergence, origin) | Redundant with qmd search and git history. | If qmd retrieval proves insufficiently precise without domain tags |
| **7th agent: Reliability/Deploy/Observability** | Oracle recommends splitting Safety into Security + Reliability. Our 6-agent model keeps them together. | If deployment/ops reviews consistently show shallow coverage under the Safety agent |
| **Claim-level convergence** | With 6 agents, convergence is low-resolution. Oracle suggests counting convergence per *section* within merged agents, not per agent. | If convergence tracking becomes meaningless at 6 agents |
| **Cap reduction** (8 → 6) | Reviewers found no justification. Keep 8 or make dynamic based on document complexity. | If token costs are a proven bottleneck |

---

## Original Design Intent

The brainstorm explored a more ambitious architecture: 5 core agents + dynamic ad-hoc generation + two-tier knowledge + immediate compounding + async deep-pass. The self-review (7 agents, 2026-02-10) recommended decomposing this into separable pieces. Key features preserved for future iterations:

- **Ad-hoc agents**: Triage detects uncovered domains → generates specialized agent on the fly → saves for reuse → graduates to global. *Deferred because*: adding agents is creating one markdown file; the 6-agent model should be proven insufficient first.
- **Two-tier knowledge**: Project-local (`.claude/flux-drive/knowledge/`) + Clavain-global (`config/flux-drive/knowledge/`). *Deferred because*: no precedence rules for conflicts, no evidence the split is needed.
- **Deep-pass agent**: Periodic cross-review analysis scanning output directories for patterns individual runs missed. *Deferred because*: O(reviews × agents) scaling, prove immediate compounding first.
- **Compounding as visible Phase 5**: User sees compounding output. *Changed to*: silent hook, because 5/7 agents converged on "the user should not perceive 5 phases."
