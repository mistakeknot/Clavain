# P2 Quick Wins Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Add guessable command aliases, consolidate upstream-check API calls, and slim down session-start injection.

**Architecture:** Three independent tasks touching disjoint file sets. Perfect for parallel Codex delegation.

**Tech Stack:** Markdown (commands), Bash (scripts), bats-core + pytest (tests)

**Beads:** Clavain-np7b (Task 1), Clavain-4728 (Task 2), Clavain-p5ex (Task 3)

---

### Task 1: Command Aliases (Clavain-np7b)

**Files:**
- Create: `commands/deep-review.md`
- Create: `commands/full-pipeline.md`
- Create: `commands/cross-review.md`
- Modify: `commands/help.md`
- Modify: `skills/using-clavain/SKILL.md` (add aliases to routing table)
- Modify: `tests/structural/test_commands.py` (33 → 36)
- Modify: `CLAUDE.md` (33 → 36 commands in overview)
- Modify: `AGENTS.md` (33 → 36 commands in 3 places)
- Modify: `.claude-plugin/plugin.json` (33 → 36 in description)

**Step 1: Create `commands/deep-review.md`**

```markdown
---
name: deep-review
description: "Alias for flux-drive — intelligent multi-agent document review"
user-invocable: true
argument-hint: "[path to file or directory]"
---

Use the `clavain:flux-drive` skill to review the document or directory specified by the user. Pass the file or directory path as context.
```

**Step 2: Create `commands/full-pipeline.md`**

```markdown
---
name: full-pipeline
description: "Alias for lfg — full autonomous engineering workflow"
argument-hint: "[feature description]"
---

Run these steps in order. Do not do anything else.

## Step 1: Brainstorm
`/clavain:brainstorm $ARGUMENTS`

## Step 2: Strategize
`/clavain:strategy`

Structures the brainstorm into a PRD, creates beads for tracking, and validates with flux-drive before planning.

**Optional:** Run `/clavain:review-doc` on the brainstorm output first for a quick polish before structuring.

## Step 3: Write Plan
`/clavain:write-plan`

Remember the plan file path (saved to `docs/plans/YYYY-MM-DD-<name>.md`) — it's needed in Step 4.

**Note:** When clodex mode is active, `/write-plan` auto-selects Codex Delegation and executes the plan via Codex agents. In this case, skip Step 5 (execute) — the plan has already been executed.

## Step 4: Review Plan (gates execution)
`/clavain:flux-drive <plan-file-from-step-3>`

Pass the plan file path from Step 3 as the flux-drive target. Review happens **before** execution so plan-level risks are caught early.

If flux-drive finds P0/P1 issues, stop and address them before proceeding to execution.

## Step 5: Execute

Run `/clavain:work <plan-file-from-step-3>`

**Parallel execution:** When the plan has independent modules, dispatch them in parallel using the `dispatching-parallel-agents` skill. This is automatic when clodex mode is active (executing-plans detects the flag and dispatches Codex agents).

## Step 6: Test & Verify

Run the project's test suite and linting before proceeding to review:

```bash
# Run project's test command (go test ./... | npm test | pytest | cargo test)
# Run project's linter if configured
```

**If tests fail:** Stop. Fix failures before proceeding. Do NOT continue to quality gates with a broken build.

**If no test command exists:** Note this and proceed — quality-gates will still run reviewer agents.

## Step 7: Quality Gates
`/clavain:quality-gates`

**Parallel opportunity:** Quality gates and resolve can overlap — quality-gates spawns review agents while resolve addresses already-known findings. If you have known TODOs from execution, start `/clavain:resolve` in parallel with quality-gates.

## Step 8: Resolve Issues

Run `/clavain:resolve` — it auto-detects the source (todo files, PR comments, or code TODOs) and handles clodex mode automatically.

## Step 9: Ship

Use the `clavain:landing-a-change` skill to verify, document, and commit the completed work.

## Error Recovery

If any step fails:

1. **Do NOT skip the failed step** — each step's output feeds into later steps
2. **Retry once** with a tighter scope (e.g., fewer features, smaller change set)
3. **If retry fails**, stop and report:
   - Which step failed
   - The error or unexpected output
   - What was completed successfully before the failure

To **resume from a specific step**, re-invoke `/clavain:lfg` and manually skip completed steps by running their slash commands directly (e.g., start from Step 6 by running `/clavain:quality-gates`).

Start with Step 1 now.
```

**Step 3: Create `commands/cross-review.md`**

```markdown
---
name: cross-review
description: "Alias for interpeer — cross-AI peer review (Claude ↔ Codex/Oracle)"
argument-hint: "[files or description to review]"
---

# Cross-AI Peer Review

Get a quick second opinion from the other AI.

## Arguments

<review_target> #$ARGUMENTS </review_target>

**If empty:** Review the most recently changed files (`git diff --name-only HEAD~1..HEAD`).

## Execution

Load the `interpeer` skill and follow its workflow.

## Escalation

If the user wants deeper review, switch modes within `interpeer`:
- **"go deeper"** or **"use Oracle"** → Switch to `deep` mode
- **"get consensus"** or **"council"** → Switch to `council` mode
- **"what do they disagree on?"** → Switch to `mine` mode
```

**Step 4: Update `commands/help.md`**

Add aliases to the Daily Drivers table. After the existing `/clavain:interpeer` row (line 21), add:

```markdown

> **Aliases:** `/deep-review` = flux-drive, `/full-pipeline` = lfg, `/cross-review` = interpeer
```

**Step 5: Update counts (33 → 36)**

In `tests/structural/test_commands.py` line 23: change `== 33` to `== 36`.

In `CLAUDE.md`: change `33 commands` to `36 commands` in the overview line and the `ls commands/*.md | wc -l` comment.

In `AGENTS.md`: change `33 commands` to `36 commands` in all 3 places it appears (grep for `33 commands`).

In `.claude-plugin/plugin.json`: change `33 commands` to `36 commands` in the description field.

In `skills/using-clavain/SKILL.md` line 18: change `33 commands` to `36 commands`.

**Step 6: Run tests**

Run: `cd /root/projects/Clavain/tests && uv run pytest structural/test_commands.py -q`
Expected: All pass with new count of 36.

**Step 7: Commit**

```bash
git add commands/deep-review.md commands/full-pipeline.md commands/cross-review.md commands/help.md tests/structural/test_commands.py CLAUDE.md AGENTS.md .claude-plugin/plugin.json skills/using-clavain/SKILL.md
git commit -m "feat: add guessable command aliases (Clavain-np7b)

- /deep-review → flux-drive
- /full-pipeline → lfg
- /cross-review → interpeer
- Update help.md, counts (33 → 36)"
```

---

### Task 2: Consolidate upstream-check API calls (Clavain-4728)

**Files:**
- Modify: `scripts/upstream-check.sh` (lines 59-62)

**Step 1: Replace 3 redundant API calls with 1**

Replace lines 59-62 in `scripts/upstream-check.sh`:

```bash
  # Get latest commit SHA + message + date on default branch (single API call)
  commit_json=$(gh api "repos/${repo}/commits?per_page=1" 2>/dev/null || echo '[]')
  latest_commit=$(echo "$commit_json" | jq -r '.[0].sha[:7] // "unknown"')
  latest_commit_msg=$(echo "$commit_json" | jq -r '.[0].commit.message | split("\n")[0] // ""')
  latest_commit_date=$(echo "$commit_json" | jq -r '.[0].commit.committer.date[:10] // ""')
```

**Step 2: Syntax check**

Run: `bash -n scripts/upstream-check.sh`
Expected: OK

**Step 3: Commit**

```bash
git add scripts/upstream-check.sh
git commit -m "perf: consolidate upstream-check API calls from 3 to 1 per repo (Clavain-4728)"
```

---

### Task 3: Split using-clavain injection (Clavain-p5ex)

**Files:**
- Modify: `skills/using-clavain/SKILL.md` (117 → ~45 lines)
- Create: `skills/using-clavain/references/routing-tables.md`

**Step 1: Create `skills/using-clavain/references/routing-tables.md`**

Move the full routing tables (Layer 1-3, review command comparison, cross-AI review modes) from `SKILL.md` into this reference file. This is the complete routing reference that `/clavain:help` and on-demand skill reads can access.

The file should contain all content from lines 26-91 of the current `SKILL.md` (the routing tables section), prefixed with:

```markdown
# Clavain Routing Tables

Full routing reference for skills, agents, and commands. This is the detailed version of the compact router injected at session start.

For the compact version, see the `using-clavain` skill.
```

**Step 2: Rewrite `skills/using-clavain/SKILL.md` as compact router**

Keep the frontmatter, the skill invocation rule, the access instructions, and a condensed routing heuristic. Replace the full tables with a compact top-commands-per-stage list:

```markdown
---
name: using-clavain
description: Use when starting any conversation - establishes how to find and use skills, agents, and commands, requiring Skill tool invocation before ANY response including clarifying questions
---

**Proactive skill invocation is required.** When a skill matches the current task — even partially — invoke it before responding. Skills are designed to be triggered automatically; skipping a relevant skill degrades output quality.

## How to Access Skills

**In Claude Code:** Use the `Skill` tool. When you invoke a skill, its content is loaded and presented to you—follow it directly. Never use the Read tool on skill files.

**In Codex CLI:** Install Clavain skills with `bash ~/.codex/clavain/scripts/install-codex.sh install`. Codex discovers them from `~/.agents/skills/clavain/` on startup, so restart Codex after install.

# Quick Router — 36 commands, 30 skills, 16 agents

| You want to... | Run this |
|----------------|----------|
| Build a feature end-to-end | `/lfg` (alias: `/full-pipeline`) |
| Review code, docs, or plans | `/flux-drive` (alias: `/deep-review`) |
| Quick review from git diff | `/quality-gates` |
| Cross-AI second opinion | `/interpeer` (alias: `/cross-review`) |
| Plan an implementation | `/write-plan` → `/work` |
| Fix a bug | `/repro-first-debugging` |
| Fix build/test failure | `/fixbuild` |
| Resolve review findings | `/resolve` |
| Check project health | `/doctor` or `/sprint-status` |
| See all commands | `/help` |

## Routing Heuristic

When a user message arrives:

1. **Detect stage** from the request ("build" → Execute, "fix bug" → Debug, "review" → Review, "plan" → Plan, "what should we" → Explore)
2. **Detect domain** from context (file types, topic, recent conversation)
3. **Invoke the primary skill first** (process skills before domain skills before meta skills)

For the full routing tables with all skills, agents, and commands by stage/domain/concern, see `using-clavain/references/routing-tables.md`.

## Red Flag

If you catch yourself thinking "I'll just do this without a skill" — STOP. Check for a matching skill first. Skills evolve; read the current version even if you "remember" it.
```

**Step 3: Run structural tests**

Run: `cd /root/projects/Clavain/tests && uv run pytest structural/ -q`
Expected: All pass (skill count unchanged, SKILL.md still exists)

**Step 4: Verify session-start hook**

Run: `cd /tmp && bash /root/projects/Clavain/hooks/session-start.sh 2>/dev/null | jq '.additionalContext' | wc -c`

Verify the additionalContext size decreased (should be smaller than before).

**Step 5: Commit**

```bash
git add skills/using-clavain/SKILL.md skills/using-clavain/references/routing-tables.md
git commit -m "feat: split using-clavain into compact router + reference tables (Clavain-p5ex)

Reduces session-start injection from ~1100 to ~500 tokens.
Full routing tables moved to references/routing-tables.md."
```

---

## Final Verification

After all tasks complete:

```bash
# Structural tests (verifies counts)
cd /root/projects/Clavain/tests && uv run pytest structural/ -q

# All bats tests
bats tests/shell/auto_compound.bats tests/shell/session_start.bats tests/shell/sprint_scan.bats tests/shell/lib.bats

# Syntax check scripts
bash -n scripts/upstream-check.sh

# Session-start JSON valid
cd /tmp && bash /root/projects/Clavain/hooks/session-start.sh 2>/dev/null | jq .

# Manifest valid
python3 -c "import json; json.load(open('/root/projects/Clavain/.claude-plugin/plugin.json'))"
```

Close beads:

```bash
bd close Clavain-np7b Clavain-4728 Clavain-p5ex
```
