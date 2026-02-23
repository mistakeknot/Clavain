# Executing Plans (compact)

Load plan, review critically, execute in batches, report between batches.

## Process

### Step 1: Load and Review

Read plan. Raise concerns with user before starting. If no concerns, create TodoWrite.

### Step 2: Check Mode

```bash
[ -f "$(pwd)/.claude/clodex-toggle.flag" ] && echo "INTERSERVE" || echo "DIRECT"
```

**INTERSERVE →** Classify tasks (independent → Codex parallel, sequential → ordered, exploratory → Claude subagent). Group into batches (max 5). Use `clavain:interserve` to dispatch. Read `.verdict` sidecar first. Between batches: report and wait for feedback.

**DIRECT →** Execute first 3 tasks per batch. Per task: mark in_progress → follow plan steps exactly → run verifications → mark completed.

### Step 3: Report

After each batch: show what was implemented, verification output. Say "Ready for feedback."

### Step 4: Continue

Apply feedback, execute next batch, repeat.

### Step 5: Complete

Use `clavain:landing-a-change` for final verification and commit.

## When to Stop

Hit a blocker, plan has critical gaps, instruction unclear, verification fails repeatedly. **Ask, don't guess.**

---

*For detailed interserve dispatch protocol or Codex failure handling, read SKILL.md.*
