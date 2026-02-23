---
name: route
description: Universal entry point — discovers work, resumes sprints, classifies tasks, and dispatches to /sprint or /work
argument-hint: "[bead ID, feature description, or empty for discovery]"
---

# Route — Adaptive Workflow Entry Point

Discovers available work, resumes active sprints, classifies task complexity, and auto-dispatches to the right workflow command. This is the primary entry point — use `/sprint` directly only to force the full lifecycle.

## Step 1: Check Active Sprints (Resume)

Before anything else, check for an active sprint to resume:

```bash
active_sprints=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" sprint-find-active 2>/dev/null) || active_sprints="[]"
sprint_count=$(echo "$active_sprints" | jq 'length' 2>/dev/null) || sprint_count=0
```

- **`sprint_count == 0`** → no active sprint, continue to Step 2.
- **Single sprint (`sprint_count == 1`)** → auto-resume:
  a. Read sprint ID, state: `sprint_id=$(echo "$active_sprints" | jq -r '.[0].id')` then `"${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" sprint-read-state "$sprint_id"`
  b. Claim session: `"${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" sprint-claim "$sprint_id" "$CLAUDE_SESSION_ID"`
     - If claim fails (returns 1): tell user another session has this sprint, offer to force-claim (call `clavain-cli sprint-release` then `clavain-cli sprint-claim`) or start fresh
  c. Set `CLAVAIN_BEAD_ID="$sprint_id"`
  d. Check for checkpoint:
     ```bash
     checkpoint=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" checkpoint-read)
     ```
     If checkpoint exists for this sprint:
     - Run `"${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" checkpoint-validate` — warn (don't block) if git SHA changed
     - Use `checkpoint_completed_steps` to determine which steps are done
     - Display: `Resuming from checkpoint. Completed: [<steps>]`
     - Route to the first *incomplete* step
  e. Determine next step: `next=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" sprint-next-step "<phase>")`
  f. Route to the appropriate command:
     - `brainstorm` → `/clavain:sprint`
     - `strategy` → `/clavain:sprint --from-step strategy`
     - `write-plan` → `/clavain:sprint --from-step plan`
     - `flux-drive` → `/interflux:flux-drive <plan_path from sprint_artifacts>`
     - `work` → `/clavain:work <plan_path from sprint_artifacts>`
     - `ship` → `/clavain:quality-gates`
     - `reflect` → `/clavain:reflect`
     - `done` → tell user "Sprint is complete"
  g. Display: `Resuming sprint <id> — <title> (phase: <phase>, next: <step>)`
  h. **Stop after dispatch.** Do NOT continue to Step 2.
- **Multiple sprints (`sprint_count > 1`)** → AskUserQuestion to choose which to resume, plus "Start fresh" option. Then claim and route as above.

**Confidence: 1.0** — active sprint resume is always definitive.

## Step 2: Parse Arguments

**If `$ARGUMENTS` contains `--lane=<name>`:** Extract the lane name and set `DISCOVERY_LANE=<name>`. Display: `Lane: <name> — filtering to lane-scoped beads`. Continue parsing remaining arguments.

**If `$ARGUMENTS` is empty or whitespace-only:**
- Set `route_mode="discovery"` — continue to **Step 3: Discovery Scan**.

**If `$ARGUMENTS` matches a bead ID** (format: `[A-Za-z]+-[a-z0-9]+`):
- Verify bead exists:
  ```bash
  bd show "$ARGUMENTS" 2>/dev/null
  ```
  If `bd show` fails: tell user "Bead not found" and fall through to discovery (Step 3).
- Set `route_mode="bead"`, `bead_id="$ARGUMENTS"`, `CLAVAIN_BEAD_ID="$ARGUMENTS"`
- Gather bead metadata and artifacts:
  ```bash
  has_plan=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" get-artifact "$bead_id" "plan" 2>/dev/null) || has_plan=""
  has_brainstorm=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" get-artifact "$bead_id" "brainstorm" 2>/dev/null) || has_brainstorm=""
  has_prd=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" get-artifact "$bead_id" "prd" 2>/dev/null) || has_prd=""
  bead_phase=$(bd state "$bead_id" phase 2>/dev/null) || bead_phase=""
  bead_action=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" infer-action "$bead_id" 2>/dev/null) || bead_action=""
  complexity=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" classify-complexity "$bead_id" "" 2>/dev/null) || complexity="3"
  complexity_label=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" complexity-label "$complexity" 2>/dev/null) || complexity_label="moderate"
  child_count=$(bd children "$bead_id" 2>/dev/null | jq 'length' 2>/dev/null) || child_count="0"
  ```
- Cache complexity on bead: `bd set-state "$bead_id" "complexity=$complexity" 2>/dev/null || true`
- Display: `Complexity: ${complexity}/5 (${complexity_label})`
- Skip to **Step 4: Classify and Dispatch**.

**Otherwise** (free text):
- Set `route_mode="text"`, `description="$ARGUMENTS"`
- Classify complexity:
  ```bash
  complexity=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" classify-complexity "" "$ARGUMENTS" 2>/dev/null) || complexity="3"
  complexity_label=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" complexity-label "$complexity" 2>/dev/null) || complexity_label="moderate"
  ```
- Display: `Complexity: ${complexity}/5 (${complexity_label})`
- Skip to **Step 4: Classify and Dispatch**.

## Step 3: Discovery Scan

Only reached when `route_mode="discovery"` (no arguments, no active sprint).

1. Run the work discovery scanner:
   ```bash
   export DISCOVERY_PROJECT_DIR="."; export DISCOVERY_LANE="${DISCOVERY_LANE:-}"; source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-discovery.sh" && discovery_scan_beads
   ```

2. Parse the output:
   - `DISCOVERY_UNAVAILABLE` → skip discovery, dispatch to `/clavain:sprint` (bd not installed)
   - `DISCOVERY_ERROR` → skip discovery, dispatch to `/clavain:sprint`
   - `[]` → no open beads, dispatch to `/clavain:sprint`
   - JSON array → present options (continue to step 3)

3. Present the top results via **AskUserQuestion**:
   - **First option (recommended):** Top-ranked bead. Label format: `"<Action> <bead-id> — <title> (P<priority>)"`. Add `", stale"` if stale is true. Mark as `(Recommended)`.
   - **Options 2-3:** Next highest-ranked beads, same label format.
   - **Second-to-last option:** `"Start fresh brainstorm"` — dispatches to `/clavain:sprint`.
   - **Last option:** `"Show full backlog"` — runs `/clavain:sprint-status`.
   - Action verbs: continue → "Continue", execute → "Execute plan for", plan → "Plan", strategize → "Strategize", brainstorm → "Brainstorm", ship → "Ship", closed → "Closed", create_bead → "Link orphan:", verify_done → "Verify (parent closed):"
   - **Stale-parent entries** (action: "verify_done"): Label format: `"Verify (parent closed): <bead-id> — <title> (P<priority>, parent: <parent_closed_epic>)"`
   - **Orphan entries** (action: "create_bead", id: null): Label format: `"Link orphan: <title> (<type>)"`

4. **Pre-flight check:** Before routing, verify the selected bead still exists:
   ```bash
   bd show <selected_bead_id> 2>/dev/null
   ```
   If `bd show` fails: "That bead is no longer available" → re-run discovery from step 1.
   **Skip this check for orphan entries** (action: "create_bead") — they have no bead ID yet.

5. **Set bead context:** Remember the selected bead ID as `CLAVAIN_BEAD_ID` for this session.

6. **Route based on selection:**
   - `continue` or `execute` with `plan_path` → `/clavain:work <plan_path>`
   - `plan` → `/clavain:write-plan`
   - `strategize` → `/clavain:strategy`
   - `brainstorm` → `/clavain:sprint`
   - `ship` → `/clavain:quality-gates`
   - `closed` → Tell user "This bead is already done" and re-run discovery
   - `verify_done` → Parent epic is closed. AskUserQuestion with options:
     1. "Close this bead (work is done)" → `bd close <id> --reason="Completed as part of parent <parent_closed_epic>"`
     2. "Review code before closing" → Read bead description and source files, then re-ask
     3. "Cascade-close all siblings" → Run `bd-cascade-close <parent_closed_epic>`
   - `create_bead` (orphan artifact) → Create bead and link:
     1. `bd create --title="<artifact title>" --type=task --priority=3`
     2. Validate bead ID format `[A-Za-z]+-[a-z0-9]+`. If failed: tell user and stop.
     3. Insert `**Bead:** <new-id>` on line 2 of the artifact file
     4. Set `CLAVAIN_BEAD_ID` to new bead ID
     5. Route based on artifact type: brainstorm → `/clavain:strategy`, prd → `/clavain:write-plan`, plan → `/clavain:work <plan_path>`
   - "Start fresh brainstorm" → `/clavain:sprint`
   - "Show full backlog" → `/clavain:sprint-status`

7. Log the selection for telemetry:
   ```bash
   export DISCOVERY_PROJECT_DIR="."; source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-discovery.sh" && discovery_log_selection "<bead_id>" "<action>" <true|false>
   ```

8. **Stop after dispatch.** Do NOT continue — the routed command handles the workflow from here.

## Step 4: Classify and Dispatch

Reached when `route_mode` is `"bead"` or `"text"`.

### 4a: Fast-Path Heuristics

Check in order — first match wins:

| Condition | Route | Confidence | Reason |
|-----------|-------|------------|--------|
| Bead has plan artifact (`has_plan` non-empty) | `/clavain:work <plan_path>` | 1.0 | Plan already exists |
| `bead_phase` is `planned` or `plan-reviewed` | `/clavain:work <plan_path>` | 1.0 | Ready for execution |
| `bead_action` is `execute` or `continue` | `/clavain:work <plan_path>` | 1.0 | Bead state indicates execution |
| Complexity = 1 (trivial) | `/clavain:work` | 0.9 | Too simple for full sprint |
| No description AND no brainstorm artifact | `/clavain:sprint` | 0.9 | Needs brainstorm first |
| Complexity = 5 (research) | `/clavain:sprint` | 0.85 | Needs full exploration |
| `child_count > 0` (epic with children) | `/clavain:sprint` | 0.85 | Epic needs orchestration |

If confidence >= 0.8: display verdict and skip to **4c: Dispatch**.

If no heuristic matched (confidence < 0.8): continue to **4b**.

### 4b: LLM Classification (haiku fallback)

Dispatch a haiku subagent:

```
Task(subagent_type="haiku", model="haiku", prompt=<classification prompt>)
```

Classification prompt:

```
You are a task router for a software development workflow.

Given this task:
- Description: {description from bead or free text}
- Has plan: {yes/no}
- Has brainstorm: {yes/no}
- Has PRD: {yes/no}
- Complexity score: {complexity}/5 ({complexity_label})
- Priority: {priority or "unset"}
- Type: {type or "unset"}
- Bead phase: {bead_phase or "none"}
- Child bead count: {child_count}

Route to ONE of:
- /sprint — Full lifecycle (brainstorm → strategy → plan → execute → review → ship). Use when: new feature with no plan, ambiguous scope, research needed, security-sensitive, cross-cutting changes, epic with children, high complexity (4-5).
- /work — Fast execution (plan → execute → ship). Use when: plan already exists, scope is clear, known pattern, simple/moderate complexity (1-3), single-module change, bug fix with clear repro.

Return ONLY valid JSON on a single line: {"command": "/sprint" or "/work", "confidence": 0.0-1.0, "reason": "one sentence"}
```

Parse the JSON response. If parsing fails, default to `/sprint` (safer fallback — sprint can always skip phases, but work can't add them).

### 4c: Dispatch

1. **Create sprint bead if needed:** If dispatching to `/clavain:sprint` and `CLAVAIN_BEAD_ID` is not set:
   ```bash
   SPRINT_ID=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" sprint-create "<feature title or description>")
   if [[ -n "$SPRINT_ID" ]]; then
       CLAVAIN_BEAD_ID="$SPRINT_ID"
       bd set-state "$SPRINT_ID" "complexity=$complexity" 2>/dev/null || true
   fi
   ```

2. **Cache complexity on bead** (if not already cached in Step 2):
   ```bash
   bd set-state "$CLAVAIN_BEAD_ID" "complexity=$complexity" 2>/dev/null || true
   ```

3. **Display the verdict:**
   ```
   Route: /work (0.92) — Plan exists and scope is clear
   ```
   or for heuristic routes:
   ```
   Route: /sprint (heuristic, 0.9) — Needs brainstorm first
   ```

4. **Auto-dispatch** — invoke the chosen command via the Skill tool:
   - If routing to `/clavain:sprint`: pass `$ARGUMENTS` (bead ID or feature text)
   - If routing to `/clavain:work`: pass the plan path if available, otherwise pass `$ARGUMENTS`
   - **Do not ask for confirmation** — the whole point is auto-routing

5. **Stop after dispatch.** The invoked command handles everything from here.
