---
agent: performance-oracle
tier: adaptive
issues:
  - id: P0-1
    severity: P0
    section: "Knowledge Layer / Retrieval via qmd"
    title: "Serial qmd calls during triage add 15-35s latency before first agent launches"
  - id: P1-1
    severity: P1
    section: "Agent Roster / Merged Agents"
    title: "Knowledge injection per merged agent may increase total token spend vs. v1 specialized agents"
  - id: P1-2
    severity: P1
    section: "Compounding System / Async Deep-Pass"
    title: "Deep-pass scanning all historical output dirs is O(reviews * agents) and grows unbounded"
  - id: P1-3
    severity: P1
    section: "Triage Changes / Ad-hoc Generation"
    title: "On-the-fly agent prompt generation adds 10-30s latency to triage for unmatched domains"
  - id: P2-1
    severity: P2
    section: "Compounding System / Immediate Compounding Agent"
    title: "Compounding agent reads synthesis + cross-AI delta, a moderate but not concerning token cost"
improvements:
  - id: IMP-1
    title: "Batch qmd calls or pipeline them with agent launch to hide latency"
    section: "Knowledge Layer / Retrieval via qmd"
  - id: IMP-2
    title: "Cap knowledge injection at 5 entries (not 10) per agent to control token budget"
    section: "Agent Roster / Merged Agents"
  - id: IMP-3
    title: "Deep-pass should index summaries only, not raw agent outputs"
    section: "Compounding System / Async Deep-Pass"
  - id: IMP-4
    title: "Cache generated ad-hoc agent prompts eagerly to amortize generation cost"
    section: "Triage Changes / Ad-hoc Generation"
verdict: needs-changes
---

## Performance Profile

- **Application type**: Claude Code plugin skill (multi-agent orchestration pipeline)
- **Where performance matters most**: Time-to-first-agent-launch (user waits interactively), total token spend per review (direct cost), and deep-pass scaling at high review counts
- **Known constraints**: Claude API rate limits, Oracle CLI timeout (480s), qmd MCP server latency per call, 200K context window per agent, ~$0.22/review at current 5-agent Opus pricing

## Baseline Measurements (from existing flux-drive runs)

Before analyzing v2, establishing what v1 actually costs:

| Metric | Measured Value | Source |
|--------|---------------|--------|
| Agent prompt sizes (current 19 agents) | 3.2KB-13.2KB each, 120KB total | `agents/review/*.md` byte counts |
| Individual agent output | 12KB-31KB per agent | Clavain-v3 run outputs |
| Synthesis summary | 5.3KB-11.5KB | summary.md across runs |
| Cross-AI delta summary | 2.8KB | `cross-ai/summary.md` |
| Total output per run | ~80KB-196KB | Full run directories |
| Historical output (11 runs) | 1.1MB, 54 files | `docs/research/flux-drive/` |
| Typical agents per run | 5-7 | Observed across runs |
| Launch prompt template | ~1.5KB overhead per agent | `phases/launch.md` template |

Token approximation: 1 byte of English markdown is roughly 0.3 tokens. So 10KB of knowledge entries is approximately 3,000 tokens.

---

## Issue 1: Serial qmd Calls During Triage (P0)

**Location**: Knowledge Layer -- Retrieval via qmd (architecture doc lines 77-81), Phase 1 triage flow

**Problem**: The architecture specifies that each agent receives relevant knowledge entries retrieved via qmd semantic search "based on the document being reviewed and the agent's focus area." During triage, the orchestrator must:

1. Profile the document (existing, fast -- it is a Read + analysis)
2. Score 5 core agents against the profile (existing, fast -- it is reasoning)
3. Check saved ad-hoc agents for domain match (NEW -- requires qmd search)
4. For each selected agent, retrieve relevant knowledge entries (NEW -- requires qmd search per agent)

If the orchestrator performs qmd retrieval during triage (to decide knowledge injection), that is 5-7 serial qmd calls. Based on MCP tool call latency (each qmd call involves: MCP protocol overhead, semantic search execution, result formatting), a conservative estimate is 3-5 seconds per call. For 5-7 calls: **15-35 seconds of additional latency** before agents can launch.

This is on top of the existing triage time (document profiling, scoring, user confirmation via AskUserQuestion). In v1, triage is fast because there is no knowledge retrieval step -- agents launch immediately after user approval.

**Impact**: User-facing. The user is waiting interactively during triage. Adding 15-35 seconds to the "thinking" phase before the "agents launched, wait 3-5 minutes" message degrades the perceived responsiveness of the tool. The current triage takes roughly 30-60 seconds (profile + score + user question). This would roughly double it.

**Fix**: Decouple knowledge retrieval from triage. Two approaches:

- **Option A (recommended)**: Pipeline qmd retrieval with agent launch. During triage, only do the ad-hoc agent roster check (1 qmd call). After the user approves agent selection, retrieve knowledge entries for each agent in parallel with (or as the first step of) agent launch. Each agent's Task prompt already includes a "Your Focus Area" section -- prepend knowledge entries there. The qmd calls for different agents are independent and can run in parallel.

- **Option B**: Pre-fetch a single batch of knowledge entries for the entire document during Step 1.0 (project understanding), then partition entries across agents by domain tag during scoring. This is 1 qmd call instead of 5-7, but loses the per-agent focus-area specificity.

**Trade-off**: Option A adds complexity to the launch phase (qmd calls interleaved with Task dispatch). Option B sacrifices retrieval precision for speed. Option A is better because the 3-5 minute agent execution time dwarfs any per-agent qmd latency when parallelized.

---

## Issue 2: Token Economics -- Merged Agents with Knowledge Injection vs. Specialized Agents (P1)

**Location**: Agent Roster (architecture doc lines 16-29), Knowledge Layer (lines 45-80)

**Problem**: The architecture claims 5 merged agents replace 19 specialized agents. But the token economics are more nuanced than "fewer agents = less cost."

### v1 Token Budget (per review, 5 agents selected from 19)

Each selected agent receives:
- Agent system prompt: 3.2KB-13.2KB (median ~5KB, approximately 1,500 tokens)
- Launch prompt template overhead: ~1.5KB (approximately 450 tokens)
- Trimmed document: ~50% of input document
- No knowledge injection

Total per-agent overhead (excluding document): approximately 2,000 tokens
Total across 5 agents: approximately 10,000 tokens of overhead

### v2 Token Budget (per review, 3-5 core agents)

Each merged agent receives:
- Merged agent system prompt: **larger** because it covers 3-4 former domains. Estimating the "Safety & Correctness" agent (security-sentinel + data-integrity + concurrency + deployment-verification) at 8-15KB (approximately 2,500-4,500 tokens) -- the sum of the merged agent prompts is 3.3KB + 4.3KB + 13.2KB + 5.9KB = 26.7KB raw, which must be compressed to remain effective, but even at 50% compression that is approximately 13KB or 4,000 tokens
- Launch prompt template overhead: ~1.5KB (approximately 450 tokens)
- Trimmed document: ~50% of input (unchanged)
- Knowledge injection: Up to 10 entries at ~500 bytes each = approximately 5KB (1,500 tokens) per agent

Total per-agent overhead (excluding document): approximately 6,000 tokens
Total across 5 agents: approximately 30,000 tokens of overhead

### Net Impact

| Component | v1 (5 of 19) | v2 (5 core) | Delta |
|-----------|-------------|-------------|-------|
| Agent prompt tokens | ~10,000 | ~22,500 | +12,500 |
| Knowledge injection | 0 | ~7,500 | +7,500 |
| Synthesis input (agent outputs to read) | 5 files | 5 files | neutral |
| Compounding agent | 0 | ~5,000 | +5,000 |
| **Total overhead increase** | -- | -- | **~+25,000 tokens** |

The savings from fewer agents come from launching fewer Claude API calls (each call has fixed overhead in system prompt processing). But v2 sends MORE tokens per call due to merged prompts and knowledge injection. At current Opus pricing ($15/MTok input, $75/MTok output), 25,000 additional input tokens costs approximately $0.38 per review. This is on the same order as the current total review cost of $0.22.

**However**: This analysis assumes the architecture keeps all 5 core agents active for most reviews. The architecture says "most runs select 3-5 of them." If the typical run drops to 3 agents (vs 5 in v1), the overhead per-agent increase is partially offset by launching fewer agents. Additionally, if merged agents produce better findings (fewer re-runs, fewer missed issues requiring follow-up reviews), the amortized cost across the review lifecycle could decrease.

**Impact**: Direct cost. Each review becomes approximately 50-100% more expensive in token spend. This matters for projects that run flux-drive frequently (this project has 11 runs in 4 days).

**Fix**:
1. Cap knowledge injection at 5 entries per agent (not 10 as the architecture suggests). Each entry is approximately 500 bytes. 5 entries = 2,500 bytes (750 tokens) vs 10 entries = 5,000 bytes (1,500 tokens). The marginal value of entries 6-10 is low if qmd ranking is good.
2. Keep merged agent prompts lean. Do not naively concatenate 4 former agent prompts. Extract the shared "First Step (MANDATORY)" pattern once, then list domain-specific focus areas as bullet points. Target: merged prompt no larger than the largest single-domain prompt it replaces (~13KB for Safety & Correctness, matching concurrency-reviewer's current size).
3. Consider model tiering for merged agents that cover "mechanical" domains. The v1 summary already recommended assigning `model: sonnet` to fd-code-quality, pattern-recognition, etc. This applies to merged agents too -- "Quality & Style" does not need Opus.

---

## Issue 3: Deep-Pass Agent Scaling (P1)

**Location**: Compounding System -- Async Deep-Pass Agent (architecture doc lines 98-107)

**Problem**: The deep-pass agent "scans `docs/research/flux-drive/` output directories across multiple reviews." Currently:

- 11 review directories exist
- 54 markdown files totaling 1.1MB
- Average 5 files per run at 15-30KB each

At 50+ reviews (the question asked), this becomes:
- ~50 directories
- ~250-350 markdown files
- ~5-7MB of content

The deep-pass agent must read all of this to "identify cross-review patterns that individual runs missed" and "detect systematic agent blind spots across runs." Even if it only reads summaries (not full agent outputs), that is 50 summary files at 5-12KB each = 250-600KB = 75,000-180,000 tokens. This exceeds a single context window at the high end.

**Scaling analysis**:

| Reviews | Files | Total Size | Tokens (est.) | Fits in 200K context? |
|---------|-------|-----------|---------------|----------------------|
| 11 (current) | 54 | 1.1MB | ~330K | No (already exceeds) |
| 25 | ~125 | ~2.5MB | ~750K | No |
| 50 | ~250 | ~5MB | ~1.5M | No |

Even reading only summaries:

| Reviews | Summary Files | Total Size | Tokens (est.) | Fits in 200K context? |
|---------|--------------|-----------|---------------|----------------------|
| 11 | 11 | ~90KB | ~27K | Yes |
| 25 | 25 | ~200KB | ~60K | Yes |
| 50 | 50 | ~400KB | ~120K | Yes, tight |
| 100 | 100 | ~800KB | ~240K | No |

**Impact**: The deep-pass agent becomes impractical at 50+ reviews if it reads raw agent outputs. Even with summaries-only, it hits context limits around 100 reviews. More importantly, the agent's analysis quality degrades as input volume grows -- a 120K-token input leaves little room for reasoning.

**Fix**:
1. Deep-pass MUST read only summaries, never raw agent outputs. This is not stated in the architecture.
2. Implement a sliding window: deep-pass only scans the last N reviews (e.g., 10-20), not the entire history. Older patterns should already be captured in the knowledge layer from previous deep-pass runs.
3. As the knowledge layer grows, deep-pass shifts from "scan raw outputs" to "scan knowledge entries + recent summaries." The knowledge layer is the compressed representation of historical patterns.
4. Consider a two-level approach: deep-pass produces its own summary file after each run. Future deep-pass runs read the previous deep-pass summary + new reviews since then. This is O(1) historical context + O(recent) new input.

---

## Issue 4: Ad-hoc Agent Generation Latency (P1)

**Location**: Triage Changes (architecture doc lines 35-40), Ad-hoc Agents (lines 28-31)

**Problem**: When triage detects a domain none of the 5 core agents cover (e.g., GraphQL schema design, accessibility, i18n), it "generates new ad-hoc agent prompt on the fly." This means:

1. Triage detects unmatched domain (requires reasoning about the document profile vs. core agent coverage)
2. Orchestrator generates a new agent system prompt (must produce a coherent, domain-specific review prompt)
3. The generated prompt must follow Clavain agent conventions (YAML frontmatter, output format, focus areas)
4. The agent is saved to `.claude/flux-drive/agents/` for reuse

Step 2 is the expensive one. Generating a high-quality agent prompt is not a trivial operation -- it requires the orchestrator to reason about what a domain expert would focus on, what patterns to look for, and how to structure the review. This is effectively a "write a skill" operation performed inline during triage.

**Estimated latency**: 10-30 seconds of LLM generation time to produce a coherent agent prompt of 3-5KB. This occurs DURING triage, while the user is waiting interactively.

**Frequency**: For mature projects with established ad-hoc agent rosters, this happens rarely (most domains are already covered). For new projects or projects entering new domains, it could happen on the first 3-5 reviews.

**Impact**: User-facing latency. The first review of a new domain type takes noticeably longer. The user sees the triage phase stall while the orchestrator generates a new agent prompt. After generation, the ad-hoc agent is cached, so subsequent reviews are unaffected.

**Mitigations already in the architecture**: Saved ad-hoc agents are reused. Graduation to Clavain-global means agents are available across projects. The amortized cost is low.

**Fix**: Accept this latency for the first occurrence (it is a one-time cost per domain per project). To reduce the sting:
1. Display a progress message: "Generating specialized agent for [domain]... (first time only, will be cached)"
2. Do NOT block other agent launches on ad-hoc generation. Launch the core agents immediately after user approval, then generate the ad-hoc agent in parallel and launch it when ready. This means the ad-hoc agent starts 10-30 seconds later than core agents, but the total wall-clock time only increases by the difference between ad-hoc generation time and core agent execution time (usually net-zero since core agents take 3-5 minutes).
3. Pre-seed common ad-hoc agents. Ship a handful of ready-made agents for frequently-needed domains (GraphQL, accessibility, i18n, database schema design) in the Clavain global knowledge. These are not "core" agents but avoid generation for the most common ad-hoc needs.

---

## Issue 5: Compounding Phase Cost (P2)

**Location**: Compounding System -- Immediate Compounding Agent (architecture doc lines 86-95)

**Problem**: The immediate compounding agent "reads the synthesis summary + cross-AI delta" after each review. Based on measured outputs:

- Synthesis summary: 5.3KB-11.5KB (1,600-3,500 tokens)
- Cross-AI delta summary: 2.8KB (840 tokens)
- Total compounding input: approximately 8-14KB (2,400-4,200 tokens)

The compounding agent then performs judgment operations: deciding what is worth remembering, extracting knowledge entries, updating lastConfirmed dates, checking ad-hoc agent graduation.

**Assessment**: This is a cheap operation. The input is small (under 5,000 tokens), the reasoning is bounded (classify each finding as "compound-worthy" or "review-specific"), and the output is small (a few knowledge entries at ~500 bytes each).

**Estimated cost**: approximately 5,000 input tokens + approximately 2,000 output tokens per review. At Opus pricing: $0.075 input + $0.15 output = approximately $0.23. If using Sonnet for compounding (reasonable since this is classification, not deep analysis): approximately $0.015 + $0.01 = approximately $0.025.

**Impact**: Low. The compounding phase adds approximately $0.02-0.23 per review depending on model choice. The time cost is approximately 10-20 seconds of LLM processing.

**Fix**: Use Sonnet (or even Haiku) for the compounding agent. This is classification and extraction work, not creative analysis. The architecture should specify `model: sonnet` or `model: haiku` for this agent explicitly. This makes the compounding phase nearly free.

---

## Summary

**Overall performance risk: Medium**

The architecture introduces real performance concerns in two areas (qmd retrieval latency and token economics) and a scaling concern (deep-pass at high review counts). The compounding cost and ad-hoc generation are manageable.

### Must-Fix Items

1. **P0: Pipeline qmd retrieval with agent launch** (Issue 1). Do not make the user wait through serial qmd calls during triage. Retrieve knowledge entries in parallel during or after agent dispatch.

2. **P1: Cap knowledge injection and keep merged prompts lean** (Issue 2). Without discipline, v2 could cost 2x per review for marginal quality gains. Set a 5-entry cap and compress merged agent prompts.

3. **P1: Deep-pass must read summaries only with a sliding window** (Issue 3). Without this constraint, the deep-pass agent becomes impractical within weeks of active use.

### Optimizations to Skip (Premature)

- **Ad-hoc generation latency** (Issue 4): One-time cost per domain, self-amortizing through caching. Not worth optimizing before observing real usage patterns.
- **Compounding cost** (Issue 5): Under $0.25 even at Opus pricing. Just specify `model: sonnet` and move on.

### Cost Projection

| Scenario | v1 Cost/Review | v2 Cost/Review (unoptimized) | v2 Cost/Review (optimized) |
|----------|---------------|-----------------------------|-----------------------------|
| 5 agents, Opus | $0.22 | $0.45-0.60 | $0.30-0.40 |
| 3 agents, mixed models | -- | $0.25-0.35 | $0.15-0.25 |
| + compounding (Sonnet) | -- | +$0.03 | +$0.03 |
| + deep-pass (periodic) | -- | $0.10-0.50 per run | $0.05-0.15 per run |

The optimized v2 path (lean prompts, 5-entry knowledge cap, mixed model tiering, summaries-only deep-pass) lands at approximately $0.18-0.43 per review -- comparable to v1 with significantly richer context.

### Open Question Responses

**Q1 (Knowledge injection token budget)**: Cap at 5 entries, not 10. At 500 bytes/entry, 5 entries = 750 tokens -- well within noise. 10 entries (1,500 tokens) start to compete with the agent prompt itself for attention.

**Q3 (Memory storage choice)**: Option 3 (qmd as memory engine) is the right call from a performance perspective. No database startup cost, no embedding computation on write, qmd search latency is the only runtime cost and it is already paid.

**Q5 (Merged agent quality)**: The performance concern is not quality degradation -- it is that quality maintenance requires larger prompts, which cost more tokens. The architecture should set explicit byte budgets for merged agent prompts (e.g., "no merged agent prompt exceeds 8KB") to prevent prompt bloat.

<!-- flux-drive:complete -->
