#!/usr/bin/env bash
# shellcheck: sourced library — no set -euo pipefail (would alter caller's error policy)
# lib-fleet.sh — Query the fleet registry (config/fleet-registry.yaml).
# Source this file; do not execute directly.
#
# Each subshell source will re-initialize from the registry file.
# The guard compares the cached config path — if CLAVAIN_FLEET_REGISTRY changes,
# the library re-loads automatically.
#
# Requires: yq v4 (mikefarah/yq). Auto-discovers ~/.local/bin/yq if not in PATH.
#
# Public API:
#   fleet_list                              — all non-orphaned agent IDs
#   fleet_get <agent_id>                    — full YAML block for one agent (without ID key)
#   fleet_by_category <category>            — agents in category (review, research, workflow, synthesis)
#   fleet_by_capability <capability>        — agents providing a capability
#   fleet_by_source <plugin>                — agents from a plugin
#   fleet_by_role <role>                    — agents that can fulfill an agency-spec role
#   fleet_cost_estimate <agent_id>          — cold_start_tokens for an agent (integer to stdout)
#   fleet_cost_estimate_live <id> [model]   — live cost estimate (registry + interstat delta)
#   fleet_within_budget <max_tokens> [cat]  — agents whose cold_start_tokens <= budget
#   fleet_check_coverage <cap...>           — exit 0 if ALL capabilities covered; exit 1 + prints missing to stderr
#
# Config resolution (same order as lib-routing.sh):
#   1. CLAVAIN_FLEET_REGISTRY env var
#   2. Script-relative: ../config/fleet-registry.yaml
#   3. CLAVAIN_SOURCE_DIR/config/fleet-registry.yaml
#   4. Plugin cache: ~/.claude/plugins/cache/*/clavain/*/config/fleet-registry.yaml

# --- Internal state ---
declare -g _FLEET_LOADED_PATH=""
declare -g _FLEET_REGISTRY_PATH=""

# --- yq dependency check ---
_fleet_require_yq() {
  if ! command -v yq >/dev/null 2>&1; then
    if [[ -x "${HOME}/.local/bin/yq" ]]; then
      export PATH="${HOME}/.local/bin:${PATH}"
    else
      echo "lib-fleet: yq not found. Install from https://github.com/mikefarah/yq" >&2
      return 1
    fi
  fi
  local ver
  ver="$(yq --version 2>&1 | grep -oE 'v[0-9]+' | head -1)"
  if [[ "$ver" != "v4" ]]; then
    echo "lib-fleet: yq v4 required (found ${ver:-unknown}). Install from https://github.com/mikefarah/yq" >&2
    return 1
  fi
}

# --- Find fleet-registry.yaml ---
_fleet_find_config() {
  # 0. Explicit env var override
  if [[ -n "${CLAVAIN_FLEET_REGISTRY:-}" && -f "$CLAVAIN_FLEET_REGISTRY" ]]; then
    echo "$CLAVAIN_FLEET_REGISTRY"
    return 0
  fi

  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local source_dir="${CLAVAIN_SOURCE_DIR:-${CLAVAIN_DIR:-}}"

  # 1. Relative to this script
  if [[ -f "$script_dir/../config/fleet-registry.yaml" ]]; then
    echo "$script_dir/../config/fleet-registry.yaml"
    return 0
  fi
  # 2. CLAVAIN_SOURCE_DIR override
  if [[ -n "$source_dir" && -f "$source_dir/config/fleet-registry.yaml" ]]; then
    echo "$source_dir/config/fleet-registry.yaml"
    return 0
  fi
  # 3. CLAUDE_PLUGIN_ROOT (set by Claude Code for the active plugin)
  if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" && -f "$CLAUDE_PLUGIN_ROOT/config/fleet-registry.yaml" ]]; then
    echo "$CLAUDE_PLUGIN_ROOT/config/fleet-registry.yaml"
    return 0
  fi
  return 1
}

# --- Initialize / re-initialize if config path changed ---
_fleet_init() {
  _fleet_require_yq || return 1

  local resolved
  resolved="$(_fleet_find_config)" || {
    _FLEET_REGISTRY_PATH=""
    return 0  # No config — all functions return empty
  }

  # Path-aware guard: skip if same config already loaded
  if [[ "$_FLEET_LOADED_PATH" == "$resolved" ]]; then
    return 0
  fi

  _FLEET_REGISTRY_PATH="$resolved"
  _FLEET_LOADED_PATH="$resolved"

  # Sanity check: file should have agents
  local count
  count="$(yq '.agents | length' "$_FLEET_REGISTRY_PATH" 2>/dev/null)" || count=0
  if [[ "$count" -eq 0 ]]; then
    echo "Warning: fleet-registry.yaml exists but has no agents — possible malformed config" >&2
  fi
}

# --- Helper: check registry is loaded ---
_fleet_check() {
  if [[ -z "${_FLEET_REGISTRY_PATH:-}" ]]; then
    echo "lib-fleet: no registry loaded (fleet-registry.yaml not found)" >&2
    return 1
  fi
}

# --- Non-orphaned filter (reused across queries) ---
# yq expression fragment: select agents without orphaned_at
_FLEET_ACTIVE='.agents | to_entries[] | select(.value.orphaned_at == null)'

# ═══════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════

# List all non-orphaned agent IDs (newline-separated)
fleet_list() {
  _fleet_init || return 1
  _fleet_check || return 1
  yq "${_FLEET_ACTIVE} | .key" "$_FLEET_REGISTRY_PATH"
}

# Get full YAML block for one agent (without the agent ID key)
fleet_get() {
  local agent_id="${1:?usage: fleet_get <agent_id>}"
  _fleet_init || return 1
  _fleet_check || return 1
  local result
  result="$(id="$agent_id" yq '.agents[env(id)]' "$_FLEET_REGISTRY_PATH")"
  if [[ "$result" == "null" ]]; then
    echo "lib-fleet: agent '$agent_id' not found" >&2
    return 1
  fi
  if [[ "${FLEET_FORMAT:-}" == "json" ]]; then
    id="$agent_id" yq -o=json '.agents[env(id)]' "$_FLEET_REGISTRY_PATH"
  else
    echo "$result"
  fi
}

# Agents in a category (newline-separated IDs)
fleet_by_category() {
  local category="${1:?usage: fleet_by_category <category>}"
  _fleet_init || return 1
  _fleet_check || return 1
  cat="$category" yq "${_FLEET_ACTIVE} | select(.value.category == env(cat)) | .key" "$_FLEET_REGISTRY_PATH"
}

# Agents providing a capability (newline-separated IDs)
fleet_by_capability() {
  local capability="${1:?usage: fleet_by_capability <capability>}"
  _fleet_init || return 1
  _fleet_check || return 1
  cap="$capability" yq "${_FLEET_ACTIVE} | select(.value.capabilities[] == env(cap)) | .key" "$_FLEET_REGISTRY_PATH"
}

# Agents from a source plugin (newline-separated IDs)
fleet_by_source() {
  local plugin="${1:?usage: fleet_by_source <plugin>}"
  _fleet_init || return 1
  _fleet_check || return 1
  src="$plugin" yq "${_FLEET_ACTIVE} | select(.value.source == env(src)) | .key" "$_FLEET_REGISTRY_PATH"
}

# Agents that can fulfill an agency-spec role (newline-separated IDs)
fleet_by_role() {
  local role="${1:?usage: fleet_by_role <role>}"
  _fleet_init || return 1
  _fleet_check || return 1
  r="$role" yq "${_FLEET_ACTIVE} | select(.value.roles[] == env(r)) | .key" "$_FLEET_REGISTRY_PATH"
}

# Cold start token estimate for an agent (integer to stdout)
fleet_cost_estimate() {
  local agent_id="${1:?usage: fleet_cost_estimate <agent_id>}"
  _fleet_init || return 1
  _fleet_check || return 1
  local result
  result="$(id="$agent_id" yq '.agents[env(id)].cold_start_tokens' "$_FLEET_REGISTRY_PATH")"
  if [[ "$result" == "null" ]]; then
    echo "lib-fleet: agent '$agent_id' not found or has no cold_start_tokens" >&2
    return 1
  fi
  echo "$result"
}

# Agents whose cold_start_tokens <= max_tokens, optionally filtered by category
fleet_within_budget() {
  local max_tokens="${1:?usage: fleet_within_budget <max_tokens> [category]}"
  local category="${2:-}"
  _fleet_init || return 1
  _fleet_check || return 1
  if [[ -n "$category" ]]; then
    max="$max_tokens" cat="$category" yq \
      "${_FLEET_ACTIVE} | select((.value.cold_start_tokens | tonumber) <= (env(max) | tonumber)) | select(.value.category == env(cat)) | .key" \
      "$_FLEET_REGISTRY_PATH"
  else
    max="$max_tokens" yq \
      "${_FLEET_ACTIVE} | select((.value.cold_start_tokens | tonumber) <= (env(max) | tonumber)) | .key" \
      "$_FLEET_REGISTRY_PATH"
  fi
}

# Check if ALL listed capabilities are covered by at least one non-orphaned agent.
# Returns 0 if all covered. Returns 1 if any missing (prints missing to stderr).
fleet_check_coverage() {
  [[ $# -eq 0 ]] && { echo "usage: fleet_check_coverage <capability...>" >&2; return 1; }
  _fleet_init || return 1
  _fleet_check || return 1
  local missing=0
  for cap_arg in "$@"; do
    local count
    count="$(cap="$cap_arg" yq "[${_FLEET_ACTIVE} | select(.value.capabilities[] == env(cap))] | length" "$_FLEET_REGISTRY_PATH")"
    if [[ "$count" -eq 0 ]]; then
      echo "$cap_arg" >&2
      missing=1
    fi
  done
  return "$missing"
}

# Live cost estimate: registry actual_tokens + interstat delta overlay.
# Returns mean token estimate (integer to stdout) for agent+model pair.
# Falls back: actual_tokens → cold_start_tokens → error.
# When INTERSTAT_DB env var points to a valid SQLite DB with runs newer than
# last_enrichment, returns a weighted average of registry baseline + delta.
fleet_cost_estimate_live() {
  local agent_id="${1:?usage: fleet_cost_estimate_live <agent_id> [model]}"
  local model="${2:-}"
  _fleet_init || return 1
  _fleet_check || return 1

  # Verify agent exists
  local exists
  exists="$(id="$agent_id" yq '.agents[env(id)] != null' "$_FLEET_REGISTRY_PATH")"
  if [[ "$exists" != "true" ]]; then
    echo "lib-fleet: agent '$agent_id' not found" >&2
    return 1
  fi

  # Default to preferred model mapped to full model ID
  if [[ -z "$model" ]]; then
    model="$(id="$agent_id" yq '.agents[env(id)].models.preferred // "sonnet"' "$_FLEET_REGISTRY_PATH")"
  fi
  # Map short model names to full IDs for DB queries
  case "$model" in
    sonnet) model="claude-sonnet-4-6" ;;
    opus)   model="claude-opus-4-6" ;;
    haiku)  model="claude-haiku-4-5" ;;
  esac

  # Validate inputs before SQL interpolation (SEC-001)
  if [[ ! "$agent_id" =~ ^[a-zA-Z0-9_.:-]+$ ]]; then
    echo "lib-fleet: invalid agent_id '$agent_id'" >&2
    return 1
  fi
  if [[ -n "$model" && ! "$model" =~ ^[a-zA-Z0-9_.:-]+$ ]]; then
    echo "lib-fleet: invalid model '$model'" >&2
    return 1
  fi

  local _fleet_interstat_db="${INTERSTAT_DB:-${HOME}/.claude/interstat/metrics.db}"

  # Try interstat delta: check for runs newer than last_enrichment
  if [[ -f "$_fleet_interstat_db" ]] && command -v sqlite3 >/dev/null 2>&1; then
    # Read last_enrichment without yq (grep/sed per PRD requirement)
    local last_enrichment=""
    last_enrichment="$(grep '^last_enrichment:' "$_FLEET_REGISTRY_PATH" 2>/dev/null | sed 's/^last_enrichment: *//' | tr -d '"' | tr -d "'")" || true

    # Validate last_enrichment is an ISO timestamp (SEC-001)
    if [[ -n "$last_enrichment" && ! "$last_enrichment" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2} ]]; then
      last_enrichment=""
    fi

    if [[ -n "$last_enrichment" ]]; then
      local delta_result
      delta_result="$(sqlite3 -separator '|' "$_fleet_interstat_db" "
        SELECT CAST(ROUND(AVG(total_tokens)) AS INTEGER), COUNT(*)
        FROM agent_runs
        WHERE agent_name='${agent_id}' AND model='${model}'
          AND total_tokens IS NOT NULL
          AND timestamp > '${last_enrichment}'
      " 2>/dev/null)" || delta_result=""

      if [[ -n "$delta_result" && "$delta_result" != "|0" ]]; then
        local delta_mean delta_count
        delta_mean="${delta_result%%|*}"
        delta_count="${delta_result##*|}"

        if [[ "$delta_count" -gt 0 && -n "$delta_mean" ]]; then
          # Get registry baseline stats
          local reg_mean reg_runs
          reg_mean="$(id="$agent_id" m="$model" yq '.agents[env(id)].models.actual_tokens[env(m)].mean // 0' "$_FLEET_REGISTRY_PATH")" || reg_mean=0
          reg_runs="$(id="$agent_id" m="$model" yq '.agents[env(id)].models.actual_tokens[env(m)].runs // 0' "$_FLEET_REGISTRY_PATH")" || reg_runs=0

          if [[ "$reg_runs" -gt 0 ]]; then
            # Weighted average: combine registry baseline + delta (any delta count useful here)
            local total_runs=$((reg_runs + delta_count))
            local combined=$(( (reg_mean * reg_runs + delta_mean * delta_count) / total_runs ))
            echo "$combined"
            return 0
          elif [[ "$delta_count" -ge 3 ]]; then
            # Delta-only: require >= 3 runs for reliability (CORRECTNESS-002)
            echo "$delta_mean"
            return 0
          fi
        fi
      fi
    fi
  fi

  # Fallback: registry actual_tokens (static baseline)
  local actual
  actual="$(id="$agent_id" m="$model" yq '.agents[env(id)].models.actual_tokens[env(m)].mean // ""' "$_FLEET_REGISTRY_PATH")" || actual=""
  if [[ -n "$actual" && "$actual" != "null" && "$actual" != "" ]]; then
    echo "$actual"
    return 0
  fi

  # Fallback: cold_start_tokens
  local cold
  cold="$(id="$agent_id" yq '.agents[env(id)].cold_start_tokens // ""' "$_FLEET_REGISTRY_PATH")" || cold=""
  if [[ -n "$cold" && "$cold" != "null" ]]; then
    echo "$cold"
    return 0
  fi

  echo "lib-fleet: no cost data for '$agent_id' (model=$model)" >&2
  return 1
}

# ─── Compound Autonomy Guard (rsj.1.8) ──────────────────────────────────────

# Check compound autonomy score for a Mycroft dispatch.
# Score = mycroft_tier × agent_capability_level.
# Returns: 0 (auto/pass), 1 (advisory), 2 (require approval), 3 (blocked)
# Prints verdict to stdout: "auto|advisory|approval|blocked <score> <reason>"
#
# Args: $1 = mycroft_tier (0-3), $2 = agent_id
fleet_compound_autonomy_check() {
  local mycroft_tier="${1:?usage: fleet_compound_autonomy_check <mycroft_tier> <agent_id>}"
  local agent_id="${2:?usage: fleet_compound_autonomy_check <mycroft_tier> <agent_id>}"
  _fleet_init || return 1

  # Get agent capability level (default from policy if not set)
  local cap_level
  cap_level="$(id="$agent_id" yq '.agents[env(id)].capability_level // ""' "$_FLEET_REGISTRY_PATH" 2>/dev/null)" || cap_level=""
  if [[ -z "$cap_level" || "$cap_level" == "null" ]]; then
    # Read default from policy
    local policy_file
    policy_file="$(dirname "$_FLEET_REGISTRY_PATH")/default-policy.yaml"
    if [[ -f "$policy_file" ]]; then
      cap_level="$(yq '.compound_autonomy.default_capability_level // 2' "$policy_file" 2>/dev/null)" || cap_level=2
    else
      cap_level=2
    fi
  fi

  # Compute compound score
  local score=$(( mycroft_tier * cap_level ))

  # Read thresholds from policy
  local policy_file
  policy_file="$(dirname "$_FLEET_REGISTRY_PATH")/default-policy.yaml"
  local t_auto=2 t_advisory=4 t_approval=6 t_blocked=9
  if [[ -f "$policy_file" ]]; then
    t_auto="$(yq '.compound_autonomy.thresholds.auto // 2' "$policy_file" 2>/dev/null)" || t_auto=2
    t_advisory="$(yq '.compound_autonomy.thresholds.advisory // 4' "$policy_file" 2>/dev/null)" || t_advisory=4
    t_approval="$(yq '.compound_autonomy.thresholds.approval // 6' "$policy_file" 2>/dev/null)" || t_approval=6
    t_blocked="$(yq '.compound_autonomy.thresholds.blocked // 9' "$policy_file" 2>/dev/null)" || t_blocked=9
  fi

  # Classify
  if [[ "$score" -ge "$t_blocked" ]]; then
    echo "blocked $score T${mycroft_tier}×L${cap_level} — requires explicit user opt-in"
    return 3
  elif [[ "$score" -ge "$t_approval" ]]; then
    echo "approval $score T${mycroft_tier}×L${cap_level} — requires human approval"
    return 2
  elif [[ "$score" -gt "$t_auto" ]]; then
    echo "advisory $score T${mycroft_tier}×L${cap_level} — proceeding with warning"
    return 1
  else
    echo "auto $score T${mycroft_tier}×L${cap_level} — within safe bounds"
    return 0
  fi
}
