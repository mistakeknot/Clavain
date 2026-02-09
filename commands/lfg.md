---
name: lfg
description: Full autonomous engineering workflow — brainstorm, plan, execute, review, ship
argument-hint: "[feature description]"
---

Run these steps in order. Do not do anything else.

## Step 1: Brainstorm
`/clavain:brainstorm $ARGUMENTS`

## Step 2: Plan + Execute
`/clavain:write-plan`

Remember the plan file path (saved to `docs/plans/YYYY-MM-DD-<name>.md`) — it's needed in Step 4.

**Note:** When clodex mode is active, `/write-plan` auto-selects Codex Delegation and executes the plan via Codex agents. In this case, skip Step 3 (work) — the plan has already been executed.

## Step 3: Execute (non-clodex only)

Check if clodex mode is active:
```bash
[[ -f "${CLAUDE_PROJECT_DIR:-.}/.claude/autopilot.flag" ]]
```

- If **clodex is active**: Skip this step — `/write-plan` already executed via Codex Delegation in Step 2.
- If **clodex is NOT active**: Run `/clavain:work`

## Step 4: Review Plan
`/clavain:flux-drive <plan-file-from-step-2>`

Pass the plan file path from Step 2 as the flux-drive target. When clodex mode is active, flux-drive automatically dispatches review agents through Codex (Step 2.3 in flux-drive SKILL.md).

## Step 5: Code Review
`/clavain:review`

## Step 6: Resolve Issues (clodex-aware)

Check if clodex mode is active (`.claude/autopilot.flag` exists):
- If **clodex is active**: Run `/clavain:resolve-todo-parallel`. The command's clodex-mode guidance will automatically route code-modifying resolutions through Codex dispatch.
- If **clodex is NOT active**: Run `/clavain:resolve-todo-parallel` normally.

## Step 7: Quality Gates
`/clavain:quality-gates`

Start with Step 1 now.
