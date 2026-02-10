# Flux-Drive v2 Architecture: Synthesis Report

**Reviewed by**: 7 agents (architecture-strategist, product-skeptic, performance-oracle, code-simplicity-reviewer, fd-user-experience, user-advocate, spec-flow-analyzer)
**Oracle**: Completed (GPT-5.2 Pro, 17min) — initial launch failed (CWD error), second launch succeeded
**Date**: 2026-02-10
**Document**: `docs/research/flux-drive-v2-architecture.md`

---

## Verdicts

| Agent | Verdict | Summary |
|-------|---------|---------|
| architecture-strategist | needs-changes | Split Safety & Correctness, decouple Phase 5 from prose output, add provenance tracking |
| product-skeptic | needs-validation | LOW confidence — decompose into 3 independent projects, fix P0/P1 backlog first |
| performance-oracle | needs-changes | Serial qmd calls add 15-35s (P0), token cost may double, deep-pass doesn't scale |
| code-simplicity-reviewer | proceed-with-major-cuts | Cut to MVP: 5 agents + single-tier knowledge + immediate compounding only |
| fd-user-experience | needs-changes | Phase 5 must be silent, ad-hoc agents need visibility/rejection, create /flux-deep |
| user-advocate | needs-changes | No usage data, project agent failure undiagnosed, compounding benefits invisible |
| spec-flow-analyzer | needs-changes | 4 P0 gaps (knowledge conflict, false positive loop, no ad-hoc quality gate, deep-pass authority) |

**Consensus verdict: NEEDS MAJOR SCOPE REDUCTION + VALIDATION**

---

## Top Findings by Convergence

### Convergence 7/7: Scope Down to MVP — Ship Incrementally

Every agent independently concluded the design bundles too many independent changes into one release. The convergent recommendation is to decompose into separable pieces and ship the smallest viable increment first.

**Who said what:**
- **product-skeptic**: "Decompose and validate incrementally. Shipping these as three independent experiments is strictly better than a monolith."
- **code-simplicity-reviewer**: "Five independently valuable changes bundled as one release. Cut to MVP: 5 agents + single-tier knowledge + immediate compounding."
- **user-advocate**: "Build roster simplification now. Defer knowledge layer until usage frequency is measured."
- **architecture-strategist**: Agrees the 5 components are separable but couples merge + knowledge injection as a pair.
- **spec-flow-analyzer**: Mapped 9 user flows — most complex ones only exist because the bundled design creates circular dependencies between subsystems.
- **performance-oracle**: "The architecture should specify model tiering and caps to prevent cost bloat."
- **fd-user-experience**: "The user should not perceive 5 phases."

### Convergence 6/7: False Positive Feedback Loop Is the Most Dangerous Failure Mode

Six agents identified the compounding system's self-reinforcing false positive problem as critical or major.

**The loop**: Finding compounded → injected into next review → agent re-confirms (primed by injection) → lastConfirmed updated → entry never decays → false positive permanent.

**Who flagged it:**
- **spec-flow-analyzer** (P0-2): "No correction or retraction mechanism for compounded knowledge entries"
- **architecture-strategist** (P1-2): "Compounding agents can write to both tiers simultaneously, creating circular reinforcement"
- **user-advocate** (M-1): "Knowledge layer trust problem — conflates confidence with staleness"
- **product-skeptic**: "No evidence that compounding adds value, but clear risk it adds noise"
- **performance-oracle**: Identified that knowledge injection increases per-agent token spend by ~1,500 tokens
- **fd-user-experience** (P1-3): "Knowledge entries injected per agent are entirely invisible — no way for user to understand what influenced findings"

**Convergent fix**: Track provenance (independent discovery vs. knowledge-primed confirmation). Only independent confirmations update lastConfirmed. Add retraction mechanism.

### Convergence 5/7: Split Safety & Correctness Into Two Agents

Five agents agreed that merging security + data-integrity + concurrency + deployment into one agent is too aggressive.

**Who flagged it:**
- **architecture-strategist** (P0-1): "Four genuinely different analytical modes. Knowledge injection adds facts, not analytical discipline."
- **product-skeptic** (Critical): "Concurrency-reviewer alone is 606 lines with 20KB of inline code examples. Compressing to 1/4 of a generalist's attention loses signal."
- **spec-flow-analyzer** (P2-4): "Merged agents lose specificity signals — triage cannot distinguish sub-domains."
- **performance-oracle** (P1-1): "Safety & Correctness raw source material is 26.7KB — even at 50% compression, 13KB/4,000 tokens."
- **user-advocate** (M-3): "Users who learned the roster lose predictability."

**Convergent fix**: Split into Safety (security + deployment) and Correctness (data integrity + concurrency) = 6 core agents, still within cap of 6.

### Convergence 5/7: Phase 5 Must Be Silent/Background

**Who flagged it:**
- **fd-user-experience** (IMP-1): "Make Phase 5 silent by default with opt-in summary via flag"
- **architecture-strategist** (P1-4): "Run Phase 5 in background after presenting results — fire-and-forget"
- **user-advocate** (Mi-1): "Phase 5 adds latency with deferred payoff"
- **performance-oracle** (P2-1): "Compounding is cheap (~$0.025 at Sonnet) — just make it silent"
- **code-simplicity-reviewer**: "Make compounding a post-Phase-4 hook instead of a 5th phase"

### Convergence 4/7: No Usage Data Validates the Compounding Investment

- **product-skeptic** (Critical): "11 runs over 3 days, all by the plugin author. Zero external usage data."
- **user-advocate** (C-1): "If the median user runs flux-drive 1-3 times per month, compounding is overhead without payoff."
- **code-simplicity-reviewer**: "Prove immediate compounding works before building two-tier knowledge, deep-pass, and ad-hoc generation."
- **spec-flow-analyzer** (P1-1): "First run on new project is the most common initial experience and is completely unspecified."

### Convergence 4/7: Defer Two-Tier Knowledge — Start Single-Tier

- **code-simplicity-reviewer**: "Zero v1 data on what patterns are project-specific vs universal. Start with single-tier global knowledge."
- **product-skeptic**: "Can be evaluated independently. Works with 19 agents or 5."
- **user-advocate** (M-5): "Multi-project knowledge graduation is a leaky abstraction."
- **spec-flow-analyzer** (P0-1): "No defined precedence when project-local and Clavain-global knowledge contradict."

### Convergence 4/7: Defer Ad-hoc Agent Generation

- **product-skeptic** (Major): "Adding a new agent is creating one markdown file. Ad-hoc generation introduces three new subsystems to avoid this."
- **code-simplicity-reviewer**: "The problem statement says you have too many agents. The solution isn't to dynamically generate more."
- **spec-flow-analyzer** (P0-3): "No deletion, deprecation, or quality-gate mechanism for ad-hoc agents."
- **user-advocate** (C-2): "Project agent failure not post-mortemed — replacing with ad-hoc generation may repeat the same failure."

### Convergence 3/7: Defer Async Deep-Pass

- **code-simplicity-reviewer**: "This is a v3 feature masquerading as v2."
- **performance-oracle** (P1-2): "Deep-pass scanning all historical output is O(reviews * agents) and grows unbounded. Hits 200K context limit at ~100 reviews."
- **product-skeptic**: "Do not build ad-hoc generation + graduation until evidence of roster gaps."

---

## Performance Impact Summary

| Metric | v1 | v2 (unoptimized) | v2 (optimized MVP) |
|--------|-----|-------------------|---------------------|
| Token overhead per review | ~10,000 | ~30,000 | ~15,000-20,000 |
| Cost per review (Opus) | ~$0.22 | ~$0.45-0.60 | ~$0.25-0.35 |
| Triage latency | 30-60s | +15-35s (serial qmd) | +3-5s (1 batch qmd call) |
| Compounding cost | $0 | ~$0.23 (Opus) | ~$0.025 (Sonnet) |
| Deep-pass scaling | N/A | Breaks at ~50 reviews | Deferred to v3 |

---

## Recommended MVP v2.0

Based on the convergence across all 7 agents, the recommended scope is:

### Ship Now (MVP v2.0)

1. **6 core agents** (splitting Safety & Correctness into Safety + Correctness)
   - Architecture & Design
   - Safety (security + deployment)
   - Correctness (data integrity + concurrency)
   - Quality & Style (code quality + language reviewers)
   - User & Product (UX, flows, value prop)
   - Performance
   - \+ Oracle (cross-AI, always offered)
2. **Single-tier knowledge** in Clavain repo (`config/flux-drive/knowledge/`)
3. **Immediate compounding** as silent post-Phase-4 hook (not a "Phase 5")
   - Model: Sonnet (classification task, not deep analysis)
   - Reads structured agent YAML frontmatter, not synthesis prose
   - Simple format: `lastConfirmed` + markdown body only
4. **qmd retrieval** batched/pipelined with agent launch (not during triage)
   - Cap: 5 entries per agent
5. **Provenance tracking** on knowledge confirmations (independent vs. primed)
6. **First-run bootstrap** explicitly described (v1-equivalent, creates knowledge dir, tells user)

### Defer to v2.x

- Two-tier knowledge (wait for data showing project vs. global distinction matters)
- Ad-hoc agent generation (wait for users to hit roster gaps; manually add 7th agent if needed)
- Async deep-pass (prove immediate compounding works first)
- Complex frontmatter metadata (domain, source, confidence, convergence, origin)
- Knowledge graduation pipeline
- Agent cap reduction to 6 (keep at 8 or make dynamic based on document complexity)

### Pre-requisites (Fix Before v2)

Per product-skeptic and spec-flow-analyzer, fix the existing P0/P1 backlog first:
- YAML frontmatter contract fragility (self-review P0, 3/5 agents agreed)
- Progress feedback during 3-5 minute wait (self-review P0 UX)
- GitHub Actions security issues (script injection, danger-full-access)
- Synthesis report template (primary deliverable has no template)

---

## Open Questions Resolved

| # | Question | Recommendation |
|---|----------|---------------|
| 1 | Knowledge injection token budget | **5 entries per agent**, not 10 (performance-oracle) |
| 2 | Ad-hoc agent graduation criteria | **Defer entirely** — don't build ad-hoc generation in MVP |
| 3 | Memory storage choice | **Option 3: qmd as memory engine** (confirmed by all) |
| 4 | Deep-pass trigger | **Defer** — create `/clavain:flux-deep` command when ready (fd-user-experience) |
| 5 | Merged agent quality | **Split Safety & Correctness** to reduce risk; run comparison test before shipping |

---

## Unresolved Critical Questions

These emerged from the review and must be answered before implementation:

1. **Retraction mechanism**: How does a false-positive knowledge entry get corrected? (spec-flow-analyzer P0-2, user-advocate M-1, architecture-strategist P1-2)
2. **First-run UX**: What does a user see on the first flux-drive v2 run with zero knowledge? (spec-flow-analyzer P1-1, user-advocate Q5)
3. **Compounding visibility**: How does the user know the system is "getting smarter"? (user-advocate M-4 — the headline feature is invisible)
4. **Comparison test**: Do 6 merged agents match 19 specialist quality? Must run before shipping (product-skeptic Critical, architecture-strategist P0-1)

---

## Agent Report Locations

| Agent | Report |
|-------|--------|
| architecture-strategist | `flux-drive-v2-architecture/architecture-strategist.md` |
| product-skeptic | `flux-drive-v2-architecture/product-skeptic.md` |
| performance-oracle | `flux-drive-v2-architecture/performance-oracle.md` |
| code-simplicity-reviewer | `flux-drive-v2-architecture/code-simplicity-reviewer.md` |
| fd-user-experience | `flux-drive-v2-architecture/fd-user-experience.md` |
| user-advocate | `flux-drive-v2-architecture/user-advocate.md` |
| spec-flow-analyzer | `flux-drive-v2-architecture/spec-flow-analyzer.md` |
| Oracle (GPT-5.2 Pro) | `flux-drive-v2-architecture/oracle.md` |

<!-- flux-drive:synthesis-complete -->
