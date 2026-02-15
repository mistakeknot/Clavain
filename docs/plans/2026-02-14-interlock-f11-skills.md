# F11: Coordination Skills — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Create two concise SKILL.md files in the interlock companion plugin that teach agents the file reservation workflow and conflict recovery protocol.

**Target Repo:** `/root/projects/interlock/`

**Bead:** Clavain-n23p

**PRD:** `docs/prds/2026-02-14-interlock-multi-agent-coordination.md` (F11)

---

### Task 1: Create `coordination-protocol/SKILL.md`

**Files:**
- Create: `/root/projects/interlock/skills/coordination-protocol/SKILL.md`

**Steps:**

1. Create the directory: `mkdir -p /root/projects/interlock/skills/coordination-protocol`

2. Write `SKILL.md` with the following structure (must be under 100 lines total):

**Frontmatter:**
```yaml
---
name: coordination-protocol
description: Use when multiple agents are editing the same repository — guides the reserve-work-release workflow to prevent file conflicts and lost work
---
```

**Content outline (all sections required):**

**## Overview** (3-4 lines)
- Interlock provides file-level coordination for multi-agent sessions
- Core principle: reserve before editing, release when done
- Prevents silent overwrites and merge conflicts between concurrent agents

**## Prerequisites** (3 lines)
- Agent must be registered via `/interlock:join` before reserving files
- intermute service must be running (verify with `/interlock:status`)

**## The Workflow** (15-20 lines)

Three-phase workflow with MCP tool names:

```
1. RESERVE: Before editing, call `reserve_files` with file patterns
   - Specify a reason (what you're doing)
   - Set appropriate TTL (default: 15 minutes)
   - If conflict returned, switch to conflict-recovery skill

2. WORK: Edit reserved files normally
   - Call `my_reservations` to verify what you hold
   - Extend reservation if work takes longer than expected

3. RELEASE: After done, call `release_files` or `release_all`
   - Release as soon as edits are committed
   - Stop hook auto-releases on session end (safety net, not primary)
```

**## MCP Tools Quick Reference** (12-15 lines)

Table format:
```
| Tool | Purpose |
|------|---------|
| `reserve_files` | Reserve files by glob pattern before editing |
| `release_files` | Release specific file reservations |
| `release_all` | Release all your reservations at once |
| `check_conflicts` | Check if files are reserved by another agent |
| `my_reservations` | List your current reservations |
| `list_agents` | Show all active agents in the project |
| `send_message` | Send a message to another agent |
| `fetch_inbox` | Check messages from other agents |
| `request_release` | Ask another agent to release their reservation |
```

**## Best Practices** (10-12 lines)

Bullet list:
- **Reserve narrowly** — reserve specific files, not entire directories
- **Short TTLs** — 15 minutes default; extend only if needed
- **Release early** — release as soon as you commit, don't hold until session end
- **Check before reserving** — call `check_conflicts` before `reserve_files` to avoid surprise 409s
- **Include a reason** — helps other agents understand why files are held
- **One concern per reservation** — separate reservations for separate tasks

**## Common Mistakes** (8-10 lines)

3-4 mistakes with fixes:
- Reserving too broadly (e.g., `src/**`) — reserve only files you will edit
- Forgetting to release after committing — always `release_files` or `release_all` after `git commit`
- Ignoring conflict responses — if `reserve_files` returns a conflict, do NOT edit the file anyway; the git pre-commit hook will block the commit
- Not joining first — `reserve_files` fails if agent is not registered; run `/interlock:join` first

**Line budget:** ~75-90 lines. Verify with `wc -l` after writing.

**Acceptance criteria:**
- [ ] File exists at `skills/coordination-protocol/SKILL.md`
- [ ] Valid YAML frontmatter with `name` and `description` fields
- [ ] Description starts with "Use when" and contains no workflow summary
- [ ] All 9 MCP tool names appear in the file (`reserve_files`, `release_files`, `release_all`, `check_conflicts`, `my_reservations`, `send_message`, `fetch_inbox`, `list_agents`, `request_release`)
- [ ] References `/interlock:join` and `/interlock:status` commands
- [ ] Total line count < 100 (verify with `wc -l`)

---

### Task 2: Create `conflict-recovery/SKILL.md`

**Files:**
- Create: `/root/projects/interlock/skills/conflict-recovery/SKILL.md`

**Steps:**

1. Create the directory: `mkdir -p /root/projects/interlock/skills/conflict-recovery`

2. Write `SKILL.md` with the following structure (must be under 100 lines total):

**Frontmatter:**
```yaml
---
name: conflict-recovery
description: Use when a file edit is blocked because another agent holds a reservation — guides recovery from check status through escalation
---
```

**Content outline (all sections required):**

**## Overview** (3-4 lines)
- When you try to reserve or edit a file held by another agent, you hit a conflict
- The PreToolUse:Edit hook warns you; the git pre-commit hook blocks commits
- This skill teaches the escalation ladder for resolving conflicts without losing work

**## When This Applies** (4-5 lines)
- `reserve_files` returns a conflict (409)
- PreToolUse:Edit hook warns that a file is reserved by another agent
- `git commit` is rejected by the pre-commit hook due to reserved files
- You discover via `/interlock:status` that files you need are held

**## Recovery Ladder** (25-30 lines)

Ordered escalation steps — try each before moving to the next:

```
### Step 1: Check Status
Call `check_conflicts` or run `/interlock:status` to see:
- Who holds the reservation (agent name + ID)
- Why (the reason string)
- When it expires (expires_at timestamp)

### Step 2: Work Elsewhere
If other unreserved files need attention, work on those first.
The reservation may expire or be released while you work.
Call `my_reservations` to see what you already hold.

### Step 3: Request Release
Call `request_release` with the holding agent's name or ID.
This sends a message asking them to release.
The other agent's `fetch_inbox` will surface your request.
Wait 1-2 minutes for a response before escalating.

### Step 4: Wait for Expiry
Check the `expires_at` timestamp from Step 1.
If expiry is <5 minutes away, wait it out.
Stale reservations are auto-cleaned by intermute every 60 seconds.

### Step 5: Escalate to User
If the reservation holder is unresponsive and the work is urgent:
- Report the conflict to the user with agent name, file, and reason
- User can manually run `/interlock:status` and decide
- User can force-release via intermute admin or `git commit --no-verify` (last resort)
```

**## Key MCP Tools for Recovery** (6-8 lines)

Subset table:
```
| Tool | When to Use |
|------|-------------|
| `check_conflicts` | Step 1: see who holds the file |
| `list_agents` | Identify the holding agent |
| `request_release` | Step 3: ask them to release |
| `fetch_inbox` | Check if they responded |
```

**## Common Mistakes** (8-10 lines)

3-4 mistakes with fixes:
- Immediately requesting release without checking expiry — if it expires in 2 minutes, just wait
- Editing the file anyway despite the warning — the git pre-commit hook will block your commit
- Using `git commit --no-verify` without user approval — this bypasses safety and risks overwriting another agent's work
- Not checking your own reservations — you might hold files the other agent needs; consider a mutual release

**Line budget:** ~65-85 lines. Verify with `wc -l` after writing.

**Acceptance criteria:**
- [ ] File exists at `skills/conflict-recovery/SKILL.md`
- [ ] Valid YAML frontmatter with `name` and `description` fields
- [ ] Description starts with "Use when" and contains no workflow summary
- [ ] References MCP tools: `check_conflicts`, `list_agents`, `request_release`, `fetch_inbox`
- [ ] References `/interlock:status` command
- [ ] Recovery ladder has 5 ordered steps (check, work elsewhere, request, wait, escalate)
- [ ] Total line count < 100 (verify with `wc -l`)

---

## Pre-flight Checklist

- [ ] Verify interlock repo exists: `ls /root/projects/interlock/`
- [ ] Verify `skills/` directory exists or create it: `mkdir -p /root/projects/interlock/skills/`
- [ ] Review MCP tool names in F6 section of PRD to confirm exact names

## Post-execution Checklist

- [ ] Both skills created:
  - `skills/coordination-protocol/SKILL.md`
  - `skills/conflict-recovery/SKILL.md`
- [ ] Both files have valid YAML frontmatter (test with: `python3 -c "import yaml; yaml.safe_load(open('SKILL.md').read().split('---')[1])"`)
- [ ] Both files are under 100 lines (`wc -l skills/*/SKILL.md`)
- [ ] `coordination-protocol` references all 9 MCP tool names
- [ ] `conflict-recovery` references at least 4 MCP tool names (`check_conflicts`, `list_agents`, `request_release`, `fetch_inbox`)
- [ ] Both skills reference `/interlock:status` command
- [ ] No workflow summary in either description field (CSO compliance)
- [ ] Bead Clavain-n23p updated with completion status
