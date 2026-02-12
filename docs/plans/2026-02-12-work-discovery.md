# Implementation Plan: Work Discovery (M1 F1+F2)

**Bead:** Clavain-6czs (F1: Beads-Based Work Scanner), Clavain-a3hp (F2: AskUserQuestion Discovery UI)
**PRD:** docs/prds/2026-02-12-phase-gated-lfg.md
**Epic:** Clavain-tayp

## Overview

Add a work discovery mode to `/lfg` so that invoking it with no arguments scans open beads, ranks by priority, and presents the top options via AskUserQuestion. User hits Enter to accept the recommended option, which routes to the appropriate `/clavain:*` command.

This plan covers F1 (scanner) and F2 (UI) together since they're a single user-facing feature. F3 (orphan detection) and F4 (session-start) are separate plans.

## Architecture

**Approach:** Add a new `hooks/lib-discovery.sh` library with scanner functions, then modify `commands/lfg.md` to invoke the scanner when no arguments are provided. The scanner reuses existing beads CLI queries and sprint-scan patterns.

**Why a library, not a script?** The discovery logic needs to be shared between:
- `commands/lfg.md` (on-demand discovery)
- `hooks/session-start.sh` (light scan, future F4)
- `hooks/sprint-scan.sh` (full scan, existing)

A shared library in `hooks/lib-discovery.sh` keeps the logic in one place, just like `hooks/lib.sh` and `hooks/sprint-scan.sh`.

## Flux-Drive Review Findings Applied

Both fd-architecture and fd-correctness reviewed this plan. Key fixes incorporated:

1. **JSON output format** — pipe-delimited was unsafe (titles can contain `|`). Now outputs JSON array.
2. **Filesystem-only artifact detection** — dropped notes-field parsing (dual-source is over-engineered for v1). Grep only.
3. **Word-boundary grep anchors** — `"Bead.*${bead_id}"` → `"Bead[: ]*${bead_id}\b"` to prevent substring false positives.
4. **JSON validation** — all `jq` outputs validated before use; `bd` failures handled gracefully.
5. **Safe telemetry logging** — `jq` constructs JSON instead of raw `printf` with user data.
6. **Plan path in output** — scanner includes the matched plan file path so lfg.md can route directly.
7. **Staleness uses plan mtime** — when a plan exists, staleness checks file modification time, not bead update date.

Full reviews: `docs/research/architecture-review-of-plan.md`, `docs/research/correctness-review-of-plan.md`

## Tasks

### Task 1: Create `hooks/lib-discovery.sh`

New file with these functions:

```bash
# discovery_scan_beads()
# Queries bd for open beads, sorts by priority then recency.
# Returns JSON array to stdout: [{id, title, priority, status, action, plan_path, stale}]
#
# Uses: bd list --status=open --json
# Sorts: priority (P0 first), then updated (most recent first)
# For each bead, determines recommended_action via filesystem scan:
#   - in_progress → "continue" (route to /work <plan-path>)
#   - open + has plan → "execute" (route to /work <plan-path>)
#   - open + has PRD but no plan → "plan" (route to /write-plan)
#   - open + has brainstorm but no PRD → "strategize" (route to /strategy)
#   - open + nothing → "brainstorm" (route to /brainstorm)
#
# Error handling:
#   - bd not installed → print DISCOVERY_UNAVAILABLE, exit 0
#   - bd command fails → print DISCOVERY_ERROR, exit 0
#   - No open beads → print empty JSON array [], exit 0
#
# Staleness: bead updated >2 days ago OR plan file mtime >2 days ago (whichever is newer)

# discovery_route_to_command()
# Given a bead ID and its recommended action, returns the slash command to invoke.
# Maps action → command string for output to the LLM.
```

**Implementation detail — action inference (filesystem-only):**

The scanner determines what each bead needs by scanning the filesystem for artifacts referencing the bead ID. No notes-field parsing — single source of truth.

```bash
infer_bead_action() {
    local bead_id="$1"
    local status="$2"  # already validated by caller

    local plan_path="" prd_path="" brainstorm_path=""

    # Filesystem scan with word-boundary anchors to prevent substring matches
    # (e.g., "Clavain-abc" must not match "Clavain-abc1")
    plan_path=$(grep -rl "Bead[: ]*${bead_id}\b" docs/plans/ 2>/dev/null | head -1 || true)
    prd_path=$(grep -rl "Bead[: ]*${bead_id}\b" docs/prds/ 2>/dev/null | head -1 || true)
    brainstorm_path=$(grep -rl "Bead[: ]*${bead_id}\b" docs/brainstorms/ 2>/dev/null | head -1 || true)

    # Determine action + emit plan_path for routing
    if [[ "$status" == "in_progress" ]]; then
        echo "continue|${plan_path}"
    elif [[ -n "$plan_path" ]]; then
        echo "execute|${plan_path}"
    elif [[ -n "$prd_path" ]]; then
        echo "plan|${prd_path}"
    elif [[ -n "$brainstorm_path" ]]; then
        echo "strategize|${brainstorm_path}"
    else
        echo "brainstorm|"
    fi
}
```

**`discovery_scan_beads()` main function:**

```bash
discovery_scan_beads() {
    # Guard: bd must be installed
    if ! command -v bd &>/dev/null; then
        echo "DISCOVERY_UNAVAILABLE"
        return 0
    fi

    # Query open beads — validate JSON output
    local raw_list
    raw_list=$(bd list --status=open --json 2>/dev/null) || {
        echo "DISCOVERY_ERROR"
        return 0
    }

    # Validate it's actually JSON
    if ! echo "$raw_list" | jq empty 2>/dev/null; then
        echo "DISCOVERY_ERROR"
        return 0
    fi

    local count
    count=$(echo "$raw_list" | jq 'length')
    if [[ "$count" == "0" ]]; then
        echo "[]"
        return 0
    fi

    # Sort: priority ASC (P0 first), then updated DESC (most recent first)
    local sorted
    sorted=$(echo "$raw_list" | jq 'sort_by(.priority, (-.updated_at | if . then . else 0 end))')

    # Build result array
    local results="[]"
    local i=0
    while [[ $i -lt $count ]]; do
        local bead_json
        bead_json=$(echo "$sorted" | jq ".[$i]")

        # Extract fields with validation
        local id status priority title updated
        id=$(echo "$bead_json" | jq -r '.id // empty')
        status=$(echo "$bead_json" | jq -r '.status // empty')
        priority=$(echo "$bead_json" | jq -r '.priority // 4')
        title=$(echo "$bead_json" | jq -r '.title // "Untitled"')
        updated=$(echo "$bead_json" | jq -r '(.updated_at // "") | tostring')

        # Skip if essential fields missing
        if [[ -z "$id" || -z "$status" ]]; then
            i=$((i + 1))
            continue
        fi

        # Infer action (filesystem-only)
        local action_result action plan_path
        action_result=$(infer_bead_action "$id" "$status")
        action="${action_result%%|*}"
        plan_path="${action_result#*|}"

        # Staleness check: plan mtime if available, else bead updated date
        local stale=false
        local two_days_ago
        two_days_ago=$(date -d '2 days ago' +%s 2>/dev/null || date -v-2d +%s 2>/dev/null || echo 0)

        if [[ -n "$plan_path" && -f "$plan_path" ]]; then
            local plan_mtime
            plan_mtime=$(stat -c %Y "$plan_path" 2>/dev/null || stat -f %m "$plan_path" 2>/dev/null || echo 0)
            [[ "$plan_mtime" -lt "$two_days_ago" ]] && stale=true
        elif [[ -n "$updated" && "$updated" != "null" ]]; then
            local updated_epoch
            updated_epoch=$(date -d "$updated" +%s 2>/dev/null || echo 0)
            [[ "$updated_epoch" -lt "$two_days_ago" ]] && stale=true
        fi

        # Append to results using jq (safe JSON construction — no printf injection)
        results=$(echo "$results" | jq \
            --arg id "$id" \
            --arg title "$title" \
            --argjson priority "$priority" \
            --arg status "$status" \
            --arg action "$action" \
            --arg plan_path "$plan_path" \
            --argjson stale "$stale" \
            '. + [{id: $id, title: $title, priority: $priority, status: $status, action: $action, plan_path: $plan_path, stale: $stale}]')

        i=$((i + 1))
    done

    echo "$results"
}
```

**Output format** — JSON array printed to stdout:

```json
[
  {"id":"Clavain-abc","title":"Fix auth timeout","priority":1,"status":"open","action":"execute","plan_path":"docs/plans/2026-02-12-fix-auth.md","stale":false},
  {"id":"Clavain-def","title":"Add dark mode","priority":2,"status":"open","action":"plan","plan_path":"","stale":true},
  {"id":"Clavain-ghi","title":"Refactor sync","priority":3,"status":"open","action":"brainstorm","plan_path":"","stale":false}
]
```

The LLM in `lfg.md` reads this JSON and constructs the AskUserQuestion call.

- [ ] Create `hooks/lib-discovery.sh` with `discovery_scan_beads()`, `infer_bead_action()`, and JSON output
- [ ] Handle `bd` unavailable → `DISCOVERY_UNAVAILABLE` sentinel (graceful fallback)
- [ ] Handle `bd` errors → `DISCOVERY_ERROR` sentinel (graceful fallback)
- [ ] Validate all `jq` outputs before use (empty/null checks on id, status)
- [ ] Use word-boundary grep anchors (`\b`) to prevent substring false positives
- [ ] Add staleness check using plan mtime when available, bead updated date otherwise
- [ ] Sort by priority (P0 first) then recency (most recently updated first)
- [ ] Include `plan_path` in output for direct routing

### Task 2: Modify `commands/lfg.md` — add discovery mode

Current lfg.md starts immediately with "Run these steps in order." Change to:

```markdown
## Before Starting

If invoked with no arguments (`$ARGUMENTS` is empty):

1. Run the work discovery scanner via Bash:
   ```bash
   source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-discovery.sh" && discovery_scan_beads
   ```

2. Parse the output:
   - `DISCOVERY_UNAVAILABLE` → skip discovery, proceed to Step 1 (bd not installed)
   - `DISCOVERY_ERROR` → skip discovery, proceed to Step 1 (bd failed)
   - `[]` → no open beads, proceed to Step 1
   - JSON array → present options (step 3)

3. If results found, present via AskUserQuestion:
   - First option: top-ranked bead with compact label and (Recommended)
     Format: "Continue Clavain-abc — Fix auth timeout (P1)" or "Plan Clavain-def — Add dark mode (P2, stale)"
   - Options 2-3: next highest-ranked beads
   - Second-to-last option: "Start fresh brainstorm"
   - Last option: "Show full backlog" (runs /sprint-status)

4. Based on selection:
   - Bead selected → route to appropriate command using `plan_path` from JSON:
     - action:continue → `/clavain:work <plan_path>` (plan_path from JSON)
     - action:execute → `/clavain:work <plan_path>` (plan_path from JSON)
     - action:plan → `/clavain:write-plan`
     - action:strategize → `/clavain:strategy`
     - action:brainstorm → `/clavain:brainstorm`
   - "Start fresh brainstorm" → proceed to Step 1 (brainstorm)
   - "Show full backlog" → `/clavain:sprint-status`

5. After routing, log the selection:
   ```bash
   source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-discovery.sh" && discovery_log_selection "<bead_id>" "<action>" <true|false>
   ```

If invoked WITH arguments, skip discovery and proceed directly to Step 1 (existing behavior).
```

- [ ] Add discovery mode section before Step 1 in lfg.md
- [ ] Preserve existing 9-step pipeline for when arguments are provided
- [ ] Handle all three sentinel values (DISCOVERY_UNAVAILABLE, DISCOVERY_ERROR, empty array)
- [ ] Map discovery actions to correct `/clavain:*` commands with plan_path from JSON
- [ ] Handle "Show full backlog" routing to sprint-status
- [ ] Log selection via discovery_log_selection()

### Task 3: Add telemetry logging

Create a simple append-only logger for discovery selections. Uses `jq` for safe JSON construction — no printf injection risk from user-controlled data (bead titles, IDs):

```bash
# In lib-discovery.sh
discovery_log_selection() {
    local bead_id="$1"
    local action="$2"
    local was_recommended="$3"  # true/false
    local telemetry_file="${HOME}/.clavain/telemetry.jsonl"
    mkdir -p "$(dirname "$telemetry_file")" 2>/dev/null || return 0

    # Use jq for safe JSON construction — prevents injection from user data
    jq -n -c \
        --arg event "discovery_select" \
        --arg bead "$bead_id" \
        --arg action "$action" \
        --argjson recommended "$was_recommended" \
        --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '{event: $event, bead: $bead, action: $action, recommended: $recommended, timestamp: $ts}' \
        >> "$telemetry_file" 2>/dev/null || true
}
```

- [ ] Add `discovery_log_selection()` to lib-discovery.sh
- [ ] Use `jq` (not printf) for JSON construction — prevents injection from bead titles/IDs
- [ ] Log which option was selected (bead ID, action, whether it was the recommended option)
- [ ] Fail silently if directory/file creation fails (telemetry must never block workflow)

### Task 4: Tests

Add tests to the existing test suite:

**Shell tests (`tests/shell/`):**

```bash
# test_discovery.bats

@test "discovery_scan_beads outputs valid JSON when beads available" {
    # Mock bd list output with sample beads
    # Verify output parses as JSON array
    # Verify each element has: id, title, priority, status, action, plan_path, stale
}

@test "discovery handles bd not installed" {
    # Unset bd from PATH
    # Verify output is "DISCOVERY_UNAVAILABLE"
}

@test "discovery handles bd returning error" {
    # Mock bd to return non-zero exit
    # Verify output is "DISCOVERY_ERROR"
}

@test "discovery handles bd returning invalid JSON" {
    # Mock bd to return garbage
    # Verify output is "DISCOVERY_ERROR"
}

@test "discovery sorts by priority then recency" {
    # Mock bd list with mixed priorities
    # Verify P0 comes first, then P1, etc.
    # Verify within same priority, most recent first
}

@test "discovery returns empty array when no open beads" {
    # Mock bd list returning []
    # Verify output is "[]"
}

@test "infer_bead_action returns correct action for each state" {
    # Setup temp dirs with test artifacts containing bead references
    # Test: in_progress → continue
    # Test: has plan → execute (with plan_path)
    # Test: has PRD no plan → plan
    # Test: has brainstorm no PRD → strategize
    # Test: nothing → brainstorm
}

@test "infer_bead_action uses word-boundary matching" {
    # Create plan referencing "Clavain-abc1"
    # Query for "Clavain-abc" — must NOT match
    # Query for "Clavain-abc1" — must match
}

@test "discovery_log_selection writes valid JSONL" {
    # Call with test data including special characters in bead ID
    # Verify telemetry file contains valid JSON line
    # Verify no printf injection (title with %s doesn't expand)
}

@test "staleness uses plan mtime when plan exists" {
    # Create a plan file with old mtime (touch -t)
    # Verify bead shows as stale
    # Touch the plan to now
    # Verify bead shows as not stale
}
```

**Structural tests (`tests/structural/`):**

```python
# Verify lib-discovery.sh exists and has required functions
# Verify lfg.md has discovery mode section (Before Starting)
# Verify lib-discovery.sh has DISCOVERY_UNAVAILABLE/DISCOVERY_ERROR sentinels
```

- [ ] Write bats tests for discovery scanner in `tests/shell/test_discovery.bats`
- [ ] Include bd error handling tests (not installed, error, invalid JSON)
- [ ] Include word-boundary grep test (substring false positive prevention)
- [ ] Include staleness mtime test
- [ ] Include telemetry injection safety test
- [ ] Write structural test for lib-discovery.sh existence
- [ ] Verify existing sprint-scan tests still pass
- [ ] Verify existing lfg-related tests still pass

### Task 5: Update using-clavain routing table

Update `skills/using-clavain/SKILL.md` and `skills/using-clavain/references/routing-tables.md` to document the new `/lfg` behavior (no-args = discovery, with-args = pipeline).

- [ ] Add discovery mode description to using-clavain SKILL.md
- [ ] Update routing-tables.md with `/lfg` no-args behavior
- [ ] Keep command count at 36 (no new command — this is an enhancement to existing `/lfg`)

## File Changes

| File | Change | Lines |
|------|--------|-------|
| `hooks/lib-discovery.sh` | NEW — scanner library (JSON output, filesystem-only detection, jq-safe telemetry) | ~120 |
| `commands/lfg.md` | MODIFY — add discovery mode before Step 1 | +35 |
| `tests/shell/test_discovery.bats` | NEW — shell tests (11 test cases incl. error handling, word-boundary, mtime, injection) | ~100 |
| `tests/structural/test_plugin_structure.py` | MODIFY — add lib-discovery.sh check | +5 |
| `skills/using-clavain/SKILL.md` | MODIFY — document discovery | +2 |
| `skills/using-clavain/references/routing-tables.md` | MODIFY — update /lfg entry | +3 |

**Total: ~265 lines new code, 2 new files, 4 modified files.**

## Verification

1. `bash -n hooks/lib-discovery.sh` — syntax check
2. `bats tests/shell/test_discovery.bats` — all 11 tests pass
3. `uv run --config tests/pyproject.toml pytest tests/structural/ -v` — structural tests pass
4. Manual: run `/lfg` with no args in a project with open beads, verify AskUserQuestion appears with JSON-sourced labels
5. Manual: run `/lfg some feature` with args, verify it skips discovery and starts pipeline
6. Manual: select a bead from discovery, verify it routes to the correct command with plan_path
7. Manual: verify telemetry line written to `$HOME/.clavain/telemetry.jsonl` is valid JSON
