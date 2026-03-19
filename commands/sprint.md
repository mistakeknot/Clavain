---
name: sprint
description: Phase sequencer — brainstorm, strategize, plan, execute, review, ship. Use /route for smart dispatch.
argument-hint: "[feature description or --from-step <step>]"
---

# Sprint — Phase Sequencer

Runs the full 10-phase lifecycle from brainstorm to ship. Normally invoked via `/route`. `CLAVAIN_BEAD_ID` set by caller; if unset, runs without bead tracking.

- `--from-step <n>`: jump to step name (brainstorm, strategy, plan, plan-review, execute, test, quality-gates, resolve, reflect, ship)
- Otherwise: `$ARGUMENTS` is feature description for Step 1

<BEHAVIORAL-RULES>
Non-negotiable:
1. Execute steps in order — no skipping, reordering, or parallelizing unless a step explicitly allows it.
2. Write artifacts to disk (docs/, .clavain/); later steps read files, not conversation context.
3. Stop at checkpoints/gates for user approval — never auto-approve.
4. Halt on failure — report what failed, what succeeded, what user can do. No silent retry or skip.
5. Local subagents (Task tool) by default — external agents (Codex, interserve) require explicit opt-in.
6. Never call EnterPlanMode — plan was created before this runs. Scope changes → stop and ask.
</BEHAVIORAL-RULES>

## Environment Bootstrap + Status

```bash
clavain-cli sprint-init "$CLAVAIN_BEAD_ID"
```

This single call validates the bead, reads complexity/phase/budget, registers interstat session attribution, and outputs a formatted status banner. No additional bootstrap commands needed.

Read the complexity from the banner output to decide routing:

- **1-2:** AskUserQuestion — "Skip to plan (Recommended)" or "Full workflow". If skip, jump to Step 3.
- **3:** Standard workflow; offer skip-to-plan if bead has clear description+AC.
- **4-5:** Full workflow, Opus orchestration.

`--from-step` always overrides complexity routing.

## Checkpointing

After each step: `clavain-cli checkpoint-write "$CLAVAIN_BEAD_ID" "<phase>" "<step_name>" "<plan_path>"`

Resume protocol:
1. `checkpoint_read` → validate git SHA (`checkpoint_validate`, warn not block) → `checkpoint_completed_steps`
2. Display: `Resuming from step <next>. Completed: [<steps>]`
3. Skip completed steps; load verdicts from `.clavain/verdicts/` if present

On Step 10 completion: `clavain-cli checkpoint-clear`

## Auto-Advance

Between steps, if `$(bd state "$CLAVAIN_BEAD_ID" sprint)` == `"true"`:
```bash
pause_reason=$(clavain-cli sprint-advance "$CLAVAIN_BEAD_ID" "<current_phase>" "<artifact_path>")
```
On non-zero exit, parse `reason_type="${pause_reason%%|*}"`:
- `gate_blocked` → AskUserQuestion: Fix issues / Skip gate / Stop sprint
- `manual_pause` → AskUserQuestion: Continue / Stop
- `stale_phase` → re-read state, route to new phase via `clavain-cli sprint-next-step`
- `budget_exceeded` → AskUserQuestion: Continue (override) / Stop / Adjust budget

Display at each advance: `Phase: <current> → <next> (auto-advancing)`. No "what next?" prompts unless pause triggered or step fails.

## Phase Tracking

After each step (silent, skip on error):
```bash
clavain-cli set-artifact "$CLAVAIN_BEAD_ID" "<artifact_type>" "<artifact_path>"
clavain-cli sprint-advance "$CLAVAIN_BEAD_ID" "<current_phase>"
```
Pass artifact path when one exists; empty string otherwise (quality-gates, ship).

---

## Step 1: Brainstorm

`/clavain:brainstorm $ARGUMENTS`

After doc created: set `phase=brainstorm`; `clavain-cli record-cost-estimate "$CLAVAIN_BEAD_ID" "brainstorm" 2>/dev/null || true`

## Step 2: Strategize

`/clavain:strategy`

Optionally run `/clavain:review-doc` on brainstorm first (set `phase=brainstorm-reviewed` after). After PRD created, run `/interpath:cuj` for each critical user-facing flow — skip only for purely internal changes. After strategy: set `phase=strategized`.

## Step 3: Write Plan

`/clavain:write-plan` → saves to `docs/plans/YYYY-MM-DD-<name>.md`. The command registers it via `set-artifact plan`.

If interserve mode active: write-plan auto-executes via Codex — skip Step 5.

After plan written: set `phase=planned`; `clavain-cli record-cost-estimate "$CLAVAIN_BEAD_ID" "planned" 2>/dev/null || true`

## Step 4: Review Plan

Budget context before flux-drive:
```bash
remaining=$(clavain-cli sprint-budget-remaining "$CLAVAIN_BEAD_ID")
[[ "$remaining" -gt 0 ]] && export FLUX_BUDGET_REMAINING="$remaining"
```

Cost preview: `clavain-cli sprint-budget-stage "$CLAVAIN_BEAD_ID" plan-review 2>/dev/null` — display token budget for this stage and which agents will be launched (skip silently on error).

```bash
plan_path=$(clavain-cli get-artifact "$CLAVAIN_BEAD_ID" "plan" 2>/dev/null) || plan_path=""
```
`/interflux:flux-drive $plan_path` — review before execution to catch plan-level risks early.

If P0/P1 issues found: stop and fix before proceeding. After passing: set `phase=plan-reviewed`.

## Step 5: Execute

```bash
plan_path=$(clavain-cli get-artifact "$CLAVAIN_BEAD_ID" "plan" 2>/dev/null) || plan_path=""
```

Gate check:
```bash
if ! clavain-cli enforce-gate "$CLAVAIN_BEAD_ID" "executing" "$plan_path"; then
    echo "Gate blocked: plan must be reviewed first. Run /interflux:flux-drive or set CLAVAIN_SKIP_GATE='reason'." >&2
    # Stop
fi
```

`/clavain:work $plan_path`

At START of execution: set `phase=executing`; `clavain-cli record-cost-estimate "$CLAVAIN_BEAD_ID" "executing" 2>/dev/null || true`

Parallel execution: use `dispatching-parallel-agents` skill for independent modules. Interserve mode auto-dispatches Codex agents.

## Step 6: Test & Verify

Run project test suite + linter. If tests fail: stop and fix — do NOT proceed with broken build. If no test command: note and proceed.

## Step 7: Quality Gates

Budget context (same pattern as Step 4):
```bash
remaining=$(clavain-cli sprint-budget-remaining "$CLAVAIN_BEAD_ID")
[[ "$remaining" -gt 0 ]] && export FLUX_BUDGET_REMAINING="$remaining"
```

Cost preview: `clavain-cli sprint-budget-stage "$CLAVAIN_BEAD_ID" quality-gates 2>/dev/null` — display token budget for this stage and which agents will be launched (skip silently on error).

`/clavain:quality-gates`

Parallel opportunity: if known TODOs from execution exist, start `/clavain:resolve` in parallel.

After completion, read verdicts:
```bash
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-verdict.sh"
verdict_parse_all       # STATUS  AGENT  SUMMARY table
verdict_count_by_status # e.g., "3 CLEAN, 1 NEEDS_ATTENTION"
```
- All CLEAN → proceed (one-line summary)
- Any NEEDS_ATTENTION → read detail via `verdict_get_attention`; report per-agent STATUS in sprint summary

Gate check after PASS:
```bash
if ! clavain-cli enforce-gate "$CLAVAIN_BEAD_ID" "shipping" ""; then
    echo "Gate blocked: re-run /clavain:quality-gates or set CLAVAIN_SKIP_GATE='reason'." >&2
    # Stop
fi
clavain-cli sprint-advance "$CLAVAIN_BEAD_ID" "shipping"
clavain-cli record-phase "$CLAVAIN_BEAD_ID" "shipping"
```
Do NOT set phase if gates FAIL.

## Step 8: Resolve Issues

`/clavain:resolve` — auto-detects source (todo files, PR comments, code TODOs), handles interserve mode.

After resolving: if quality-gates found recurring patterns, run `/clavain:compound` to document in `config/flux-drive/knowledge/`. If findings revealed a plan-level mistake, add `## Lessons Learned` to the plan file.

## Step 9: Reflect

`clavain-cli sprint-advance "$CLAVAIN_BEAD_ID" "shipping"` then `/reflect`.

`/reflect` owns artifact registration AND the `reflect → done` advance — do NOT call sprint-advance after it returns. Gate is soft (warn but allow if no reflect artifact).

## Step 10: Ship

Use `clavain:landing-a-change` skill to verify, document, commit.

After ship: `clavain-cli set-artifact "$CLAVAIN_BEAD_ID" "closed" "$(git rev-parse HEAD)" 2>/dev/null || true`; set `phase=done`; `bd close "$CLAVAIN_BEAD_ID" 2>/dev/null || true`

Close sweep:
```bash
swept=$(clavain-cli close-children "$CLAVAIN_BEAD_ID" "Shipped with parent epic $CLAVAIN_BEAD_ID")
[[ "$swept" -gt 0 ]] && echo "Auto-closed $swept child beads"
```

Sprint summary:
```
Sprint Summary:
- Bead: <CLAVAIN_BEAD_ID>
- Steps completed: <n>/10
- Budget: <tokens_spent>k / <token_budget>k (<percentage>%)
- Agents dispatched: <count>
- Verdicts: <verdict_count_by_status output>
- Estimated tokens: <verdict_total_tokens output>
- Swept: <swept> child beads auto-closed
```

Cost table — locate and run cost-query.sh:
```bash
_cost_script=""
_c="${CLAUDE_PLUGIN_ROOT}/../interstat/scripts/cost-query.sh"
[[ -f "$_c" ]] && _cost_script="$_c"
[[ -z "$_cost_script" && -n "${CLAVAIN_SOURCE_DIR:-}" ]] && _c="${CLAVAIN_SOURCE_DIR}/../../interverse/interstat/scripts/cost-query.sh" && [[ -f "$_c" ]] && _cost_script="$_c"
[[ -n "$_cost_script" ]] && _cost_rows=$(bash "$_cost_script" cost-usd --bead="$CLAVAIN_BEAD_ID" 2>/dev/null) || _cost_rows=""
```
If `_cost_rows` non-empty: display Model/Runs/Input/Output/Cost table. Then: `clavain-cli record-cost-actuals "$CLAVAIN_BEAD_ID" 2>/dev/null || true`
If empty: `(no cost data — bead attribution not active)`

## Error Recovery

1. Do NOT skip failed step
2. Retry once with tighter scope
3. If retry fails: report which step, the error, what succeeded

To resume: `/clavain:route` (auto-detects active sprint) or `/clavain:sprint --from-step <step>`.

Start with Step 1 now.
