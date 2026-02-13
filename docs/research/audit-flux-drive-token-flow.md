# Flux-Drive Token Flow Audit

**Date**: 2026-02-13  
**Scope**: Full token flow analysis of flux-drive and flux-gen systems in Clavain  
**Method**: Systematic file reading, line counting, and content analysis

## Executive Summary

Flux-drive loads content in **5 distinct phases** with a mix of eager (session-start) and lazy (on-demand) loading. Total token budget for a typical review spans **15k-50k tokens** depending on configuration, with the majority consumed by agent prompts containing full document content.

**Key findings:**
1. **Session-start overhead**: 1,000 tokens (using-clavain skill) loaded eagerly every session
2. **Phase files**: 10,700 words (~14k tokens) loaded lazily as phases progress
3. **Domain profiles**: 10,200 words (~13.5k tokens) but only 1-3 profiles loaded per review
4. **Agent prompts**: Each agent receives 2k-10k tokens depending on document size
5. **Knowledge layer**: Currently 1,000 words (~1.3k tokens), grows over time
6. **Redundancy**: Full document content repeated N times (once per agent)

---

## 1. Session-Start Injection (Eager Loading)

### using-clavain Skill
- **File**: `skills/using-clavain/SKILL.md`
- **Size**: 42 lines, ~300 words
- **Injected via**: SessionStart hook → `additionalContext` JSON field
- **Loaded**: Every session start
- **Token cost**: ~400 tokens
- **Purpose**: Quick reference table for routing to skills/agents/commands

### using-clavain Routing Tables
- **File**: `skills/using-clavain/references/routing-tables.md`
- **Size**: 88 lines, ~700 words
- **Loaded**: On-demand when user reads the file (NOT injected at session start)
- **Token cost**: ~900 tokens
- **Purpose**: Full routing tables by stage/domain/concern

**Total session-start overhead**: ~400 tokens (just SKILL.md)

---

## 2. Flux-Drive Orchestration Flow (Lazy Loading)

### 2.1 Entry Point: SKILL.md
- **File**: `skills/flux-drive/SKILL.md`
- **Size**: 546 lines, ~3,700 words
- **Loaded**: When `/flux-drive` command is invoked
- **Token cost**: ~5,000 tokens
- **Content**:
  - Input detection and path derivation
  - Phase 1: Analyze + Static Triage (domain detection, agent scoring)
  - Phase 2-4: Delegates to separate phase files
  - Agent roster (Plugin, Project, Cross-AI)
  - Scoring examples and dynamic slot allocation

**Progressive loading instruction**: "Read each phase file when you reach it — not before."

### 2.2 Phase Files (Loaded Sequentially)

| Phase | File | Lines | Words | Tokens | When Loaded |
|-------|------|-------|-------|--------|-------------|
| Launch (Task) | `phases/launch.md` | 428 | ~3,000 | ~4,000 | Step 2.0 (after triage) |
| Launch (Codex) | `phases/launch-codex.md` | 118 | ~800 | ~1,100 | Step 2.0 (if clodex mode) |
| Synthesize | `phases/synthesize.md` | 368 | ~2,600 | ~3,500 | Step 3.0 (after agents complete) |
| Cross-AI | `phases/cross-ai.md` | 30 | ~200 | ~300 | Step 4.0 (if Oracle in roster) |
| Shared Contracts | `phases/shared-contracts.md` | 97 | ~700 | ~900 | Referenced by launch phases |

**Total phase file overhead**: ~10,700 words = ~14,000 tokens (but loaded sequentially, not all at once)

**Optimization opportunity**: Phases are read sequentially, so only the active phase consumes tokens at any given time. Peak single-phase overhead is ~4,000 tokens (launch.md).

---

## 3. Domain Detection & Classification (Lazy, Cached)

### 3.1 Detection Script
- **File**: `scripts/detect-domains.py`
- **Size**: 695 lines
- **Loaded**: Never read as text — executed as subprocess
- **Execution time**: <10 seconds (heuristic matching, no LLM)
- **Cache**: `.claude/flux-drive.yaml` in project root
- **Staleness check**: <100ms (hash → git → mtime fallback)

### 3.2 Domain Index
- **File**: `config/flux-drive/domains/index.yaml`
- **Size**: 454 lines, ~2,000 words
- **Loaded**: Only by detect-domains.py (not by Claude)
- **Token cost**: 0 (not injected into prompts)
- **Content**: Signal patterns for 11 domains (directories, files, frameworks, keywords)

### 3.3 Domain Profiles (Selective Loading)

11 domain profiles, each ~100 lines:

| Domain | Lines | Purpose |
|--------|-------|---------|
| game-simulation | 115 | 5 agents × 5-6 bullets each + 3 agent specs |
| ml-pipeline | 115 | Similar structure |
| web-api | 100 | Similar structure |
| cli-tool | 100 | Similar structure |
| (7 more) | ~100 each | Similar structure |

**Total available**: 1,130 lines, ~10,200 words = ~13,500 tokens

**Actually loaded per review**:
- 1-3 domains detected per project (capped at 3)
- Only relevant `### fd-{agent}` sections extracted
- Typical injection: 3-5 bullets per agent × 5 agents × 2 domains = ~300 words = ~400 tokens

**Optimization**: Domain profiles are read but only small subsections are injected. The full 13.5k token corpus is NOT loaded into any prompt.

---

## 4. Agent Prompts (Per-Agent Token Budget)

### 4.1 Core Review Agents (Plugin Agents)

7 fd-* agents, loaded via `subagent_type`:

| Agent | Lines | Words | Base Tokens | With Domain Context |
|-------|-------|-------|-------------|-------------------|
| fd-architecture | 81 | ~700 | ~900 | +300 = 1,200 |
| fd-safety | 82 | ~700 | ~900 | +300 = 1,200 |
| fd-correctness | 83 | ~700 | ~900 | +300 = 1,200 |
| fd-quality | 88 | ~750 | ~1,000 | +300 = 1,300 |
| fd-user-product | 84 | ~700 | ~900 | +300 = 1,200 |
| fd-performance | 88 | ~750 | ~1,000 | +300 = 1,300 |
| fd-game-design | 110 | ~950 | ~1,250 | +300 = 1,550 |

**Total agent definition overhead**: 616 lines, ~5,400 words = ~7,000 tokens (but loaded by Claude Code, not visible in prompt)

**Per-agent prompt structure** (from launch.md template):
```
## CRITICAL: Output Format Override         ~200 words
## Review Task                              ~50 words
## Knowledge Context                        ~200 words (5 entries × 40 words)
## Domain Context                           ~200 words (injection criteria)
## Project Context                          ~50 words
## Document to Review                       VARIABLE (2k-50k+ tokens)
## Your Focus Area                          ~100 words
```

**Total per-agent overhead** (excluding document): ~800 words = ~1,000 tokens

**Document content**: Repeated N times (once per agent). For a 5-agent review of a 10k-token document:
- 5 agents × (1k overhead + 10k document) = **55k tokens total**
- This is the LARGEST token sink

### 4.2 Project Agents (Generated by flux-gen)

- **Template**: `commands/flux-gen.md` generates `.claude/agents/fd-{name}.md`
- **Structure**: Same as plugin agents (~100 lines each)
- **Loading**: Full content pasted into Task prompt (subagent_type: general-purpose)
- **Overhead**: +1k tokens per project agent (in addition to plugin agents)

### 4.3 Knowledge Layer Injection (Per-Agent)

- **Source**: `config/flux-drive/knowledge/*.md` (currently 7 files, ~1,000 words)
- **Retrieval**: qmd semantic search (5 entries max per agent)
- **Loaded**: On-demand during Phase 2 (Step 2.1)
- **Token cost per agent**: ~200 words × 5 entries = ~250 tokens
- **Growth**: Accumulates over time via post-synthesis compounding

**Entry format**:
```yaml
---
lastConfirmed: 2026-02-10
provenance: independent
---
Pattern description (1-3 sentences).

Evidence: file paths, symbols, line ranges.
Verify: 1-3 steps to confirm.
```

**Typical entry size**: 40-50 words = ~60 tokens

**Decay mechanism**: Entries not independently confirmed in 10 reviews (>60 days) → archived

---

## 5. Document/Diff Content (Largest Variable)

### 5.1 File Inputs
- **Full document**: Repeated once per agent
- **Trimming rules**: None by default (except for very large documents >1000 lines)
- **Pyramid scan** (500+ line documents): Adds ~500 words of section summaries, still includes full document

**Example**: 5-agent review of 30-page plan (15k tokens)
- 5 × 15k = **75k tokens** for document content alone
- Plus 5 × 1k overhead = 5k tokens
- **Total: 80k tokens**

### 5.2 Diff Inputs
- **Small diffs (<1000 lines)**: Full diff to all agents
- **Large diffs (1000+ lines)**: Soft-prioritize slicing via `config/flux-drive/diff-routing.md`

**Diff routing config**:
- **File**: `config/flux-drive/diff-routing.md`
- **Size**: 134 lines, ~750 words = ~1,000 tokens
- **Loaded**: On-demand when diff exceeds 1000 lines
- **Content**: File patterns + keywords per agent (fd-safety, fd-correctness, etc.)

**Slicing behavior**:
- Cross-cutting agents (fd-architecture, fd-quality): Always full diff
- Domain agents: Priority hunks (full) + context summaries (one-liner per file)
- **80% threshold**: If priority files cover ≥80% of diff, skip slicing

**Token savings from slicing**:
- Without slicing: 6 agents × 5k token diff = 30k tokens
- With slicing: 2 full (10k) + 4 sliced (4 × 2k priority + 4 × 0.5k summaries) = 10k + 10k = **20k tokens** (~33% reduction)

### 5.3 Repo Reviews (Directory Input)
- **Content**: README + build files + key source files (sampled during Step 1.0)
- **Size**: Varies wildly (2k-20k tokens depending on project)
- **Repeated**: Once per agent, like file inputs

---

## 6. Flux-Gen (Domain Agent Generator)

### 6.1 Entry Point
- **File**: `commands/flux-gen.md`
- **Size**: 194 lines, ~1,500 words = ~2,000 tokens
- **Loaded**: When `/flux-gen` command is invoked
- **Purpose**: Generate project-specific agents from domain profiles

### 6.2 Generation Process
1. Read cached domain detection (`.claude/flux-drive.yaml`)
2. Load domain profile(s) from `config/flux-drive/domains/{domain}.md`
3. Extract `## Agent Specifications` section
4. Generate `.claude/agents/fd-{name}.md` files using template

**Token cost**:
- Command file: 2k tokens (one-time load)
- Domain profile read: 1-2 profiles × 3k tokens = 3-6k tokens
- Generation: No LLM call needed (template substitution)

---

## 7. Token Flow Summary by Phase

### Phase 1: Analyze + Static Triage
**Loaded**:
- flux-drive/SKILL.md: 5,000 tokens
- Document/diff content: 2k-50k tokens (read once for profiling)
- Domain detection (if cache stale): 0 tokens (subprocess, not LLM)
- Domain profiles (for scoring): 3-6k tokens (1-3 profiles × 2-3k each)
- Agent roster: 0 tokens (just metadata)

**Total Phase 1**: ~10k-60k tokens (mostly document content)

### Phase 2: Launch
**Loaded**:
- phases/launch.md: 4,000 tokens
- OR phases/launch-codex.md: 1,100 tokens
- phases/shared-contracts.md: 900 tokens
- diff-routing.md (if slicing): 1,000 tokens
- Knowledge retrieval (per agent): 250 tokens × N agents

**Per-agent prompt** (N agents launched):
- Agent system prompt: 1,000 tokens (plugin) or 1,500 tokens (project)
- Domain context injection: 300 tokens
- Knowledge context: 250 tokens
- Template overhead: 1,000 tokens
- Document content: 2k-50k tokens

**Total Phase 2**: 5k + (N × document_size + 2.5k overhead)

**Example** (5 agents, 10k doc):
- 5k orchestration overhead
- 5 × (10k doc + 2.5k overhead) = 62.5k
- **Total: 67.5k tokens**

### Phase 3: Synthesize
**Loaded**:
- phases/synthesize.md: 3,500 tokens
- Agent outputs (Findings Index read): 50 lines × N agents = ~500 words = ~700 tokens
- Agent outputs (full prose, if needed): Variable (only for malformed outputs or conflict resolution)

**Total Phase 3**: ~5k tokens (orchestration + index reading)

### Phase 4: Cross-AI Comparison (Optional)
**Loaded**:
- phases/cross-ai.md: 300 tokens
- Oracle output (read): ~1k tokens

**Total Phase 4**: ~1.5k tokens

---

## 8. Optimization Opportunities

### 8.1 Redundant Full Document Content (HIGH IMPACT)
**Problem**: Each agent receives the full document, repeated N times.
- 5 agents × 15k doc = **75k tokens**
- Only ~10% of document is relevant to each agent's focus area

**Solution options**:
1. **Aggressive slicing** (like diff slicing): Each agent gets only relevant sections
2. **Shared context with focused summaries**: One full document + per-agent section highlights
3. **Token-efficient formats**: Compressed markdown, remove boilerplate

**Estimated savings**: 50-70% reduction (from 75k to 22k-37k tokens)

### 8.2 Domain Profile Loading (MEDIUM IMPACT)
**Problem**: Full domain profiles (100 lines each) are read, but only small subsections are injected.
- Read: 3 profiles × 3k tokens = 9k tokens
- Used: ~400 tokens (just injection criteria bullets)

**Solution**: Pre-extract injection criteria into separate files, skip full profile reads.

**Estimated savings**: 8k tokens per review

### 8.3 Knowledge Layer Growth (LOW IMPACT NOW, HIGH LATER)
**Problem**: Knowledge entries accumulate over time.
- Current: 7 entries × 60 tokens = ~420 tokens per agent
- After 100 reviews: ~50 entries → 3k tokens per agent × 5 agents = **15k tokens**

**Solution**: Stricter decay rules, cap at 10 entries per domain, archive more aggressively.

**Estimated savings**: Prevents future 15k token bloat

### 8.4 Phase File Consolidation (LOW IMPACT)
**Problem**: 5 separate phase files (14k tokens total) loaded sequentially.
- Not a problem now (sequential loading)
- But adds cognitive overhead (orchestrator must read 5 files)

**Solution**: Merge launch.md + synthesize.md into single orchestration file.

**Estimated savings**: 0 tokens (they're already sequential), but cleaner flow

### 8.5 Prompt Template Bloat (MEDIUM IMPACT)
**Problem**: Agent prompts have verbose output format instructions (~200 words per agent).
- 5 agents × 200 words = 1k tokens

**Solution**: Move output format to a shared reference, just include link.

**Estimated savings**: ~1k tokens per review

---

## 9. Token Budget Breakdown by Review Type

### Small File Review (single 500-line file, 2-3 agents)
- Session start: 400 tokens
- Phase 1 (triage): 5k + 2k doc = 7k tokens
- Phase 2 (launch): 5k + (3 agents × (2k doc + 2.5k overhead)) = 18.5k tokens
- Phase 3 (synthesis): 5k tokens
- **Total: ~31k tokens**

### Medium Plan Review (30-page doc, 5 agents)
- Session start: 400 tokens
- Phase 1: 5k + 15k doc = 20k tokens
- Phase 2: 5k + (5 agents × (15k doc + 2.5k overhead)) = 92.5k tokens
- Phase 3: 5k tokens
- **Total: ~118k tokens**

### Large Diff Review (2000-line diff, 6 agents, slicing active)
- Session start: 400 tokens
- Phase 1: 5k + 5k diff = 10k tokens
- Phase 2: 5k + (2 full × (5k diff + 2.5k) + 4 sliced × (2k priority + 2.5k)) = 5k + 15k + 18k = 38k tokens
- Phase 3: 5k tokens
- **Total: ~53k tokens** (vs 80k without slicing)

### Repo Review (directory input, 8 agents)
- Session start: 400 tokens
- Phase 1: 5k + 10k sampled content = 15k tokens
- Phase 2: 5k + (8 agents × (10k content + 2.5k overhead)) = 105k tokens
- Phase 3: 5k tokens
- **Total: ~125k tokens**

---

## 10. Comparison to Other Review Systems

### Traditional PR Review (single LLM pass)
- Full file content: 50k tokens
- Review prompt: 1k tokens
- **Total: 51k tokens**
- **Quality**: Lower (no domain specialization)

### Multi-agent without flux-drive (naive parallel)
- 5 agents × (50k doc + 500 token prompt) = 252k tokens
- **Problem**: No triage, no slicing, no coordination

### Flux-drive (this system)
- **Total: 53k-125k tokens** (depending on review type)
- **Quality**: Higher (domain-aware agents, knowledge layer, synthesis)
- **Cost**: 2-3× token overhead vs single-pass, but 50% less than naive multi-agent

---

## 11. Future Growth Projections

### Knowledge Layer (After 100 Reviews)
- Current: 7 entries, 1k total words
- After 100 reviews: ~50 entries (assuming 50% compound, 50% decay)
- Per-agent injection: 5 entries × 60 tokens = 300 tokens (capped)
- **Growth: +200 tokens per agent** (from 250 to 300)

### Domain Profiles (Stable)
- 11 domains × 100 lines = 1,130 lines (complete)
- No growth expected (profiles are static definitions)

### Agent Roster (Slow Growth)
- Core: 7 fd-* agents (stable)
- Project: 1-3 per project (generated once)
- **Growth: ~1 new core agent per year**

---

## 12. Recommendations (Priority Order)

### P0: Reduce Document Repetition (50-70% token savings)
Implement document slicing for agents (like current diff slicing):
- Each agent gets: Summary + relevant sections + other sections as 1-liners
- Routing rules: Map document sections to agent domains

**Effort**: 2-3 days (extend diff-routing.md logic to structured docs)
**Impact**: 50k → 25k tokens for typical 5-agent review

### P1: Lazy-Load Domain Profiles (8k token savings)
Extract injection criteria into separate files:
- `domains/{domain}-injection.yaml` — just the bullets
- Skip reading full 100-line profiles unless generating agents

**Effort**: 1 day (script to extract, update loader)
**Impact**: 9k → 1k tokens for domain context loading

### P2: Compress Phase Files (0 token savings, better UX)
Merge launch.md + synthesize.md into `orchestration.md`:
- Single source of truth for dispatch flow
- Easier to maintain

**Effort**: 2 days (careful merge, test suite updates)
**Impact**: No token savings, but simpler cognitive model

### P3: Knowledge Layer Caps (prevents future 15k bloat)
- Cap at 10 entries per domain (not 50)
- Decay after 5 reviews (not 10)
- Archive more aggressively

**Effort**: 1 day (update compounding agent rules)
**Impact**: Prevents future 15k token bloat

### P4: Shared Output Format Reference (1k token savings)
Move output format instructions to a reference file:
- `phases/output-format.md`
- Agent prompts just say "Use format from output-format.md"

**Effort**: 1 day (extract, update templates)
**Impact**: 1k tokens per review

---

## 13. Appendix: File Inventory

### Core Orchestration Files
- `skills/flux-drive/SKILL.md`: 546 lines, 5k tokens
- `phases/launch.md`: 428 lines, 4k tokens
- `phases/launch-codex.md`: 118 lines, 1.1k tokens
- `phases/synthesize.md`: 368 lines, 3.5k tokens
- `phases/cross-ai.md`: 30 lines, 300 tokens
- `phases/shared-contracts.md`: 97 lines, 900 tokens

### Configuration Files
- `config/flux-drive/domains/index.yaml`: 454 lines, 0 tokens (not injected)
- `config/flux-drive/domains/*.md`: 11 files, 1,130 lines, 13.5k tokens (selectively loaded)
- `config/flux-drive/knowledge/*.md`: 7 files, 134 lines, 1.3k tokens (semantic search)
- `config/flux-drive/diff-routing.md`: 134 lines, 1k tokens (on-demand)

### Agent Definitions
- `agents/review/fd-*.md`: 7 files, 616 lines, 7k tokens (loaded by Claude Code)
- `.claude/agents/fd-*.md`: 0-10 files (generated per-project)

### Support Scripts
- `scripts/detect-domains.py`: 695 lines (subprocess, no token cost)
- `scripts/dispatch.sh`: Template system (subprocess)

### Session Start
- `skills/using-clavain/SKILL.md`: 42 lines, 400 tokens (eager)
- `hooks/session-start.sh`: Injects using-clavain content

---

## 14. Conclusion

Flux-drive's token flow is **dominated by document content repetition** (50k-75k tokens) across N agents. The orchestration overhead is reasonable (~15k tokens for all phases), and domain/knowledge layers are efficiently loaded on-demand.

The system trades token efficiency for quality: multiple specialized agents produce better reviews than a single generalist pass, but at 2-3× token cost. **The highest-impact optimization is document slicing** (like the current diff slicing), which could reduce token usage by 50-70% while preserving review quality.

Current growth trajectory is sustainable — knowledge layer is capped via decay, domain profiles are complete, and agent roster growth is slow. The system will scale well to 100+ reviews without major token bloat.
