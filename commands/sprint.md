---
name: sprint
description: Full autonomous engineering workflow — brainstorm, strategize, plan, execute, review, ship
argument-hint: "[feature description]"
---

## Before Starting — Sprint Resume

Before running discovery, check for an active sprint:

1. Source sprint library:
   ```bash
   export SPRINT_LIB_PROJECT_DIR="."; source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-sprint.sh"
   ```

2. Find active sprints:
   ```bash
   active_sprints=$(sprint_find_active 2>/dev/null) || active_sprints="[]"
   sprint_count=$(echo "$active_sprints" | jq 'length' 2>/dev/null) || sprint_count=0
   ```

3. Parse the result:
   - `sprint_count == 0` → no active sprint, fall through to Work Discovery (below)
   - Single sprint (`sprint_count == 1`) → auto-resume:
     a. Read sprint ID, state: `sprint_id=$(echo "$active_sprints" | jq -r '.[0].id')` then `sprint_read_state "$sprint_id"`
     b. Claim session: `sprint_claim "$sprint_id" "$CLAUDE_SESSION_ID"`
        - If claim fails (returns 1): tell user another session has this sprint, offer to force-claim (by calling `sprint_release` then `sprint_claim`) or start fresh
     c. Set `CLAVAIN_BEAD_ID="$sprint_id"` (sprint bead is the epic; takes precedence over discovery-selected beads)
     d. Determine next step: `next=$(sprint_next_step "<phase>")`
     e. Route to the appropriate command based on the step:
        - `brainstorm` → `/clavain:brainstorm`
        - `strategy` → `/clavain:strategy`
        - `write-plan` → `/clavain:write-plan`
        - `flux-drive` → `/interflux:flux-drive <plan_path from sprint_artifacts>`
        - `work` → `/clavain:work <plan_path from sprint_artifacts>`
        - `ship` → `/clavain:quality-gates`
        - `reflect` → `/reflect`
        - `done` → tell user "Sprint is complete"
     f. Display: `Resuming sprint <id> — <title> (phase: <phase>, next: <step>)`
     g. **After routing to a command, stop.** Do NOT continue to Step 1.
   - Multiple sprints (`sprint_count > 1`) → AskUserQuestion to choose which to resume, plus "Start fresh" option. Then claim and route as above.

4. **Checkpoint recovery** (supplements sprint state): After claiming, check for a local checkpoint:
   ```bash
   checkpoint=$(checkpoint_read)
   ```
   If a checkpoint exists for this sprint:
   - Run `checkpoint_validate` — warn (don't block) if git SHA changed
   - Use `checkpoint_completed_steps` to determine which steps are already done
   - Display: `Resuming from checkpoint. Completed: [<steps>]`
   - Route to the first *incomplete* step (overrides `sprint_next_step` when checkpoint has more detail)

5. If starting fresh (no active sprint or user chose "Start fresh"):
   Proceed to existing Work Discovery logic below.

## Work Discovery (Fallback)

If invoked with no arguments (`$ARGUMENTS` is empty or whitespace-only) AND no active sprint was found:

1. Run the work discovery scanner:
   ```bash
   export DISCOVERY_PROJECT_DIR="."; source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-discovery.sh" && discovery_scan_beads
   ```

2. Parse the output:
   - `DISCOVERY_UNAVAILABLE` → skip discovery, proceed to Step 1 (bd not installed)
   - `DISCOVERY_ERROR` → skip discovery, proceed to Step 1 (bd query failed)
   - `[]` → no open beads, proceed to Step 1
   - JSON array → present options (continue to step 3)

3. Present the top results via **AskUserQuestion**:
   - **First option (recommended):** Top-ranked bead. Label format: `"<Action> <bead-id> — <title> (P<priority>)"`. Add `", stale"` if stale is true. Mark as `(Recommended)`.
   - **Options 2-3:** Next highest-ranked beads, same label format.
   - **Second-to-last option:** `"Start fresh brainstorm"` — proceeds to Step 1 below.
   - **Last option:** `"Show full backlog"` — runs `/clavain:sprint-status`.
   - Action verbs: continue → "Continue", execute → "Execute plan for", plan → "Plan", strategize → "Strategize", brainstorm → "Brainstorm", ship → "Ship", closed → "Closed", create_bead → "Link orphan:"
   - **Orphan entries** (action: "create_bead", id: null): Label format: `"Link orphan: <title> (<type>)"`. These are untracked artifacts in docs/ that have no bead. Description: "Create a bead and link it to this artifact."

4. **Pre-flight check** (guards against stale scan results): Before routing, verify the selected bead still exists:
   ```bash
   bd show <selected_bead_id> 2>/dev/null
   ```
   If `bd show` fails (bead was closed/deleted since scan), tell the user "That bead is no longer available" and re-run discovery from step 1.
   **Skip this check for orphan entries** (action: "create_bead") — they have no bead ID yet.

5. **Set bead context** for phase tracking: remember the selected bead ID as `CLAVAIN_BEAD_ID` for this session. All subsequent workflow commands use this to record phase transitions.

6. Based on selection, route to the appropriate command:
   - `continue` or `execute` with a `plan_path` → `/clavain:work <plan_path>`
   - `plan` → `/clavain:write-plan`
   - `strategize` → `/clavain:strategy`
   - `brainstorm` → `/clavain:brainstorm`
   - `ship` → `/clavain:quality-gates` (bead is in shipping phase — run final gates)
   - `closed` → Tell user "This bead is already done" and re-run discovery
   - `create_bead` (orphan artifact) → Create bead and link:
     1. Run `bd create --title="<artifact title>" --type=task --priority=3` and capture the new bead ID from stdout
     2. **Validate** the bead ID matches format `[A-Za-z]+-[a-z0-9]+`. If `bd create` failed or returned invalid output, tell the user "Failed to create bead — try `bd create` manually" and stop.
     3. Insert `**Bead:** <new-id>` on line 2 of the artifact file (after the `# Title` heading). Use the Edit tool: old_string = first line of file, new_string = first line + newline + `**Bead:** <new-id>`
     4. Set `CLAVAIN_BEAD_ID` to the new bead ID
     5. Route based on artifact type: brainstorm → `/clavain:strategy`, prd → `/clavain:write-plan`, plan → `/clavain:work <plan_path>`
   - "Start fresh brainstorm" → proceed to Step 1
   - "Show full backlog" → `/clavain:sprint-status`

7. Log the selection for telemetry:
   ```bash
   export DISCOVERY_PROJECT_DIR="."; source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-discovery.sh" && discovery_log_selection "<bead_id>" "<action>" <true|false>
   ```
   Where `true` = user picked the first (recommended) option, `false` = user picked a different option.

8. **After routing to a command, stop.** Do NOT continue to Step 1 — the routed command handles the workflow from here.

If invoked WITH arguments (`$ARGUMENTS` is not empty):
- **If `$ARGUMENTS` contains `--resume`**: Read checkpoint with `checkpoint_read`. If a checkpoint exists, validate with `checkpoint_validate`, display completed steps, and skip to the first incomplete step. If no checkpoint, fall through to Work Discovery.
- **If `$ARGUMENTS` contains `--from-step <n>`**: Skip directly to step `<n>` regardless of checkpoint state. Step names: brainstorm, strategy, plan, plan-review, execute, test, quality-gates, resolve, reflect, ship.
- **If `$ARGUMENTS` matches a bead ID** (format: `[A-Za-z]+-[a-z0-9]+`):
  ```bash
  # Verify bead exists
  bd show "$ARGUMENTS" 2>/dev/null
  ```
  If valid: set `CLAVAIN_BEAD_ID="$ARGUMENTS"`, read its phase with `phase_get`, call `infer_bead_action` to determine the action, then route per step 6 above. If `bd show` fails: tell user "Bead not found" and proceed to Step 1.
- **Otherwise**: Treat `$ARGUMENTS` as a feature description and proceed directly to Step 1.

---

Run these steps in order. Do not do anything else. Do not stop between steps unless a defined pause trigger occurs (gate block, step failure, or manual pause setting).

### Session Checkpointing

After each step completes successfully, write a checkpoint:
```bash
export SPRINT_LIB_PROJECT_DIR="."; source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-sprint.sh"
checkpoint_write "$CLAVAIN_BEAD_ID" "<phase>" "<step_name>" "<plan_path>"
```

Step names: `brainstorm`, `strategy`, `plan`, `plan-review`, `execute`, `test`, `quality-gates`, `resolve`, `reflect`, `ship`.

When resuming (via Sprint Resume above or `--resume`):
1. Read checkpoint: `checkpoint_read`
2. Validate git SHA: `checkpoint_validate` (warn on mismatch, don't block)
3. Get completed steps: `checkpoint_completed_steps`
4. Display: `Resuming from step <next>. Completed: [<steps>]`
5. Skip completed steps — jump to the first incomplete one
6. Load agent verdicts from `.clavain/verdicts/` if present

When the sprint completes (Step 10 Ship), clear the checkpoint:
```bash
checkpoint_clear
```

### Auto-Advance Protocol

When transitioning between steps, use auto-advance instead of manual routing:

```bash
export SPRINT_LIB_PROJECT_DIR="."; source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-sprint.sh"
# Validate sprint bead before advancing
is_sprint=$(bd state "$CLAVAIN_BEAD_ID" sprint 2>/dev/null) || is_sprint=""
if [[ "$is_sprint" == "true" ]]; then
    pause_reason=$(sprint_advance "$CLAVAIN_BEAD_ID" "<current_phase>" "<artifact_path>")
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

After each step completes successfully, record the phase transition via `sprint_advance()`. If `CLAVAIN_BEAD_ID` is set (from discovery, sprint resume, or sprint creation), run:
```bash
export SPRINT_LIB_PROJECT_DIR="."; source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-sprint.sh"
sprint_set_artifact "$CLAVAIN_BEAD_ID" "<artifact_type>" "<artifact_path>"
sprint_advance "$CLAVAIN_BEAD_ID" "<current_phase>"
```
Phase tracking is silent — never block on errors. If no bead ID is available, skip phase tracking. Pass the artifact path (brainstorm doc, plan file, etc.) when one exists for the step; pass empty string when there is no single artifact (e.g., quality-gates, ship).

## Pre-Step: Complexity Assessment

Before starting, classify the task complexity:

```bash
export SPRINT_LIB_PROJECT_DIR="."; source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-sprint.sh"
score=$(sprint_classify_complexity "$CLAVAIN_BEAD_ID" "$ARGUMENTS")
label=$(sprint_complexity_label "$score")
```

Display to the user: `Complexity: ${score}/5 (${label})`

Cache complexity on the bead (used by `sprint_advance()` for phase skipping):
```bash
bd set-state "$CLAVAIN_BEAD_ID" "complexity=$score" 2>/dev/null || true
```

Score-based routing:
- **1-2 (trivial/simple):** Ask user via AskUserQuestion whether to skip brainstorm + strategy and go directly to Step 3 (write-plan). Options: "Skip to plan (Recommended)", "Full workflow", "Override complexity". If skipping, set `force_full_chain=false` on the bead and jump to Step 3. If full workflow, set `force_full_chain=true`. Phase skipping is also enforced automatically in `sprint_advance()` based on cached complexity.
- **3 (moderate):** Standard workflow, all steps.
- **4-5 (complex/research):** Full workflow with Opus orchestration, full agent roster.

The user can override with `--skip-to <step>` or `--complexity <1-5>`.

## Step 1: Brainstorm
`/clavain:brainstorm $ARGUMENTS`

**Phase:** After brainstorm doc is created, set `phase=brainstorm` with reason `"Brainstorm: <doc_path>"`.

### Create Sprint Bead

If `CLAVAIN_BEAD_ID` is not set after brainstorm (no sprint bead exists yet):

```bash
export SPRINT_LIB_PROJECT_DIR="."; source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-sprint.sh"
SPRINT_ID=$(sprint_create "<feature title>")
if [[ -n "$SPRINT_ID" ]]; then
    sprint_set_artifact "$SPRINT_ID" "brainstorm" "<brainstorm_doc_path>"
    sprint_record_phase_completion "$SPRINT_ID" "brainstorm"
    CLAVAIN_BEAD_ID="$SPRINT_ID"
fi
```

Insert `**Bead:** <SPRINT_ID>` on line 2 of the brainstorm doc (after the `# Title` heading).

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
export SPRINT_LIB_PROJECT_DIR="."; source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-sprint.sh"
remaining=$(sprint_budget_remaining "$CLAVAIN_BEAD_ID")
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
export SPRINT_LIB_PROJECT_DIR="."; source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-sprint.sh"
if ! enforce_gate "$CLAVAIN_BEAD_ID" "executing" "<plan_path>"; then
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
export SPRINT_LIB_PROJECT_DIR="."; source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-sprint.sh"
remaining=$(sprint_budget_remaining "$CLAVAIN_BEAD_ID")
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
export SPRINT_LIB_PROJECT_DIR="."; source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-sprint.sh"
if ! enforce_gate "$CLAVAIN_BEAD_ID" "shipping" ""; then
    echo "Gate blocked: review findings are stale or pre-conditions not met. Re-run /clavain:quality-gates, or set CLAVAIN_SKIP_GATE='reason' to override." >&2
    # Do NOT advance to shipping — stop and tell user
fi
sprint_advance "$CLAVAIN_BEAD_ID" "shipping"
sprint_record_phase_completion "$CLAVAIN_BEAD_ID" "shipping"
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
export SPRINT_LIB_PROJECT_DIR="."; source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-sprint.sh"
sprint_advance "$CLAVAIN_BEAD_ID" "shipping"
```

Run `/reflect` — it captures learnings (complexity-scaled), registers the artifact, and advances `reflect → done`.

**Phase-advance ownership:** `/reflect` owns both artifact registration AND the `reflect → done` advance. Do NOT call `sprint_advance` after `/reflect` returns.

**Soft gate:** Gate hardness is soft for the initial rollout (emit warning but allow advance if no reflect artifact exists). Graduation to hard gate is tracked separately.

## Step 10: Ship

Use the `clavain:landing-a-change` skill to verify, document, and commit the completed work.

**Phase:** After successful ship, set `phase=done` with reason `"Shipped"`. Also close the bead: `bd close "$CLAVAIN_BEAD_ID" 2>/dev/null || true`.

**Sprint summary:** At completion, display:
```
Sprint Summary:
- Bead: <CLAVAIN_BEAD_ID>
- Steps completed: <n>/10
- Budget: <tokens_spent>k / <token_budget>k (<percentage>%)
- Agents dispatched: <count>
- Verdicts: <verdict_count_by_status output>
- Estimated tokens: <verdict_total_tokens output>
```

## Error Recovery

If any step fails:

1. **Do NOT skip the failed step** — each step's output feeds into later steps
2. **Retry once** with a tighter scope (e.g., fewer features, smaller change set)
3. **If retry fails**, stop and report:
   - Which step failed
   - The error or unexpected output
   - What was completed successfully before the failure

To **resume from a specific step**, re-invoke `/clavain:sprint` and manually skip completed steps by running their slash commands directly (e.g., start from Step 6 by running `/clavain:quality-gates`).

Start with Step 1 now.
