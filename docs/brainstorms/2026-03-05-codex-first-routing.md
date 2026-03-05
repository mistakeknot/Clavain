# Codex-First Routing: Auto-Delegate CC Work to Codex

**Bead:** iv-2s7k7
**Date:** 2026-03-05
**Status:** Design

## Problem

Claude Code (CC) consumes expensive Opus/Sonnet tokens for work that Codex CLI can handle equally well at lower cost (or free under subscription). The existing interserve mode is opt-in and manual — you have to explicitly invoke the skill. There's no automatic routing of work to Codex, and no feedback loop to improve routing over time.

**Token waste areas:** exploration/search, scoped implementation, code review, test generation, documentation updates.

## Research Findings

### Open-Source Landscape

| Project | Approach | Key Insight |
|---------|----------|-------------|
| RouteLLM (LMSYS) | Preference-based classifier trained on Chatbot Arena data | 85% cost reduction; routers generalize across model pairs — they learn task complexity, not model quirks |
| oh-my-claudecode | Keyword + tier routing (Haiku/Sonnet/Opus), 32 agents | Simple tier system (LOW/MED/HIGH) works. No CC↔Codex boundary, no learning loop |
| ruflo | Hive-mind swarm, "cheapest handler" routing | Native CC+Codex integration exists. Over-engineered (64 agents, 87 MCP tools) |
| myclaude | Multi-agent workflow (CC+Codex+Gemini) | Multi-runtime possible but manual skill selection |
| vLLM Semantic Router | Semantic-aware model switching | Right paradigm (semantic classification) but API-layer only |
| LiteLLM/OpenRouter | Unified gateway with routing | Proxy pattern; doesn't help agent-level delegation |

**Gap:** Nobody has built closed-loop CC↔Codex routing with outcome-based calibration.

### CC Platform Capabilities (v2.0.10+)

1. **`updatedInput` in PreToolUse** — Can modify tool parameters before execution. CANNOT change tool type (can't redirect Agent→Bash).
2. **Custom subagents** — Full control: model, tools, hooks, permissions, memory, system prompt. Can call Bash (dispatch.sh) internally.
3. **SubagentStart hooks** — Can inject `additionalContext` into any spawned subagent.
4. **`--agents` CLI flag** — Runtime agent injection without file changes.
5. **Subagent `memory` field** — Built-in persistent cross-session learning directory.

### Key Constraint

Hooks can block tool calls and modify parameters, but they **cannot rewrite one tool into a different tool**. A PreToolUse hook on `Agent` cannot transparently replace it with `Bash(dispatch.sh)`. This rules out a transparent proxy approach.

## Architecture

Three layers, each independently useful, progressively more valuable together.

### Layer 1: codex-delegate Subagent

A custom subagent at `os/clavain/agents/codex-delegate.md` whose job is:
1. Accept a task prompt from Claude
2. Classify the task (exploration vs implementation vs review)
3. Select the appropriate dispatch tier (fast/deep)
4. Craft a dispatch.sh megaprompt with proper scope
5. Execute via Bash (dispatch.sh) with appropriate flags
6. Read the output + verdict sidecar
7. Return a clean summary to Claude
8. Record the outcome to interspect

**Model:** Haiku (the agent itself is just orchestration — the real work happens in Codex)
**Tools:** Bash, Read, Write (for prompt file crafting)
**Memory:** `project` scope — learns which task patterns succeed/fail for this codebase

```yaml
name: codex-delegate
description: Delegates well-scoped tasks to Codex CLI for cost-efficient execution.
  Use proactively for implementation, exploration, search, test generation, and code review
  when the task has clear scope and success criteria. Keep architecture, brainstorming,
  and interactive work in Claude.
model: haiku
tools: Bash, Read, Write, Grep, Glob
memory: project
permissionMode: acceptEdits
```

### Layer 2: Routing Policy Injection (SessionStart)

The session-start hook already injects companion context. Add a delegation policy section:

```
**DELEGATION POLICY (codex-first routing)**
Before spawning subagents for scoped work, evaluate for Codex delegation:

DELEGATE to codex-delegate when:
- Task has clear file scope (known files/directories)
- Task has verifiable success criteria (tests, build, linter)
- Task is: implementation, bug fix, test generation, exploration, search, code review
- Complexity is C1-C3 (trivial to moderate)

KEEP IN CLAUDE when:
- Task requires interactive user input
- Task is architectural/brainstorming (needs deep cross-file reasoning)
- Task is iterative (likely to need multiple back-and-forth rounds)
- Complexity is C4-C5 (complex to architectural)
- Task modifies delegation infrastructure itself

Current stats: {delegation_pass_rate}% pass rate, {delegation_count} delegations this project
Categories needing attention: {high_retry_categories}
```

The stats section is populated from interspect calibration data (Layer 3). When no data exists, it shows "No delegation data yet — building baseline."

### Layer 3: Interspect Outcome Tracking

New event type: `delegation_outcome`

```json
{
  "event": "delegation_outcome",
  "hook_id": "interspect-delegation",
  "task_category": "implementation|exploration|review|test-gen|doc-update",
  "routed_to": "codex",
  "dispatch_tier": "fast|deep",
  "complexity": "C1|C2|C3",
  "verdict": "pass|warn|fail",
  "retry_needed": false,
  "duration_s": 45,
  "codex_tokens_in": 3200,
  "codex_tokens_out": 1800,
  "cc_tokens_saved_estimate": 12400
}
```

**Calibration output:** `.clavain/interspect/delegation-calibration.json`

```json
{
  "schema_version": 1,
  "generated_at": "2026-03-05T22:00:00Z",
  "overall_pass_rate": 0.87,
  "total_delegations": 42,
  "categories": {
    "implementation": { "count": 18, "pass_rate": 0.89, "avg_duration_s": 52 },
    "exploration": { "count": 12, "pass_rate": 0.92, "avg_duration_s": 28 },
    "review": { "count": 8, "pass_rate": 0.75, "avg_duration_s": 65 },
    "test-gen": { "count": 4, "pass_rate": 1.0, "avg_duration_s": 40 }
  },
  "high_retry_categories": ["review"],
  "estimated_cc_tokens_saved": 520800
}
```

Session-start hook reads this file and injects the stats into the routing policy text.

### Layer 4 (Future): PreToolUse Advisory Gate

Once Layers 1-3 are working and we have outcome data, optionally add a PreToolUse hook on `Agent` that:
- When Claude spawns a general-purpose or Explore agent for a task that looks delegatable
- Returns `additionalContext` (not block): "This task appears delegatable to Codex. Consider using codex-delegate instead."
- Does NOT block — just advises

This is the soft enforcement layer. It catches cases where Claude "forgot" the routing policy.

## Implementation Plan

### Phase 1: codex-delegate subagent (Layer 1)
1. Create `os/clavain/agents/codex-delegate.md` with system prompt
2. Test with manual invocations: "Use codex-delegate to fix the typo in X"
3. Verify dispatch.sh integration works from subagent context

### Phase 2: Routing policy injection (Layer 2)
1. Add delegation policy section to session-start.sh
2. Add to shedding cascade (priority: after companion_context, before conventions)
3. Test that Claude actually routes to codex-delegate when prompted with delegatable tasks

### Phase 3: Outcome tracking (Layer 3)
1. Add `interspect-delegation` to hook_id allowlist in lib-interspect.sh
2. Add outcome recording in codex-delegate subagent's system prompt
3. Build calibration aggregation (extend interspect calibrate command)
4. Wire calibration data into session-start policy injection

### Phase 4: Advisory gate (Layer 4 — optional)
1. PreToolUse hook on `Agent` matcher
2. Classify prompt for delegatability
3. Return additionalContext advisory (never block)

## Routing Policy in routing.yaml

New top-level section:

```yaml
delegation:
  mode: enforce  # off | shadow | enforce
  codex_available: true

  # Task categories and their default routing
  categories:
    exploration: codex-first
    implementation: codex-first
    review: codex-first
    test-generation: codex-first
    doc-update: codex-first
    architecture: claude-only
    brainstorm: claude-only
    interactive: claude-only

  # Complexity ceiling — C4+ stays in Claude regardless of category
  max_delegatable_complexity: C3

  # Minimum pass rate before auto-delegating a category
  # Categories below this threshold get advisory-only routing
  min_category_pass_rate: 0.70
```

## Success Metrics

1. **Delegation rate:** % of subagent-eligible tasks routed to Codex (target: 60%+)
2. **Pass rate:** % of delegated tasks that succeed without retry (target: 85%+)
3. **Token savings:** Estimated CC tokens saved per session (target: 50%+ reduction)
4. **Session extension:** More useful work per session before hitting limits

## Open Questions

1. Should codex-delegate be a Clavain plugin agent or a project-level agent?
   - Leaning: Plugin agent (in `os/clavain/agents/`) — available everywhere
2. How to handle Codex failures gracefully? Retry once then fall back to Claude?
   - Leaning: Single retry with tighter scope, then offer Claude fallback
3. Should the subagent's memory accumulate codebase-specific routing preferences?
   - Leaning: Yes, project-scoped memory learns which patterns work for each repo
4. Token savings estimation — how accurate can we be without CC token counters?
   - Leaning: Rough estimate based on prompt length × model cost, track relative trend

## Original Intent (from brainstorm)

User's trigger: "How can we make sure Clavain/Interverse helps reduce token spend by routing to Codex whenever it makes sense?"

Desired behavior: Auto-delegate + measure success + autonomously improve routing. Not advisory-only, not manual — a closed loop.

Key constraints discovered:
- Hooks can't rewrite tools (rules out transparent proxy)
- Custom subagents ARE the right mechanism (native, no hacking)
- RouteLLM proves preference-based learning works for routing
- Interspect already has the outcome tracking pipeline
