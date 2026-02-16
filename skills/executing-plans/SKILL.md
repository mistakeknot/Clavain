---
name: executing-plans
description: Use when you have a written implementation plan to execute in a separate session with review checkpoints
---

# Executing Plans

## Overview

Load plan, review critically, execute tasks in batches, report for review between batches.

**Core principle:** Batch execution with checkpoints for architect review.

**Announce at start:** "I'm using the executing-plans skill to implement this plan."

## The Process

### Step 1: Load and Review Plan
1. Read plan file
2. Review critically - identify any questions or concerns about the plan
3. If concerns: Raise them with your human partner before starting
4. If no concerns: Create TodoWrite and proceed

### Step 2: Check Execution Mode

```bash
FLAG_FILE="$(pwd)/.claude/interserve-toggle.flag"
[ -f "$FLAG_FILE" ] && echo "INTERSERVE_ACTIVE" || echo "DIRECT_MODE"
```

- **INTERSERVE_ACTIVE** → Go to Step 2A (Codex Dispatch)
- **DIRECT_MODE** → Go to Step 2B (Direct Execution)

### Step 2A: Codex Dispatch (interserve mode)

When interserve mode is active, dispatch tasks to Codex agents instead of executing directly. This enables parallelization — independent tasks run concurrently.

1. **Classify tasks** from the plan into:
   - **Independent** — no shared files, can run in parallel → Codex agents
   - **Sequential** — depends on prior task output → dispatch in order
   - **Exploratory** — needs deep reasoning or unclear scope → Claude subagent

2. **Group into dispatch batches:**
   - Independent tasks in the same batch run in parallel
   - Sequential tasks go in consecutive batches
   - Max 5 agents per batch (to avoid overwhelming resources)

3. **For each batch**, use the `clavain:interserve` skill:
   - Write prompt files (one per task) to `/tmp/codex-task-<name>.md` — plain language with goal, files, build/test commands, and verdict suffix
   - Dispatch all independent tasks in a single message (parallel Bash calls)
   - Wait for all agents to complete
   - Read each agent's `.verdict` file first (7 lines — structured summary)
   - If STATUS is `pass`: trust the verdict, report success, move on
   - If STATUS is `warn` or `fail`: read the full output file for details, diagnose, retry or escalate
   - If no `.verdict` file: fall back to reading the full output

4. **Between batches:** Report what completed, what passed/failed, and any issues. Wait for feedback before next batch.

5. **On failure:** If a Codex agent fails, offer:
   - Retry with tighter prompt (include error context)
   - Execute directly (fall back to Step 2B for that task)
   - Skip and continue

### Step 2B: Direct Execution (default)

**Default: First 3 tasks per batch**

For each task:
1. Mark as in_progress
2. Follow each step exactly (plan has bite-sized steps)
3. Run verifications as specified
4. Mark as completed

### Step 3: Report
When batch complete:
- Show what was implemented
- Show verification output
- Say: "Ready for feedback."

### Step 4: Continue
Based on feedback:
- Apply changes if needed
- Execute next batch
- Repeat until complete

### Step 5: Complete Development

After all tasks complete and verified:
- Announce: "I'm using the landing-a-change skill to complete this work."
- **REQUIRED SUB-SKILL:** Use clavain:landing-a-change
- Follow that skill to verify tests, present options, execute choice

## When to Stop and Ask for Help

**STOP executing immediately when:**
- Hit a blocker mid-batch (missing dependency, test fails, instruction unclear)
- Plan has critical gaps preventing starting
- You don't understand an instruction
- Verification fails repeatedly

**Ask for clarification rather than guessing.**

## When to Revisit Earlier Steps

**Return to Review (Step 1) when:**
- Partner updates the plan based on your feedback
- Fundamental approach needs rethinking

**Don't force through blockers** - stop and ask.

## Remember
- Review plan critically first
- Follow plan steps exactly
- Don't skip verifications
- Reference skills when plan says to
- Between batches: just report and wait
- Stop when blocked, don't guess
- Never start implementation on main/master branch without explicit user consent

## Integration

**Required workflow skills:**
- **clavain:writing-plans** - Creates the plan this skill executes
- **clavain:landing-a-change** - Complete development after all tasks
- **clavain:interserve** - Codex dispatch (used when interserve mode is active)
