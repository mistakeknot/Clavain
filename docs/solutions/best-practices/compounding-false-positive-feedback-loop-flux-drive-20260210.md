---
module: Flux-Drive
date: 2026-02-10
problem_type: best_practice
component: tooling
symptoms:
  - "Knowledge entries injected into agent context cause agents to re-confirm stale or false findings"
  - "lastConfirmed date updates even when confirmation was primed by the knowledge layer itself"
  - "False positive findings become permanent because they self-reinforce through injection"
root_cause: logic_error
resolution_type: documentation_update
severity: high
tags: [compounding, feedback-loop, knowledge-layer, provenance, flux-drive, multi-agent]
---

# Best Practice: Provenance Tracking Breaks Compounding Feedback Loops

## Problem

When designing a compounding knowledge system for multi-agent review (flux-drive v2), a 7-agent self-review (6/7 convergence) discovered that naively injecting prior findings into agent context creates a self-reinforcing false-positive feedback loop:

```
Finding compounded → injected into next review → agent re-confirms (primed by injection)
→ lastConfirmed updated → entry never decays → false positive permanent
```

This is the most dangerous failure mode of any system that compounds LLM outputs across runs: the system's "memory" poisons its future analysis.

## Environment

- Module: Flux-Drive (multi-agent document review skill)
- Component: Knowledge layer + compounding system
- Date: 2026-02-10
- Context: Designing flux-drive v2 architecture — reviewed its own redesign with 7 Claude agents + Oracle (GPT-5.2 Pro)

## Symptoms

- Agent A flags "auth middleware swallows errors" (incorrectly — it doesn't)
- Compounding agent extracts this as a knowledge entry with `lastConfirmed: 2026-02-10`
- Next review: knowledge entry injected into Agent A's context
- Agent A sees "prior knowledge" confirming the false positive, re-flags it with high confidence
- Compounding agent updates `lastConfirmed` — entry is now REINFORCED, not questioned
- Repeat: false positive is permanently baked into the knowledge layer
- No mechanism to challenge, retract, or decay the entry because it's continuously "confirmed"

## What Didn't Work

**Attempted Solution 1:** Decay based on `lastConfirmed` age
- **Why it failed:** The entry IS being confirmed — every review updates `lastConfirmed` because the agent was primed to find it. Decay never triggers.

**Attempted Solution 2:** Manual deletion by users
- **Why it failed:** Users don't inspect knowledge entries. The false positive is invisible — it just keeps appearing in reviews, looking like a genuine finding.

## Solution

Add a `provenance` field to knowledge entries that distinguishes how a confirmation happened:

```yaml
# Before (broken — no provenance distinction):
---
lastConfirmed: 2026-02-10
---
Auth middleware swallows context cancellation errors.

# After (fixed — provenance tracking):
---
lastConfirmed: 2026-02-10
provenance: independent
---
Auth middleware swallows context cancellation errors.

Evidence: middleware/auth.go:47-52, handleRequest()
Verify: grep for ctx.Err() after http.Do() calls in middleware/*.go.
```

Two provenance values:
- `independent` — agent flagged this WITHOUT seeing the knowledge entry in its context (genuine re-confirmation)
- `primed` — agent had this entry in its context when it re-flagged it (NOT a true confirmation)

**Rule:** Only `independent` confirmations update `lastConfirmed`. Primed confirmations are ignored for decay purposes.

This breaks the self-reinforcing loop: if an entry is only ever re-confirmed when primed, its `lastConfirmed` date stays stale, and decay eventually archives it.

## Why This Works

1. **Root cause**: The feedback loop exists because the system conflates "agent found this" with "agent was told about this and agreed." These are fundamentally different evidentiary standards.

2. **The fix separates signal from echo**: An independent discovery is evidence that the finding is real. A primed confirmation is just the agent agreeing with its own input — which LLMs reliably do. By only counting independent discoveries, the decay mechanism works as intended.

3. **Evidence anchors prevent folklore**: Oracle (GPT-5.2 Pro) additionally recommended that knowledge entries include file paths, symbol names, and verification steps. Without these, entries become generic claims that can't be validated. The verification steps allow both humans and agents to check whether a finding is still current.

4. **Generalizes to any LLM compounding system**: This pattern applies wherever you feed LLM outputs back as inputs to future LLM runs — RAG systems, memory layers, auto-generated documentation, progressive refinement loops. The provenance distinction is the key invariant.

## Prevention

- **Always track provenance** when compounding LLM outputs across runs. The question is not "did the agent find this?" but "did the agent find this independently or was it prompted to?"
- **Never update freshness/confirmation metrics** based on primed re-confirmations. Only independent discoveries count.
- **Include evidence anchors** (file paths, line ranges, verification steps) in compounded entries so they can be validated, not just re-confirmed.
- **Design retraction mechanisms** before building compounding systems. If you can compound, you must be able to un-compound.
- **Test for the feedback loop explicitly**: inject a known-false entry, run several reviews, verify it decays rather than strengthening.

## Related Issues

No related issues documented yet.

## Discovery Context

This pattern was discovered when flux-drive reviewed its own v2 architecture redesign:
- 7 Claude agents independently analyzed the design (6/7 converged on this finding)
- Oracle (GPT-5.2 Pro) confirmed and extended with evidence anchor requirements
- Full review: `docs/research/flux-drive/flux-drive-v2-architecture/summary.md`
- Architecture doc: `docs/research/flux-drive-v2-architecture.md`
