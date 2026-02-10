# Plan: Clavain-2yx — Strip `<example>` blocks from agent prompts during flux-drive dispatch

## Context
Agent `.md` files in `agents/review/` contain `<example>` and `<commentary>` blocks in their YAML frontmatter `description` field. These blocks help the Claude Code orchestrator decide when to invoke the agent (triage routing), but they serve no purpose once the agent is actually running its review. Including them wastes ~500-1500 chars per agent × N agents = significant token overhead per flux-drive run.

## Current State
- Agent `.md` files have `<example>...</example>` blocks embedded in the `description` field of their YAML frontmatter
- These blocks contain Context/user/assistant/commentary sections for triage matching
- `launch.md` Step 2.2 pastes full agent `.md` content into the task prompt for Project Agents
- For Adaptive Reviewers, the `subagent_type` loads the full system prompt natively (including examples in the description)
- `launch-codex.md` pastes agent content into the `AGENT_IDENTITY:` section of task files

## Implementation Plan

### Step 1: Add stripping instruction to launch.md
**File:** `skills/flux-drive/phases/launch.md`

In Step 2.2, where the prompt template is constructed, add an instruction before the agent prompt is included:

> **Before including an agent's system prompt in the task prompt:**
> Strip all `<example>...</example>` blocks (including any nested `<commentary>...</commentary>`) from the agent content. These blocks are for triage routing only and are not needed during the agent's review execution.

This applies to **Project Agents only** (whose `.md` content is manually pasted). Adaptive Reviewers load their system prompt via `subagent_type`, and we cannot strip content from that — but we can note in the prompt template that example blocks in the agent's native prompt should be ignored.

### Step 2: Add stripping instruction to launch-codex.md
**File:** `skills/flux-drive/phases/launch-codex.md`

Same instruction for the `AGENT_IDENTITY:` section of Codex task files:
- Before writing the agent's system prompt into the task description file, strip `<example>...</example>` blocks

### Step 3: Add a note about Adaptive Reviewers
For Adaptive Reviewers (loaded via `subagent_type`), the orchestrator does not control the system prompt content. Add a note:

> For Adaptive Reviewers: The agent's native system prompt may contain `<example>` blocks. These are harmless but consume tokens. No action needed — the prompt is loaded by the framework, not by the orchestrator.

This is informational only. If we later want to optimize this, it would require changes to the agent `.md` files themselves (covered by Clavain-6a4).

## Design Decisions
- **Prompt-level instruction, not code**: The orchestrator is Claude itself — we tell it to strip content as part of the skill instructions. No regex or scripting needed.
- **Project Agents only**: These are the ones whose content the orchestrator directly controls. Adaptive Reviewer prompts are framework-managed.
- **Strip entire `<example>` blocks**: Including `<commentary>`. The pattern is unambiguous: `<example>` through `</example>`.
- **Deferred for Adaptive Reviewers**: Stripping from native prompts is a separate concern (Clavain-6a4).

## Files Changed
1. `skills/flux-drive/phases/launch.md` — Add stripping instruction in Step 2.2 prompt construction
2. `skills/flux-drive/phases/launch-codex.md` — Same instruction for AGENT_IDENTITY section

## Estimated Scope
~5-10 lines of new instructional content per file. Very small change.

## Acceptance Criteria
- [ ] launch.md instructs orchestrator to strip `<example>` blocks from Project Agent prompts
- [ ] launch-codex.md instructs same for Codex task file construction
- [ ] Stripping targets `<example>...</example>` including nested `<commentary>`
- [ ] Adaptive Reviewer prompts are noted as not strippable at this layer
- [ ] No changes to agent `.md` files themselves
