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

### Step 2D: Post-Task Verification

After completing each task (in any execution mode), check for a `<verify>` block at the end of the task:

1. **Parse the verify block:** Look for `<verify>...</verify>` after the task's last step. Extract each `- run:` / `expect:` pair.
2. **Run each verification command** in order.
3. **Check results:**
   - `expect: exit 0` — command must exit with code 0
   - `expect: contains "string"` — command output must include the quoted string
4. **On success:** Log "Verify passed for Task N" and continue.
5. **On failure:** Treat as deviation Rule 1 (auto-fix bug). Review the task implementation, fix the issue, re-run the verification. Apply the 3-attempt limit — if verify still fails after 3 attempts, log the failure and continue to the next task.
6. **No verify block:** Skip silently — this is backward compatible. Log nothing.

### Step 3: Report
When batch complete:
- Show what was implemented
- Show verification output (pass/fail per task from `<verify>` blocks)
- List any deviations (Rules 1-3 auto-fixes applied)
- List any deferred items (out-of-scope issues discovered, tasks that hit the 3-attempt limit)
- Say: "Ready for feedback."

### Step 4: Continue
Based on feedback:
- Apply changes if needed
- Execute next batch
- Repeat until complete

### Step 4B: Must-Have Validation

After all tasks complete, check for a `## Must-Haves` section in the plan header:

1. **Truths:** For each truth listed, verify it's observable. If the truth references a command or URL, run it. If it describes user behavior, check that the relevant code path exists.
2. **Artifacts:** For each artifact, verify the file exists and exports the listed symbols. Use grep or read the file to confirm.
3. **Key Links:** For each key link, verify the connection exists in the source code (e.g., "Component A calls Component B" — grep for the import and function call).

**Report must-have results** in the completion summary:

```
Must-Have Validation:
  Truths: 3/3 verified
  Artifacts: 2/2 exist with exports
  Key Links: 1/2 — Registration endpoint missing validate_email call
```

If any must-have fails: report the failure but do NOT block completion. Must-haves are advisory — the user decides whether to fix them before shipping.

If no Must-Haves section exists: skip silently (backward compatible).

### Step 5: Complete Development

After all tasks complete and verified:
- Announce: "I'm using the landing-a-change skill to complete this work."
- **REQUIRED SUB-SKILL:** Use clavain:landing-a-change
- Follow that skill to verify tests, present options, execute choice

## Deviation Rules

While executing, you WILL discover work not in the plan. Apply these rules automatically. Track all deviations for the batch report.

### Rule 1: Auto-fix bugs
**Trigger:** Code doesn't work as intended — wrong queries, type errors, null pointer exceptions, broken validation, logic errors.
**Action:** Fix inline, verify fix, continue task. No permission needed.

### Rule 2: Auto-add critical functionality
**Trigger:** Code missing essentials for correctness, security, or basic operation — missing error handling, no input validation, missing null checks, no auth on protected routes, missing DB indexes.
**Action:** Add it, verify, continue. These aren't "features" — they're correctness requirements. No permission needed.

### Rule 3: Auto-fix blockers
**Trigger:** Something prevents completing the current task — missing dependency, broken imports, wrong types, missing env var, build config error.
**Action:** Fix it, verify, continue. No permission needed.

### Rule 4: Ask about architectural changes
**Trigger:** Fix requires significant structural modification — new DB table (not column), switching libraries/frameworks, changing auth approach, breaking API changes, new service layer.
**Action:** STOP. Report what you found, the proposed change, why it's needed, and alternatives. User decision required.

### Priority
1. Rule 4 applies → STOP (architectural decision needed)
2. Rules 1-3 apply → Fix automatically
3. Genuinely unsure → Treat as Rule 4 (ask)

### Scope Boundary
Only auto-fix issues DIRECTLY caused by the current task's changes. Pre-existing warnings, linting errors, or failures in unrelated files are out of scope. Log out-of-scope discoveries to `deferred-items.md` in the batch report — do NOT fix them.

### Fix Attempt Limit
After 3 auto-fix attempts on a single task, STOP fixing. Document remaining issues in the batch report under "Deferred Issues". Continue to the next task.

### Analysis Paralysis Guard
If you make 5+ consecutive Read/Grep/Glob calls without any Edit/Write/Bash action: STOP. State in one sentence why you haven't written anything yet. Then either write code (you have enough context) or report "blocked" with the specific missing information.

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
