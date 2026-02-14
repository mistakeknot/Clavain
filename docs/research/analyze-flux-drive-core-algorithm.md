# Flux-Drive Core Algorithm Analysis

**Date**: 2026-02-13  
**Purpose**: Extract the abstract review orchestration protocol from Clavain's flux-drive implementation

---

## Executive Summary

Flux-drive implements a **Domain-Aware Multi-Agent Review Protocol** — a deterministic algorithm for triaging, launching, and synthesizing parallel specialized reviews. The core protocol is domain-agnostic; Clavain's implementation adds specific agent rosters, domain profiles, and integration glue.

**Key insight**: The protocol separates **static triage** (which agents are relevant?) from **dynamic expansion** (do early results justify more agents?) and uses structured output contracts to enable synthesis without reading full prose.

---

## The Abstract Protocol

### Phase 1: Static Analysis & Triage

#### Universal Patterns

1. **Input Classification**
   - Detect input type: `file | directory | diff`
   - Derive workspace paths: `INPUT_PATH → INPUT_DIR → PROJECT_ROOT → OUTPUT_DIR`
   - Build input profile: document type, complexity, languages, frameworks, domains
   - For diffs: extract file counts, change stats, binary files, renamed files
   - For documents: extract sections, assess depth per section, estimate complexity

2. **Domain Detection** (optional but recommended)
   - Scan project structure for domain signals: directories, file types, build deps, keywords
   - Score each known domain using weighted signal matches
   - Cache results with staleness detection (structural hash + git state + mtime)
   - Support multi-domain classification (e.g., "game server" = game + web-api)

3. **Agent Roster Compilation**
   - Load available agents from multiple sources: project-specific, plugin-provided, cross-AI
   - Each agent has: domain focus, scoring criteria, invocation method, slot cost

4. **Scoring & Selection**
   - **Pre-filter**: Eliminate agents with 0 relevance before scoring
   - **Score components**: base_score (0-3) + domain_boost (0-2) + project_bonus (0-1) + domain_agent (0-1)
   - **Dynamic slot ceiling**: `base_slots + scope_slots + domain_slots + generated_slots`, capped at `hard_maximum`
   - **Stage assignment**: Top 40% (rounded up, min 2, max 5) → Stage 1; rest → Stage 2 + expansion pool
   - **Deduplication**: Prefer project-specific > plugin > cross-AI when agents overlap

5. **Content Preparation** (slicing optimization)
   - For large inputs (diff ≥1000 lines or document ≥200 lines), apply soft-prioritize slicing
   - Map file patterns/keywords → agent priority
   - Cross-cutting agents (architecture, quality) always get full content
   - Domain-specific agents get priority hunks/sections + compressed summaries of the rest
   - Write content to temp files (shared or per-agent) to avoid duplicating in prompts

6. **User Approval Gate**
   - Present triage table: agents, scores, stages, reasons
   - Allow editing before launch

#### Configurable Surfaces

- **Agent roster**: List of available agents with scoring criteria
- **Domain index**: Signal patterns for domain detection
- **Domain profiles**: Per-domain review criteria to inject into agent prompts
- **Routing config**: File/hunk patterns mapping to agents (for slicing)
- **Slot allocation formula**: `base + scope + domain + generated` terms
- **Stage ratio**: What % of agents launch in Stage 1 (default: 40%)
- **Slicing thresholds**: 1000 lines for diffs, 200 for documents, 80% overlap to disable

#### Clavain-Specific Glue

- **Plugin discovery**: Uses `CLAUDE_PLUGIN_ROOT` env var, `subagent_type` mappings
- **Task dispatch**: Claude Code's `Task` API with `run_in_background: true`
- **qmd integration**: Semantic search for knowledge context (optional, fails gracefully)
- **Domain profile paths**: Hardcoded to `config/flux-drive/domains/{domain}.md`
- **Agent categories**: "Project" (.claude/agents/), "Plugin" (clavain:review:*), "Cross-AI" (oracle CLI)

---

### Phase 2: Parallel Launch & Monitoring

#### Universal Patterns

1. **Staged Dispatch**
   - Launch Stage 1 agents in parallel (top-tier relevance)
   - Wait for Stage 1 completion with polling (30s intervals, 5min timeout)
   - Present completion progress: `[N/M agents complete]`, `✅ agent-name (47s)`

2. **Domain-Aware Expansion Decision**
   - After Stage 1, score each Stage 2 / expansion pool agent:
     - `+3` if any P0 finding in an adjacent agent's domain
     - `+2` if any P1 finding in an adjacent agent's domain
     - `+2` if Stage 1 agents disagree on a finding in this agent's domain
     - `+1` if agent has domain injection criteria for a detected domain
   - **Expansion threshold**: `max_score ≥ 3` → recommend expansion, `= 2` → offer, `≤ 1` → recommend stop
   - Present reasoning: "P0 in game design → fd-correctness validates simulation state"

3. **Agent Prompt Construction**
   - Output format contract: Findings Index (machine-parseable) + prose sections
   - Completion signal: `<!-- flux-drive:complete -->` + rename `.partial → .md`
   - Content reference: Path to temp file (agent Reads it as first action)
   - Context injection: knowledge entries (from qmd), domain-specific review criteria, project divergence warnings

4. **Completion Verification**
   - Poll for `.md` files (not `.partial`) in OUTPUT_DIR
   - Retry failed agents once (synchronous, 5min cap)
   - Create error stubs for agents that fail after retry
   - Clean up `.partial` files after all agents complete or timeout

#### Configurable Surfaces

- **Adjacency map**: Which agent domains are related (for expansion scoring)
- **Expansion thresholds**: Score cutoffs for recommend/offer/stop (3/2/1)
- **Polling interval**: How often to check completion (default: 30s)
- **Timeout limits**: Per-stage timeout (default: 5min Task, 10min Codex, 30min Oracle)
- **Retry policy**: Retry once, synchronous, same timeout
- **Prompt template**: Output format, context sections, domain injection format

#### Clavain-Specific Glue

- **Task API**: `Task(subagent_type=..., run_in_background=true, timeout=300000)`
- **Oracle CLI invocation**: `DISPLAY=:99 CHROME_PATH=... oracle --wait --write-output ...`
- **Knowledge retrieval**: `mcp__plugin_clavain_qmd__vsearch` with collection="Clavain"
- **Temp file paths**: `/tmp/flux-drive-{stem}-{ts}.md` pattern
- **Plugin root**: `${CLAUDE_PLUGIN_ROOT}` for domain profile loading
- **Error stub format**: Specific YAML frontmatter expected by synthesis phase

---

### Phase 3: Synthesis & Output

#### Universal Patterns

1. **Structured Collection**
   - Parse Findings Index first (first ~30 lines) — structured list of all findings
   - Only read prose sections when disambiguation is needed
   - Track which agents saw which content (for convergence adjustment with slicing)

2. **Deduplication & Convergence**
   - Group findings by section/topic
   - Deduplicate: keep most specific finding when multiple agents flag the same issue
   - Track convergence: `N/M agents` where M = agents that had full access to that content
   - Flag conflicts when agents disagree (note both positions)

3. **Slicing-Aware Synthesis**
   - When slicing was active, adjust convergence counts: only count agents that saw priority content
   - Tag findings from context-only files as `[discovered beyond sliced scope]`
   - Track "Request full section/hunks" notes — if 2+ agents request same file, suggest routing improvement

4. **Verdict Computation**
   - If any P0 → "risky"
   - Else if any P1 → "needs-changes"
   - Else → "safe"

5. **Output Generation**
   - Write `summary.md`: Key findings, issues checklist, improvements, agent links, slicing report
   - Write `findings.json`: Machine-readable findings with convergence data
   - For file inputs: offer inline annotations (ask user first)
   - Create tracking artifacts from P0/P1 findings (if issue tracker available)

6. **Silent Compounding** (knowledge accumulation)
   - After presenting results, launch background agent to extract durable patterns
   - Save patterns to knowledge store with provenance tracking (independent vs primed)
   - Decay check: archive entries not independently confirmed in >60 days
   - This is silent — user's last interaction is the synthesis report

#### Configurable Surfaces

- **Verdict thresholds**: Severity cutoffs for risky/needs-changes/safe
- **Convergence threshold**: How many agents must agree to mark high-confidence
- **Deduplication priority**: Project > Plugin > Cross-AI (or custom ordering)
- **Slicing report format**: Table columns, metrics to track
- **Knowledge compounding criteria**: Which findings to save (P0/P1 only? all?)
- **Knowledge decay window**: Days until unconfirmed entries are archived
- **Output format**: summary.md structure, findings.json schema

#### Clavain-Specific Glue

- **Beads integration**: `bd create` for P0/P1/P2 findings (if `.beads/` exists)
- **Output paths**: `{PROJECT_ROOT}/docs/research/flux-drive/{stem}/`
- **Knowledge paths**: `config/flux-drive/knowledge/*.md` with YAML frontmatter
- **Compounding agent**: Uses `Task(subagent_type: general-purpose)` with sanitization rules
- **Phase tracking**: Interphase integration via `phase_infer_bead`, `advance_phase`
- **Summary template**: Specific markdown structure with Flux Drive branding

---

## Protocol Invariants (Must-Haves)

These are universal requirements for any implementation of this protocol:

1. **Deterministic triage**: Same input + same roster → same agent selection
2. **Structured output contract**: Agents must produce machine-parseable indices, not just prose
3. **Completion signaling**: Orchestrator must detect when agents finish (not just poll for text)
4. **Stage separation**: High-relevance agents run first; expansion decision uses their results
5. **Convergence tracking**: Synthesis must count how many agents saw the same content
6. **Slicing metadata**: When content is filtered, orchestrator tracks which agent saw what
7. **Graceful degradation**: Failed agents produce error stubs; synthesis continues with partial results
8. **User approval gates**: Before Stage 1 launch, before Stage 2 expansion
9. **Knowledge accumulation**: Some mechanism to learn from reviews (doesn't have to be silent compounding)

---

## Optional Enhancements (Nice-to-Haves)

These improve the protocol but aren't required for correctness:

1. **Domain detection**: Projects can be profiled manually; auto-detection is a UX win
2. **Knowledge injection**: Agents work without prior context; injecting patterns improves recall
3. **Content slicing**: Optimization for token efficiency; full content works but costs more
4. **Dynamic expansion**: Static triage works; expansion decision improves precision
5. **Cross-AI agents**: Single-model reviews work; cross-AI reduces blind spots
6. **Temp file content**: Agents can receive inline content; temp files avoid duplication
7. **Retry on failure**: Agents fail sometimes; retries improve completion rate
8. **Findings JSON**: summary.md is human-readable; JSON enables automation

---

## Clavain-Specific Implementation Details

### Agent Types & Invocation

| Type | Discovery | Invocation | Prompt Source |
|------|-----------|------------|---------------|
| Project Agents | `ls {PROJECT_ROOT}/.claude/agents/fd-*.md` | `Task(subagent_type: general-purpose)` | Paste full `.md` content |
| Plugin Agents | Hardcoded roster in plugin | `Task(subagent_type: clavain:review:fd-*)` | Plugin provides system prompt |
| Cross-AI | `which oracle && pgrep Xvfb` | `Bash` with Oracle CLI | Inline prompt |

### Domain System Architecture

1. **Index**: `config/flux-drive/domains/index.yaml` — 11 domains with signal patterns
2. **Profiles**: `config/flux-drive/domains/{domain}.md` — per-domain review criteria + agent specs
3. **Detector**: `scripts/detect-domains.py` — deterministic scorer with 3-tier staleness check
4. **Cache**: `{PROJECT_ROOT}/.claude/flux-drive.yaml` — detected domains + structural hash
5. **Generator**: `/flux-gen` command — creates project agents from domain profile specs

### Content Slicing Implementation

**Diff slicing** (when diff ≥ 1000 lines):
- `config/flux-drive/diff-routing.md` defines per-agent priority patterns (file globs + hunk keywords)
- Orchestrator classifies each changed file as `priority` or `context` per agent
- Cross-cutting agents (fd-architecture, fd-quality) skip slicing (always full diff)
- Domain agents receive priority hunks + one-liner summaries: `[context] path: +12 -5 (modified)`

**Document slicing** (when file ≥ 200 lines):
- Uses same routing keywords but applies to `##` heading sections instead of diff hunks
- Orchestrator writes per-agent temp files: priority sections full + context sections summarized
- 80% threshold: if agent's priority content covers ≥80% of total, skip slicing (overhead not worth it)

**Slicing metadata tracking**:
```yaml
slicing_map:
  fd-safety: {priority: [file1, file2], context: [file3], mode: sliced}
  fd-architecture: {priority: all, context: none, mode: full}
```

### Knowledge System (Compounding)

After synthesis, silent background agent:
1. Reads Findings Indexes from all agents
2. Decides: compound (durable pattern) or skip (one-off)
3. Writes `config/flux-drive/knowledge/{kebab-case}.md` with YAML frontmatter:
   ```yaml
   ---
   lastConfirmed: 2026-02-13
   provenance: independent  # or "primed" if finding matched injected knowledge
   ---
   {1-3 sentence pattern description}
   
   Evidence: {file paths, symbols, line ranges}
   Verify: {steps to confirm still valid}
   ```
4. Sanitizes external project details (no hostnames, customer names)
5. Archives entries not independently confirmed in >60 days

On next review, qmd search retrieves relevant entries → injected into agent prompts.

### Integration Points

**Depends on**:
- Claude Code: Task API, subagent_type system, plugin hooks
- Interphase: Phase tracking, bead context (optional)
- Beads: Issue creation from findings (optional)
- qmd MCP: Knowledge retrieval (optional)
- Oracle CLI: Cross-AI reviews (optional)

**Called by**:
- `/clavain:flux-drive` command
- `lfg` skill (within full pipeline)
- Direct skill invocation: `clavain:flux-drive`

**Chains to**:
- `/clavain:interpeer` — when user wants to investigate cross-AI disagreements
- `/clavain:resolve` — when user wants to auto-fix P0 findings

---

## Extraction Opportunities

To port this protocol to a different environment (not Claude Code), you'd need to replace:

### Hard Dependencies (Must Replace)

1. **Agent dispatch**: Replace Task API with your multi-agent runtime
2. **Completion detection**: Replace polling for `.md` files with your runtime's status API
3. **Structured output parsing**: Ensure agents produce Findings Index format (or adapt parser)
4. **Temp file management**: Agents must Read temp files (or inline content if your runtime supports it)

### Soft Dependencies (Can Remove)

1. **Plugin system**: Hardcode agent roster instead of discovering from `CLAUDE_PLUGIN_ROOT`
2. **qmd search**: Remove knowledge injection (agents work without it)
3. **Domain detection**: Manual domain classification (or skip domain system entirely)
4. **Oracle CLI**: Remove cross-AI agents (or integrate different model provider)
5. **Beads/Interphase**: Remove issue tracking and phase gates

### Protocol-Preserving Simplifications

If you remove domain detection, knowledge injection, content slicing, and cross-AI:

- **Phase 1**: Manual triage (user picks agents from roster)
- **Phase 2**: Launch all agents in parallel, no expansion decision
- **Phase 3**: Synthesis from Findings Index, no slicing adjustment

This is ~40% of the current implementation but preserves the core protocol: structured triage → parallel dispatch → index-based synthesis.

---

## Key Design Patterns

### 1. Index-First Collection

Agents write a **structured index** (machine-parseable) before prose. Orchestrator reads indices first; only reads prose for disambiguation. This enables:
- Fast synthesis (30 lines per agent vs full output)
- Convergence counting without NLP
- Conflict detection without semantic analysis

**Why it works**: Prose is for humans; indices are for the orchestrator. Separating these concerns reduces synthesis complexity by 10x.

### 2. Soft-Prioritize Slicing

Domain agents receive priority content in full + summaries of the rest. No information is lost; just selectively compressed. This enables:
- Token efficiency without precision loss
- Discovery beyond sliced scope (agents can flag context-only files as "needs full review")
- Adaptive slicing (80% overlap threshold disables slicing when overhead exceeds benefit)

**Why it works**: Summaries give enough signal to know "this file might matter" without paying full token cost upfront. Agents request full content when needed.

### 3. Domain-Aware Expansion

Stage 1 results inform Stage 2 launch decision via **adjacency scoring**. If Stage 1 finds a P0 in game design, fd-correctness gets +3 (validates simulation state). This enables:
- Precision over recall (don't launch agents unlikely to find issues)
- Context-aware coverage (serious findings in one domain justify deep review in adjacent domains)
- User control (expansion is recommended, not forced)

**Why it works**: Static triage (Phase 1) handles common case; dynamic expansion (Phase 2) handles outliers where early results reveal unexpected complexity.

### 4. Provenance-Tracked Knowledge

Knowledge entries track `provenance: independent | primed`. If an agent flags a finding that matches injected knowledge:
- Agent notes "independently confirmed" → entry's `lastConfirmed` date updates
- Agent notes "primed confirmation" → entry is decay-eligible (might be outdated)

This enables:
- Knowledge decay (archive entries not independently validated)
- Confidence tracking (how many times has this been seen?)
- Priming detection (avoid echo chamber where injected patterns are re-confirmed without verification)

**Why it works**: Injecting prior findings improves recall but risks confirmation bias. Provenance tracking lets the system detect when knowledge is stale.

### 5. Graceful Degradation

Every optional component has a fallback:
- Domain detection fails → LLM fallback classification
- qmd unavailable → skip knowledge injection
- Agent fails after retry → error stub (synthesis continues)
- Beads not configured → skip issue tracking
- Oracle unavailable → skip cross-AI review

**Why it works**: The protocol has a minimal viable core (triage → launch → synthesize). Everything else is an optimization. Failures in optimizations degrade UX but don't break correctness.

---

## Performance Characteristics

**Phase 1 (Static Triage)**: <30 seconds
- Domain detection: <10s (cached on subsequent runs, <100ms staleness check)
- Document profiling: <5s (Read + light parsing)
- Agent scoring: <1s (pure math, no I/O)
- Content slicing prep: <10s (section extraction + classification)

**Phase 2 (Parallel Launch)**: 3-5 minutes per stage
- Agent runtime: 2-4 min (model-dependent)
- Polling overhead: negligible (30s interval)
- Retry overhead: +5 min max (rare, only for failed agents)

**Phase 3 (Synthesis)**: <60 seconds
- Index parsing: <5s (30 lines × N agents)
- Deduplication: <10s (pairwise comparison, N typically ≤12)
- Output generation: <20s (Write × 2-3 files)
- Bead creation: <20s (N findings × `bd create`)
- Silent compounding: background, user doesn't wait

**Total wall time**: 5-10 minutes for standard review (single stage, 4-6 agents)

---

## Comparison to Alternatives

### vs. Sequential Review (single agent, multiple passes)

**Flux-drive advantages**:
- 5-10 min wall time vs 30-60 min sequential
- Domain experts instead of generalist (deeper analysis)
- Convergence signal (N agents agree → high confidence)

**Sequential advantages**:
- Simpler orchestration (no parallel dispatch)
- Lower token cost (1 agent vs N agents)
- No synthesis complexity

**Verdict**: Flux-drive wins for non-trivial reviews where domain expertise and speed matter. Sequential wins for quick checks.

### vs. Ensemble Review (all agents, no triage)

**Flux-drive advantages**:
- Selective launch (4-6 agents vs 12 max)
- Domain-aware expansion (only launch Stage 2 if Stage 1 finds issues)
- Content slicing (reduce token cost per agent)

**Ensemble advantages**:
- No triage complexity
- No missed coverage (all agents run)

**Verdict**: Flux-drive wins for most cases. Ensemble is overkill — you pay for agents that find nothing.

### vs. LLM-Router (single orchestrator dispatches sub-reviews on-demand)

**Flux-drive advantages**:
- Deterministic triage (no LLM variance in agent selection)
- Parallel dispatch (all Stage 1 agents run simultaneously)
- Structured contracts (Findings Index enables fast synthesis)

**LLM-Router advantages**:
- Dynamic routing (can discover new review angles mid-flight)
- Single prompt (simpler user input)

**Verdict**: Flux-drive wins for repeatable, high-confidence reviews. LLM-Router wins for exploratory analysis where the review scope is unclear.

---

## Future Protocol Extensions

### 1. Feedback Loop (Agent Results → Triage Refinement)

After Stage 1, use findings to **re-score** Stage 2 agents. Example:
- Stage 1 flags "migration adds column without default" → boost fd-safety score (+2)
- Stage 1 disagrees on "this is a race condition" → boost fd-correctness (+3)

**Impact**: More precise expansion than adjacency-based heuristic.

### 2. Differential Review (compare against baseline)

When reviewing a diff, load findings from previous review of the base branch:
- Flag new findings (not in baseline)
- Flag resolved findings (in baseline, not in current)
- Flag recurring findings (in both)

**Impact**: Focus on regressions and improvements, not rehashing old issues.

### 3. Interactive Synthesis (user steers deduplication)

When agents disagree, present conflict to user mid-synthesis:
- "fd-safety says P0, fd-architecture says P2 — which severity?"
- "fd-quality and Project Agent suggest different fixes — which?"

**Impact**: User expertise improves synthesis quality without re-running reviews.

### 4. Knowledge Contribution (agents update knowledge mid-review)

Instead of silent post-synthesis compounding, allow agents to write knowledge entries during review:
- Agent discovers new pattern → writes to `knowledge/` with `provenance: discovered`
- Next agent in same stage can retrieve and use it

**Impact**: Knowledge accumulation happens within the review, not after.

### 5. Multi-Model Ensemble (run core agents with different models)

Launch fd-architecture with 3 models (Claude, GPT, Gemini), compare findings:
- Convergence across models → very high confidence
- Model-specific findings → flag for human review

**Impact**: Cross-model validation without full Oracle overhead.

---

## Conclusion

Flux-drive's core algorithm is a **4-phase deterministic orchestrator**:

1. **Static Triage**: Profile input, detect domains, score agents, select top-tier
2. **Parallel Launch**: Dispatch Stage 1, monitor, decide expansion, dispatch Stage 2
3. **Synthesis**: Parse indices, deduplicate, compute verdict, generate outputs
4. **Knowledge Accumulation**: Extract durable patterns, track provenance, decay stale entries

The protocol is domain-agnostic and runtime-agnostic. Clavain's implementation adds:
- Claude Code integration (Task API, plugin system)
- Domain profiles (11 domains, 330 review criteria, 23 agent specs)
- Content slicing (soft-prioritize with 80% threshold)
- Knowledge compounding (provenance tracking, decay)

To port to a different environment: replace Task API, remove optional components (domain detection, knowledge, slicing), preserve core invariants (structured outputs, staged dispatch, index-based synthesis).

**The key insight**: Multi-agent review is an **information retrieval problem**. Triage = recall (which agents to query?), Synthesis = precision (which findings to trust?). The protocol optimizes for both without sacrificing determinism.
