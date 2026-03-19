---
title: "Flux-Drive Multi-Agent Review Patterns"
category: best-practices
tags: [flux-drive, multi-agent, feedback-loop, provenance, content-assembly, smoke-test, oracle, browser-mode]
date: 2026-03-19
synthesized_from:
  - best-practices/compounding-false-positive-feedback-loop-flux-drive-20260210.md
  - best-practices/unify-content-assembly-before-adding-variants-20260211.md
  - best-practices/smoke-test-agent-instruction-conflict-20260210.md
  - integration-issues/oracle-browser-output-lost-flux-drive-20260211.md
---

# Flux-Drive Multi-Agent Review Patterns

Lessons from building and operating a multi-agent document review system with 6+ concurrent Claude agents and Oracle (GPT-5.2 Pro) cross-AI review.

## 1. Break Compounding Feedback Loops with Provenance Tracking

When prior findings are injected into agent context for subsequent reviews, agents re-confirm false positives because they are primed by the injection. The finding is continuously "confirmed" and never decays.

**Fix:** Add a `provenance` field to knowledge entries:
- `independent` -- agent flagged this WITHOUT seeing the entry (genuine re-confirmation)
- `primed` -- agent had this entry in context when it re-flagged (NOT a true confirmation)

Only `independent` confirmations update `lastConfirmed`. Primed confirmations are ignored for decay. This breaks the self-reinforcing loop.

**General principle:** In any system that compounds LLM outputs across runs (RAG, memory layers, progressive refinement), always distinguish between independent discovery and primed agreement. Design retraction mechanisms before building compounding.

## 2. Unify Content-Assembly Before Building Variants

When diff slicing (for large diffs) and pyramid mode (for large files) were proposed as separate systems, 3/3 review agents independently flagged them as the same abstraction applied to different input types. Both route relevant content to domain agents and compress the rest.

**Fix:** Define a single `ContentSlice` interface with two producers (`DiffSlicer`, `PyramidScanner`). The prompt template and synthesis phase consume ContentSlice uniformly.

**General principle:** Before building a variant of an existing system for a new input type, check if the core operation is the same. If so, generalize the interface first. Two parallel code paths double maintenance and testing surface.

## 3. Smoke Tests Must Accommodate the Task Tool Write-First Wrapper

The Task tool injects a "MANDATORY FIRST STEP" preamble telling agents to write output to a file. Smoke test instructions that say "Do NOT write files" conflict with this. Result: 6/8 agents note the contradiction, some attempt tool use.

**Accepted pattern:** Grade smoke tests on output quality, not tool compliance. The goal is verifying agents load and respond coherently. Write permission is denied in subagent context anyway.

**Behavioral variance by agent type:**
- Research/workflow agents: most prompt-compliant, fastest (4s)
- Language reviewers: may attempt Read/Write, moderate (6-16s)
- Security agents: most tool-hungry, read project docs first (22s). Budget 3-5x extra time.

## 4. Oracle Browser Mode Requires --write-output, Not Stdout Redirect

Oracle's browser mode uses `console.log()` for output with ANSI formatting. Redirecting stdout (`> file 2>&1`) captures corrupted output. External `timeout` sends SIGTERM, killing Oracle before it writes output or updates session status.

**Three required changes:**
1. Use `--write-output <path>` instead of `> file 2>&1` (writes clean text, no ANSI)
2. Remove external `timeout` wrapper (prevents SIGTERM killing Oracle mid-operation)
3. Use `--timeout 1800` (Oracle's internal timeout handles cleanup gracefully)

**Budget 30 minutes for GPT-5.2 Pro browser reviews.** If a session gets stuck, use `oracle session <id>` to reattach.

## Cross-Cutting Lessons

- **Convergence is signal.** When 3+ agents independently flag the same issue, treat it as high-confidence. The unify-content-assembly finding had 3/3 convergence.
- **Test the failure modes, not just the happy path.** Inject known-false entries into knowledge layers and verify they decay. Run smoke tests to verify agents load.
- **External tools have their own lifecycle.** Oracle, Codex, and the Task tool all have behaviors (ANSI output, write-first wrappers, timeout handling) that must be accommodated, not fought.
