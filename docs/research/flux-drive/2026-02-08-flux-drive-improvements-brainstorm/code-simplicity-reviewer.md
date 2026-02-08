---
agent: code-simplicity-reviewer
tier: 3
issues:
  - id: P0-1
    severity: P0
    section: "Improvement Areas"
    title: "qmd Integration and Triage Calibration are premature YAGNI violations"
  - id: P1-1
    severity: P1
    section: "Open Questions"
    title: "--fast flag adds scope creep without documented use case"
  - id: P1-2
    severity: P1
    section: "Improvement Areas"
    title: "Phase 4 Validation scope is excessive — testing without user demand"
improvements:
  - id: IMP-1
    title: "Defer qmd Integration (Step 1.0) to Phase 2"
    section: "Improvement Areas — 4. qmd Integration"
  - id: IMP-2
    title: "Remove Triage Calibration from this pass"
    section: "Improvement Areas — 5. Triage Calibration"
  - id: IMP-3
    title: "Scope Phase 4 Validation to testable failures only"
    section: "Improvement Areas — 6. Phase 4 Validation"
  - id: IMP-4
    title: "Remove --fast flag from Open Questions"
    section: "Open Questions"
verdict: needs-changes
---

### Summary

This brainstorm proposes 6 improvements, but applies YAGNI rigorously, only **3 are necessary** for the stated goal of "addressing untested code paths and token waste." The other 3 (qmd integration, triage calibration, premature Phase 4 testing) lack documented user demand or clear failure modes. Removing these 3 avoids 2-3 weeks of speculative work. **Recommendation: Implement only Improvements 1-3 now; defer 4-5 and skip 6 entirely.**

### Section-by-Section Review

#### "Why This Approach" (lines 10-12)

The justification correctly identifies real problems:
- Untested Phase 4 code paths — **legit**
- 38% token waste from duplication — **legit**
- Aspirational integration claims — **legit**

But it doesn't defend the *secondary* improvements. This is a sign that 4-5 got bundled without clear justification.

#### Improvement 1: Agent Output Validation (lines 23-27)

**Status: KEEP. This is necessary.**

- Current risk: Malformed agent outputs could fail silently during synthesis (Step 3.1)
- Real failure mode: Agent crashes or returns invalid YAML, synthesis chokes
- Scope: Tiny (add 3-line validation in Step 3.0.5)
- This directly addresses Phase 3 reliability

**No changes needed.**

#### Improvement 2: Token Optimization (lines 29-33)

**Status: KEEP, but scope it ruthlessly.**

The improvement is real (38% waste). But it proposes 4 sub-tasks:

1. **Enforce section trimming** — KEEP
   - Rule already exists in SKILL.md lines 277-284 ("Token Optimization")
   - Problem: Not enforced in prompts; agents ignore it
   - Fix: Add 1 sentence to prompt template: "Strip sections outside your domain to 1 line each"
   - **LOC saved: ~12K tokens per review (36K for 6 agents)**

2. **Add haiku model hint** — KEEP
   - Tier 3 agents (haiku) can review simpler documents
   - But: Only for agents scoring low (1-2). Don't override for primary agents.
   - This is already in SKILL.md line 191 ("recommended model parameter")
   - **Action: Clarify it's not a default, just a triage option**

3. **Compress prompt template** — QUESTIONABLE
   - Current template: ~85 lines (lines 257-351 in SKILL.md)
   - Claimed reduction: 50 lines
   - What gets cut? Unspecified. Likely "nice to haves" like examples, edge cases
   - **Risk: Loss of clarity without documented token savings**
   - **Verdict: DEFER. First, measure if section trimming alone hits the 29% target.**

4. **Domain-specific document slicing (Step 1.0)** — DEFER (see qmd section below)
   - This is conflated with qmd integration
   - Decouple it: Can we do basic per-domain section extraction without qmd?
   - **Too much scope for this pass**

**Recommendation for Improvement 2:** Implement only #1 (enforce trimming) + clarify #2 (haiku is optional). Defer #3 and #4.

#### Improvement 3: Fix Stale Integration Claims (lines 35-38)

**Status: KEEP. This is necessary.**

- Lines 540-541 claim integrations that don't exist
- Claims made: "Called by writing-plans and brainstorming skills"
- Reality: Neither skill calls flux-drive
- Fix: Delete lines 540-541; add to AGENTS.md backlog for future integration
- **Scope: 2 lines deleted, 1 line added to backlog**

**No changes needed.**

#### Improvement 4: qmd Integration (lines 40-43)

**Status: DEFER. This is a new feature, not a fix.**

- Purpose: Use qmd semantic search in Step 1.0 to find project docs
- Reality: Step 1.0 already works fine (reads CLAUDE.md/AGENTS.md directly)
- Benefit: "Better project context" — vague. For which agents? Which documents?
- Problem: Adds a dependency (qmd MCP) + network call + parsing
- Risk: qmd search returns wrong docs, confuses triage
- **Current triage works**: Score agents, pick the N highest. No need for richer context.

**YAGNI violation**: "Just in case better context would help" — but there's no evidence thin-section triage is failing today.

**Recommendation**: DEFER to Phase 2. If post-launch data shows Tier 3 agents are flailing on thin sections, revisit qmd. Don't speculate.

#### Improvement 5: Triage Calibration (lines 45-48)

**Status: DEFER. This is optional nice-to-have.**

- Purpose: Add scoring examples + thresholds + convergence mining
- Reality: Triage scoring rules already exist (SKILL.md lines 94-130)
- Benefit: More precise triage? Maybe. No evidence current triage is wrong.
- Problem: Requires analysis of past reviews (convergence data mining) — unavailable yet
- Scope: Vague ("mine convergence data"). How? From where? Time estimate: 1-2 weeks research

**YAGNI violation**: "We should have data-driven calibration" — but triage is working now. Premature optimization.

**Recommendation**: DEFER to Phase 2 (after 10-20 real reviews). Gather data first, calibrate second.

#### Improvement 6: Phase 4 Validation (lines 50-55)

**Status: RISKY. Too much testing without documented demand.**

Proposed tests:
1. Oracle availability detection — OK (small)
2. Oracle CLI invocation with env vars — OK (small)
3. splinterpeer auto-chain on disagreements — RISKY (unimplemented feature)
4. winterpeer offer logic on critical decisions — RISKY (unimplemented feature)
5. "Fix any bugs found" — VAGUE

- **Problem 1**: Lines 521-541 describe splinterpeer auto-chain and winterpeer offer as design (not implemented yet)
- **Problem 2**: Testing unimplemented features means writing them as part of "validation"
- **Problem 3**: No Oracle user has complained Phase 4 is broken. Why test it now?

**YAGNI violation**: "We should be ready for Phase 4 even if no one uses it yet"

**Recommendation**: REDUCE to:
- Test 1 (Oracle availability) — **KEEP**
- Test 2 (Oracle CLI invocation) — **KEEP**
- Tests 3-5 — **SKIP until Phase 4 is actually called in production**

#### Open Questions (lines 57-61)

**Problem**: These are speculative features, not open questions about the 6 improvements.

1. **"Should we add a --fast flag?"** — REMOVE
   - No user asking for it
   - Adds parameter complexity
   - "3 agents max" is an arbitrary number
   - **If users want faster reviews, they'll ask. Don't build options preemptively.**

2. **"Should thin-section enrichment be tested now?"** — REMOVE
   - Conflated with Improvement 4 (qmd)
   - "Tested now or deferred?" — deferred, obviously
   - Not a real open question

3. **"What model should Tier 3 agents default to?"** — KEEP
   - Real question: Is haiku sufficient for all Tier 3 agents, or only pattern/simplicity agents?
   - This affects Improvement 2's token savings
   - **Answer**: Haiku for pattern/simplicity only; sonnet for architecture/security/performance

### Issues Found

#### P0-1: qmd Integration and Triage Calibration are premature YAGNI violations

**Why it's a problem:**
- Neither improves reliability or fixes bugs
- Both require speculative design (how will qmd data flow? what convergence patterns exist?)
- Both lack documented user demand

**Evidence:**
- qmd: "helps Tier 1 agents get better project context" — but Tier 1 agents already read CLAUDE.md/AGENTS.md. What context is missing?
- Triage calibration: "mine convergence data" — from what? First 5 reviews haven't happened yet.

**Impact:**
- Adds 1-2 weeks of speculative work
- Increases code paths to test in Phase 4
- Both can be deferred and reassessed with real usage data

#### P1-1: --fast flag adds scope creep without documented use case

**Why it's a problem:**
- No user has asked for faster reviews
- "3 agents max" is arbitrary; different use cases need different limits
- Adds a parameter that complicates triage logic

**YAGNI principle:**
- Don't add features "just in case"
- If users want speed, they'll ask

#### P1-2: Phase 4 Validation scope is excessive

**Why it's a problem:**
- Tests 3-5 (splinterpeer, winterpeer) are testing *unimplemented* features
- No Phase 4 user has complained it's broken
- "Fix any bugs found" is vague — what bugs?

**Evidence:**
- Lines 521-541 describe splinterpeer/winterpeer as design, not implemented code
- Testing them now means implementing them as part of "validation"
- That's not validation; that's feature development

### Improvements Suggested

#### IMP-1: Defer qmd Integration (Step 1.0) to Phase 2

**Current approach:** Add qmd semantic search in Step 1.0 to enrich triage context.

**Proposed approach:** Keep Step 1.0 as-is (read CLAUDE.md/AGENTS.md only). After 10-20 real reviews, analyze whether triage decisions improved with qmd context. If yes, add it. If no, forget it.

**Rationale:**
- Triage works today; no failure evidence
- qmd is a new dependency; introduce only when needed
- Risk is low (no production impact), so deferral is safe
- Saves 1-2 weeks of speculative work

#### IMP-2: Remove Triage Calibration from this pass

**Current approach:** Add scoring examples, thresholds, and convergence mining.

**Proposed approach:** Implement the 6 improvements (minus this one). Use post-launch data to inform calibration in Phase 2.

**Rationale:**
- Calibration without data is speculation
- Current rules (SKILL.md lines 94-130) are clear and reasonable
- Convergence data doesn't exist yet
- Premature optimization; measure first, optimize second

**Impact:** Saves 1-2 weeks.

#### IMP-3: Scope Phase 4 Validation to testable failures only

**Current approach:** Test all of Phase 4 including unimplemented features (splinterpeer, winterpeer).

**Proposed approach:**
- Test Oracle availability detection (5 min)
- Test Oracle CLI invocation with env vars (10 min)
- SKIP splinterpeer/winterpeer tests (they're not implemented)
- SKIP "fix any bugs found" (too vague; add to backlog if bugs appear in production)

**Rationale:**
- Tests 1-2 validate Phase 4 entry points (legit)
- Tests 3-4 are really feature development, not validation
- No user has run Phase 4 yet; can't have bugs in unused code
- Saves 1-2 weeks of speculative implementation + testing

#### IMP-4: Remove --fast flag from Open Questions

**Current question:** "Should we add a --fast flag that limits to 3 agents max for quick reviews?"

**Proposed action:** Remove it entirely. If users ask for speed controls, add them then.

**Rationale:**
- YAGNI: No user asked for this
- "3 agents max" is arbitrary; different docs need different limits
- Adds parameter complexity without clear use case
- Saves 0.5 weeks

### Overall Assessment

**Verdict: NEEDS-CHANGES**

Of the 6 proposed improvements, implement **only 1-3** (validation, token optimization enforcement, fix stale claims). Defer 4-5 (qmd, calibration) to Phase 2, and reduce 6 (Phase 4 validation) to only testable entry points.

This cuts 3-4 weeks of speculative work while shipping all the *necessary* improvements. The deferred work is safe to postpone because: (1) no users depend on qmd enrichment yet, (2) calibration needs real data to inform it, and (3) Phase 4 isn't called in production. Ship the essential fixes now; revisit the rest with real usage data in hand.

**Estimated time savings: 3-4 weeks. Scope reduction: 50% of proposed work.**
