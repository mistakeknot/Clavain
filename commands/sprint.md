---
name: sprint
description: Full autonomous engineering workflow — brainstorm, strategize, plan, execute, review, ship
argument-hint: "[feature description]"
---

## Before Starting — Work Discovery

If invoked with no arguments (`$ARGUMENTS` is empty or whitespace-only):

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
- **If `$ARGUMENTS` matches a bead ID** (format: `[A-Za-z]+-[a-z0-9]+`):
  ```bash
  # Verify bead exists
  bd show "$ARGUMENTS" 2>/dev/null
  ```
  If valid: set `CLAVAIN_BEAD_ID="$ARGUMENTS"`, read its phase with `phase_get`, call `infer_bead_action` to determine the action, then route per step 6 above. If `bd show` fails: tell user "Bead not found" and proceed to Step 1.
- **Otherwise**: Treat `$ARGUMENTS` as a feature description and proceed directly to Step 1.

---

Run these steps in order. Do not do anything else.

### Phase Tracking

After each step completes successfully, record the phase transition. If `CLAVAIN_BEAD_ID` is set (from discovery or the user), run:
```bash
export GATES_PROJECT_DIR="."; source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-gates.sh" && advance_phase "$CLAVAIN_BEAD_ID" "<phase>" "<reason>" "<artifact_path>"
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

**Note:** When clodex mode is active, `/write-plan` auto-selects Codex Delegation and executes the plan via Codex agents. In this case, skip Step 5 (execute) — the plan has already been executed.

**Phase:** After plan is written, set `phase=planned` with reason `"Plan: <plan_path>"`.

## Step 4: Review Plan (gates execution)
`/interflux:flux-drive <plan-file-from-step-3>`

Pass the plan file path from Step 3 as the flux-drive target. Review happens **before** execution so plan-level risks are caught early.

If flux-drive finds P0/P1 issues, stop and address them before proceeding to execution.

**Phase:** After plan review passes, set `phase=plan-reviewed` with reason `"Plan reviewed: <plan_path>"`.

## Step 5: Execute

**Gate check:** Before executing, enforce the gate:
```bash
export GATES_PROJECT_DIR="."; source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-gates.sh"
if ! enforce_gate "$CLAVAIN_BEAD_ID" "executing" "<plan_path>"; then
    echo "Gate blocked: plan must be reviewed first. Run /interflux:flux-drive on the plan, or set CLAVAIN_SKIP_GATE='reason' to override." >&2
    # Stop — do NOT proceed to execution
fi
```

Run `/clavain:work <plan-file-from-step-3>`

**Phase:** At the START of execution (before work begins), set `phase=executing` with reason `"Executing: <plan_path>"`.

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

**Gate check + Phase:** After quality gates PASS, enforce the shipping gate before recording:
```bash
export GATES_PROJECT_DIR="."; source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-gates.sh"
if ! enforce_gate "$CLAVAIN_BEAD_ID" "shipping" ""; then
    echo "Gate blocked: review findings are stale or pre-conditions not met. Re-run /clavain:quality-gates, or set CLAVAIN_SKIP_GATE='reason' to override." >&2
    # Do NOT advance to shipping — stop and tell user
fi
advance_phase "$CLAVAIN_BEAD_ID" "shipping" "Quality gates passed" ""
```
Do NOT set the phase if gates FAIL.

## Step 8: Resolve Issues

Run `/clavain:resolve` — it auto-detects the source (todo files, PR comments, or code TODOs) and handles clodex mode automatically.

**After resolving:** If quality-gates found patterns that could recur in other code (e.g., format injection, portability issues, race conditions), compound them:
- Run `/clavain:compound` to document the pattern in `config/flux-drive/knowledge/`
- If findings revealed a plan-level mistake, annotate the plan file with a `## Lessons Learned` section so future similar plans benefit

## Step 9: Ship

Use the `clavain:landing-a-change` skill to verify, document, and commit the completed work.

**Phase:** After successful ship, set `phase=done` with reason `"Shipped"`. Also close the bead: `bd close "$CLAVAIN_BEAD_ID" 2>/dev/null || true`.

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
