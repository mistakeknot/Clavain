---
name: lfg
description: Full autonomous engineering workflow — brainstorm, plan, execute, review, ship
argument-hint: "[feature description]"
---

Run these steps in order. Do not do anything else.

## Step 1: Brainstorm
`/clavain:brainstorm $ARGUMENTS`

## Step 2: Write Plan
`/clavain:write-plan`

Remember the plan file path (saved to `docs/plans/YYYY-MM-DD-<name>.md`) — it's needed in Step 3.

**Note:** When clodex mode is active, `/write-plan` auto-selects Codex Delegation and executes the plan via Codex agents. In this case, skip Step 4 (execute) — the plan has already been executed.

## Step 3: Review Plan (gates execution)
`/clavain:flux-drive <plan-file-from-step-2>`

Pass the plan file path from Step 2 as the flux-drive target. Review happens **before** execution so plan-level risks are caught early.

If flux-drive finds P0/P1 issues, stop and address them before proceeding to execution.

## Step 4: Execute

Run `/clavain:work <plan-file-from-step-2>`

## Step 5: Test & Verify

Run the project's test suite and linting before proceeding to review:

```bash
# Run project's test command (go test ./... | npm test | pytest | cargo test)
# Run project's linter if configured
```

**If tests fail:** Stop. Fix failures before proceeding. Do NOT continue to quality gates with a broken build.

**If no test command exists:** Note this and proceed — quality-gates will still run reviewer agents.

## Step 6: Quality Gates
`/clavain:quality-gates`

## Step 7: Resolve Issues

Run `/clavain:resolve` — it auto-detects the source (todo files, PR comments, or code TODOs) and handles clodex mode automatically.

## Step 8: Ship

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
