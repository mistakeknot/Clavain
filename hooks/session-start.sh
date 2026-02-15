#!/usr/bin/env bash
# SessionStart hook for Clavain plugin

set -euo pipefail

# Read hook input from stdin (must happen before anything else consumes it)
HOOK_INPUT=$(cat)

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
fi

# Read using-clavain content (fail gracefully — don't mix stderr into injected context)
using_clavain_content=$(cat "${PLUGIN_ROOT}/skills/using-clavain/SKILL.md" 2>/dev/null) || using_clavain_content="Could not load using-clavain skill. Run /clavain:using-clavain manually."

using_clavain_escaped=$(escape_for_json "$using_clavain_content")

# Detect companion plugins and build integration context
companions=""

# Beads — detect if project uses beads
if [[ -d "${PLUGIN_ROOT}/../../.beads" ]] || [[ -d ".beads" ]]; then
    companions="${companions}\\n- **beads**: .beads/ detected — use \`bd\` for task tracking (not TaskCreate)"
    # Surface beads health warnings (bd doctor --json is local-only, typically <100ms)
    if command -v bd &>/dev/null; then
        beads_issues=$( (bd doctor --json 2>/dev/null || true) | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    print(sum(1 for c in d.get('checks',[]) if c.get('status') in ('warning','error')))
except: print(0)" 2>/dev/null) || beads_issues="0"
        if [[ "$beads_issues" -gt 0 ]]; then
            companions="${companions}\\n  - beads doctor found ${beads_issues} issue(s) — run \`bd doctor --fix\` to repair"
        fi
    fi
fi

# Oracle — check if available for cross-AI review
if command -v oracle &>/dev/null && pgrep -f "Xvfb :99" &>/dev/null; then
    companions="${companions}\\n- **oracle**: available for cross-AI review (GPT-5.2 Pro)"
fi

# interflux — multi-agent review engine companion
interflux_root=$(_discover_interflux_plugin)
if [[ -n "$interflux_root" ]]; then
    companions="${companions}\\n- **interflux**: review engine available (fd-* agents, domain detection, qmd)"
fi

# interpath — product artifact generation companion
interpath_root=$(_discover_interpath_plugin)
if [[ -n "$interpath_root" ]]; then
    companions="${companions}\\n- **interpath**: product artifact generation (roadmaps, PRDs, vision docs)"
fi

# interwatch — doc freshness monitoring companion
interwatch_root=$(_discover_interwatch_plugin)
if [[ -n "$interwatch_root" ]]; then
    companions="${companions}\\n- **interwatch**: doc freshness monitoring"
fi

# interlock — multi-agent coordination companion
interlock_root=$(_discover_interlock_plugin)
if [[ -n "$interlock_root" ]]; then
    companions="${companions}\\n- **interlock**: multi-agent coordination (file reservations, conflict detection)"

    # Auto-join Intermute if reachable and in a git repo
    # This replaces the need for manual /interlock:join
    _intermute_url="${INTERMUTE_URL:-http://127.0.0.1:7338}"
    if git rev-parse --is-inside-work-tree &>/dev/null; then
        if curl -sf --connect-timeout 1 --max-time 2 "${_intermute_url}/health" >/dev/null 2>&1; then
            # Ensure join flag exists (interlock hooks gate on this)
            _join_flag="${HOME}/.config/clavain/intermute-joined"
            mkdir -p "$(dirname "$_join_flag")" 2>/dev/null || true
            touch "$_join_flag" 2>/dev/null || true

            # Query active agents for awareness context
            _agents_json=$(curl -sf --max-time 2 "${_intermute_url}/api/agents?project=$(basename "$(git rev-parse --show-toplevel 2>/dev/null)")" 2>/dev/null) || _agents_json=""
            if [[ -n "$_agents_json" ]]; then
                _agent_count=$(echo "$_agents_json" | jq '.agents | length' 2>/dev/null) || _agent_count="0"
                if [[ "$_agent_count" -gt 0 ]]; then
                    _agent_names=$(echo "$_agents_json" | jq -r '[.agents[].name] | join(", ")' 2>/dev/null) || _agent_names=""
                    companions="${companions}\\n  - Intermute: ${_agent_count} agent(s) online (${_agent_names})"

                    # Show active reservations summary
                    _reservations_json=$(curl -sf --max-time 2 "${_intermute_url}/api/reservations?project=$(basename "$(git rev-parse --show-toplevel 2>/dev/null)")" 2>/dev/null) || _reservations_json=""
                    if [[ -n "$_reservations_json" ]]; then
                        _res_count=$(echo "$_reservations_json" | jq '[.reservations[]? | select(.is_active == true)] | length' 2>/dev/null) || _res_count="0"
                        if [[ "$_res_count" -gt 0 ]]; then
                            _res_summary=$(echo "$_reservations_json" | jq -r '[.reservations[]? | select(.is_active == true) | "\(.agent_id[:8])→\(.path_pattern)"] | join(", ")' 2>/dev/null) || _res_summary=""
                            companions="${companions}\\n  - Active reservations (${_res_count}): ${_res_summary}"
                        fi
                    fi
                fi
            fi
        fi
    fi
fi

# Clodex — detect persistent toggle state
CLODEX_FLAG="${CLAUDE_PROJECT_DIR:-.}/.claude/clodex-toggle.flag"
if [[ -f "$CLODEX_FLAG" ]]; then
    companions="${companions}\\n- **CLODEX MODE: ON** — Route source code changes through Codex (preserves Claude token budget for orchestration).\\n  1. Plan: Read/Grep/Glob freely\\n  2. Prompt: Write task to /tmp/, dispatch via /clodex\\n  3. Verify: read output, run tests, review diffs\\n  4. Git ops (add/commit/push) are yours — do directly\\n  Bash: read-only for source files (no redirects, sed -i, tee). Git + test/build OK.\\n  Direct-edit OK: .md/.json/.yaml/.yml/.toml/.txt/.csv/.xml/.html/.css/.svg/.lock/.cfg/.ini/.conf/.env, /tmp/*\\n  Everything else (code files): dispatch via /clodex. If Codex unavailable: /clodex-toggle off, or use /subagent-driven-development."
fi

companion_context=""
if [[ -n "$companions" ]]; then
    companion_context="\\n\\nDetected companions (FYI):${companions}"
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
# sprint_brief_scan outputs \\n literals; escape any remaining JSON-unsafe chars
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

# Sprint bead detection (active sprint resume hint)
sprint_resume_hint=""
# shellcheck source=hooks/lib-sprint.sh
source "${SCRIPT_DIR}/lib-sprint.sh" 2>/dev/null || true
if type sprint_find_active &>/dev/null; then
    export SPRINT_LIB_PROJECT_DIR="."
    active_sprints=$(sprint_find_active 2>/dev/null) || active_sprints="[]"
    sprint_count=$(echo "$active_sprints" | jq 'length' 2>/dev/null) || sprint_count=0
    if [[ "$sprint_count" -gt 0 ]]; then
        top_sprint=$(echo "$active_sprints" | jq '.[0]')
        top_id=$(echo "$top_sprint" | jq -r '.id')
        top_title=$(echo "$top_sprint" | jq -r '.title')
        top_phase=$(echo "$top_sprint" | jq -r '.phase')
        next_step=$(sprint_next_step "$top_phase" 2>/dev/null) || next_step="unknown"
        sprint_resume_hint="\\n• Active sprint: ${top_id} — ${top_title} (phase: ${top_phase}, next: ${next_step}). Resume with /sprint or /sprint ${top_id}"
        sprint_resume_hint=$(escape_for_json "$sprint_resume_hint")
    fi
fi

# Previous session handoff context (.clavain/scratch/handoff.md)
# session-handoff creates scratch/; we only read here (don't create dirs).
handoff_context=""
if [[ -f ".clavain/scratch/handoff.md" ]]; then
    # Cap at 40 lines to prevent context bloat
    handoff_content=$(head -40 ".clavain/scratch/handoff.md" 2>/dev/null) || handoff_content=""
    if [[ -n "$handoff_content" ]]; then
        handoff_context="\\n\\n**Previous session context:**\\n$(escape_for_json "$handoff_content")"
    fi
fi

# In-flight agent detection (from previous sessions)
# Two sources: (1) manifest from Stop hook, (2) live filesystem scan
inflight_context=""
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

# Output context injection as JSON
cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "You have Clavain.\n\n**Below is the full content of your 'clavain:using-clavain' skill - your introduction to using skills. For all other skills, use the 'Skill' tool:**\n\n${using_clavain_escaped}${companion_context}${conventions}${setup_hint}${upstream_warning}${sprint_context}${discovery_context}${sprint_resume_hint}${handoff_context}${inflight_context}"
  }
}
EOF

exit 0
