---
name: brainstorm
description: Collaborative brainstorm workflow — explore ideas through structured dialogue (assess clarity, research repo, explore approaches, capture design) with auto-handoff to /write-plan.
argument-hint: "[feature idea or problem to explore]"
---

# Brainstorm a Feature or Improvement

**Note: The current year is 2026.** Use this when dating brainstorm documents.

Brainstorming helps answer **WHAT** to build through collaborative dialogue. It precedes `/clavain:write-plan`, which answers **HOW** to build it.

## Feature Description

<feature_description> #$ARGUMENTS </feature_description>

**If the feature description above is empty, ask the user:** "What would you like to explore? Please describe the feature, problem, or improvement you're thinking about."

Do not proceed until you have a feature description from the user.

<BEHAVIORAL-RULES>
These rules are non-negotiable for this orchestration command:

1. **Execute phases in order.** Do not skip, reorder, or parallelize phases unless the phase explicitly allows it. Each phase's output feeds into later phases.
2. **Write output to files, read from files.** The brainstorm document MUST be written to disk (docs/brainstorms/). Later phases and downstream commands read from this file, not from conversation context.
3. **Stop at checkpoints for user approval.** When a phase defines a gate, AskUserQuestion, or design validation — stop and wait. Never auto-approve on behalf of the user.
4. **Halt on failure and present error.** If a phase fails (tool error, research agent failure), stop immediately. Report what failed and what the user can do. Do not skip the failed phase.
5. **Local agents by default.** Use local subagents (Task tool) for research dispatch. External agents (Codex, interserve) require explicit user opt-in. Never silently escalate to external dispatch.
6. **Never enter plan mode autonomously.** Do not call EnterPlanMode during brainstorming. If the user wants to plan, hand off to `/clavain:write-plan`.
</BEHAVIORAL-RULES>

## Execution Flow

### Phase 0: Assess Requirements Clarity

Evaluate whether brainstorming is needed based on the feature description.

**Clear requirements indicators:**
- Specific acceptance criteria provided
- Referenced existing patterns to follow
- Described exact expected behavior
- Constrained, well-defined scope

**If requirements are already clear:**
Use **AskUserQuestion tool** to suggest: "Your requirements seem detailed enough to proceed directly to planning. Should I run `/clavain:write-plan` instead, or would you like to explore the idea further?"

### Phase 0.5: Complexity Classification (Sprint Only)

If inside a sprint (check: `bd state "$CLAVAIN_BEAD_ID" sprint` returns `"true"`):

```bash
complexity=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" classify-complexity "$CLAVAIN_BEAD_ID" "<feature_description>")
```

Route based on complexity:

- **Simple** (`complexity == "simple"`): Skip Phase 1 collaborative dialogue. Do a brief repo scan, then present ONE consolidated AskUserQuestion confirming the approach. Proceed directly to Phase 3 (Capture).
- **Medium** (`complexity == "medium"`): Do Phase 1 repo scan, propose 2-3 approaches (Phase 2), ask ONE question to choose. Proceed to Phase 3.
- **Complex** (`complexity == "complex"`): Full dialogue — run all phases as normal.

**Invariant:** Even simple features get exactly one question. Never zero.

If NOT inside a sprint: skip classification, run all phases as normal (existing behavior).

### Phase 1: Understand the Idea

#### 1.1 Repository Research (Lightweight)

Run a quick repo scan to understand existing patterns:

- Task interflux:research:repo-research-analyst("Understand existing patterns related to: <feature_description>")

Focus on: similar features, established patterns, CLAUDE.md guidance.

#### 1.2 Collaborative Dialogue

Use the **AskUserQuestion tool** to ask questions **one at a time**.

**Dialogue principles:**
- **One question per message** — don't overwhelm with multiple questions
- **Prefer multiple choice** when natural options exist (easier to answer than open-ended)
- **Start broad** (purpose, users) **then narrow** (constraints, edge cases)
- **Validate assumptions explicitly** — don't assume, confirm
- **Ask about success criteria** — what does "done" look like?
- **Scale to complexity** — a few sentences for simple ideas, deeper exploration for nuanced ones

**Question progression:** Purpose → Constraints → Success criteria → Edge cases

**Exit condition:** Continue until the idea is clear OR user says "proceed"

### Phase 2: Explore Approaches

Propose **2-3 concrete approaches** based on research and conversation.

For each approach, provide:
- Brief description (2-3 sentences)
- Pros and cons
- When it's best suited

Lead with your recommendation and explain why. Apply YAGNI—prefer simpler solutions.

Use **AskUserQuestion tool** to ask which approach the user prefers.

### Phase 3: Capture the Design

Write a brainstorm document to `docs/brainstorms/YYYY-MM-DD-<topic>-brainstorm.md`.

**Document structure:**
- **What We're Building** — clear description of the feature/improvement
- **Why This Approach** — rationale for the chosen direction
- **Key Decisions** — choices made during dialogue, with reasoning
- **Open Questions** — anything unresolved that planning should address

Ensure `docs/brainstorms/` directory exists before writing.

### Phase 3b: Record Phase

After writing the brainstorm document, record the phase transition:
```bash
BEAD_ID=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" infer-bead "<brainstorm_doc_path>")
"${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" advance-phase "$BEAD_ID" "brainstorm" "Brainstorm: <brainstorm_doc_path>" "<brainstorm_doc_path>"
```
If `CLAVAIN_BEAD_ID` is set in the environment, that takes priority. If no bead ID is found, skip silently.

### Phase 4: Handoff

**If inside a sprint** (check: `bd state "$CLAVAIN_BEAD_ID" sprint` returns `"true"`):
- Skip the handoff question. Sprint auto-advance handles the next step.
- Display the output summary (below) and return to the caller.

**If standalone** (no sprint context):
Use **AskUserQuestion tool** to present next steps:

**Question:** "Brainstorm captured. What would you like to do next?"

**Options:**
1. **Proceed to planning** - Run `/clavain:write-plan` (will auto-detect this brainstorm)
2. **Refine design further** - Continue exploring
3. **Done for now** - Return later

## Output Summary

When complete, display:

```
Brainstorm complete!

Document: docs/brainstorms/YYYY-MM-DD-<topic>-brainstorm.md

Key decisions:
- [Decision 1]
- [Decision 2]

Next: Run `/clavain:write-plan` when ready to implement.
```

## Important Guidelines

- **Stay focused on WHAT, not HOW** - Implementation details belong in the plan
- **Ask one question at a time** - Don't overwhelm
- **Apply YAGNI** - Prefer simpler approaches
- **Keep outputs concise** - 200-300 words per section max

NEVER CODE! Just explore and document decisions.
