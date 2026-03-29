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
3. Stop at checkpoints/gates for user approval — never auto-approve (unless autonomy tier allows).
4. Halt on failure — report what failed, what succeeded, what user can do. No silent retry or skip.
5. Local subagents (Task tool) by default — external agents (Codex, interserve) require explicit opt-in.
6. Never call EnterPlanMode — plan was created before this runs. Scope changes → stop and ask.
7. **Exactly 10 steps.** Do NOT invent, rename, or append steps beyond the 10 defined below.
</BEHAVIORAL-RULES>

## Progress Tracking

Display this checklist after bootstrap and update after each step. Use exact step names.

```
Sprint Progress (<CLAVAIN_BEAD_ID>):
- [ ] Step 1:  Brainstorm
- [ ] Step 2:  Strategy
- [ ] Step 3:  Write Plan
- [ ] Step 4:  Plan Review
- [ ] Step 5:  Execute
- [ ] Step 6:  Test & Verify
- [ ] Step 7:  Quality Gates
- [ ] Step 8:  Resolve
- [ ] Step 9:  Reflect
- [ ] Step 10: Ship
```

Mark each `[x]` as completed. Append artifact path: `✓ docs/plans/...`. After Step 10, sprint is **done** — no further steps exist.

## Environment Bootstrap + Status

```bash
clavain-cli sprint-init "$CLAVAIN_BEAD_ID"
```

This single call validates the bead, reads complexity/phase/budget, registers interstat session attribution, and outputs a formatted status banner. No additional bootstrap commands needed.

**Surface recent learnings:**
```bash
recent_learnings=$(clavain-cli recent-reflect-learnings "$CLAVAIN_BEAD_ID" 3 2>/dev/null) || recent_learnings=""
if [[ -n "$recent_learnings" ]]; then
    printf 'Past learnings that influenced this sprint:\n%s\n' "$recent_learnings"
fi
```

Read the complexity from the banner output to decide routing and autonomy tier.

## Autonomy Tiers

Determine the autonomy tier from complexity (or `--autonomy=<1|2|3>` override, or `bd state "$CLAVAIN_BEAD_ID" autonomy_tier`):

| Tier | Complexity | Behavior |
|------|-----------|----------|
| **1** | C1-C2 | **Full auto.** Skip brainstorm dialogue, auto-approve plan review if no P0/P1, auto-advance all steps. Only gate: quality-gates FAIL pauses. |
| **2** | C3 | **One checkpoint.** Auto-advance brainstorm → plan. Pause after plan review for user confirmation. Auto-advance execute → ship. |
| **3** | C4-C5 | **Interactive.** All AskUserQuestion checkpoints active (current behavior). |

```bash
autonomy_override=$(bd state "$CLAVAIN_BEAD_ID" autonomy_tier 2>/dev/null) || autonomy_override=""
if [[ -n "$autonomy_override" && "$autonomy_override" =~ ^[123]$ ]]; then
    autonomy_tier="$autonomy_override"
elif [[ "$complexity" -le 2 ]]; then
    autonomy_tier=1
elif [[ "$complexity" -eq 3 ]]; then
    autonomy_tier=2
else
    autonomy_tier=3
fi
```

Display: `Autonomy: Tier $autonomy_tier`. Pass tier to sub-commands via `CLAVAIN_AUTONOMY_TIER=$autonomy_tier`.

**Tier 1 routing:** Skip brainstorm (Phase 0 detects clear requirements → jump to Step 3). If brainstorm is needed (ambiguous), escalate to Tier 2.

**Tier 2 routing:** Standard workflow; auto-advance except pause after Step 4 (plan review).

**Tier 3 routing:** Full workflow with all checkpoints.

`--from-step` always overrides complexity routing. `--autonomy=<tier>` overrides tier. `bd set-state <bead> manual_pause true` forces pause at next checkpoint regardless of tier.

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
- `strategic_contradiction` → AskUserQuestion: Revise plan to align / Update lane intent / Override and continue / Stop sprint. Display the contradiction reason and the lane's strategic_intent for context.

Display at each advance: `Phase: <current> → <next> (auto-advancing)`. No "what next?" prompts unless pause triggered, step fails, or tier requires a checkpoint at this step.

**Tier-aware checkpoints:** Tier 1 pauses only on `gate_blocked` (quality-gates FAIL). Tier 2 also pauses after Step 4 (plan review). Tier 3 preserves all existing AskUserQuestion calls in sub-commands.

## Phase Tracking

After each step (silent, skip on error):
```bash
clavain-cli set-artifact "$CLAVAIN_BEAD_ID" "<artifact_type>" "<artifact_path>"
clavain-cli sprint-advance "$CLAVAIN_BEAD_ID" "<current_phase>" || echo "WARNING: phase advance failed (artifact was recorded)" >&2
```
Artifact is always recorded even if advance fails. This is intentional — artifacts provide audit trail regardless of phase state. If advance fails, log the warning but do not halt the sprint.

Pass artifact path when one exists; empty string otherwise (quality-gates, ship).

### Provenance Recording (rsj.1.7)

After each artifact write, record its provenance vector — the chain of inputs that produced it. This enables backward tracing (stemma) when debugging failures.

```bash
# Gather input artifact paths for this step
input_artifacts=""  # comma-separated list of artifact types this step consumed
# Step 1 (brainstorm): inputs="" (no prior artifacts)
# Step 2 (strategy): inputs="brainstorm"
# Step 3 (plan): inputs="brainstorm,prd"
# Step 4 (review): inputs="plan"
# Step 5 (execute): inputs="plan"
# Step 6 (test): inputs="" (tests current code state)
# Step 7 (quality): inputs="test-pass-sha"
# Step 10 (ship): inputs="test-pass-sha"

provenance_json=$(jq -n \
    --arg session "${CLAUDE_SESSION_ID:-unknown}" \
    --arg bead "$CLAVAIN_BEAD_ID" \
    --arg step "<step_name>" \
    --arg inputs "$input_artifacts" \
    --arg output "<artifact_path>" \
    --arg ts "$(date +%s)" \
    '{session:$session, bead:$bead, step:$step, inputs:($inputs|split(",")|map(select(.!=""))), output:$output, ts:($ts|tonumber)}')
bd set-state "$CLAVAIN_BEAD_ID" "provenance_<artifact_type>=$provenance_json" 2>/dev/null || true
```

The provenance DAG can be walked backward via: `bd state <bead> provenance_<type>` → read `inputs[]` → resolve each input's provenance → recurse.

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

**Auto-run — no AskUserQuestion before starting.** The Tier 2 checkpoint pauses *after* the review to present findings, not before.

Budget context before review:
```bash
remaining=$(clavain-cli sprint-budget-remaining "$CLAVAIN_BEAD_ID")
[[ "$remaining" -gt 0 ]] && export FLUX_BUDGET_REMAINING="$remaining"
```

Cost preview: `clavain-cli sprint-budget-stage "$CLAVAIN_BEAD_ID" plan-review 2>/dev/null` — display token budget for this stage and which agents will be launched (skip silently on error).

### 4a: Generate project-specific review agents

```bash
plan_path=$(clavain-cli get-artifact "$CLAVAIN_BEAD_ID" "plan" 2>/dev/null) || plan_path=""
```

`/interflux:flux-gen` — auto-detect project domains and generate `fd-*` agents in `.claude/agents/`. Use `skip-existing` mode (no confirmation, no overwrite). If agents already exist, this completes in seconds. If flux-gen fails or no domains detected, proceed — core agents work without domain specialization.

### 4b: Run plan review

`/interflux:flux-drive $plan_path` — review before execution to catch plan-level risks early. flux-drive auto-discovers project agents generated in 4a and gives them a triage bonus.

### 4c: Tier-aware checkpoint

- **Tier 1:** Auto-approve if no P0/P1 findings. Proceed to Step 5 immediately.
- **Tier 2:** Present findings summary. If P0/P1 found, stop and fix. If clean or P2+ only, proceed to Step 5.
- **Tier 3:** AskUserQuestion with findings. Wait for explicit approval.

After passing: set `phase=plan-reviewed`.

### 4d: Strategic intent validation (rsj.1.5)

If lane intent exists on this bead:
```bash
lane_intent=$(bd state "$CLAVAIN_BEAD_ID" lane_intent 2>/dev/null) || lane_intent=""
```

When `lane_intent` is non-empty, check whether the plan contradicts it. Use a haiku agent (foreground, ~500 tokens):
- Input: plan summary (first 500 chars), lane intent text
- Prompt: "Does this plan contradict or undermine the lane's strategic intent? Return JSON: `{\"contradicts\": bool, \"reason\": \"...\"}`"
- If `contradicts == true`:
  1. Display: `Strategic contradiction detected: <reason>` + lane intent
  2. Escalate: `sprint_escalate_strategic_contradiction "$CLAVAIN_BEAD_ID" "$lane_name" "$reason"`
  3. The escalation pauses the lane and records evidence
  4. Emit pause: `echo "strategic_contradiction|plan-reviewed|$reason"` → user decision flow

If no lane intent or `contradicts == false`: proceed silently to Step 5.

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

**Record test-pass artifact** (canonical test result — downstream steps check this instead of re-running):
```bash
clavain-cli set-artifact "$CLAVAIN_BEAD_ID" "test-pass-sha" "$(git rev-parse HEAD)" 2>/dev/null || true
```

This SHA lets landing-a-change (Step 10) skip re-running tests when HEAD hasn't moved since the last pass.

## Step 7: Quality Gates

Budget context (same pattern as Step 4):
```bash
remaining=$(clavain-cli sprint-budget-remaining "$CLAVAIN_BEAD_ID")
[[ "$remaining" -gt 0 ]] && export FLUX_BUDGET_REMAINING="$remaining"
```

Cost preview: `clavain-cli sprint-budget-stage "$CLAVAIN_BEAD_ID" quality-gates 2>/dev/null` — display token budget for this stage and which agents will be launched (skip silently on error).

`/clavain:quality-gates`

Quality-gates is a gate orchestrator: it prepares the diff, delegates agent selection/dispatch to flux-drive (which handles triage, project agents, routing overrides, content slicing), and enforces the pass/fail gate. It handles verdict recording, gate enforcement, and phase advancement internally.

**Parallel Window 1 (optional):** While flux-drive agents run, if known TODOs from execution exist, start `/clavain:resolve` in a background agent. Quality-gates writes `quality-verdict` artifact; resolve writes `resolution` artifact — no type conflicts.

After quality-gates returns, read verdicts:
```bash
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-verdict.sh"
verdict_parse_all       # STATUS  AGENT  SUMMARY table
verdict_count_by_status # e.g., "3 CLEAN, 1 NEEDS_ATTENTION"
```
- All CLEAN → proceed (one-line summary)
- Any NEEDS_ATTENTION → read detail via `verdict_get_attention`; report per-agent STATUS in sprint summary

Sprint-level gate check (verify quality-gates advanced phase):
```bash
if ! clavain-cli enforce-gate "$CLAVAIN_BEAD_ID" "shipping" ""; then
    echo "Gate blocked: re-run /clavain:quality-gates or set CLAVAIN_SKIP_GATE='reason'." >&2
    # Stop
fi
clavain-cli sprint-advance "$CLAVAIN_BEAD_ID" "shipping"
```
Do NOT set phase if gates FAIL.

## Step 8: Resolve Issues

If resolve was already dispatched in parallel during Step 7, check if it completed:
```bash
resolution=$(clavain-cli get-artifact "$CLAVAIN_BEAD_ID" "resolution" 2>/dev/null) || resolution=""
```
If `resolution` is set, skip to Step 9 (already resolved). Otherwise run now:

`/clavain:resolve` — auto-detects source (todo files, PR comments, code TODOs), handles interserve mode.

After resolving: if quality-gates found recurring patterns, run `/clavain:compound` to document in `config/flux-drive/knowledge/`. If findings revealed a plan-level mistake, add `## Lessons Learned` to the plan file.

## Step 9: Reflect

### 9a: Decomposition quality actuals (rsj.1.9.1)

Before running /reflect, collect decomposition actuals for calibration. This is stage 2 (collect actuals — outcome side) of the closed-loop pattern.

```bash
# Check if this bead has a decomposition prediction (was it an epic with children?)
decomp_pred=$(bd state "$CLAVAIN_BEAD_ID" decomp_prediction 2>/dev/null) || decomp_pred=""
if [[ -n "$decomp_pred" ]]; then
    # Collect actuals
    actual_children=$(bd children "$CLAVAIN_BEAD_ID" --json 2>/dev/null | jq 'length' 2>/dev/null) || actual_children=0
    closed_children=$(bd children "$CLAVAIN_BEAD_ID" --json 2>/dev/null | jq '[.[] | select(.status=="closed")] | length' 2>/dev/null) || closed_children=0
    deferred_children=$(bd children "$CLAVAIN_BEAD_ID" --json 2>/dev/null | jq '[.[] | select(.status=="deferred")] | length' 2>/dev/null) || deferred_children=0
    predicted_children=$(echo "$decomp_pred" | jq -r '.predicted_children' 2>/dev/null) || predicted_children=0

    # Re-planning events: children created AFTER the prediction timestamp
    pred_ts=$(echo "$decomp_pred" | jq -r '.ts' 2>/dev/null) || pred_ts=0
    replanned=$(bd children "$CLAVAIN_BEAD_ID" --json 2>/dev/null | jq --argjson ts "$pred_ts" '[.[] | select((.created_at // 0) > ($ts * 1000))] | length' 2>/dev/null) || replanned=0

    decomp_actual=$(jq -n \
        --arg bead "$CLAVAIN_BEAD_ID" \
        --arg session "${CLAUDE_SESSION_ID:-unknown}" \
        --argjson predicted "$predicted_children" \
        --argjson actual "$actual_children" \
        --argjson closed "$closed_children" \
        --argjson deferred "$deferred_children" \
        --argjson replanned "$replanned" \
        --arg ts "$(date +%s)" \
        '{bead:$bead, session:$session, predicted_children:$predicted, actual_children:$actual, closed:$closed, deferred:$deferred, replanned:$replanned, completion_rate:(if $actual>0 then ($closed/$actual) else 0 end), prediction_accuracy:(if $predicted>0 then (1-((($actual-$predicted)|fabs)/$predicted)) else 0 end), ts:($ts|tonumber)}')
    bd set-state "$CLAVAIN_BEAD_ID" "decomp_actual=$decomp_actual" 2>/dev/null || true

    # Record to interspect evidence for cross-sprint aggregation
    if type -t _interspect_insert_evidence &>/dev/null; then
        _interspect_insert_evidence \
            "${CLAUDE_SESSION_ID:-unknown}" "sprint" "decomposition_outcome" \
            "" "$decomp_actual" "decomp-quality" \
            2>/dev/null || true
    fi
fi
```

Calibration (stage 3) auto-triggers when interspect has >= 30 `decomposition_outcome` events. Until then, defaults apply.

### 9b: Reflect

**Parallel Window 2 (optional):** If resolve has no blocking findings (all findings are P2+), resolve and reflect can run in parallel. Resolve writes `resolution` artifact; reflect writes `reflection` artifact — no type conflicts. Sprint waits for both artifacts before advancing to Step 10.

`clavain-cli sprint-advance "$CLAVAIN_BEAD_ID" "shipping"`

Note: This advances `shipping → reflect` in the kernel. Step 7's `sprint-advance "shipping"` advanced `executing → shipping`. Both pass `"shipping"` as `currentPhase` which causes `recordPhaseTokens` to double-record under the "shipping" key — this is a known calibration quirk (Sylveste-84sv partial fix; full fix requires `recordPhaseTokens` to deduplicate).

`/reflect`

`/reflect` owns artifact registration AND the `reflect → done` advance — do NOT call sprint-advance after it returns. Gate is firm: Step 10 requires a reflect artifact with >= 3 substantive lines.

## Step 10: Ship

**Reflect gate (firm):**
```bash
reflect_artifact=$(clavain-cli get-artifact "$CLAVAIN_BEAD_ID" "reflection" 2>/dev/null) || reflect_artifact=""
if [[ -z "$reflect_artifact" || ! -f "$reflect_artifact" ]]; then
    echo "ERROR: Step 10 requires a reflect artifact. Run /reflect first." >&2
    exit 1
fi
# Check minimum content: >= 3 substantive lines (non-empty, outside frontmatter)
body_lines=$(awk 'BEGIN{fm=0; count=0} /^---$/{fm++; next} fm>=2 && /[^ \t]/{count++} END{print count}' "$reflect_artifact")
if [[ "$body_lines" -lt 3 ]]; then
    echo "ERROR: Reflect artifact has $body_lines substantive lines (minimum: 3). Add more detail to $reflect_artifact." >&2
    exit 1
fi
```

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

When a subsystem fails, consult `commands/degraded-modes.yaml` for the appropriate degradation:

1. Identify which subsystem failed (review-fleet, test-suite, intercore, routing, budget)
2. Apply the degraded mode: set the flag, log to stderr, continue at reduced capability
3. If multiple critical subsystems fail (level: checkpoint-only): save all work, commit clean changes, report diagnostic
4. Record degradation events for sprint summary: `clavain-cli set-artifact "$CLAVAIN_BEAD_ID" "degradation" "<subsystem>:<level>"`

To resume: `/clavain:route` (auto-detects active sprint) or `/clavain:sprint --from-step <step>`.

Start with Step 1 now.
