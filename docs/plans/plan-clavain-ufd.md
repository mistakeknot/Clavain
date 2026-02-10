# Plan: Clavain-ufd — Evaluate two-pass architecture: triage agent → targeted specialists

## Context
This is an **evaluation/research bead**, not an implementation bead. The question: should flux-drive replace its current "score-and-launch-all" architecture with a two-pass model where a cheap triage agent reads the document first, flags concerns by domain, and then only targeted specialists are launched for flagged domains?

## Current Architecture
1. Orchestrator (Claude main session) reads document, scores agents, launches all selected agents
2. Each agent gets the full document (or trimmed version)
3. If 6 agents are selected, document is duplicated 6 times across agent contexts
4. Total document token cost: N × document_size

## Proposed Architecture
1. **Pass 1** (cheap): Single "triage agent" reads the full document. Outputs a structured list of concerns tagged by domain (security, architecture, performance, etc.). This agent doesn't need deep expertise — just flags "this section has a security implication."
2. **Pass 2** (targeted): Launch specialist agents ONLY for domains where Pass 1 flagged concerns. Each specialist gets relevant sections + triage flags, not the full document.

## Evaluation Plan

### Analysis 1: Token cost comparison
Calculate for a typical 300-line document with 6 agents selected:

**Current model:**
- Triage: ~2K tokens (orchestrator scoring)
- Agent prompts: ~4K tokens × 6 = 24K
- Document: ~6K tokens × 6 = 36K
- Output override: ~2K × 6 = 12K
- **Total: ~74K tokens**

**Two-pass model:**
- Pass 1 triage agent: ~10K tokens (full document + triage prompt)
- Pass 1 output: ~1K tokens
- Pass 2 agents (assume 3 of 6 flagged): ~4K × 3 + ~3K × 3 (partial doc) = 21K
- **Total: ~32K tokens (57% savings)**

But if Pass 1 flags all 6 domains → ~10K + 74K = 84K (worse than current).

### Analysis 2: Quality risk assessment
**What triage agent might miss:**
- Subtle cross-cutting concerns (security + performance interaction)
- Issues that only emerge when a specialist reads carefully
- False negatives in domains the triage agent is weak in

**Mitigation strategies:**
- Always launch architecture-strategist and security-sentinel (regardless of triage)
- Triage agent errs on the side of inclusion (low threshold for flagging)
- User can override and launch additional agents

### Analysis 3: Overlap with Clavain-s3j (incremental depth)
Clavain-s3j (launch top agents first, expand on demand) achieves similar goals with less architectural change:
- Stage 1: Top 2-3 agents (full dispatch, not cheap triage)
- Stage 2: Expand based on Stage 1 findings
- **No new "triage agent" needed** — uses existing agents as Stage 1

The two-pass architecture is a more radical version of incremental depth. If Clavain-s3j delivers sufficient savings (30-50%), the two-pass architecture may not be worth the added complexity.

### Analysis 4: Implementation complexity
**Two-pass adds:**
- New triage agent prompt (must be carefully designed)
- Section extraction logic (give specialists partial documents)
- Domain tagging taxonomy (what counts as "security" vs "architecture"?)
- Pass 1 → Pass 2 handoff protocol
- Regression testing (does the triage agent miss things?)

**Clavain-s3j adds:**
- Staged dispatch logic
- Expansion decision table
- Partial agent set handling in synthesis

## Recommendation

**Defer two-pass in favor of Clavain-s3j (incremental depth).**

Rationale:
1. Clavain-s3j is simpler and achieves 30-50% savings with less risk
2. Two-pass requires a new triage agent that must be trained/calibrated — high effort
3. Two-pass adds a single point of failure (triage agent quality)
4. If Clavain-s3j proves insufficient, two-pass can be revisited with real data
5. The document duplication problem is better solved by raising context windows (already 200K) than by section extraction

## Resolution Path
1. Close this bead as "deferred — evaluate after Clavain-s3j ships"
2. If Clavain-s3j shows <20% savings in practice, reopen this evaluation
3. Add a note to Clavain-s3j linking back to this evaluation for future reference

## Files Changed
None (evaluation/research only).

## Acceptance Criteria
- [ ] Token cost comparison completed for both architectures
- [ ] Quality risk assessment documented
- [ ] Overlap with Clavain-s3j analyzed
- [ ] Decision documented with clear rationale
- [ ] Bead closed with reason linking to recommendation
