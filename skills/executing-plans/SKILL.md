---
name: executing-plans
description: Use when you have a written implementation plan to execute in a separate session with review checkpoints
---

<!-- compact: SKILL-compact.md — if it exists in this directory, load it instead of following the full instructions below. The compact version contains the same batch execution and interserve dispatch protocol. -->

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

Check for an execution manifest alongside the plan file. Replace the plan's `.md` extension with `.exec.yaml` — if that file exists, use Orchestrated Mode (Step 2C). This takes priority over the other modes.

If no manifest exists, check for the interserve flag:

```bash
FLAG_FILE="$(pwd)/.claude/clodex-toggle.flag"
[ -f "$FLAG_FILE" ] && echo "INTERSERVE_ACTIVE" || echo "DIRECT_MODE"
```

Fallback chain:
- **ORCHESTRATED_MODE** (manifest exists) → Go to Step 2C (Orchestrated Execution)
- **INTERSERVE_ACTIVE** (flag exists, no manifest) → Go to Step 2A (Codex Dispatch)
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

### Step 2C: Orchestrated Execution (manifest exists)

When a `.exec.yaml` manifest exists alongside the plan, use the Python orchestrator for dependency-aware dispatch.

1. **Locate the orchestrator:**
   ```bash
   ORCHESTRATE=$(find ~/.claude/plugins/cache -path '*/clavain/*/scripts/orchestrate.py' 2>/dev/null | head -1)
   [ -z "$ORCHESTRATE" ] && ORCHESTRATE=$(find ~/projects -name orchestrate.py -path '*/clavain/scripts/*' 2>/dev/null | head -1)
   ```

2. **Validate the manifest:**
   Run: `python3 "$ORCHESTRATE" --validate "$MANIFEST"`
   If validation fails, report errors and fall back to Step 2A or 2B.

3. **Show the execution plan:**
   Run: `python3 "$ORCHESTRATE" --dry-run "$MANIFEST"`
   Present the wave breakdown to the user.

4. **Ask for approval** via AskUserQuestion:
   - "Approve" — dispatch as shown
   - "Edit mode" — override execution mode (all-parallel, all-sequential, etc.)
   - "Skip to manual" — fall back to Step 2A/2B

5. **Execute:**
   Run: `python3 "$ORCHESTRATE" "$MANIFEST" --plan "$PLAN_PATH" --project-dir "$(pwd)"`
   Use `timeout: 600000` on the Bash tool call (10 minutes).

6. **Read the orchestrator's summary.** For each task:
   - `pass` → trust the result, report success
   - `warn` → read the full output, assess severity
   - `fail` or `error` → offer retry, manual execution, or skip
   - `skipped` → report which dependency failure caused the skip

7. **On partial failure:** If some tasks succeeded and others failed, offer:
   - Fix the failing tasks and re-run orchestrator (it will re-dispatch only unfinished work if outputs exist)
   - Execute failed tasks directly (fall back to Step 2B for those tasks)
   - Skip and continue

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
