#!/usr/bin/env bash
# Sprint awareness scanner library for Clavain.
# Sourced by session-start.sh (brief scan) and sprint-status command (full scan).
# All functions use SPRINT_PROJECT_DIR (defaults to CWD).

# Guard against double-sourcing
[[ -n "${_SPRINT_SCAN_LOADED:-}" ]] && return 0
_SPRINT_SCAN_LOADED=1

SPRINT_PROJECT_DIR="${SPRINT_PROJECT_DIR:-.}"

# ─── Detection Functions ───────────────────────────────────────────────

# Check if HANDOFF.md exists (session continuity signal).
# Returns 0 if present, 1 if absent. Prints path if found.
sprint_check_handoff() {
    local handoff="${SPRINT_PROJECT_DIR}/HANDOFF.md"
    if [[ -f "$handoff" ]]; then
        echo "$handoff"
        return 0
    fi
    return 1
}

# Count brainstorm files that have no matching plan or PRD.
# A brainstorm is "orphaned" if its topic slug doesn't appear as a substring
# in any plan or PRD filename.
# Prints the count. Returns 0 if any orphaned, 1 if none.
sprint_count_orphaned_brainstorms() {
    local brainstorms_dir="${SPRINT_PROJECT_DIR}/docs/brainstorms"
    local plans_dir="${SPRINT_PROJECT_DIR}/docs/plans"
    local prds_dir="${SPRINT_PROJECT_DIR}/docs/prds"
    local count=0

    [[ -d "$brainstorms_dir" ]] || { echo "0"; return 1; }

    local plans="" prds=""
    if [[ -d "$plans_dir" ]]; then
        plans=$(ls "$plans_dir" 2>/dev/null || true)
    fi
    if [[ -d "$prds_dir" ]]; then
        prds=$(ls "$prds_dir" 2>/dev/null || true)
    fi

    local file slug matched
    for file in "$brainstorms_dir"/*-brainstorm.md; do
        [[ -f "$file" ]] || continue
        # Extract topic slug: YYYY-MM-DD-<topic>-brainstorm.md → <topic>
        slug=$(basename "$file" | sed 's/^[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}-//; s/-brainstorm\.md$//')
        [[ -z "$slug" ]] && continue

        matched=0
        # Check plans (case-insensitive substring)
        if echo "$plans" | grep -qi "$slug"; then
            matched=1
        fi
        # Check PRDs (case-insensitive substring)
        if [[ $matched -eq 0 ]] && echo "$prds" | grep -qi "$slug"; then
            matched=1
        fi

        if [[ $matched -eq 0 ]]; then
            count=$((count + 1))
        fi
    done

    echo "$count"
    [[ $count -gt 0 ]] && return 0 || return 1
}

# List orphaned brainstorms with details (for full scan).
# Prints one line per orphaned brainstorm: "filename (topic: slug)"
sprint_list_orphaned_brainstorms() {
    local brainstorms_dir="${SPRINT_PROJECT_DIR}/docs/brainstorms"
    local plans_dir="${SPRINT_PROJECT_DIR}/docs/plans"
    local prds_dir="${SPRINT_PROJECT_DIR}/docs/prds"

    [[ -d "$brainstorms_dir" ]] || return 1

    local plans="" prds=""
    if [[ -d "$plans_dir" ]]; then
        plans=$(ls "$plans_dir" 2>/dev/null || true)
    fi
    if [[ -d "$prds_dir" ]]; then
        prds=$(ls "$prds_dir" 2>/dev/null || true)
    fi

    local file slug matched found=0
    for file in "$brainstorms_dir"/*-brainstorm.md; do
        [[ -f "$file" ]] || continue
        slug=$(basename "$file" | sed 's/^[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}-//; s/-brainstorm\.md$//')
        [[ -z "$slug" ]] && continue

        matched=0
        if echo "$plans" | grep -qi "$slug"; then matched=1; fi
        if [[ $matched -eq 0 ]] && echo "$prds" | grep -qi "$slug"; then matched=1; fi

        if [[ $matched -eq 0 ]]; then
            echo "$(basename "$file") (topic: $slug)"
            found=1
        fi
    done

    [[ $found -eq 1 ]] && return 0 || return 1
}

# Find plans with incomplete checklist items.
# Prints "filename: N/M complete" for each incomplete plan.
# Returns 0 if any incomplete plans found, 1 if all complete or no plans.
sprint_find_incomplete_plans() {
    local plans_dir="${SPRINT_PROJECT_DIR}/docs/plans"
    [[ -d "$plans_dir" ]] || return 1

    local file total checked unchecked found=0
    for file in "$plans_dir"/*.md; do
        [[ -f "$file" ]] || continue
        total=$(grep -c '^\s*- \[[ x]\]' "$file" 2>/dev/null || echo 0)
        [[ $total -eq 0 ]] && continue
        checked=$(grep -c '^\s*- \[x\]' "$file" 2>/dev/null || echo 0)
        unchecked=$((total - checked))
        if [[ $unchecked -gt 0 ]]; then
            echo "$(basename "$file"): ${checked}/${total} complete"
            found=1
        fi
    done

    [[ $found -eq 1 ]] && return 0 || return 1
}

# Quick beads stats summary (for full scan).
# Prints bd stats output. Returns 1 if bd unavailable or no .beads.
sprint_beads_summary() {
    command -v bd &>/dev/null || return 1
    [[ -d "${SPRINT_PROJECT_DIR}/.beads" ]] || return 1
    bd stats 2>/dev/null
}

# Count stale beads (in_progress with no recent activity).
# Prints count. Returns 0 if stale found, 1 if none.
sprint_stale_beads() {
    command -v bd &>/dev/null || return 1
    [[ -d "${SPRINT_PROJECT_DIR}/.beads" ]] || return 1
    local stale_output
    stale_output=$(bd stale 2>/dev/null) || return 1
    if [[ -z "$stale_output" ]]; then
        echo "0"
        return 1
    fi
    local count
    count=$(echo "$stale_output" | grep -c '.' || echo 0)
    echo "$count"
    [[ $count -gt 0 ]] && return 0 || return 1
}

# Check if brainstorms exist but no PRDs (strategy gap).
# Returns 0 if gap detected, 1 if no gap.
sprint_check_strategy_gap() {
    local brainstorms_dir="${SPRINT_PROJECT_DIR}/docs/brainstorms"
    local prds_dir="${SPRINT_PROJECT_DIR}/docs/prds"

    [[ -d "$brainstorms_dir" ]] || return 1

    # Check brainstorms actually has files
    local brainstorm_count
    brainstorm_count=$(find "$brainstorms_dir" -name '*-brainstorm.md' -maxdepth 1 2>/dev/null | wc -l)
    [[ $brainstorm_count -eq 0 ]] && return 1

    # Check if PRDs directory exists and has files
    if [[ -d "$prds_dir" ]]; then
        local prd_count
        prd_count=$(find "$prds_dir" -name '*.md' -maxdepth 1 2>/dev/null | wc -l)
        [[ $prd_count -gt 0 ]] && return 1
    fi

    return 0
}

# Check for untracked commits (commits not associated with any plan/bead).
# This is the slow check — only used in full scan.
# Prints commit summaries. Returns 0 if skipped phases found.
sprint_check_skipped_phases() {
    # Only works in git repos
    git rev-parse --is-inside-work-tree &>/dev/null || return 1

    local plans_dir="${SPRINT_PROJECT_DIR}/docs/plans"
    local recent_commits
    recent_commits=$(git log --oneline -20 --no-merges 2>/dev/null) || return 1
    [[ -z "$recent_commits" ]] && return 1

    # Look for commits that don't reference any plan, bead, or review
    local found=0
    while IFS= read -r line; do
        local hash msg
        hash="${line%% *}"
        msg="${line#* }"
        # Skip if commit message references a plan, bead, PR, or review
        if echo "$msg" | grep -qiE '(plan|bead|review|PR #|fix #|closes #|resolves #)'; then
            continue
        fi
        # Skip version bumps and chore commits
        if echo "$msg" | grep -qiE '^(chore|docs|ci|style|build):'; then
            continue
        fi
        echo "$line"
        found=1
    done <<< "$recent_commits"

    [[ $found -eq 1 ]] && return 0 || return 1
}

# ─── Orchestrators ─────────────────────────────────────────────────────

# Check Intermute for active agents and reservations.
# Prints coordination summary. Returns 0 if agents found, 1 otherwise.
sprint_check_coordination() {
    local intermute_url="${INTERMUTE_URL:-http://127.0.0.1:7338}"
    # Quick health check (1s timeout — don't slow down sprint scan)
    curl -sf --connect-timeout 1 --max-time 1 "${intermute_url}/health" >/dev/null 2>&1 || return 1
    command -v jq &>/dev/null || return 1

    local project
    project=$(basename "$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null) || return 1
    [[ -n "$project" ]] || return 1

    local agents_json
    agents_json=$(curl -sf --max-time 2 "${intermute_url}/api/agents?project=${project}" 2>/dev/null) || return 1
    local count
    count=$(echo "$agents_json" | jq '.agents | length' 2>/dev/null) || return 1
    [[ "$count" -gt 0 ]] || return 1

    # Build agent summary with reservations
    local reservations_json
    reservations_json=$(curl -sf --max-time 2 "${intermute_url}/api/reservations?project=${project}" 2>/dev/null) || reservations_json=""

    local output="${count} agent(s) online: "
    local agent_list
    agent_list=$(echo "$agents_json" | jq -r '.agents[] | "\(.name // .id[:8])"' 2>/dev/null) || agent_list=""

    if [[ -n "$reservations_json" ]]; then
        # Show each agent with their reserved files
        local agent_summaries=""
        while IFS= read -r agent_name; do
            [[ -z "$agent_name" ]] && continue
            local agent_id
            agent_id=$(echo "$agents_json" | jq -r --arg name "$agent_name" '.agents[] | select(.name == $name or (.id[:8]) == $name) | .id' 2>/dev/null | head -1) || agent_id=""
            local agent_files=""
            if [[ -n "$agent_id" && -n "$reservations_json" ]]; then
                agent_files=$(echo "$reservations_json" | jq -r --arg aid "$agent_id" \
                    '[.reservations[]? | select(.agent_id == $aid and .is_active == true) | .path_pattern] | join(",")' 2>/dev/null) || agent_files=""
            fi
            if [[ -n "$agent_files" ]]; then
                agent_summaries="${agent_summaries}${agent_name}→${agent_files}, "
            else
                agent_summaries="${agent_summaries}${agent_name}, "
            fi
        done <<< "$agent_list"
        output="${count} agent(s) online: ${agent_summaries%, }"
    else
        output="${count} agent(s) online: $(echo "$agent_list" | tr '\n' ',' | sed 's/,$//')"
    fi

    echo "$output"
    return 0
}

# Brief scan for session-start hook. Fast signals only, zero output when clean.
# Output is plain text suitable for JSON escaping and additionalContext injection.
sprint_brief_scan() {
    local signals=""

    # Multi-session coordination — always show if agents are active
    local coord_status
    coord_status=$(sprint_check_coordination 2>/dev/null) || coord_status=""
    if [[ -n "$coord_status" ]]; then
        signals="${signals}• Coordination: ${coord_status}\n"
    fi

    # HANDOFF.md — always show (highest priority)
    if sprint_check_handoff &>/dev/null; then
        signals="${signals}• HANDOFF.md found — previous session left unfinished work. Read it before starting.\n"
    fi

    # Orphaned brainstorms — only if ≥2
    local orphan_count
    orphan_count=$(sprint_count_orphaned_brainstorms 2>/dev/null) || orphan_count="0"
    if [[ "$orphan_count" -ge 2 ]] 2>/dev/null; then
        signals="${signals}• ${orphan_count} brainstorms without matching plans — consider running /write-plan or closing them.\n"
    fi

    # Incomplete plans — only if <50% complete and older than 1 day
    local plans_dir="${SPRINT_PROJECT_DIR}/docs/plans"
    if [[ -d "$plans_dir" ]]; then
        local file total checked pct age_days now
        now=$(date +%s)
        for file in "$plans_dir"/*.md; do
            [[ -f "$file" ]] || continue
            total=$(grep -c '^\s*- \[[ x]\]' "$file" 2>/dev/null || echo 0)
            [[ $total -eq 0 ]] && continue
            checked=$(grep -c '^\s*- \[x\]' "$file" 2>/dev/null || echo 0)
            pct=$(( (checked * 100) / total ))
            if [[ $pct -lt 50 ]]; then
                local file_mtime
                file_mtime=$(stat -c %Y "$file" 2>/dev/null || stat -f %m "$file" 2>/dev/null || echo "$now")
                age_days=$(( (now - file_mtime) / 86400 ))
                if [[ $age_days -ge 1 ]]; then
                    signals="${signals}• Plan $(basename "$file") is ${pct}% complete (${checked}/${total} items) and ${age_days}d old.\n"
                fi
            fi
        done
    fi

    # Stale beads — only if count > 0
    local stale_count
    stale_count=$(sprint_stale_beads 2>/dev/null) || stale_count="0"
    if [[ "$stale_count" -gt 0 ]] 2>/dev/null; then
        signals="${signals}• ${stale_count} stale beads (in-progress with no recent activity). Run \`bd stale\` to review.\n"
    fi

    # Strategy gap — brainstorms exist but no PRDs
    if sprint_check_strategy_gap 2>/dev/null; then
        signals="${signals}• Brainstorms exist but no PRDs — consider running /strategy to bridge the gap.\n"
    fi

    # Only output if we have signals
    if [[ -n "$signals" ]]; then
        printf "\\n\\n**Sprint status:**\\n%s" "$signals"
    fi
}

# Full scan for /sprint-status command. All signals, with details.
# Output is formatted text for direct display.
sprint_full_scan() {
    echo "# Sprint Status"
    echo ""

    # 0. Multi-Session Coordination
    echo "## Coordination"
    local coord_status
    coord_status=$(sprint_check_coordination 2>/dev/null) || coord_status=""
    if [[ -n "$coord_status" ]]; then
        echo "$coord_status"
    else
        echo "No active coordination (Intermute offline or no agents)"
    fi
    echo ""

    # 1. Session Continuity
    echo "## Session Continuity"
    local handoff_path
    if handoff_path=$(sprint_check_handoff 2>/dev/null); then
        echo "HANDOFF.md found at: $handoff_path"
        echo "Previous session left unfinished work. Read it before starting."
    else
        echo "Clean — no HANDOFF.md"
    fi
    echo ""

    # 2. Workflow Pipeline
    echo "## Workflow Pipeline"
    local brainstorm_count=0 plan_count=0 prd_count=0
    if [[ -d "${SPRINT_PROJECT_DIR}/docs/brainstorms" ]]; then
        brainstorm_count=$(find "${SPRINT_PROJECT_DIR}/docs/brainstorms" -name '*.md' -maxdepth 1 2>/dev/null | wc -l)
    fi
    if [[ -d "${SPRINT_PROJECT_DIR}/docs/plans" ]]; then
        plan_count=$(find "${SPRINT_PROJECT_DIR}/docs/plans" -name '*.md' -maxdepth 1 2>/dev/null | wc -l)
    fi
    if [[ -d "${SPRINT_PROJECT_DIR}/docs/prds" ]]; then
        prd_count=$(find "${SPRINT_PROJECT_DIR}/docs/prds" -name '*.md' -maxdepth 1 2>/dev/null | wc -l)
    fi
    echo "Brainstorms: $brainstorm_count | PRDs: $prd_count | Plans: $plan_count"
    echo ""

    # 3. Plan Progress
    echo "## Plan Progress"
    local plan_output
    plan_output=$(sprint_find_incomplete_plans 2>/dev/null) || plan_output=""
    if [[ -n "$plan_output" ]]; then
        echo "$plan_output"
    else
        echo "All plans complete (or no plans with checklists)"
    fi
    echo ""

    # 4. Orphaned Brainstorms
    echo "## Orphaned Brainstorms"
    local orphan_output
    orphan_output=$(sprint_list_orphaned_brainstorms 2>/dev/null) || orphan_output=""
    if [[ -n "$orphan_output" ]]; then
        echo "$orphan_output"
    else
        echo "None — all brainstorms have matching plans or PRDs"
    fi
    echo ""

    # 5. Beads Health
    echo "## Beads Health"
    local beads_output
    beads_output=$(sprint_beads_summary 2>/dev/null) || beads_output=""
    if [[ -n "$beads_output" ]]; then
        echo "$beads_output"
        echo ""
        local stale_out
        stale_out=$(sprint_stale_beads 2>/dev/null) || stale_out="0"
        echo "Stale beads: $stale_out"
    else
        echo "Beads not available (bd not installed or .beads not initialized)"
    fi
    echo ""

    # 6. Skipped Phases
    echo "## Skipped Phases"
    local skipped_output
    skipped_output=$(sprint_check_skipped_phases 2>/dev/null) || skipped_output=""
    if [[ -n "$skipped_output" ]]; then
        echo "Recent commits without plan/bead references:"
        echo "$skipped_output"
    else
        echo "Clean — recent commits reference plans, beads, or reviews"
    fi
    echo ""

    # 7. Recommendations
    echo "## Recommendations"
    local recs=0
    if sprint_check_handoff &>/dev/null; then
        echo "1. Read HANDOFF.md and resume previous work"
        recs=$((recs + 1))
    fi
    local orphan_count
    orphan_count=$(sprint_count_orphaned_brainstorms 2>/dev/null) || orphan_count="0"
    if [[ "$orphan_count" -ge 1 ]] 2>/dev/null; then
        recs=$((recs + 1))
        echo "${recs}. Convert orphaned brainstorms to plans with /write-plan"
    fi
    if sprint_check_strategy_gap 2>/dev/null; then
        recs=$((recs + 1))
        echo "${recs}. Bridge brainstorm→plan gap with /strategy"
    fi
    if [[ $recs -eq 0 ]]; then
        echo "Everything looks good. Ready to work."
    fi
}
