# Plan: Clavain-1va — Remove manual token trimming from launch.md

## Context
launch.md Step 2.2 contains instructions for the orchestrator to manually trim document content before constructing agent prompts. The trimming targets documents with 200+ lines, replacing non-focus sections with 1-sentence summaries to hit ~50% of original size. With 200K context windows now standard for Claude models, this manual trimming is unnecessary overhead that adds complexity to the orchestrator's job and potentially removes useful context from agents.

## Current State
- `skills/flux-drive/phases/launch.md` contains token trimming instructions in Step 2.2:
  - For file inputs 200+ lines: keep full content for agent's focus area + Summary/Goals/Non-Goals, replace other sections with summaries
  - Target: ~50% of original
  - "Agent should not see trimming instructions"
- A 200-line document ≈ 4K tokens. Even at 500 lines ≈ 10K tokens. With 8 agents, that's 80K tokens of document content — well within 200K context.

## Implementation Plan

### Step 1: Remove trimming instructions from launch.md
**File:** `skills/flux-drive/phases/launch.md`

Remove the entire token trimming section from Step 2.2. Replace with a simple note:

> **Document content**: Include the full document content in each agent's prompt. Do not trim, summarize, or abbreviate any sections. Each agent gets the complete document.
> 
> **Exception**: For very large inputs (1000+ lines), include only the sections relevant to the agent's focus area plus Summary/Goals/Non-Goals. Note which sections were omitted.

This keeps a safety valve for extreme cases while removing the 200-line trigger that hits most normal documents.

### Step 2: Remove trimming from launch-codex.md
**File:** `skills/flux-drive/phases/launch-codex.md`

If any trimming instructions exist here, remove them similarly. Codex agents also have large context windows (128K-200K).

### Step 3: Update SKILL.md if it references trimming
**File:** `skills/flux-drive/SKILL.md`

Check if the Phase 2 description mentions token trimming. If so, update to reflect the "full document by default" approach.

## Design Decisions
- **1000-line threshold for exception**: A 1000-line document ≈ 20K tokens × 8 agents = 160K tokens of document alone. At that scale, trimming becomes worthwhile. Below that, the cost is negligible.
- **Focus-area preservation**: Even for huge docs, agents should get their focus sections in full. Only trim non-focus sections.
- **Remove, don't just raise threshold**: The trimming instructions themselves add ~15 lines of orchestrator complexity. Simpler to remove entirely with a high-bar exception.

## Files Changed
1. `skills/flux-drive/phases/launch.md` — Remove trimming section, add simple full-document instruction
2. `skills/flux-drive/phases/launch-codex.md` — Same if applicable
3. `skills/flux-drive/SKILL.md` — Minor update if it references trimming

## Estimated Scope
Net deletion: ~15-20 lines removed, ~5 lines added. Simplification.

## Acceptance Criteria
- [ ] No trimming instructions for documents under 1000 lines
- [ ] Agents receive full document content by default
- [ ] Safety valve exists for very large inputs (1000+ lines)
- [ ] launch-codex.md is consistent with launch.md
- [ ] No references to "50% target" or "200-line threshold" remain
