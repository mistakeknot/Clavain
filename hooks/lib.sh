#!/usr/bin/env bash
# Shared utilities for Clavain hook scripts

# Discover the interphase companion plugin root directory.
# Checks INTERPHASE_ROOT env var first, then searches the plugin cache.
# Output: plugin root path to stdout, or empty string if not found.
_discover_beads_plugin() {
    if [[ -n "${_CACHED_INTERPHASE_ROOT+set}" ]]; then
        echo "$_CACHED_INTERPHASE_ROOT"
        return 0
    fi
    if [[ -n "${INTERPHASE_ROOT:-}" ]]; then
        _CACHED_INTERPHASE_ROOT="$INTERPHASE_ROOT"
        echo "$INTERPHASE_ROOT"
        return 0
    fi
    local f
    f=$(find "${HOME}/.claude/plugins/cache" -maxdepth 5 \
        -path '*/interphase/*/hooks/lib-gates.sh' 2>/dev/null | sort -V | tail -1)
    if [[ -n "$f" ]]; then
        # lib-gates.sh is at <root>/hooks/lib-gates.sh, so strip two levels
        _CACHED_INTERPHASE_ROOT="$(dirname "$(dirname "$f")")"
        echo "$_CACHED_INTERPHASE_ROOT"
        return 0
    fi
    _CACHED_INTERPHASE_ROOT=""
    echo ""
}

# Discover the interflux companion plugin root directory.
# Checks INTERFLUX_ROOT env var first, then searches the plugin cache.
# Output: plugin root path to stdout, or empty string if not found.
_discover_interflux_plugin() {
    if [[ -n "${_CACHED_INTERFLUX_ROOT+set}" ]]; then
        echo "$_CACHED_INTERFLUX_ROOT"
        return 0
    fi
    if [[ -n "${INTERFLUX_ROOT:-}" ]]; then
        _CACHED_INTERFLUX_ROOT="$INTERFLUX_ROOT"
        echo "$INTERFLUX_ROOT"
        return 0
    fi
    local f
    f=$(find "${HOME}/.claude/plugins/cache" -maxdepth 5 \
        -path '*/interflux/*/.claude-plugin/plugin.json' 2>/dev/null | sort -V | tail -1)
    if [[ -n "$f" ]]; then
        # plugin.json is at <root>/.claude-plugin/plugin.json, so strip two levels
        _CACHED_INTERFLUX_ROOT="$(dirname "$(dirname "$f")")"
        echo "$_CACHED_INTERFLUX_ROOT"
        return 0
    fi
    _CACHED_INTERFLUX_ROOT=""
    echo ""
}

# Discover the interpath companion plugin root directory.
# Checks INTERPATH_ROOT env var first, then searches the plugin cache.
# Output: plugin root path to stdout, or empty string if not found.
_discover_interpath_plugin() {
    if [[ -n "${_CACHED_INTERPATH_ROOT+set}" ]]; then
        echo "$_CACHED_INTERPATH_ROOT"
        return 0
    fi
    if [[ -n "${INTERPATH_ROOT:-}" ]]; then
        _CACHED_INTERPATH_ROOT="$INTERPATH_ROOT"
        echo "$INTERPATH_ROOT"
        return 0
    fi
    local f
    f=$(find "${HOME}/.claude/plugins/cache" -maxdepth 5 \
        -path '*/interpath/*/scripts/interpath.sh' 2>/dev/null | sort -V | tail -1)
    if [[ -n "$f" ]]; then
        # interpath.sh is at <root>/scripts/interpath.sh, so strip two levels
        _CACHED_INTERPATH_ROOT="$(dirname "$(dirname "$f")")"
        echo "$_CACHED_INTERPATH_ROOT"
        return 0
    fi
    _CACHED_INTERPATH_ROOT=""
    echo ""
}

# Discover the interwatch companion plugin root directory.
# Checks INTERWATCH_ROOT env var first, then searches the plugin cache.
# Output: plugin root path to stdout, or empty string if not found.
_discover_interwatch_plugin() {
    if [[ -n "${_CACHED_INTERWATCH_ROOT+set}" ]]; then
        echo "$_CACHED_INTERWATCH_ROOT"
        return 0
    fi
    if [[ -n "${INTERWATCH_ROOT:-}" ]]; then
        _CACHED_INTERWATCH_ROOT="$INTERWATCH_ROOT"
        echo "$INTERWATCH_ROOT"
        return 0
    fi
    local f
    f=$(find "${HOME}/.claude/plugins/cache" -maxdepth 5 \
        -path '*/interwatch/*/scripts/interwatch.sh' 2>/dev/null | sort -V | tail -1)
    if [[ -n "$f" ]]; then
        # interwatch.sh is at <root>/scripts/interwatch.sh, so strip two levels
        _CACHED_INTERWATCH_ROOT="$(dirname "$(dirname "$f")")"
        echo "$_CACHED_INTERWATCH_ROOT"
        return 0
    fi
    _CACHED_INTERWATCH_ROOT=""
    echo ""
}

# Discover the interlock companion plugin root directory.
# Checks INTERLOCK_ROOT env var first, then searches the plugin cache.
# Output: plugin root path to stdout, or empty string if not found.
_discover_interlock_plugin() {
    if [[ -n "${_CACHED_INTERLOCK_ROOT+set}" ]]; then
        echo "$_CACHED_INTERLOCK_ROOT"
        return 0
    fi
    if [[ -n "${INTERLOCK_ROOT:-}" ]]; then
        _CACHED_INTERLOCK_ROOT="$INTERLOCK_ROOT"
        echo "$INTERLOCK_ROOT"
        return 0
    fi
    local f
    f=$(find "${HOME}/.claude/plugins/cache" -maxdepth 5 \
        -path '*/interlock/*/scripts/interlock-register.sh' 2>/dev/null | sort -V | tail -1)
    if [[ -n "$f" ]]; then
        # interlock-register.sh is at <root>/scripts/interlock-register.sh, so strip two levels
        _CACHED_INTERLOCK_ROOT="$(dirname "$(dirname "$f")")"
        echo "$_CACHED_INTERLOCK_ROOT"
        return 0
    fi
    _CACHED_INTERLOCK_ROOT=""
    echo ""
}

# ─── In-flight agent detection ───────────────────────────────────────────────
# Detects background agents from previous sessions that may still be running.
# Used by SessionStart to warn about duplicates and by Stop to write manifests.

# Derive the Claude Code project directory for the current CWD.
# Claude Code encodes CWD as path with / replaced by -.
# Output: project dir path to stdout (may not exist).
_claude_project_dir() {
    local cwd="${1:-$(pwd)}"
    local encoded="${cwd//\//-}"
    echo "${HOME}/.claude/projects/${encoded}"
}

# Extract a short task description from a subagent JSONL output file.
# Reads line 1, extracts .message.content, picks a useful summary.
# Output: task description (max 80 chars) to stdout, or "unknown" on failure.
_extract_agent_task() {
    local jsonl_path="$1"
    [[ -f "$jsonl_path" ]] || { echo "unknown"; return; }
    local content
    content=$(head -1 "$jsonl_path" 2>/dev/null | jq -r '.message.content // empty' 2>/dev/null) || { echo "unknown"; return; }
    [[ -z "$content" ]] && { echo "unknown"; return; }
    # Try "save your FULL analysis to:" pattern (flux-drive agent prompts)
    local match
    match=$(echo "$content" | grep -oP 'save your FULL analysis to:\s*\K\S+' 2>/dev/null | head -1) || true
    if [[ -n "$match" ]]; then
        echo "${match:0:80}"
        return
    fi
    # Try "Read and execute" pattern (file-indirection prompts)
    match=$(echo "$content" | grep -oP 'Read and execute\s+\K\S+' 2>/dev/null | head -1) || true
    if [[ -n "$match" ]]; then
        echo "${match:0:80}"
        return
    fi
    # Fallback: first substantive line (skip blank/whitespace)
    local line
    line=$(echo "$content" | grep -m1 '[[:alnum:]]' 2>/dev/null) || line="$content"
    echo "${line:0:80}"
}

# Detect in-flight agents from other sessions.
# Scans for recently-modified subagent JSONL files, excluding current session.
# Args: $1 = current session ID (to exclude), $2 = threshold minutes (default 10)
# Output: one line per agent "session_id agent_id age_minutes task_description"
# Returns: 0 if agents found, 1 if none.
_detect_inflight_agents() {
    local current_session="${1:-}"
    local threshold="${2:-10}"
    local project_dir
    project_dir=$(_claude_project_dir) || return 1
    [[ -d "$project_dir" ]] || return 1
    local found=0
    local jsonl_file session_dir session_id agent_id age_secs age_mins task
    # Find agent JSONL files modified within threshold, exclude compact artifacts
    while IFS= read -r jsonl_file; do
        [[ -z "$jsonl_file" ]] && continue
        # Extract session dir: .../projects/{cwd}/{session_id}/tasks/{agent_id}.jsonl
        # or sometimes .../projects/{cwd}/{session_id}/{agent_id}.jsonl
        session_dir=$(dirname "$jsonl_file")
        # Strip /tasks if present
        [[ "$(basename "$session_dir")" == "tasks" ]] && session_dir=$(dirname "$session_dir")
        session_id=$(basename "$session_dir")
        # Skip current session
        [[ "$session_id" == "$current_session" ]] && continue
        agent_id=$(basename "$jsonl_file" .jsonl)
        # Skip compact artifacts
        [[ "$agent_id" == agent-acompact-* ]] && continue
        # Calculate age
        local mtime
        mtime=$(stat -c %Y "$jsonl_file" 2>/dev/null) || continue
        age_secs=$(( $(date +%s) - mtime ))
        age_mins=$(( age_secs / 60 ))
        task=$(_extract_agent_task "$jsonl_file")
        echo "${session_id} ${agent_id} ${age_mins} ${task}"
        found=1
    done < <(find "$project_dir" -maxdepth 4 -name 'agent-*.jsonl' \
        ! -name 'agent-acompact-*' -mmin "-${threshold}" 2>/dev/null | sort)
    [[ "$found" -eq 1 ]] && return 0 || return 1
}

# Write a manifest of in-flight agents for the current session.
# Called by Stop hook so the next SessionStart can discover them.
# Args: $1 = current session ID
# Output: writes .clavain/scratch/inflight-agents.json
_write_inflight_manifest() {
    local session_id="${1:-unknown}"
    local project_dir
    project_dir=$(_claude_project_dir) || return 0
    local session_dir="${project_dir}/${session_id}"
    [[ -d "$session_dir" ]] || return 0
    # Find agent JSONLs modified in the last 60 seconds (recently active)
    local agents=()
    local jsonl_file agent_id task
    while IFS= read -r jsonl_file; do
        [[ -z "$jsonl_file" ]] && continue
        agent_id=$(basename "$jsonl_file" .jsonl)
        [[ "$agent_id" == agent-acompact-* ]] && continue
        task=$(_extract_agent_task "$jsonl_file")
        agents+=("{\"id\":\"${agent_id}\",\"task\":\"${task}\"}")
    done < <(find "$session_dir" -maxdepth 2 -name 'agent-*.jsonl' \
        ! -name 'agent-acompact-*' -mmin -1 2>/dev/null)
    # Only write manifest if there are active agents
    [[ ${#agents[@]} -eq 0 ]] && return 0
    mkdir -p ".clavain/scratch" 2>/dev/null || return 0
    local json_array
    json_array=$(printf '%s,' "${agents[@]}")
    json_array="[${json_array%,}]"
    cat > ".clavain/scratch/inflight-agents.json" <<ENDJSON
{"session_id":"${session_id}","agents":${json_array},"timestamp":$(date +%s)}
ENDJSON
}

# Escape string for JSON embedding using bash parameter substitution.
# Each ${s//old/new} is a single C-level pass — fast and reliable.
escape_for_json() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\b'/\\b}"
    s="${s//$'\f'/\\f}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\r'/\\r}"
    s="${s//$'\t'/\\t}"
    local i ch esc
    for i in {1..31}; do
        case "$i" in 8|9|10|12|13) continue ;;  # already handled as \b, \t, \n, \f, \r
        esac
        printf -v ch "\\$(printf '%03o' "$i")"
        printf -v esc '\\u%04x' "$i"
        s="${s//$ch/$esc}"
    done
    printf '%s' "$s"
}

# Check skill sizes against budget thresholds.
# Usage: skill_check_budget <skills_dir> [warn_threshold] [error_threshold]
# Output: lines of "PASS|WARN|ERROR skill-name size" to stdout
# Returns: 0 if all pass, 1 if any warn, 2 if any error
skill_check_budget() {
    local skills_dir="${1:?skills directory required}"
    local warn_at="${2:-16000}"
    local error_at="${3:-32000}"
    local max_severity=0

    for skill_md in "$skills_dir"/*/SKILL.md; do
        [[ -f "$skill_md" ]] || continue
        local skill_name
        skill_name=$(basename "$(dirname "$skill_md")")
        local size
        size=$(wc -c < "$skill_md")

        if [[ $size -gt $error_at ]]; then
            echo "ERROR $skill_name ${size} bytes (>${error_at})"
            [[ $max_severity -lt 2 ]] && max_severity=2
        elif [[ $size -gt $warn_at ]]; then
            echo "WARN $skill_name ${size} bytes (>${warn_at})"
            [[ $max_severity -lt 1 ]] && max_severity=1
        else
            echo "PASS $skill_name ${size} bytes"
        fi
    done
    return $max_severity
}
