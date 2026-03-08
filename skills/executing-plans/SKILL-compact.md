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

## Deviation Rules

During execution you WILL find unplanned work. Apply automatically:

- **R1 Auto-fix bugs** (wrong queries, type errors, null pointers) — fix inline, no permission needed
- **R2 Auto-add critical functionality** (missing validation, auth, error handling) — add it, no permission needed
- **R3 Auto-fix blockers** (missing deps, broken imports) — fix it, no permission needed
- **R4 Ask about architectural changes** (new DB tables, framework switches, breaking APIs) — STOP, user decision required

**Priority:** R4 (stop) > R1-R3 (auto-fix) > unsure (treat as R4).

**Scope:** Only fix issues caused by the current task. Pre-existing issues → deferred-items. 3 fix attempts per task max, then defer.

**Stuck guard:** 5+ reads without writes = stuck. Write code or declare blocked.

## When to Stop

Hit a blocker, plan has critical gaps, instruction unclear, verification fails repeatedly. **Ask, don't guess.**

---

*For detailed interserve dispatch protocol or Codex failure handling, read SKILL.md.*
