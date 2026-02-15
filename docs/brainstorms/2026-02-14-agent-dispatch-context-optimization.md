# Brainstorm: Reducing Context Cost of Mass Agent Dispatch

**Date:** 2026-02-14
**Status:** Brainstorm
**Problem:** Parent session context bloat when dispatching 10-26 subagents via the Task tool

> Full analysis with 15 approaches, comparative table, and implementation roadmap at:
> `docs/research/brainstorm-agent-dispatch-patterns.md`

---

## Problem Summary

Dispatching 26 agents via Task tool consumes ~116K chars (~29K tokens) of the parent session's context window purely on dispatch overhead -- prompts, tool results, and notifications. That's 15-18% of the context window before any actual work.

## Top 5 Approaches (from 15 evaluated)

### 1. File Indirection (70% savings, implement today)

Write full agent prompts to temp files. Task call becomes: "Read /tmp/prompt-{agent}.md and execute." Drops per-agent prompt from ~3K chars to ~200 chars.

### 2. Hierarchical Dispatch (98% savings, needs testing)

Single "dispatcher" subagent reads a manifest and launches all N agents internally. Parent sees 1 Task call. Critical dependency: verify that grandchild notifications don't bubble to grandparent.

### 3. Hybrid Codex + Task Routing (89% savings, works today)

Route research agents and formulaic reviewers through Codex CLI (dispatch.sh). Keep nuanced review agents on Claude Task tool. All Codex dispatch appears as small Bash commands in context.

### 4. Compact Dispatch Protocol (67-99% savings)

Shared context file (written once) + per-agent delta files (focus area only). Combined with approaches above, achieves near-100% savings.

### 5. Progressive Delegation (50% average savings)

Dispatch in small rounds, terminate early when enough signal gathered. Already partially implemented in flux-drive's staged dispatch. Trades context for wall-clock time.

## Recommended Implementation Path

- **Day 1:** File indirection for all Task prompts (Approaches 1 + 4)
- **Day 2:** Test notification bubbling (prerequisite for Approach 2)
- **Day 3:** Either hierarchical dispatch (if bubbling doesn't occur) or hybrid routing (fallback)

## Key Unknown

Do grandchild agent notifications bubble to the grandparent session? This determines whether hierarchical dispatch achieves 98% or 80% savings. Must be empirically tested.

See `docs/research/brainstorm-agent-dispatch-patterns.md` for the full 15-approach analysis.
