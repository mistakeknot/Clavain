#!/usr/bin/env bash
# SessionStart hook for Clavain plugin

set -euo pipefail

# Read hook input from stdin (must happen before anything else consumes it)
HOOK_INPUT=$(cat)

# Detect trigger type (startup, resume, clear, compact)
_hook_source=$(echo "$HOOK_INPUT" | jq -r '.source // "startup"' 2>/dev/null) || _hook_source="startup"

# Determine plugin root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# shellcheck source=hooks/lib.sh
source "${SCRIPT_DIR}/lib.sh"

# Persist session_id as CLAUDE_SESSION_ID so downstream tools (interphase's
# _gate_update_statusline) can write bead state for the statusline to read.
if [[ -n "${CLAUDE_ENV_FILE:-}" ]]; then
    _session_id=$(echo "$HOOK_INPUT" | jq -r '.session_id // empty' 2>/dev/null) || _session_id=""
    if [[ -n "$_session_id" ]]; then
        echo "export CLAUDE_SESSION_ID=${_session_id}" >> "$CLAUDE_ENV_FILE"
    fi
fi

# Clean up stale plugin cache versions.
# Strategy: replace old DIRECTORIES with symlinks to current version (so any
# still-running session's Stop hooks resolve), then remove stale SYMLINKS that
# already point to current (left over from a previous cleanup cycle).
CURRENT_VERSION_DIR="$(basename "$PLUGIN_ROOT")"
CACHE_PARENT="$(dirname "$PLUGIN_ROOT")"
if [[ -d "$CACHE_PARENT" ]] && [[ "$CACHE_PARENT" == *"/plugins/cache/"* ]]; then
    for old_entry in "$CACHE_PARENT"/*/; do
        old_name="$(basename "$old_entry")"
        [[ "$old_name" == "$CURRENT_VERSION_DIR" ]] && continue
        old_path="${old_entry%/}"
        if [[ -L "$old_path" ]]; then
            # Symlink from a previous cycle — safe to remove
            rm -f "$old_path" 2>/dev/null || true
        elif [[ -d "$old_path" ]]; then
            # Real directory — replace with symlink so late Stop hooks still work
            rm -rf "$old_path" 2>/dev/null || true
            ln -sf "$CURRENT_VERSION_DIR" "$old_path" 2>/dev/null || true
        fi
    done
    # Plugin versions changed — invalidate companion discovery cache
    _invalidate_companion_cache
fi

# Read using-clavain content (fail gracefully — don't mix stderr into injected context)
using_clavain_content=$(cat "${PLUGIN_ROOT}/skills/using-clavain/SKILL.md" 2>/dev/null) || using_clavain_content="Could not load using-clavain skill. Run /clavain:using-clavain manually."

using_clavain_escaped=$(escape_for_json "$using_clavain_content")

# Detect companion plugins — store as env var for on-demand access, inject only
# critical awareness context (interserve mode, active agents) into additionalContext.
companion_list=""
companion_context=""

# Beads
if [[ -d "${PLUGIN_ROOT}/../../.beads" ]] || [[ -d ".beads" ]]; then
    companion_list="${companion_list}beads,"
    # Surface beads health warnings (bd doctor --json is local-only, typically <100ms)
    if command -v bd &>/dev/null; then
        beads_issues=$( (bd doctor --json 2>/dev/null || true) | jq '[.checks[]? | select(.status == "warning" or .status == "error")] | length' 2>/dev/null) || beads_issues="0"
        if [[ "$beads_issues" -gt 0 ]]; then
            companion_context="${companion_context}\\n- beads doctor: ${beads_issues} issue(s) — run \`bd doctor --fix\`"
        fi
    fi
fi

# Oracle
if command -v oracle &>/dev/null && pgrep -f "Xvfb :99" &>/dev/null; then
    companion_list="${companion_list}oracle,"
fi

# interflux
interflux_root=$(_discover_interflux_plugin)
[[ -n "$interflux_root" ]] && companion_list="${companion_list}interflux,"

# interpath
interpath_root=$(_discover_interpath_plugin)
[[ -n "$interpath_root" ]] && companion_list="${companion_list}interpath,"

# interwatch
interwatch_root=$(_discover_interwatch_plugin)
[[ -n "$interwatch_root" ]] && companion_list="${companion_list}interwatch,"

# interlock + Intermute auto-join
interlock_root=$(_discover_interlock_plugin)
if [[ -n "$interlock_root" ]]; then
    companion_list="${companion_list}interlock,"

    # Auto-join Intermute if reachable and in a git repo
    _intermute_url="${INTERMUTE_URL:-http://127.0.0.1:7338}"
    if git rev-parse --is-inside-work-tree &>/dev/null; then
        if curl -sf --connect-timeout 1 --max-time 2 "${_intermute_url}/health" >/dev/null 2>&1; then
            _join_flag="${HOME}/.config/clavain/intermute-joined"
            mkdir -p "$(dirname "$_join_flag")" 2>/dev/null || true
            touch "$_join_flag" 2>/dev/null || true

            # Active agents — inject only if others are online (coordination-critical)
            # Cache responses for sprint_check_coordination to avoid redundant fetches (iv-kcf6)
            _intermute_project=$(basename "$(git rev-parse --show-toplevel 2>/dev/null)")
            _agents_json=$(curl -sf --connect-timeout 1 --max-time 2 "${_intermute_url}/api/agents?project=${_intermute_project}" 2>/dev/null) || _agents_json=""
            _INTERMUTE_AGENTS_CACHE="$_agents_json"
            if [[ -n "$_agents_json" ]]; then
                _agent_count=$(echo "$_agents_json" | jq '.agents | length' 2>/dev/null) || _agent_count="0"
                if [[ "$_agent_count" -gt 0 ]]; then
                    _agent_names=$(echo "$_agents_json" | jq -r '[.agents[].name] | join(", ")' 2>/dev/null) || _agent_names=""
                    _agent_names=$(escape_for_json "$_agent_names")
                    companion_context="${companion_context}\\n- Intermute: ${_agent_count} agent(s) online (${_agent_names})"

                    _reservations_json=$(curl -sf --connect-timeout 1 --max-time 2 "${_intermute_url}/api/reservations?project=${_intermute_project}" 2>/dev/null) || _reservations_json=""
                    _INTERMUTE_RESERVATIONS_CACHE="$_reservations_json"
                    if [[ -n "$_reservations_json" ]]; then
                        _res_count=$(echo "$_reservations_json" | jq '[.reservations[]? | select(.is_active == true)] | length' 2>/dev/null) || _res_count="0"
                        if [[ "$_res_count" -gt 0 ]]; then
                            _res_summary=$(echo "$_reservations_json" | jq -r '[.reservations[]? | select(.is_active == true) | "\(.agent_id[:8])→\(.path_pattern)"] | join(", ")' 2>/dev/null) || _res_summary=""
                            companion_context="${companion_context}\\n  - Active reservations (${_res_count}): ${_res_summary}"
                        fi
                    fi
                fi
            fi
            _INTERMUTE_HEALTH_OK=1
        fi
    fi
fi

# Interserve — always inject when active (changes agent behavior)
INTERSERVE_FLAG="${CLAUDE_PROJECT_DIR:-.}/.claude/clodex-toggle.flag"
if [[ -f "$INTERSERVE_FLAG" ]]; then
    companion_list="${companion_list}interserve,"
    companion_context="${companion_context}\\n- **INTERSERVE MODE: ON** — Route source code changes through Codex (preserves Claude token budget for orchestration).\\n  1. Plan: Read/Grep/Glob freely\\n  2. Prompt: Write task to /tmp/, dispatch via /interserve\\n  3. Verify: read output, run tests, review diffs\\n  4. Git ops (add/commit/push) are yours — do directly\\n  Bash: read-only for source files (no redirects, sed -i, tee). Git + test/build OK.\\n  Direct-edit OK: .md/.json/.yaml/.yml/.toml/.txt/.csv/.xml/.html/.css/.svg/.lock/.cfg/.ini/.conf/.env, /tmp/*\\n  Everything else (code files): dispatch via /interserve."
fi

# Drift summary injection (iv-mqm4) — surface stale docs at session start
# Reads .interwatch/drift.json and injects Medium+ confidence items
_drift_file=".interwatch/drift.json"
if [[ -n "$interwatch_root" && -f "$_drift_file" ]]; then
    _drift_json=$(cat "$_drift_file" 2>/dev/null) || _drift_json=""
    if [[ -n "$_drift_json" ]]; then
        # Extract Medium/High/Certain watchables, sorted by score desc, capped at 3
        _drift_items=$(echo "$_drift_json" | jq -r '
            [.watchables | to_entries[]
             | select(.value.confidence == "Medium" or .value.confidence == "High" or .value.confidence == "Certain")
             | {name: .key, score: .value.score, confidence: .value.confidence, path: .value.path}]
            | sort_by(-.score)
            | .[:3]
            | map("\(.name) (\(.path), \(.confidence), score \(.score))")
            | join(", ")
        ' 2>/dev/null) || _drift_items=""
        if [[ -n "$_drift_items" ]]; then
            _drift_items=$(escape_for_json "$_drift_items")
            companion_context="${companion_context}\\n- Drift detected: ${_drift_items}. Run /interwatch:watch to refresh."
        fi
    fi
fi

# Persist companion list as env var for on-demand access by skills
companion_list="${companion_list%,}"  # trim trailing comma
if [[ -n "${CLAUDE_ENV_FILE:-}" && -n "$companion_list" ]]; then
    echo "export CLAVAIN_COMPANIONS=${companion_list}" >> "$CLAUDE_ENV_FILE"
fi

# Only inject companion context if there's something actionable (not just "detected X")
if [[ -n "$companion_context" ]]; then
    companion_context="\\n\\nActive companion alerts:${companion_context}"
fi

# Core conventions reminder (full version in config/CLAUDE.md)
conventions="\\n\\n**Clavain conventions:** Read before Edit. No heredocs/loops in Bash. Trunk-based git (commit to main). Record learnings to memory immediately."

# Setup hint for first-time users
setup_hint="\\n\\n**First time?** Run \`/clavain:setup\` to install companion plugins and configure hooks."

# Check upstream staleness (local file check only — no network calls)
upstream_warning=""
VERSIONS_FILE="${PLUGIN_ROOT}/docs/upstream-versions.json"
if [[ -f "$VERSIONS_FILE" ]]; then
    # Check if the file is older than 7 days (portable: GNU stat -c, BSD stat -f)
    file_mtime=$(stat -c %Y "$VERSIONS_FILE" 2>/dev/null || stat -f %m "$VERSIONS_FILE" 2>/dev/null || echo 0)
    file_age_days=$(( ($(date +%s) - file_mtime) / 86400 ))
    if [[ $file_age_days -gt 7 ]]; then
        upstream_warning="\\n\\n**Upstream sync stale** (${file_age_days} days since last check). Run \`/clavain:upstream-sync\` to check for updates from beads, oracle, and other upstream tools."
    fi
else
    upstream_warning="\\n\\n**No upstream baseline found.** Run \`bash scripts/upstream-check.sh --update\` in the Clavain repo to establish baseline."
fi

# Sprint awareness scan (lightweight)
# shellcheck source=hooks/sprint-scan.sh
source "${SCRIPT_DIR}/sprint-scan.sh"
sprint_context=$(sprint_brief_scan 2>/dev/null) || sprint_context=""
# sprint_brief_scan outputs real newlines; escape for JSON embedding
if [[ -n "$sprint_context" ]]; then
    sprint_context=$(escape_for_json "$sprint_context")
fi

# Work discovery brief scan (interphase companion — beads-based work state)
# Source the discovery shim which delegates to interphase if available.
# If interphase is not installed, discovery_brief_scan won't be defined → silent skip.
discovery_context=""
# shellcheck source=hooks/lib-discovery.sh
source "${SCRIPT_DIR}/lib-discovery.sh" 2>/dev/null || true
if type discovery_brief_scan &>/dev/null; then
    discovery_context=$(discovery_brief_scan 2>/dev/null) || discovery_context=""
    if [[ -n "$discovery_context" ]]; then
        discovery_context="\\n• $(escape_for_json "$discovery_context")"
    fi
fi

# Sprint resume hint is already included in sprint_brief_scan output (sprint-scan.sh:346-365).
# Removed duplicate sprint_find_active call here (iv-zlht).
# shellcheck disable=SC2034
sprint_resume_hint=""

# Capture session-start snapshots for handoff diff detection (iv-fd7l0).
# Only on real startup — compact/resume sessions inherit the original snapshots.
if [[ "$_hook_source" == "startup" ]]; then
    # shellcheck source=hooks/lib-intercore.sh
    source "${SCRIPT_DIR}/lib-intercore.sh" 2>/dev/null || true
    _snap_session=$(echo "$HOOK_INPUT" | jq -r '.session_id // empty' 2>/dev/null) || _snap_session=""
    if [[ -n "$_snap_session" ]] && intercore_available 2>/dev/null; then
        # Git status snapshot (tracked files only, sorted for diffing)
        if command -v git &>/dev/null && git rev-parse --is-inside-work-tree &>/dev/null 2>&1; then
            _git_snap=$(git status --porcelain 2>/dev/null | grep -v '^\?\?' | sort || true)
            intercore_state_set "git_snapshot" "$_snap_session" "$_git_snap" 2>/dev/null || true
        fi
        # In-progress beads snapshot
        if command -v bd &>/dev/null; then
            _bead_snap=$(bd list --status=in_progress 2>/dev/null | grep '●' | sort || true)
            intercore_state_set "beads_snapshot" "$_snap_session" "$_bead_snap" 2>/dev/null || true
        fi
    fi
fi

# In-flight agent detection (from previous sessions)
# Skip on compact — agents were already delivered this session; re-detecting
# them produces stale notifications that flood the context.
inflight_context=""
if [[ "$_hook_source" == "compact" ]]; then
    inflight_context="\\n\\n**Context was compacted.** Task-notifications from background agents received after this point may reference work already completed or reviewed. Check agent output freshness before re-actioning."
else
    _current_session=$(echo "$HOOK_INPUT" | jq -r '.session_id // empty' 2>/dev/null) || _current_session=""

    # Source 1: Manifest file (written by Stop hook)
    if [[ -f ".clavain/scratch/inflight-agents.json" ]]; then
        _manifest_agents=""
        _manifest_session=$(jq -r '.session_id // "unknown"' ".clavain/scratch/inflight-agents.json" 2>/dev/null) || _manifest_session="unknown"
        while IFS= read -r _agent_line; do
            [[ -z "$_agent_line" ]] && continue
            _agent_id=$(echo "$_agent_line" | jq -r '.id // empty' 2>/dev/null) || continue
            _agent_task=$(echo "$_agent_line" | jq -r '.task // "unknown"' 2>/dev/null) || _agent_task="unknown"
            # Check if agent is still running by looking at JSONL mtime (modified in last 2 min = likely running)
            _project_dir=$(_claude_project_dir 2>/dev/null) || _project_dir=""
            _status="finished"
            if [[ -n "$_project_dir" ]]; then
                _agent_jsonl=$(find "$_project_dir/${_manifest_session}" -maxdepth 2 -name "${_agent_id}.jsonl" -mmin -2 2>/dev/null | head -1 || true)
                [[ -n "$_agent_jsonl" ]] && _status="still running"
            fi
            _manifest_agents="${_manifest_agents}\\n  - [${_manifest_session:0:8}] ${_agent_task} (${_status})"
        done < <(jq -c '.agents[]' ".clavain/scratch/inflight-agents.json" 2>/dev/null)
        if [[ -n "$_manifest_agents" ]]; then
            inflight_context="\\n\\n**In-flight agents from previous session:**${_manifest_agents}\\nCheck output before launching similar work."
        fi
        # Consume manifest
        rm -f ".clavain/scratch/inflight-agents.json" 2>/dev/null || true
    fi

    # Source 2: Live scan (catches crash/kill without Stop hook)
    if [[ -n "$_current_session" ]]; then
        _live_agents=""
        while IFS=' ' read -r _sid _aid _age _task; do
            [[ -z "$_sid" ]] && continue
            # Skip agents already reported from manifest
            [[ "$inflight_context" == *"$_task"* ]] && continue
            _live_agents="${_live_agents}\\n  - [${_sid:0:8}] ${_task} (${_age}m ago)"
        done < <(_detect_inflight_agents "$_current_session" 10 2>/dev/null)
        if [[ -n "$_live_agents" ]]; then
            if [[ -n "$inflight_context" ]]; then
                inflight_context="${inflight_context}${_live_agents}"
            else
                inflight_context="\\n\\n**In-flight agents detected (from recent sessions):**${_live_agents}\\nCheck output before launching similar work."
            fi
        fi
    fi
fi

# Assemble additionalContext with budget cap.
# Priority-based shedding: drop lowest-priority sections whole (not byte-level truncation)
# to avoid breaking mid-escape-sequence in JSON output.
_context_preamble="You have Clavain.\n\n**Below is the full content of your 'clavain:using-clavain' skill - your introduction to using skills. For all other skills, use the 'Skill' tool:**\n\n"
_full_context="${_context_preamble}${using_clavain_escaped}${companion_context}${conventions}${setup_hint}${upstream_warning}${sprint_context}${discovery_context}${inflight_context}"
ADDITIONAL_CONTEXT_CAP=10000

# Shed sections in reverse priority order (lowest value dropped first).
# Shedding order: inflight → discovery → sprint → upstream → setup
if [[ ${#_full_context} -gt $ADDITIONAL_CONTEXT_CAP ]]; then
    inflight_context=""
    _full_context="${_context_preamble}${using_clavain_escaped}${companion_context}${conventions}${setup_hint}${upstream_warning}${sprint_context}${discovery_context}"
fi
if [[ ${#_full_context} -gt $ADDITIONAL_CONTEXT_CAP ]]; then
    discovery_context=""
    _full_context="${_context_preamble}${using_clavain_escaped}${companion_context}${conventions}${setup_hint}${upstream_warning}${sprint_context}"
fi
if [[ ${#_full_context} -gt $ADDITIONAL_CONTEXT_CAP ]]; then
    sprint_context=""
    _full_context="${_context_preamble}${using_clavain_escaped}${companion_context}${conventions}${setup_hint}${upstream_warning}"
fi
if [[ ${#_full_context} -gt $ADDITIONAL_CONTEXT_CAP ]]; then
    upstream_warning=""
    setup_hint=""
    _full_context="${_context_preamble}${using_clavain_escaped}${companion_context}${conventions}"
fi

# Output context injection as JSON
cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "${_full_context}"
  }
}
EOF

exit 0
