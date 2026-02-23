---
name: sprint
description: Phase sequencer — brainstorm, strategize, plan, execute, review, ship. Use /route for smart dispatch.
argument-hint: "[feature description or --from-step <step>]"
---

# Sprint — Phase Sequencer

Runs the full 10-phase development lifecycle from brainstorm to ship. Normally invoked via `/route` which handles discovery, resume, and classification. Can be invoked directly to force the full lifecycle.

**Expects:** `CLAVAIN_BEAD_ID` set by caller (`/route` or manual). If not set, sprint runs without bead tracking.

## Arguments

- **`--from-step <n>`**: Skip directly to step `<n>`. Step names: brainstorm, strategy, plan, plan-review, execute, test, quality-gates, resolve, reflect, ship.
- **Otherwise**: `$ARGUMENTS` is treated as a feature description for Step 1 (Brainstorm).

## Complexity (Read from Bead)

Read cached complexity (set by `/route`):

```bash
complexity=$(bd state "$CLAVAIN_BEAD_ID" complexity 2>/dev/null) || complexity="3"
label=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" complexity-label "$complexity" 2>/dev/null) || label="moderate"
```

Display to the user: `Complexity: ${complexity}/5 (${label})`

Score-based routing:
- **1-2 (trivial/simple):** Ask user via AskUserQuestion whether to skip brainstorm + strategy and go directly to Step 3 (write-plan). Options: "Skip to plan (Recommended)", "Full workflow". If skipping, jump to Step 3.
- **3 (moderate):** Standard workflow, all steps.
- **4-5 (complex/research):** Full workflow with Opus orchestration, full agent roster.

---

Run these steps in order. Do not do anything else. Do not stop between steps unless a defined pause trigger occurs (gate block, step failure, or manual pause setting).

### Session Checkpointing

After each step completes successfully, write a checkpoint:
```bash
"${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" checkpoint-write "$CLAVAIN_BEAD_ID" "<phase>" "<step_name>" "<plan_path>"
```

Step names: `brainstorm`, `strategy`, `plan`, `plan-review`, `execute`, `test`, `quality-gates`, `resolve`, `reflect`, `ship`.

When resuming (via `/route` sprint resume):
1. Read checkpoint: `checkpoint_read`
2. Validate git SHA: `checkpoint_validate` (warn on mismatch, don't block)
3. Get completed steps: `checkpoint_completed_steps`
4. Display: `Resuming from step <next>. Completed: [<steps>]`
5. Skip completed steps — jump to the first incomplete one
6. Load agent verdicts from `.clavain/verdicts/` if present

When the sprint completes (Step 10 Ship), clear the checkpoint:
```bash
"${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" checkpoint-clear
```

### Auto-Advance Protocol

When transitioning between steps, use auto-advance instead of manual routing:

```bash
# Validate sprint bead before advancing
is_sprint=$(bd state "$CLAVAIN_BEAD_ID" sprint 2>/dev/null) || is_sprint=""
if [[ "$is_sprint" == "true" ]]; then
    pause_reason=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" sprint-advance "$CLAVAIN_BEAD_ID" "<current_phase>" "<artifact_path>")
    if [[ $? -ne 0 ]]; then
        # Parse structured pause reason: type|phase|detail
        reason_type="${pause_reason%%|*}"
        case "$reason_type" in
            gate_blocked)
                # AskUserQuestion: "Gate blocked. Options: Fix issues, Skip gate, Stop sprint"
                ;;
            manual_pause)
                # AskUserQuestion: "Sprint paused (auto_advance=false). Options: Continue, Stop"
                ;;
            stale_phase)
                # Another session already advanced — re-read state and continue from new phase
                ;;
            budget_exceeded)
                # AskUserQuestion: "Budget exceeded (<detail>). Options: Continue (override), Stop sprint, Adjust budget"
                ;;
        esac
    fi
fi
```

**Status messages:** At each auto-advance, display: `Phase: <current> → <next> (auto-advancing)`

**No "what next?" prompts between steps.** Sprint proceeds automatically unless:
1. `sprint_should_pause()` returns a pause trigger
2. A step fails (test failure, gate block)
3. User set `auto_advance=false` on the sprint bead

### Phase Tracking

After each step completes successfully, record the phase transition via `sprint_advance()`. If `CLAVAIN_BEAD_ID` is set (from `/route` or manual), run:
```bash
"${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" set-artifact "$CLAVAIN_BEAD_ID" "<artifact_type>" "<artifact_path>"
"${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" sprint-advance "$CLAVAIN_BEAD_ID" "<current_phase>"
```
Phase tracking is silent — never block on errors. If no bead ID is available, skip phase tracking. Pass the artifact path (brainstorm doc, plan file, etc.) when one exists for the step; pass empty string when there is no single artifact (e.g., quality-gates, ship).

## Step 1: Brainstorm
`/clavain:brainstorm $ARGUMENTS`

**Phase:** After brainstorm doc is created, set `phase=brainstorm` with reason `"Brainstorm: <doc_path>"`.

## Step 2: Strategize
`/clavain:strategy`

Structures the brainstorm into a PRD, creates beads for tracking, and validates with flux-drive before planning.

**Optional:** Run `/clavain:review-doc` on the brainstorm output first for a quick polish before structuring. If you do, set `phase=brainstorm-reviewed` after review-doc completes.

**Phase:** After strategy completes, set `phase=strategized` with reason `"PRD: <prd_path>"`.

## Step 3: Write Plan
`/clavain:write-plan`

Remember the plan file path (saved to `docs/plans/YYYY-MM-DD-<name>.md`) — it's needed in Step 4.

**Note:** When interserve mode is active, `/write-plan` auto-selects Codex Delegation and executes the plan via Codex agents. In this case, skip Step 5 (execute) — the plan has already been executed.

**Phase:** After plan is written, set `phase=planned` with reason `"Plan: <plan_path>"`.

## Step 4: Review Plan (gates execution)

**Budget context:** Before invoking flux-drive, compute remaining budget:
```bash
remaining=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" sprint-budget-remaining "$CLAVAIN_BEAD_ID")
if [[ "$remaining" -gt 0 ]]; then
    export FLUX_BUDGET_REMAINING="$remaining"
fi
```

`/interflux:flux-drive <plan-file-from-step-3>`

Pass the plan file path from Step 3 as the flux-drive target. Review happens **before** execution so plan-level risks are caught early.

If flux-drive finds P0/P1 issues, stop and address them before proceeding to execution.

**Phase:** After plan review passes, set `phase=plan-reviewed` with reason `"Plan reviewed: <plan_path>"`.

## Step 5: Execute

**Gate check:** Before executing, enforce the gate:
```bash
if ! "${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" enforce-gate "$CLAVAIN_BEAD_ID" "executing" "<plan_path>"; then
    echo "Gate blocked: plan must be reviewed first. Run /interflux:flux-drive on the plan, or set CLAVAIN_SKIP_GATE='reason' to override." >&2
    # Stop — do NOT proceed to execution
fi
```

Run `/clavain:work <plan-file-from-step-3>`

**Phase:** At the START of execution (before work begins), set `phase=executing` with reason `"Executing: <plan_path>"`.

**Parallel execution:** When the plan has independent modules, dispatch them in parallel using the `dispatching-parallel-agents` skill. This is automatic when interserve mode is active (executing-plans detects the flag and dispatches Codex agents).

## Step 6: Test & Verify

Run the project's test suite and linting before proceeding to review:

```bash
# Run project's test command (go test ./... | npm test | pytest | cargo test)
# Run project's linter if configured
```

**If tests fail:** Stop. Fix failures before proceeding. Do NOT continue to quality gates with a broken build.

**If no test command exists:** Note this and proceed — quality-gates will still run reviewer agents.

## Step 7: Quality Gates

**Budget context:** Before invoking quality-gates, compute remaining budget:
```bash
remaining=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" sprint-budget-remaining "$CLAVAIN_BEAD_ID")
if [[ "$remaining" -gt 0 ]]; then
    export FLUX_BUDGET_REMAINING="$remaining"
fi
```

`/clavain:quality-gates`

**Parallel opportunity:** Quality gates and resolve can overlap — quality-gates spawns review agents while resolve addresses already-known findings. If you have known TODOs from execution, start `/clavain:resolve` in parallel with quality-gates.

**Verdict consumption:** After quality-gates completes, read structured verdicts instead of raw agent output:
```bash
source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-verdict.sh"
verdict_parse_all    # Summary table: STATUS  AGENT  SUMMARY
verdict_count_by_status  # e.g., "3 CLEAN, 1 NEEDS_ATTENTION"
```
- If all CLEAN: proceed (one-line summary in context)
- If any NEEDS_ATTENTION: read only those agents' detail files via `verdict_get_attention`
- Report per-agent STATUS in sprint summary

**Gate check + Phase:** After quality gates PASS, enforce the shipping gate before recording:
```bash
if ! "${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" enforce-gate "$CLAVAIN_BEAD_ID" "shipping" ""; then
    echo "Gate blocked: review findings are stale or pre-conditions not met. Re-run /clavain:quality-gates, or set CLAVAIN_SKIP_GATE='reason' to override." >&2
    # Do NOT advance to shipping — stop and tell user
fi
"${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" sprint-advance "$CLAVAIN_BEAD_ID" "shipping"
"${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" record-phase "$CLAVAIN_BEAD_ID" "shipping"
```
Do NOT set the phase if gates FAIL.

## Step 8: Resolve Issues

Run `/clavain:resolve` — it auto-detects the source (todo files, PR comments, or code TODOs) and handles interserve mode automatically.

**After resolving:** If quality-gates found patterns that could recur in other code (e.g., format injection, portability issues, race conditions), compound them:
- Run `/clavain:compound` to document the pattern in `config/flux-drive/knowledge/`
- If findings revealed a plan-level mistake, annotate the plan file with a `## Lessons Learned` section so future similar plans benefit

## Step 9: Reflect

Advance the sprint from `shipping` to `reflect`, then invoke `/reflect`:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" sprint-advance "$CLAVAIN_BEAD_ID" "shipping"
```

Run `/reflect` — it captures learnings (complexity-scaled), registers the artifact, and advances `reflect → done`.

**Phase-advance ownership:** `/reflect` owns both artifact registration AND the `reflect → done` advance. Do NOT call `sprint_advance` after `/reflect` returns.

**Soft gate:** Gate hardness is soft for the initial rollout (emit warning but allow advance if no reflect artifact exists). Graduation to hard gate is tracked separately.

## Step 10: Ship

Use the `clavain:landing-a-change` skill to verify, document, and commit the completed work.

**Phase:** After successful ship, set `phase=done` with reason `"Shipped"`. Also close the bead: `bd close "$CLAVAIN_BEAD_ID" 2>/dev/null || true`.

**Close sweep:** After closing the sprint bead, auto-close any open beads that were blocked by it:

```bash
swept=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" close-children "$CLAVAIN_BEAD_ID" "Shipped with parent epic $CLAVAIN_BEAD_ID")
if [[ "$swept" -gt 0 ]]; then
    echo "Auto-closed $swept child beads"
fi
```

**Sprint summary:** At completion, display:
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

## Error Recovery

If any step fails:

1. **Do NOT skip the failed step** — each step's output feeds into later steps
2. **Retry once** with a tighter scope (e.g., fewer features, smaller change set)
3. **If retry fails**, stop and report:
   - Which step failed
   - The error or unexpected output
   - What was completed successfully before the failure

To **resume from a specific step**, re-invoke `/clavain:route` which will detect the active sprint and resume from the right phase. Or use `/clavain:sprint --from-step <step>` to skip directly.

Start with Step 1 now.
