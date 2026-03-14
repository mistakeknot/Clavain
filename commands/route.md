---
name: route
description: Universal entry point — discovers work, resumes sprints, classifies tasks, and dispatches to /sprint or /work
argument-hint: "[bead ID, feature description, or empty for discovery]"
---

# Route — Adaptive Workflow Entry Point

Discovers available work, resumes active sprints, classifies task complexity, and auto-dispatches to the right workflow command. This is the primary entry point — use `/sprint` directly only to force the full lifecycle.

> **New project?** If this project doesn't have beads, CLAUDE.md, or docs/ structure yet, run `/clavain:project-onboard` first to set everything up.

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
  c2. **Register bead for token attribution:**
     ```bash
     _is_sid=$(cat /tmp/interstat-session-id 2>/dev/null || echo "")
     [[ -n "$_is_sid" ]] && echo "$CLAVAIN_BEAD_ID" > "/tmp/interstat-bead-${_is_sid}" 2>/dev/null || true
     ic session attribute --session="${_is_sid}" --bead="$CLAVAIN_BEAD_ID" 2>/dev/null || true
     ```
  d. Check for checkpoint:
     ```bash
     checkpoint=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" checkpoint-read)
     ```
     If checkpoint exists for this sprint:
     - Run `"${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" checkpoint-validate`
     - If git SHA changed (WARNING in stderr): display `"Code changed since checkpoint (was <old>, now <new>). Completed steps may not reflect current state."` and use AskUserQuestion: "Resume from checkpoint (trust completed steps)" / "Re-run from start (discard checkpoint)" / "Re-run from plan-review (re-validate with current code)". Default: resume.
     - If no SHA change: use `checkpoint_completed_steps` silently
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
- **Multiple sprints (`sprint_count > 1`)** → Sort by most recently advanced (latest phase transition timestamp), then present via AskUserQuestion. Label format: `"Resume <id> — <title> (phase: <phase>, last active: <relative_time>)"`. Include "Start fresh" as final option. Recommended = most recently active sprint. Then claim and route as above.

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
- **Staleness check (haiku):** Before dispatching, verify the bead isn't already implemented. Run a background haiku agent:
  ```
  Agent(model="haiku", description="Check bead staleness", run_in_background=false, prompt="
  You are checking whether bead $bead_id is already implemented.

  Bead title: <title from bd show>
  Bead description: <description from bd show>

  Check the codebase for evidence this feature already exists:
  1. Search for CLI subcommands, command files, or functions matching the described feature
  2. Check if the described capability is already working (test with a quick command if applicable)
  3. Look for the feature in existing code structure

  Return ONLY valid JSON: {\"implemented\": true/false, \"evidence\": \"one sentence\"}
  If uncertain, return {\"implemented\": false, \"evidence\": \"no clear signal\"}
  ")
  ```
  If `implemented: true`: Display `⚠ This bead may already be done: <evidence>`. Use AskUserQuestion: "This feature appears to already exist. Options: Close bead (already done) / Proceed anyway / Investigate further". If user chooses to close: `bd close "$bead_id" --reason="Bead sweep: <evidence>"` and re-run discovery (Step 3).
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
   - JSON array → continue to staleness sweep (step 2b) then present options (step 3)

2b. **Background staleness sweep (haiku):** For the top 3 discovery candidates that DON'T already have a `possibly_done` flag from the deterministic check, check `ic state get "bead_sweep" "<bead_id>"` for cached results (1-hour TTL). For any cache misses, spawn a **single** background haiku agent to batch-check them:
   ```
   Agent(model="haiku", description="Batch bead staleness check", run_in_background=true, prompt="
   You are checking whether these beads are already implemented in the codebase.
   For each bead, search for evidence the feature exists (CLI commands, functions, config, tests).

   Beads to check:
   1. <id1>: <title1> — <description1>
   2. <id2>: <title2> — <description2>
   3. <id3>: <title3> — <description3>

   For each bead, run targeted searches (Grep for function names, Glob for command files, Bash for CLI --help).
   Return ONLY valid JSON array: [{\"id\": \"<id>\", \"implemented\": true/false, \"evidence\": \"one sentence\"}]
   ")
   ```
   Cache results: `echo '<json>' | ic state set "bead_sweep" "<bead_id>" --ttl=3600s` for each result.
   **Wait briefly (up to 5 seconds) for the background agent.** If it completes in time, merge its results into the discovery output as `possibly_done` flags before presenting options. If it hasn't finished after 5 seconds, continue to step 3 — results will be cached for next session. This prevents presenting already-done beads as actionable options in most cases.

3. Present the top results via **AskUserQuestion**:
   - **First option (recommended):** Top-ranked bead. Label format: `"<Action> <bead-id> — <title> (P<priority>)"`. Add `", stale"` if stale is true. Mark as `(Recommended)`.
   - **Options 2-3:** Next highest-ranked beads, same label format.
   - **Second-to-last option:** `"Start fresh brainstorm"` — dispatches to `/clavain:sprint`.
   - **Last option:** `"Show full backlog"` — runs `/clavain:sprint-status`.
   - Action verbs: continue → "Continue", execute → "Execute plan for", plan → "Plan", strategize → "Strategize", brainstorm → "Brainstorm", ship → "Ship", closed → "Closed", create_bead → "Link orphan:", verify_done → "Verify (parent closed):", review_discovery → "Review discovery:"
   - **Stale-parent entries** (action: "verify_done"): Label format: `"Verify (parent closed): <bead-id> — <title> (P<priority>, parent: <parent_closed_epic>)"`
   - **Orphan entries** (action: "create_bead", id: null): Label format: `"Link orphan: <title> (<type>)"`
   - **Interject discovery entries** (action: "review_discovery"): Label format: `"Review discovery: <bead-id> — <clean_title> (<discovery_source>, score <discovery_score>)"`. Strip `[interject] ` prefix from title. If `discovery_source` or `discovery_score` are null, omit the parenthetical.
   - **Possibly-done beads**: If any result has a `possibly_done` field (non-null string), display a notice after the options list: `"⚠ Sweep detected N bead(s) that may already be done — run /bead-sweep to verify: <id1> (<reason1>), <id2> (<reason2>)"`. Do NOT include these as selectable options — they're informational. The user can run `/bead-sweep` to verify and close them.

4. **Pre-flight check:** Before routing, verify the selected bead still exists:
   ```bash
   bd show <selected_bead_id> 2>/dev/null
   ```
   If `bd show` fails: "That bead is no longer available" → re-run discovery from step 1.
   **Skip this check for orphan entries** (action: "create_bead") — they have no bead ID yet.

5. **Claim bead and track in session:**
   - Remember the selected bead ID as `CLAVAIN_BEAD_ID` for this session.
   - **Claim the bead** (skip for `closed`, `verify_done`, and `create_bead` actions):
     ```bash
     bd update "$CLAVAIN_BEAD_ID" --claim
     ```
     If `--claim` fails (exit code non-zero):
     - "already claimed" in error → tell user "Bead already claimed by another agent" and re-run discovery from Step 1
     - "lock" or "timeout" in error → retry once after 2 seconds; if still fails, tell user "Could not claim bead (database busy)" and re-run discovery from Step 1
     Do NOT fall back to `--status=in_progress` — a failed claim means exclusivity is not guaranteed.
   - **Write claim identity** (after successful `--claim`):
     ```bash
     bd set-state "$CLAVAIN_BEAD_ID" "claimed_by=${CLAUDE_SESSION_ID:-unknown}" 2>/dev/null || true
     bd set-state "$CLAVAIN_BEAD_ID" "claimed_at=$(date +%s)" 2>/dev/null || true
     ```
   - **Register bead for token attribution:**
     ```bash
     _is_sid=$(cat /tmp/interstat-session-id 2>/dev/null || echo "")
     [[ -n "$_is_sid" ]] && echo "$CLAVAIN_BEAD_ID" > "/tmp/interstat-bead-${_is_sid}" 2>/dev/null || true
     ic session attribute --session="${_is_sid}" --bead="$CLAVAIN_BEAD_ID" 2>/dev/null || true
     ```
   - **Add to session tasks** using TaskCreate:
     - Title: `<bead_id> — <title>`
     - Status: `in_progress`
     This gives the session a visible checklist entry for the active work.

6. **Route based on selection:**
   - `continue` or `execute` with `plan_path` → `/clavain:work <plan_path>`
   - `plan` → `/clavain:write-plan`
   - `strategize` → `/clavain:strategy`
   - `brainstorm` → `/clavain:sprint`
   - `review_discovery` → Show bead description (the full discovery details), then AskUserQuestion with options:
     1. "Promote to sprint" → Set phase to `brainstorm`, route to `/clavain:sprint`
     2. "Dismiss discovery" → `bd close <id> --reason="Discovery dismissed — not relevant"`, then re-run discovery
     3. "Skip for now" → Re-run discovery (don't close the bead)
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
| Bead has plan AND `bead_phase` is `plan-reviewed` | `/clavain:work <plan_path>` | 1.0 | Plan reviewed and approved |
| Bead has plan AND `bead_phase` is `planned` (not yet reviewed) | `/clavain:sprint --from-step plan-review` | 1.0 | Plan exists but needs review before execution |
| Bead has plan artifact (`has_plan` non-empty) AND no `bead_phase` | `/clavain:sprint --from-step plan-review` | 0.95 | Plan exists, ensure review gate |
| `bead_action` is `execute` or `continue` | `/clavain:work <plan_path>` | 1.0 | Bead state indicates execution |
| Complexity = 1 (trivial) | `/clavain:work` | 0.9 | Too simple for full sprint |
| No description AND no brainstorm artifact | `/clavain:sprint` | 0.9 | Needs brainstorm first |
| Complexity = 5 (research) | `/clavain:sprint` | 0.85 | Needs full exploration |
| `child_count > 0` (epic with children) | `/clavain:sprint` | 0.85 | Epic needs orchestration |
| `issue_type` is `bug` | `/clavain:work` | 0.9 | Bugs have clear scope — fix the thing |
| `issue_type` is `task` AND complexity <= 3 | `/clavain:work` | 0.85 | Scoped task, moderate complexity |
| `issue_type` is `decision` | `/clavain:sprint` | 0.85 | Decisions need brainstorm/exploration |
| `issue_type` is `epic` AND `child_count == 0` | `/clavain:sprint` | 0.85 | Epic needs decomposition first |
| Description matches `[research]`, `investigate`, `explore`, `assess`, `evaluate` (case-insensitive) | `/clavain:sprint` | 0.85 | Research work needs full lifecycle |
| Complexity = 2 | `/clavain:work` | 0.85 | Simple enough for direct execution |
| Complexity = 4 | `/clavain:sprint` | 0.85 | Complex enough for full lifecycle |
| Has brainstorm but no plan | `/clavain:sprint` | 0.85 | Explored but needs planning |
| `issue_type` is `feature` AND complexity = 3 | `/clavain:sprint` | 0.85 | Moderate features need brainstorm |

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

3. **Claim bead and track in session:** If `CLAVAIN_BEAD_ID` is set:
   - **Claim the bead:**
     ```bash
     bd update "$CLAVAIN_BEAD_ID" --claim
     ```
     If `--claim` fails (exit code non-zero):
     - Tell user "Bead was claimed by another agent while routing."
     - Do NOT proceed with the current bead.
     - Restart from Step 1 of the discovery flow to find unclaimed work.
   - **Write claim identity** (after successful `--claim`):
     ```bash
     bd set-state "$CLAVAIN_BEAD_ID" "claimed_by=${CLAUDE_SESSION_ID:-unknown}" 2>/dev/null || true
     bd set-state "$CLAVAIN_BEAD_ID" "claimed_at=$(date +%s)" 2>/dev/null || true
     ```
   - **Register bead for token attribution:**
     ```bash
     _is_sid=$(cat /tmp/interstat-session-id 2>/dev/null || echo "")
     [[ -n "$_is_sid" ]] && echo "$CLAVAIN_BEAD_ID" > "/tmp/interstat-bead-${_is_sid}" 2>/dev/null || true
     ic session attribute --session="${_is_sid}" --bead="$CLAVAIN_BEAD_ID" 2>/dev/null || true
     ```
   - **Add to session tasks** using TaskCreate:
     - Title: `<bead_id> — <title or description>`
     - Status: `in_progress`

4. **Display the verdict:**
   ```
   Route: /work (0.92) — Plan exists and scope is clear
   ```
   or for heuristic routes:
   ```
   Route: /sprint (heuristic, 0.9) — Needs brainstorm first
   ```

5. **Auto-dispatch** — invoke the chosen command via the Skill tool:
   - If routing to `/clavain:sprint`: pass `$ARGUMENTS` (bead ID or feature text)
   - If routing to `/clavain:work`: pass the plan path if available, otherwise pass `$ARGUMENTS`
   - **Do not ask for confirmation** — the whole point is auto-routing

6. **Stop after dispatch.** The invoked command handles everything from here.
