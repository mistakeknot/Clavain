---
name: route
description: Universal entry point — discovers work, resumes sprints, classifies tasks, and dispatches to /sprint or /work
argument-hint: "[bead ID, feature description, or empty for discovery]"
---

# Route

Auto-dispatch to `/sprint` or `/work`. New project? → `/clavain:project-onboard`.

## Patterns (reference by name)

**S2 measurement (eligibility first):** Before any measurement work or helper launch, inspect the selected routing policy already available to you. If `decision_models.route.mode` is not exactly `shadow`, the backend is neither `heuristic` nor `jev` with `privacy_contract: shadow-observer-v1`, or the global `CLAVAIN_SELECTOR` kill is `off`, silently do nothing. If the configuration is not already known, use a normal configuration read only; never run a measurement or helper subprocess to find out. Observe only when the exact UTF8 byte counts of the complete native prompt and response, the normalized native choice and the lowercase SHA256 subject hash are already in hand from host telemetry. Do not make new tool calls to compute, hash or count anything; never guess or estimate counts; never use heredocs or interpolate raw description, prompt, response or evidence text into shell code. Otherwise skip silently and continue the native path. The observer derives the savings figure from the supplied counts; it remains an estimate.

**token-attribution:** `_is_sid=$(cat /tmp/interstat-session-id 2>/dev/null||echo ""); [[ -n "$_is_sid" ]] && echo "$CLAVAIN_BEAD_ID" > "/tmp/interstat-bead-${_is_sid}" 2>/dev/null||true; ic session attribute --session="${_is_sid}" --bead="$CLAVAIN_BEAD_ID" 2>/dev/null||true`

**claim-identity:** `bd set-state "$CLAVAIN_BEAD_ID" "claimed_by=${CLAUDE_SESSION_ID:-unknown}" 2>/dev/null||true; bd set-state "$CLAVAIN_BEAD_ID" "claimed_at=$(date +%s)" 2>/dev/null||true`

**claim-bead:** `bd update "$CLAVAIN_BEAD_ID" --claim`. Failure: "already claimed"→re-run discovery; "lock"/"timeout"→retry once then re-run. Never fall back to `--status=in_progress`. Success: run claim-identity then token-attribution.

## Step 1: Check Active Sprints (Resume)

```bash
active_sprints=$(clavain-cli sprint-find-active 2>/dev/null) || active_sprints="[]"
sprint_count=$(echo "$active_sprints" | jq 'length' 2>/dev/null) || sprint_count=0
```

- **0 sprints** → Step 2.
- **1 sprint** → auto-resume:
  a. Read: `sprint_id=$(echo "$active_sprints"|jq -r '.[0].id')`, `sprint_state=$(clavain-cli sprint-read-state "$sprint_id")`, `sprint_phase=$(echo "$sprint_state"|jq -r '.phase // ""')`
  b. Claim: `clavain-cli sprint-claim "$sprint_id" "$CLAUDE_SESSION_ID"` (fail→offer force-claim or fresh)
  c. `CLAVAIN_BEAD_ID="$sprint_id"`, run token-attribution
  d. Checkpoint: `clavain-cli checkpoint-read`. If SHA changed→AskUserQuestion(resume/restart/re-plan). Clean→use steps silently.
  e. If `sprint_phase=reflect`, read `reflection=$(clavain-cli get-artifact "$sprint_id" "reflection" 2>/dev/null) || reflection=""`; `[[ -n "$reflection" && -f "$reflection" ]]` routes to `/clavain:sprint --from-step ship`, otherwise route to `/clavain:reflect`. For every other phase, route by `clavain-cli sprint-next-step`: brainstorm→`/sprint`, strategy→`/sprint --from-step strategy`, write-plan→`/sprint --from-step plan`, work→`/clavain:work`, resolve→`/clavain:resolve`, ship→`/clavain:sprint --from-step ship`, reflect→`/clavain:reflect`, done→tell user. Display: `Resuming sprint <id> — <title>`. **Stop.**
- **Multiple** → AskUserQuestion sorted by recency: `"Resume <id> — <title> (phase, last active)"`. Include "Start fresh".

## Step 2: Parse Arguments

**`--lane=<name>` flag:** Extract, set `DISCOVERY_LANE`, continue parsing.

**Empty args** → `route_mode="discovery"` → Step 3.

**Goal-scale input** (mentions "goal", spans multiple work items, or names an
outcome rather than a task): route to `/clavain:goal-form` — the formation
ritual owns charter + mint + /goal handoff. Do not start ordinary
implementation for goal-scale asks.

**Bead ID** (format `[A-Za-z]+-[a-z0-9]+`):
- `bd show "$ARGUMENTS"` — if fails, tell user and fall through to Step 3
- Set `route_mode="bead"`, `bead_id="$ARGUMENTS"`, `CLAVAIN_BEAD_ID="$ARGUMENTS"`
- Gather metadata:
  ```bash
  has_plan=$(clavain-cli get-artifact "$bead_id" plan 2>/dev/null)||has_plan=""
  has_brainstorm=$(clavain-cli get-artifact "$bead_id" brainstorm 2>/dev/null)||has_brainstorm=""
  has_prd=$(clavain-cli get-artifact "$bead_id" prd 2>/dev/null)||has_prd=""
  bead_phase=$(bd state "$bead_id" phase 2>/dev/null)||bead_phase=""
  bead_action=$(clavain-cli infer-action "$bead_id" 2>/dev/null)||bead_action=""
  complexity=$(clavain-cli classify-complexity "$bead_id" "" 2>/dev/null)||complexity="3"
  complexity_label=$(clavain-cli complexity-label "$complexity" 2>/dev/null)||complexity_label="moderate"
  child_count=$(bd children "$bead_id" 2>/dev/null|jq 'length' 2>/dev/null)||child_count="0"
  ```
- Cache: `bd set-state "$bead_id" "complexity=$complexity"`
- Display: `Complexity: ${complexity}/5 (${complexity_label})`
- **Staleness check:** Haiku agent (foreground): is bead already implemented? Return `{"implemented":bool,"evidence":"..."}`. If true→AskUserQuestion(close/proceed/investigate).
- After the native result, apply the **S2 eligibility and measurement pattern** above; if eligible, launch S2 below in the background before continuing that same native path. Normalize only a JSON boolean `implemented`: true → `implemented`, false → `not_implemented`; skip malformed results. `route_subject_sha256`, `route_input_bytes` and `route_output_bytes` must be the exact values already in hand for this bead ID and the complete native prompt / response (including evidence); otherwise skip silently. Pass only these counts and hash; never pass or persist the text.
  ```bash
  python3 "$CLAUDE_PLUGIN_ROOT/scripts/clavain_selector/route_shadow.py" --site route-staleness --native-choice "$route_native_choice" --subject-sha256 "$route_subject_sha256" --input-bytes "$route_input_bytes" --output-bytes "$route_output_bytes" --plugin-root "$CLAUDE_PLUGIN_ROOT" --config "${CLAVAIN_ROUTING_POLICY:-$CLAUDE_PLUGIN_ROOT/config/routing.yaml}" --project-root "$PWD" </dev/null >/dev/null 2>&1 &
  ```
  Never wait for the observer or read its return to affect behavior; retain the foreground check and close/proceed/investigate question.
- → Step 4.

**Free text:**
- `route_mode="text"`, `description="$ARGUMENTS"`
- Classify: `complexity=$(clavain-cli classify-complexity "" "$ARGUMENTS")`
- Display complexity → Step 4.

## Step 3: Discovery Scan

Only when `route_mode="discovery"`.

1. ```bash
   export DISCOVERY_PROJECT_DIR="."; export DISCOVERY_LANE="${DISCOVERY_LANE:-}"; source "$CLAUDE_PLUGIN_ROOT/hooks/lib-discovery.sh" && discovery_scan_beads
   ```

2. Parse: `DISCOVERY_UNAVAILABLE`/`DISCOVERY_ERROR`/`[]` → `/clavain:sprint`. JSON array → continue.

3. **Staleness sweep:** Top 3 without `possibly_done`: check `ic state get "bead_sweep" "<id>"` (1hr cache). Misses→single background haiku batch-check. Wait 5s max.

   Apply the **S2 eligibility and measurement pattern** above. Observe only fresh Haiku results that arrive within the existing 5s wait; drop late results and cache hits, and do no follow-up, polling or completion tracking for them. For each such returned bead, if eligible, launch S2 once. Normalize JSON boolean `implemented` strictly to `implemented` / `not_implemented`; skip malformed entries. `route_subject_sha256` (for that bead ID) and `route_input_bytes` / `route_output_bytes` (complete batch prompt / response) must be exact values already in hand, else skip silently; `route_batch_size` is the number of beads checked in that batch. This apportions the batch estimate equally (rounding each share up), still an estimate. Never pass native text or evidence.
   ```bash
   python3 "$CLAUDE_PLUGIN_ROOT/scripts/clavain_selector/route_shadow.py" --site route-sweep --native-choice "$route_native_choice" --subject-sha256 "$route_subject_sha256" --input-bytes "$route_input_bytes" --output-bytes "$route_output_bytes" --batch-size "$route_batch_size" --plugin-root "$CLAUDE_PLUGIN_ROOT" --config "${CLAVAIN_ROUTING_POLICY:-$CLAUDE_PLUGIN_ROOT/config/routing.yaml}" --project-root "$PWD" </dev/null >/dev/null 2>&1 &
   ```
   Never wait for the observer or read its return to affect behavior; keep the native background sweep, cache and 5s wait limit unchanged.

3b. **Context warmth annotation:** For each top-3 bead, check if recent sessions touched related files:
   ```bash
   if command -v cass > /dev/null 2>&1; then
       for bead in "${top_beads[@]:0:3}"; do
           primary_file=$(bd state "$bead" primary_file 2>/dev/null) || primary_file=""
           if [[ -n "$primary_file" && "$primary_file" != *"(no"* ]]; then
               warmth=$(cass context "$primary_file" --json --limit 1 2>/dev/null | jq -r '.[0].age_minutes // empty' 2>/dev/null) || warmth=""
               if [[ -n "$warmth" && "$warmth" -lt 120 ]]; then
                   # Annotate: this bead has warm context (session touched files <2hrs ago)
                   bead_warmth[$bead]="warm (${warmth}m ago)"
               fi
           fi
       done
   fi
   ```
   Append warmth annotation to AskUserQuestion labels: `"<Action> <id> — <title> (P<pri>) 🔥 warm (Nm ago)"`. Context warmth is a **tiebreaker**, not a primary signal — never override priority ordering, only annotate for user awareness.

4. **AskUserQuestion**: top 3 beads + "Start fresh brainstorm" + "Show full backlog". Label: `"<Action> <id> — <title> (P<pri>)"`. Actions: continue/execute/plan/strategize/brainstorm/ship/create_bead→"Link orphan:"/verify_done→"Verify (parent closed):"/review_discovery→"Review discovery:". Interject: strip `[interject] `, append source+score. Possibly-done: `⚠` notice only.

5. Pre-flight: `bd show <id>` — if fails, re-run. Skip for orphans.

6. PATTERN: claim-bead (skip for closed/verify_done/create_bead). TaskCreate: `<id> — <title>`.

7. Route: continue/execute→`/clavain:work <plan>`, plan→`/clavain:write-plan`, strategize→`/clavain:strategy`, brainstorm→`/clavain:sprint`, review_discovery→AskUserQuestion(promote/dismiss/skip), ship→`/clavain:quality-gates`, closed→re-run, verify_done→AskUserQuestion(close/review/cascade), create_bead→`bd create`+insert bead ref+route by type, fresh→`/clavain:sprint`, backlog→`/clavain:sprint-status`.

8. Log: `discovery_log_selection "<id>" "<action>" <was_recommended>`. **Stop after dispatch.**

## Step 4: Classify and Dispatch

Reached when `route_mode` is `"bead"` or `"text"`.

### 4a: Fast-Path Heuristics

**Decision maps first.** If the bead's labels include `wayfinder:map`, display `Route: /clavain:wayfind <id> — decision map, not build work` and stop; the user starts it. In text mode, when the request names a destination but its route needs decisions across several sessions, suggest `/clavain:wayfind "<idea>"` alongside the table's route. Never start it.

First match wins. **Row order is semantically significant** — rows 1-4 are terminal (conf 1.0), rows 5+ are advisory. Do not reorder.

| Condition | Route | Conf |
|-----------|-------|------|
| has_plan AND phase=`plan-reviewed` | `/clavain:work <plan_path>` | 1.0 |
| has_plan AND phase=`planned` | `/clavain:sprint --from-step plan-review` | 1.0 |
| has_plan AND no phase | `/clavain:sprint --from-step plan-review` | 0.95 |
| bead_action=`execute`\|`continue` AND has_plan | `/clavain:work <plan_path>` | 1.0 |
| Complexity = 1 (trivial) | `/clavain:work` | 0.9 |
| No description AND no brainstorm | `/clavain:sprint` | 0.9 |
| Has brainstorm but no plan | `/clavain:sprint` | 0.85 |
| Complexity = 5 (research) | `/clavain:sprint` | 0.85 |
| child_count > 0 (epic w/ children) | `/clavain:sprint` | 0.85 |
| issue_type=`bug` | `/clavain:work` | 0.9 |
| issue_type=`task` AND complexity <= 3 | `/clavain:work` | 0.85 |
| issue_type=`decision` | `/clavain:sprint` | 0.85 |
| issue_type=`epic` AND child_count=0 | `/clavain:sprint` | 0.85 |
| Description matches research/investigate/explore/assess/evaluate | `/clavain:sprint` | 0.85 |
| Complexity = 2 | `/clavain:work` | 0.85 |
| Complexity = 4 | `/clavain:sprint` | 0.85 |
| issue_type=`feature` AND complexity = 3 | `/clavain:sprint` | 0.85 |

If confidence >= 0.8: display verdict, skip to 4c.

### 4b: LLM Classification (haiku fallback)

Haiku subagent: given bead metadata (description, has_plan, has_brainstorm, has_prd, complexity, priority, type, phase, child_count), route to `/sprint` (full lifecycle, C4-5, ambiguous, research, epic) or `/work` (clear scope, C1-3, bug fix, plan exists).

Examples to include in prompt:
- `/sprint`: `{type:feature, C:4, no plan, "Redesign auth flow"}` — ambiguous scope needs brainstorm
- `/work`: `{type:bug, C:2, "Fix null pointer in payment handler"}` — clear scope, directly executable
- `/work`: `{type:task, C:3, has_plan:true, phase:plan-reviewed}` — plan exists and reviewed

Return `{"command":"/sprint"|"/work","confidence":0.0-1.0,"reason":"..."}`. Parse fails→default `/sprint`.

After the native result, apply the **S2 eligibility and measurement pattern** above; if eligible, launch S2 in the background. Normalize only exact `/sprint` → `sprint` or `/work` → `work` into `route_native_choice`; skip malformed results while retaining the native `/sprint` default. `route_subject_sha256` (bead ID, or free-text description in text mode) and `route_input_bytes` / `route_output_bytes` (complete native prompt / response) must be exact values already in hand, else skip silently. No prompt, description or reason is passed or persisted.

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/clavain_selector/route_shadow.py" --site route-4b --native-choice "$route_native_choice" --subject-sha256 "$route_subject_sha256" --input-bytes "$route_input_bytes" --output-bytes "$route_output_bytes" --plugin-root "$CLAUDE_PLUGIN_ROOT" --config "${CLAVAIN_ROUTING_POLICY:-$CLAUDE_PLUGIN_ROOT/config/routing.yaml}" --project-root "$PWD" </dev/null >/dev/null 2>&1 &
```

Never wait for the observer or read its return to affect behavior. Continue to 4c using only the native result/default. See `docs/reference/route-shadow.md` for local log interpretation.

### 4c: Dispatch

1. If dispatching to `/clavain:sprint` and no `CLAVAIN_BEAD_ID`: `SPRINT_ID=$(clavain-cli sprint-create "<title>")`, set as `CLAVAIN_BEAD_ID`, cache complexity.
2. Cache complexity: `bd set-state "$CLAVAIN_BEAD_ID" "complexity=$complexity"`
3. Run PATTERN: claim-bead. On failure: re-run discovery. Add TaskCreate.
4. Display: `Route: /work (0.92) — Plan exists and scope is clear` or `Route: /sprint (heuristic, 0.9) — Needs brainstorm first`. If budget data available (`clavain-cli sprint-budget-remaining "$CLAVAIN_BEAD_ID"` returns non-zero), append: `(budget: Nk remaining)`.
5. Auto-dispatch via Skill tool. Pass bead ID or plan path. **Do not ask for confirmation.**
6. **Stop after dispatch.**
