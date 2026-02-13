# Beads Issues for Flux-Drive and Flux-Gen Improvements

**Research Date:** 2026-02-13  
**Researcher:** File Search Agent  
**Context:** Token optimization and orchestrator improvements for flux-drive multi-agent review system

---

## Primary Issues

### 1. Clavain-62ek: Orchestrator Overhaul (CLOSED - P2)

**Status:** ✓ CLOSED (Implemented 2026-02-12)  
**Owner:** mk  
**Type:** task  
**Priority:** P2

**Description:**
Rewrite triage scoring (0-7 scale with domain boost), adaptive slot allocation (4-12 agents), and domain-aware staged expansion with adjacency map.

**Close Reason:**
Implemented: 0-7 scoring scale, adaptive 4-12 slot allocation, domain adjacency map expansion algorithm

**Dependencies:**
- → ✓ Clavain-0uzm: Add Step 1.0 domain classification to flux-drive triage (P1)

**Context:**
This was the orchestrator redesign that replaced the fixed 0-2 scoring with a more nuanced 0-7 scale and introduced adaptive slot allocation (4-12 agents instead of fixed cap at 8). The domain adjacency map enables intelligent expansion where related domains can boost agent selection.

**Key Achievements:**
- 0-7 scoring scale with domain boost (+1 for domain specialists)
- Adaptive slot allocation: 4-12 agents based on document complexity
- Domain-aware expansion using adjacency map (e.g., game-simulation → web-api for multiplayer games)

**Related Files:**
- `/root/projects/Clavain/config/flux-drive/domains/index.yaml` — 11 domain profiles with detection signals
- Domain profiles under `/root/projects/Clavain/config/flux-drive/domains/` (game-simulation.md, cli-tool.md, etc.)

---

### 2. Clavain-i1u6: Token Optimizations (OPEN - P2)

**Status:** ○ OPEN  
**Owner:** mk  
**Type:** task  
**Priority:** P2  
**Created:** 2026-02-12  
**Updated:** 2026-02-12

**Description:**
O3: write document to file, agents Read it. O1: per-agent sliced views for domain agents. O4: compress output format 50→15 lines. O5: conditional knowledge skip. Target 62% token reduction.

**Optimization Breakdown:**

#### O3: File Reference Pattern
Instead of injecting full document content into every agent prompt, write the document to a file and have agents Read it. This eliminates duplication across N agent prompts.

**Expected Savings:** ~30% (document content is largest prompt component)

#### O1: Universal Slicing
Provide per-agent sliced views of the document. Domain-specific agents only see sections relevant to their focus area. For example:
- fd-architecture sees architecture sections, not implementation details
- fd-performance sees hot paths and data flow, not UI code

**Expected Savings:** ~15% (reduces per-agent document size)

#### O4: Compress Output Format
Current YAML frontmatter + prose output is ~50 lines per finding. Compress to ~15 lines by:
- Removing redundant section headings
- Inline evidence (not separate Evidence: blocks)
- Shorter prose format

**Expected Savings:** ~10% (affects synthesis phase token usage)

#### O5: Conditional Knowledge Skip
When qmd returns no relevant knowledge entries, skip the entire "Knowledge Context" section from agent prompts instead of including empty placeholders.

**Expected Savings:** ~7% (per-agent reduction when knowledge is sparse)

**Total Target:** 62% token reduction across full flux-drive run

**Status:** Not started. Requires experimentation to validate that compressions don't degrade review quality.

---

## Related Open Issues

### Clavain-4cqy: flux-gen template improvements (P2)
Add 'What NOT to Flag' and success criteria to flux-gen agent templates. Blocked by Clavain-4jeg.

### Clavain-2mmc: Instruction ambiguities (P3)
Clarify flux-drive instruction ambiguities discovered during v0.5.4 quality review.

### Clavain-0d3a: flux-gen UX (P3)
Improve onboarding, integration, and documentation mentions for flux-gen command.

### Clavain-9tq: Fast-follow v2 features (P3)
8 deferred flux-drive v2 features (two-tier knowledge, ad-hoc generation, async deep-pass, etc.).

### Clavain-dm1a: Token budget controls (P4)
Add token budget controls + per-run cost reporting to flux-drive.

---

## Key Plans and Research

### Plan: 2026-02-09-flux-drive-fixes.md

**Summary:** Fixes to output format contract, trimming responsibility, tier naming, error handling, and timeout inconsistencies.

**Key Changes Implemented:**
1. **Output format override (P0)** — moved YAML frontmatter requirements to top of prompt template with explicit "IGNORE your default format" instruction
2. **Token trimming clarity (P1)** — moved trimming from agent prompt to orchestrator instructions
3. **Tier naming reconciliation (P2)** — renamed Tier 1/2/3 to Domain Specialists / Project Agents / Adaptive Reviewers
4. **Retry/error handling (P2)** — added retry logic for Task-dispatched agents
5. **Oracle timeout fix (P3)** — aligned timeout to 480s inner / 600s outer

**Status:** All 5 tasks completed.

---

### Plan: 2026-02-12-flux-gen-drive-integration.md

**Summary:** Auto-generation of project-specific agents when flux-drive detects domains, with staleness detection and agent lifecycle management.

**Key Features:**
1. **Staleness detection** — three-tier approach (hash → git → mtime) to detect when domain cache is outdated
2. **Auto-generation** — flux-drive automatically runs flux-gen when domains detected but no agents exist
3. **Agent provenance** — YAML frontmatter tracks which agents were auto-generated and for which domain
4. **Orphan detection** — identifies agents whose domain is no longer detected

**New Steps in flux-drive:**
- **Step 1.0.2:** Check staleness (pure, no side effects)
- **Step 1.0.3:** Re-detect and compare (pure, writes only cache)
- **Step 1.0.4:** Agent generation (side-effecting, writes agent files)

**Cache Format v1:**
```yaml
cache_version: 1
domains:
  - name: game-simulation
    confidence: 0.65
    primary: true
detected_at: '2026-02-12T10:15:32-08:00'
structural_hash: 'sha256:a1b2c3d4...'
```

**Structural Files Tracked:**
- package.json, Cargo.toml, go.mod, pyproject.toml, requirements.txt, Gemfile, build.gradle, project.godot, pom.xml, CMakeLists.txt, Makefile
- Extensions: .gd, .tscn, .unity, .uproject

**Performance Budget:**
- Hash check: < 100ms
- Git log: < 500ms
- Mtime fallback: < 200ms
- Full re-detection: < 10s
- Total overhead: < 2s typical, < 15s worst case

**Status:** Plan reviewed by fd-architecture, fd-correctness, fd-quality. All P0/P1 findings incorporated. Not yet implemented.

---

### Plan: 2026-02-12-wire-domain-detection-runtime.md

**Summary:** Wire domain detection results into agent prompt injection.

**Problem:** Domain detection runs and produces confidence scores, but agents never see the domain-specific review bullets from domain profiles.

**Solution:**
- **Step 2.1a** in launch.md — load domain profiles after knowledge retrieval
- **Domain Context section** in prompt template — inject domain-specific criteria bullets
- Cap at 3 domains to prevent prompt bloat

**Example Domain Context Injection:**
```
## Domain Context

This project is classified as: game-simulation (0.65), cli-tool (0.35)

Additional review criteria for fd-architecture in these project types:

### game-simulation
- Check for death spirals (feedback loops that compound over time)
- Verify fixed-timestep physics for determinism
- Review serialization for save/load consistency

### cli-tool
- Verify exit codes follow conventions (0=success, 1=error, 2=usage)
- Check for --help and --version flags
- Review stdin/stdout handling for pipes
```

**Status:** Plan complete. Implementation wired up with domain profiles in `/root/projects/Clavain/config/flux-drive/domains/`.

---

### Research: flux-drive-v2-architecture.md

**Summary:** Major architectural redesign of flux-drive agent roster and knowledge system.

**Key Changes:**
1. **Agent consolidation** — 19 specialized agents → 6 core agents + Oracle
   - Architecture & Design (merges architecture-strategist, pattern-recognition, code-simplicity)
   - Safety (security-sentinel, deployment-verification)
   - Correctness (data-integrity-reviewer, concurrency-reviewer)
   - Quality & Style (fd-code-quality, all 5 language reviewers — auto-detects language)
   - User & Product (fd-user-experience, product-skeptic, user-advocate, spec-flow-analyzer)
   - Performance (performance-oracle)
   - Oracle (cross-AI via GPT-5.2 Pro)

2. **Knowledge layer** — single-tier global knowledge at `config/flux-drive/knowledge/`
   - Minimal YAML frontmatter: `lastConfirmed`, `provenance`
   - Evidence anchors (file paths, line ranges, verification steps) in body
   - **Provenance tracking** — distinguishes `independent` confirmations from `primed` (prevents false-positive feedback loop)

3. **Compounding system** — silent post-synthesis hook
   - Sonnet model (~$0.025/run)
   - Reads YAML frontmatter (not prose)
   - Updates `lastConfirmed` only for `independent` re-confirmations
   - Decay: archives entries not independently confirmed in 10 reviews

4. **Triage changes** — simpler scoring for 6 agents vs 19, cap stays at 8

**Validation Status:** Self-reviewed by 7 agents + Oracle (2026-02-10). 6/7 convergence on provenance tracking requirement. All P0/P1 findings incorporated.

**Deferred Features (v2.x / v3):**
- Two-tier knowledge (project-local + global)
- Ad-hoc agent generation
- Async deep-pass agent
- 7th agent: Reliability/Deploy/Observability
- Claim-level convergence

**Review Findings:**
- **Strongest finding (6/7 convergence):** False-positive feedback loop without provenance tracking
- Oracle recommended: evidence anchors in knowledge entries, not just claims
- Consensus: Silent compounding (not visible Phase 5) for better UX

---

## Solutions and Learnings

### Solution: compounding-false-positive-feedback-loop-flux-drive-20260210.md

**Module:** flux-drive  
**Severity:** high  
**Problem:** Knowledge entries injected into agent context cause self-reinforcing false-positive loops.

**Root Cause:**
```
Finding compounded → injected into next review → agent re-confirms (primed by injection)
→ lastConfirmed updated → entry never decays → false positive permanent
```

**Solution:** Provenance tracking
- `provenance: independent` — agent found this without seeing the knowledge entry
- `provenance: primed` — agent had this entry in context when it re-flagged it

**Rule:** Only `independent` confirmations update `lastConfirmed`. Primed confirmations ignored for decay.

**Prevention:**
- Always track provenance when compounding LLM outputs across runs
- Never update freshness metrics based on primed re-confirmations
- Include evidence anchors (file paths, verification steps) so entries can be validated
- Design retraction mechanisms before building compounding systems

**Discovery:** 7-agent self-review (6/7 converged) + Oracle (GPT-5.2 Pro) confirmed.

---

### Solution: oracle-browser-output-lost-flux-drive-20260211.md

**Module:** flux-drive  
**Severity:** high  
**Problem:** Oracle browser mode output files contain only banner text, no GPT response.

**Symptoms:**
- Output file has only startup banner
- Sessions stuck as "running" in meta.json
- Model logs empty (0 lines)
- Exit code 124 from `timeout` wrapper

**Root Cause (3 compounding issues):**
1. Browser mode uses `console.log()` for response output — stdout redirect doesn't reliably capture it
2. External `timeout` sends SIGTERM before Oracle's cleanup code runs
3. `--write-output` wasn't being used (purpose-built for clean output)

**Solution:**
```bash
# Before (broken):
timeout 480 oracle --wait -p "..." > file.md 2>&1

# After (fixed):
oracle --wait --timeout 1800 --write-output file.md -p "..."
```

**Key Changes:**
1. `--write-output <path>` instead of `> file 2>&1`
2. Removed external `timeout` wrapper
3. Added `--timeout 1800` (Oracle's internal timeout)

**Prevention:**
- Always use `--write-output` for Oracle browser mode
- Never wrap Oracle with external `timeout`
- Budget 30 minutes for GPT-5.2 Pro reviews (`--timeout 1800`)

---

## Domain Detection System

### Domain Profiles (11 total)

Located at `/root/projects/Clavain/config/flux-drive/domains/`:
1. **game-simulation** — game engines, state machines, tick systems
2. **ml-pipeline** — training, inference, model artifacts
3. **web-api** — REST, GraphQL, gRPC endpoints
4. **cli-tool** — command-line interfaces, subcommands
5. **mobile-app** — iOS, Android, React Native, Flutter
6. **embedded-systems** — firmware, HAL, drivers, RTOS
7. **library-sdk** — public APIs, semver, backward compatibility
8. **data-pipeline** — ETL, Airflow, DBT, streaming
9. **claude-code-plugin** — .claude-plugin structure, hooks, skills
10. **tui-app** — Bubble Tea, Ratatui, terminal UIs
11. **desktop-tauri** — Tauri, Electron, webview-based desktop apps

### Detection Signals

Each domain profile has 4 signal types:
- **Directories:** e.g., `game/`, `simulation/`, `ecs/`, `tick/`
- **Files:** e.g., `*.gd`, `project.godot`, `*.tscn`
- **Frameworks:** e.g., godot, unity, bevy, pygame
- **Keywords:** e.g., tick_rate, delta_time, storyteller, death_spiral

### Detection Script

`scripts/detect-domains.py` — deterministic scorer (265 lines, 32 unit tests)

**Modes:**
- Default: scan project, write cache
- `--json`: output JSON to stdout
- `--no-cache`: force re-scan
- `--check-stale`: lightweight staleness check (Tier 1: hash, Tier 2: git, Tier 3: mtime)

**Exit Codes:**
- 0: Cache exists and is fresh (or `override: true`)
- 1: No domains detected
- 2: Fatal error (script crash, missing index.yaml)
- 3: Cache is stale (structural changes detected)
- 4: No cache exists (first run)

---

## Token Optimization Deep Dive

### Current Token Usage Breakdown (estimated)

Based on flux-drive Phase 2 (launch) for a typical 8-agent run reviewing a 2000-line document:

| Component | Tokens/Agent | Total (8 agents) | % of Total |
|-----------|--------------|------------------|------------|
| Document content | ~3,000 | ~24,000 | 45% |
| System prompt (agent .md) | ~800 | ~6,400 | 12% |
| Output format instructions | ~400 | ~3,200 | 6% |
| Knowledge context (5 entries) | ~600 | ~4,800 | 9% |
| Domain context | ~200 | ~1,600 | 3% |
| Project context (CLAUDE.md, AGENTS.md) | ~1,000 | ~8,000 | 15% |
| Token optimization instructions | ~150 | ~1,200 | 2% |
| Task prompt preamble | ~300 | ~2,400 | 5% |
| Misc (retry handling, error messages) | ~100 | ~800 | 1% |
| **Total input** | ~6,550 | ~52,400 | 100% |

**Output tokens:** ~4,000 per agent (frontmatter + findings) × 8 = ~32,000

**Grand Total:** ~84,400 tokens per flux-drive run (input + output)

### O3: File Reference Pattern

**Current:** Document content injected into every agent prompt (3,000 tokens × 8 = 24,000 tokens)

**Proposed:**
```markdown
## Document to Review

Read the document from: {REVIEW_DIR}/document.md

Use the Read tool to access the full content. Focus on sections relevant to your domain.
```

**Savings:** 24,000 - (100 × 8) = 23,200 tokens (~44% of input, ~27% of total)

**Trade-off:** Each agent now makes a Read tool call, adding latency (but can be parallelized).

### O1: Universal Slicing

**Current:** Full document (3,000 tokens) sent to every agent regardless of focus

**Proposed:** Orchestrator slices document based on agent focus:
- fd-architecture: architecture sections, design decisions
- fd-safety: auth, secrets, deployment, trust boundaries
- fd-correctness: data flow, concurrency, transactions
- fd-quality: implementation files only (skip architecture docs)
- fd-user-product: user flows, UI, product specs
- fd-performance: hot paths, data structures, algorithms

**Example Slicing:**
- Architecture agent: 2,000 tokens (sections: Architecture, Design, Patterns)
- Safety agent: 1,500 tokens (sections: Auth, Deployment, Security)
- Correctness agent: 1,800 tokens (sections: Data Model, Transactions, Async)
- Quality agent: 2,500 tokens (full implementation, skip high-level design)
- User agent: 1,200 tokens (sections: User Flows, UX, Features)
- Performance agent: 1,000 tokens (sections: Performance, Scaling)

**Average:** ~1,667 tokens per agent (down from 3,000)

**Savings:** (3,000 - 1,667) × 8 = 10,664 tokens (~20% of input, ~13% of total)

**Trade-off:** Requires heuristics for which sections match which agent. Risk of over-filtering.

### O4: Compress Output Format

**Current Format (50 lines):**
```yaml
---
agent: fd-architecture
tier: domain
issues:
  - id: P0-1
    severity: P0
    section: "Section Name"
    title: "Short description of the issue"
improvements:
  - id: IMP-1
    title: "Short description"
    section: "Section Name"
verdict: safe
---

### Summary (3-5 lines)
[Top findings]

### Issues Found
**P0-1: Short description** (Section Name)
[Detailed explanation]

Evidence: [file paths, line numbers]

### Improvements Suggested
**IMP-1: Short description** (Section Name)
[Rationale]

### Overall Assessment
[1-2 sentences]
```

**Proposed Compressed Format (15 lines):**
```yaml
---
agent: fd-architecture
verdict: safe
issues:
  - P0-1|Section Name|Short description
improvements:
  - IMP-1|Section Name|Short description
---

Summary: [Top findings in 2-3 lines]

P0-1: [Detailed explanation with inline evidence: file.go:47-52]

IMP-1: [Rationale in 1-2 lines]

Overall: [1 sentence]
```

**Savings:** ~35 lines × 50 chars/line = 1,750 chars ≈ 440 tokens per agent × 8 = 3,520 tokens (~4% of total)

**Trade-off:** Less human-readable, harder to parse. Synthesis phase needs updated parser.

### O5: Conditional Knowledge Skip

**Current:** Knowledge Context section always present, even when qmd returns 0 entries:
```markdown
## Knowledge Context

No relevant past findings for this review.
```

**Proposed:** Omit section entirely when empty.

**Savings:** ~100 tokens × 8 agents = 800 tokens (~1% of total)

**Additional:** When <3 knowledge entries returned, skip the "retrieval notes" preamble (saves ~50 tokens/agent).

### Combined Savings Estimate

| Optimization | Tokens Saved | % Reduction |
|--------------|--------------|-------------|
| O3: File reference | 23,200 | 27% |
| O1: Universal slicing | 10,664 | 13% |
| O4: Output compression | 3,520 | 4% |
| O5: Knowledge skip | 800 | 1% |
| **Total** | **38,184** | **45%** |

**Revised Total:** 84,400 - 38,184 = 46,216 tokens per run

**Note:** Original target was 62% reduction (52,296 tokens saved). Achieving this requires aggressive O1 slicing (avg 1,200 tokens/agent instead of 1,667) or additional optimizations not yet specified.

---

## Implementation Priorities

### P0 (Blocking)
None currently. Clavain-62ek orchestrator overhaul is complete.

### P1 (High Impact)
None currently.

### P2 (Next Up)
1. **Clavain-i1u6: Token optimizations** — 45-62% token reduction, significant cost savings at scale
2. **Clavain-4cqy: flux-gen template improvements** — improve agent quality (blocked by Clavain-4jeg)

### P3 (Nice to Have)
1. **Clavain-2mmc: Instruction clarifications** — improve reliability
2. **Clavain-0d3a: flux-gen UX** — improve adoption
3. **Clavain-9tq: Fast-follow v2 features** — 8 deferred features from v2 redesign

### P4 (Long-term)
1. **Clavain-dm1a: Token budget controls** — per-run cost tracking

---

## Key Insights

### 1. Orchestrator Maturity
The orchestrator redesign (Clavain-62ek) is complete and represents a significant advancement:
- 0-7 scoring scale (more nuanced than 0-2)
- Adaptive 4-12 slot allocation (vs fixed cap at 8)
- Domain adjacency map expansion
- 11 domain profiles fully populated

The foundation is solid for token optimization work.

### 2. Token Optimization is High-Leverage
Clavain-i1u6 targets 62% reduction. Even conservative estimates (45%) would halve costs:
- Current: ~84k tokens/run
- With O3+O1+O4+O5: ~46k tokens/run
- At scale (100 runs/month): 3.8M tokens saved/month

### 3. Provenance Tracking is Critical
The compounding false-positive feedback loop (discovered via 7-agent self-review) is the most dangerous failure mode of any LLM compounding system. Provenance tracking (`independent` vs `primed`) is the key invariant.

### 4. Evidence Anchors Prevent Folklore
Oracle's strongest recommendation: knowledge entries MUST include file paths, line ranges, and verification steps. Without these, entries become unverifiable claims that can't be challenged.

### 5. Staleness Detection is Clever
Three-tier approach (hash → git → mtime) provides:
- < 100ms response time (Tier 1 hash)
- Graceful degradation (git failure → mtime fallback)
- High accuracy (structural files + extensions)

### 6. Domain System is Comprehensive
11 domain profiles with 4 signal types (directories, files, frameworks, keywords) cover a wide range of project types. The injection criteria are now wired into runtime (Step 2.1a).

---

## Recommendations

### For Clavain-i1u6 (Token Optimizations)

1. **Start with O3 (file reference)** — highest impact (27%), lowest risk
   - Implement: Write document to temp file, replace content injection with Read instruction
   - Test: Verify all agents still produce equivalent findings
   - Measure: Actual token savings vs estimate

2. **Add O5 (knowledge skip)** — lowest risk, easy win (1%)
   - Implement: Conditional template rendering
   - No quality risk

3. **Experiment with O1 (universal slicing)** — high impact (13%), moderate risk
   - Start conservative: only slice for clearly non-overlapping domains
   - Validate: Run side-by-side with unsliced for 5 test cases
   - Tune: Adjust slicing heuristics based on false negatives

4. **Defer O4 (output compression)** — low impact (4%), breaks tooling
   - Synthesis parser needs rewrite
   - Human readability trade-off
   - Consider only if O3+O1+O5 don't reach 62% target

5. **Measure and iterate**
   - Add token counters to flux-drive (track input/output per agent)
   - Log per-optimization savings
   - A/B test quality: does slicing hurt recall?

### For Future Work

1. **Implement flux-gen auto-generation** (plan ready, reviewed, not yet coded)
2. **Add token budget controls** (Clavain-dm1a) — per-run cost tracking and caps
3. **Revisit v2 deferred features** after 20+ reviews with current system
4. **Consider O6: Shared document cache** — if multiple reviews target same project in short time window

---

## Appendix: File Locations

### Beads Database
- `/root/projects/Clavain/.beads/beads.db` — SQLite database with all beads

### Plans
- `/root/projects/Clavain/docs/plans/2026-02-09-flux-drive-fixes.md`
- `/root/projects/Clavain/docs/plans/2026-02-12-flux-gen-drive-integration.md`
- `/root/projects/Clavain/docs/plans/2026-02-12-wire-domain-detection-runtime.md`

### Research
- `/root/projects/Clavain/docs/research/flux-drive-v2-architecture.md`
- `/root/projects/Clavain/docs/research/flux-drive/` (many subdirs with review outputs)

### Solutions
- `/root/projects/Clavain/docs/solutions/best-practices/compounding-false-positive-feedback-loop-flux-drive-20260210.md`
- `/root/projects/Clavain/docs/solutions/integration-issues/oracle-browser-output-lost-flux-drive-20260211.md`

### Config
- `/root/projects/Clavain/config/flux-drive/domains/index.yaml` — domain detection signals
- `/root/projects/Clavain/config/flux-drive/domains/*.md` — 11 domain profiles

### Scripts
- `/root/projects/Clavain/scripts/detect-domains.py` — domain classification script

### Skills
- `/root/projects/Clavain/skills/flux-drive/SKILL.md` — main flux-drive skill
- `/root/projects/Clavain/skills/flux-drive/phases/launch.md` — agent dispatch logic
- `/root/projects/Clavain/skills/flux-drive/phases/synthesize.md` — convergence and dedup
- `/root/projects/Clavain/skills/flux-gen/SKILL.md` — project agent generator

---

**End of Analysis**
