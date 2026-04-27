#!/usr/bin/env bash
# shellcheck: sourced library — no set -euo pipefail (would alter caller's error policy)
# lib-routing.sh — Read config/routing.yaml and resolve model tiers.
# Source this file; do not execute directly.
#
# Public API (B1 — static routing):
#   routing_resolve_model --phase <phase> [--category <cat>] [--agent <name>]
#   routing_resolve_agents --phase <phase> --agents "a,b,c" [--category <cat>]
#   routing_resolve_dispatch_tier <tier-name>
#   routing_list_mappings
#
# Public API (B2 — complexity-aware routing):
#   routing_classify_complexity --prompt-tokens <n> [--file-count <n>] [--reasoning-depth <n>]
#   routing_resolve_model_complex --complexity <tier> [--phase ...] [--category ...] [--agent ...]
#   routing_resolve_dispatch_tier_complex --complexity <tier> <tier-name>
#
# Track B5 (local model routing) is integrated into routing_resolve_model_complex.
# In shadow mode: logs [B5-shadow] to stderr. In enforce: returns local model.
# Config: local_models section of routing.yaml. Env: INTERFERE_ROUTING_MODE.

# Guard: only load once per shell process
[[ -n "${_ROUTING_LOADED:-}" ]] && return 0

# --- Global cache (populated by _routing_load_cache) ---
declare -g _ROUTING_SA_DEFAULT_MODEL=""
declare -gA _ROUTING_SA_DEFAULTS=()       # [category]=model
declare -gA _ROUTING_SA_PHASE_MODEL=()    # [phase]=model
declare -gA _ROUTING_SA_PHASE_CAT=()      # [phase:category]=model
declare -gA _ROUTING_SA_OVERRIDE=()       # [agent]=model
declare -gA _ROUTING_DISPATCH_TIER=()     # [tier]=model
declare -gA _ROUTING_DISPATCH_DESC=()     # [tier]=description
declare -gA _ROUTING_DISPATCH_FALLBACK=() # [tier]=fallback_tier
declare -g _ROUTING_CONFIG_PATH=""
declare -g _ROUTING_CACHE_POPULATED=""

# --- B2: Complexity cache ---
declare -g _ROUTING_CX_MODE=""                  # off | shadow | enforce
declare -gA _ROUTING_CX_PROMPT_TOKENS=()       # [C1..C5]=threshold
declare -gA _ROUTING_CX_FILE_COUNT=()           # [C1..C5]=threshold
declare -gA _ROUTING_CX_REASONING_DEPTH=()      # [C1..C5]=threshold
declare -gA _ROUTING_CX_DESC=()                 # [C1..C5]=description
declare -gA _ROUTING_CX_SUBAGENT_MODEL=()       # [C1..C5]=model|inherit
declare -gA _ROUTING_CX_DISPATCH_TIER=()        # [C1..C5]=tier|inherit

# --- B3: Calibration cache ---
declare -g _ROUTING_CAL_MODE=""                   # shadow | enforce (from routing.yaml)

# --- B5: Local model routing cache ---
declare -g _ROUTING_B5_MODE=""                     # off | shadow | enforce
declare -g _ROUTING_B5_ENDPOINT=""                 # e.g., http://localhost:8421
declare -gA _ROUTING_B5_TIER_MAP=()               # [local:model]=tier (1/2/3)
declare -gA _ROUTING_B5_CX_MODEL=()               # [C1..C5]=local:model
declare -gA _ROUTING_B5_INELIGIBLE=()             # [agent]=1
declare -g _ROUTING_B5_HEALTH_CACHE=""             # yes | no
declare -g _ROUTING_B5_HEALTH_TIME=0               # epoch seconds of last check

# --- Safety floor cache (from agent-roles.yaml) ---
declare -gA _ROUTING_SF_AGENT_MIN=()             # [agent_name]=min_model
declare -gA _ROUTING_SF_AGENT_DOMAIN_CX=()       # [agent_name]=low|medium|high
declare -gA _ROUTING_SF_AGENT_MAX_MODEL=()       # [agent_name]=haiku|sonnet|opus (empty if no ceiling)

# --- Model tier ordering for safety floor comparison ---
# Returns numeric tier: haiku=1, sonnet=2, opus=3. Unknown=0.
_routing_model_tier() {
  case "${1:-}" in
    haiku)                              echo 1 ;;
    local:qwen3-8b)                     echo 1 ;;  # Track B5: legacy haiku-equivalent
    local:qwen3.5-9b-4bit)              echo 1 ;;  # Track B5: draft model
    sonnet)                             echo 2 ;;
    local:qwen3-30b)                    echo 2 ;;  # Track B5: legacy sonnet-equivalent
    local:qwen2.5-72b)                  echo 2 ;;  # Track B5: legacy sonnet-equivalent
    local:qwen3.5-35b-a3b-4bit)         echo 2 ;;  # Track B5: MoE sonnet-equivalent
    local:nemotron-30b-a3b-8bit)        echo 2 ;;  # Track B5: MoE sonnet-equivalent
    opus)                               echo 3 ;;
    local:qwen3.5-122b-a10b-4bit)       echo 3 ;;  # Track B5: MoE opus-equivalent
    local:gpt-oss-120b-mxfp4)           echo 3 ;;  # Track B5: opus-equivalent
    flash-moe:qwen3.5-397b)             echo 3 ;;  # Track B5: SSD-streamed opus-equivalent
    *)                                  echo 0 ;;
  esac
}

# --- Apply safety floor clamping ---
# Usage: _routing_apply_safety_floor <agent> <model_var_name> <caller_label>
# Looks up agent's min_model, clamps model if below floor. Handles namespaced
# agent IDs (e.g. "interflux:review:fd-safety") by stripping to short name.
# Prints the (possibly clamped) model to stdout. Returns 0 always.
_routing_apply_safety_floor() {
  local agent="$1" model="$2" caller="$3"
  [[ -z "$agent" || -z "$model" ]] && { echo "$model"; return 0; }

  # Resolve floor key: try full agent ID first, then strip namespace prefix
  local floor_key="$agent"
  if [[ -z "${_ROUTING_SF_AGENT_MIN[$floor_key]:-}" && "$floor_key" == *:* ]]; then
    floor_key="${floor_key##*:}"
  fi

  if [[ -n "${_ROUTING_SF_AGENT_MIN[$floor_key]:-}" ]]; then
    local floor="${_ROUTING_SF_AGENT_MIN[$floor_key]}"
    local model_tier floor_tier
    model_tier=$(_routing_model_tier "$model")
    floor_tier=$(_routing_model_tier "$floor")
    if [[ $floor_tier -eq 0 ]]; then
      echo "Warning: [safety-floor] agent=$agent has invalid min_model='$floor' — floor ignored" >&2
    elif [[ $model_tier -lt $floor_tier ]]; then
      echo "[safety-floor] agent=$agent resolved=$model clamped_to=$floor role=$caller" >&2
      model="$floor"
    fi
  fi

  echo "$model"
  return 0
}

# --- Downgrade model one tier ---
# Usage: _routing_downgrade <model>
# Returns next lower tier. haiku stays haiku. Empty/unknown preserved or defaults to haiku.
_routing_downgrade() {
  case "${1:-}" in
    opus)               echo "sonnet" ;;
    sonnet)             echo "haiku" ;;
    haiku)              echo "haiku" ;;
    local:qwen3-30b)    echo "local:qwen3-8b" ;;  # Track B5
    local:qwen2.5-72b)  echo "local:qwen3-8b" ;;  # Track B5
    local:qwen3-8b)     echo "local:qwen3-8b" ;;  # Track B5: already lowest
    *)                  echo "${1:-haiku}" ;;       # unknown → preserve or default
  esac
}

# --- Find routing.yaml ---
_routing_find_config() {
  # 0. Explicit env var override
  if [[ -n "${CLAVAIN_ROUTING_CONFIG:-}" && -f "$CLAVAIN_ROUTING_CONFIG" ]]; then
    echo "$CLAVAIN_ROUTING_CONFIG"
    return 0
  fi

  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local source_dir="${CLAVAIN_SOURCE_DIR:-${CLAVAIN_DIR:-}}"

  # 1. Relative to this script
  if [[ -f "$script_dir/../config/routing.yaml" ]]; then
    echo "$script_dir/../config/routing.yaml"
    return 0
  fi
  # 2. CLAVAIN_SOURCE_DIR override
  if [[ -n "$source_dir" && -f "$source_dir/config/routing.yaml" ]]; then
    echo "$source_dir/config/routing.yaml"
    return 0
  fi
  # 3. CLAUDE_PLUGIN_ROOT (set by Claude Code for the active plugin)
  if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" && -f "$CLAUDE_PLUGIN_ROOT/config/routing.yaml" ]]; then
    echo "$CLAUDE_PLUGIN_ROOT/config/routing.yaml"
    return 0
  fi
  return 1
}

# --- Find agent-roles.yaml (companion to routing.yaml) ---
_routing_find_roles_config() {
  # 0. Explicit env var — if set, use it (or fail if not a regular file)
  if [[ -n "${CLAVAIN_ROLES_CONFIG:-}" ]]; then
    if [[ -f "$CLAVAIN_ROLES_CONFIG" ]]; then
      echo "$CLAVAIN_ROLES_CONFIG"
      return 0
    fi
    return 1  # Env var set but file missing/invalid — don't search further
  fi

  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

  # 1. Interflux plugin config (canonical location)
  local d
  for d in \
    "${INTERFLUX_ROOT:-}/config/flux-drive" \
    "$script_dir/../../../interverse/interflux/config/flux-drive" \
    "$script_dir/../../interverse/interflux/config/flux-drive" \
    "${CLAUDE_PLUGIN_ROOT:-}/../interflux/config/flux-drive" \
  ; do
    if [[ -f "$d/agent-roles.yaml" ]]; then
      echo "$d/agent-roles.yaml"
      return 0
    fi
  done

  # 2. Same directory as routing.yaml
  if [[ -n "$_ROUTING_CONFIG_PATH" ]]; then
    local config_dir
    config_dir="$(dirname "$_ROUTING_CONFIG_PATH")"
    if [[ -f "$config_dir/agent-roles.yaml" ]]; then
      echo "$config_dir/agent-roles.yaml"
      return 0
    fi
  fi

  return 1  # Not found — safety floors will be inactive
}

# --- Parse routing.yaml into cache ---
_routing_load_cache() {
  [[ -n "$_ROUTING_CACHE_POPULATED" ]] && return 0

  _ROUTING_CONFIG_PATH="$(_routing_find_config)" || {
    _ROUTING_CACHE_POPULATED=1
    return 0  # No config — all resolvers return empty
  }

  # State machine for line-by-line YAML parsing (max 3 levels)
  local section=""        # subagents | dispatch | complexity
  local subsection=""     # defaults | phases | overrides | tiers | fallback | cx_tiers | cx_overrides
  local current_phase=""
  local in_categories=""  # true when inside a categories: block
  local current_tier=""
  local current_cx_tier=""  # B2: current complexity tier being parsed

  while IFS= read -r line; do
    # Skip comments and blank lines
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${line// /}" ]] && continue

    # --- Top-level sections ---
    if [[ "$line" =~ ^subagents: ]]; then
      section="subagents"; subsection=""; current_phase=""; in_categories=""; current_tier=""
      continue
    fi
    if [[ "$line" =~ ^dispatch: ]]; then
      section="dispatch"; subsection=""; current_phase=""; in_categories=""; current_tier=""
      continue
    fi
    if [[ "$line" =~ ^complexity: ]]; then
      section="complexity"; subsection=""; current_cx_tier=""
      continue
    fi
    if [[ "$line" =~ ^calibration: ]]; then
      section="calibration"; subsection=""
      continue
    fi
    if [[ "$line" =~ ^local_models: ]]; then
      section="local_models"; subsection=""
      continue
    fi
    # Another top-level key — reset
    if [[ "$line" =~ ^[a-z] ]]; then
      section=""; subsection=""
      continue
    fi

    # --- Level 2 (2-space indent) ---
    if [[ "$section" == "subagents" ]]; then
      # defaults:, phases:, overrides:
      if [[ "$line" =~ ^[[:space:]]{2}defaults: ]]; then
        subsection="defaults"; current_phase=""; in_categories=""
        continue
      fi
      if [[ "$line" =~ ^[[:space:]]{2}phases: ]]; then
        subsection="phases"; current_phase=""; in_categories=""
        continue
      fi
      if [[ "$line" =~ ^[[:space:]]{2}overrides:[[:space:]]*(\{[[:space:]]*\})?[[:space:]]*$ ]]; then
        subsection="overrides"; current_phase=""; in_categories=""
        continue
      fi
      # Another 2-indent key under subagents — reset subsection
      if [[ "$line" =~ ^[[:space:]]{2}[a-z] && ! "$line" =~ ^[[:space:]]{4} ]]; then
        subsection=""; current_phase=""; in_categories=""
      fi

      # --- defaults section ---
      if [[ "$subsection" == "defaults" ]]; then
        # model: value
        if [[ "$line" =~ ^[[:space:]]{4}model:[[:space:]]*(.+) ]]; then
          _ROUTING_SA_DEFAULT_MODEL="${BASH_REMATCH[1]%%[[:space:]#]*}"
          in_categories=""
          continue
        fi
        # categories:
        if [[ "$line" =~ ^[[:space:]]{4}categories: ]]; then
          in_categories="defaults"
          continue
        fi
        # category value (6-space indent)
        if [[ "$in_categories" == "defaults" && "$line" =~ ^[[:space:]]{6}([a-z][a-z0-9_-]*):[[:space:]]*(.+) ]]; then
          local cat_name="${BASH_REMATCH[1]}"
          local cat_val="${BASH_REMATCH[2]%%[[:space:]#]*}"
          _ROUTING_SA_DEFAULTS["$cat_name"]="$cat_val"
          continue
        fi
        # Exit categories on non-6-space line
        if [[ "$in_categories" == "defaults" && ! "$line" =~ ^[[:space:]]{6} ]]; then
          in_categories=""
        fi
      fi

      # --- phases section ---
      if [[ "$subsection" == "phases" ]]; then
        # Phase name (4-space indent, ends with colon)
        if [[ "$line" =~ ^[[:space:]]{4}([a-z][a-z0-9_-]*):[[:space:]]*$ ]]; then
          current_phase="${BASH_REMATCH[1]}"
          in_categories=""
          continue
        fi
        # Phase-level model (6-space indent)
        if [[ -n "$current_phase" && "$line" =~ ^[[:space:]]{6}model:[[:space:]]*(.+) ]]; then
          _ROUTING_SA_PHASE_MODEL["$current_phase"]="${BASH_REMATCH[1]%%[[:space:]#]*}"
          in_categories=""
          continue
        fi
        # Phase categories block
        if [[ -n "$current_phase" && "$line" =~ ^[[:space:]]{6}categories: ]]; then
          in_categories="phase"
          continue
        fi
        # Phase category value (8-space indent)
        if [[ "$in_categories" == "phase" && -n "$current_phase" && "$line" =~ ^[[:space:]]{8}([a-z][a-z0-9_-]*):[[:space:]]*(.+) ]]; then
          local pcat_name="${BASH_REMATCH[1]}"
          local pcat_val="${BASH_REMATCH[2]%%[[:space:]#]*}"
          _ROUTING_SA_PHASE_CAT["${current_phase}:${pcat_name}"]="$pcat_val"
          continue
        fi
        # Exit phase categories on non-8-space line
        if [[ "$in_categories" == "phase" && ! "$line" =~ ^[[:space:]]{8} ]]; then
          in_categories=""
        fi
      fi

      # --- overrides section ---
      if [[ "$subsection" == "overrides" ]]; then
        # agent: model (4-space indent, allows colons in agent name for namespaced agents)
        if [[ "$line" =~ ^[[:space:]]{4}([a-z][a-z0-9_:-]*):[[:space:]]*(.+) ]]; then
          local agent_name="${BASH_REMATCH[1]}"
          local agent_val="${BASH_REMATCH[2]%%[[:space:]#]*}"
          [[ -n "$agent_val" ]] && _ROUTING_SA_OVERRIDE["$agent_name"]="$agent_val"
          continue
        fi
      fi
    fi

    # --- dispatch section ---
    if [[ "$section" == "dispatch" ]]; then
      if [[ "$line" =~ ^[[:space:]]{2}tiers: ]]; then
        subsection="tiers"; current_tier=""
        continue
      fi
      if [[ "$line" =~ ^[[:space:]]{2}fallback: ]]; then
        subsection="fallback"; current_tier=""
        continue
      fi
      if [[ "$line" =~ ^[[:space:]]{2}[a-z] && ! "$line" =~ ^[[:space:]]{4} ]]; then
        subsection=""; current_tier=""
      fi

      # --- tiers ---
      if [[ "$subsection" == "tiers" ]]; then
        # Tier name (4-space indent)
        if [[ "$line" =~ ^[[:space:]]{4}([a-z][a-z0-9_-]*):[[:space:]]*$ ]]; then
          current_tier="${BASH_REMATCH[1]}"
          continue
        fi
        # model: value (6-space indent)
        if [[ -n "$current_tier" && "$line" =~ ^[[:space:]]{6}model:[[:space:]]*(.+) ]]; then
          _ROUTING_DISPATCH_TIER["$current_tier"]="${BASH_REMATCH[1]%%[[:space:]#]*}"
          continue
        fi
        # description: value (6-space indent)
        if [[ -n "$current_tier" && "$line" =~ ^[[:space:]]{6}description:[[:space:]]*(.+) ]]; then
          _ROUTING_DISPATCH_DESC["$current_tier"]="${BASH_REMATCH[1]%%[[:space:]#]*}"
          continue
        fi
      fi

      # --- fallback ---
      if [[ "$subsection" == "fallback" ]]; then
        if [[ "$line" =~ ^[[:space:]]{4}([a-z][a-z0-9_-]*):[[:space:]]*(.+) ]]; then
          local fb_tier="${BASH_REMATCH[1]}"
          local fb_val="${BASH_REMATCH[2]%%[[:space:]#]*}"
          _ROUTING_DISPATCH_FALLBACK["$fb_tier"]="$fb_val"
          continue
        fi
      fi
    fi

    # --- complexity section (B2) ---
    if [[ "$section" == "complexity" ]]; then
      # mode: off|shadow|enforce (2-space indent)
      if [[ "$line" =~ ^[[:space:]]{2}mode:[[:space:]]*(.+) ]]; then
        _ROUTING_CX_MODE="${BASH_REMATCH[1]%%[[:space:]#]*}"
        continue
      fi
      # tiers: subsection
      if [[ "$line" =~ ^[[:space:]]{2}tiers: ]]; then
        subsection="cx_tiers"; current_cx_tier=""
        continue
      fi
      # overrides: subsection
      if [[ "$line" =~ ^[[:space:]]{2}overrides: ]]; then
        subsection="cx_overrides"; current_cx_tier=""
        continue
      fi

      # --- complexity tiers ---
      if [[ "$subsection" == "cx_tiers" ]]; then
        # Tier name (4-space indent, e.g. "    C5:")
        if [[ "$line" =~ ^[[:space:]]{4}(C[1-5]):[[:space:]]*$ ]]; then
          current_cx_tier="${BASH_REMATCH[1]}"
          continue
        fi
        if [[ -n "$current_cx_tier" ]]; then
          if [[ "$line" =~ ^[[:space:]]{6}description:[[:space:]]*(.+) ]]; then
            _ROUTING_CX_DESC["$current_cx_tier"]="${BASH_REMATCH[1]%%[[:space:]#]*}"
            continue
          fi
          if [[ "$line" =~ ^[[:space:]]{6}prompt_tokens:[[:space:]]*([0-9]+) ]]; then
            _ROUTING_CX_PROMPT_TOKENS["$current_cx_tier"]="${BASH_REMATCH[1]}"
            continue
          fi
          if [[ "$line" =~ ^[[:space:]]{6}file_count:[[:space:]]*([0-9]+) ]]; then
            _ROUTING_CX_FILE_COUNT["$current_cx_tier"]="${BASH_REMATCH[1]}"
            continue
          fi
          if [[ "$line" =~ ^[[:space:]]{6}reasoning_depth:[[:space:]]*([1-5]) ]]; then
            _ROUTING_CX_REASONING_DEPTH["$current_cx_tier"]="${BASH_REMATCH[1]}"
            continue
          fi
        fi
      fi

      # --- complexity overrides ---
      if [[ "$subsection" == "cx_overrides" ]]; then
        # Tier name (4-space indent)
        if [[ "$line" =~ ^[[:space:]]{4}(C[1-5]):[[:space:]]*$ ]]; then
          current_cx_tier="${BASH_REMATCH[1]}"
          continue
        fi
        if [[ -n "$current_cx_tier" ]]; then
          if [[ "$line" =~ ^[[:space:]]{6}subagent_model:[[:space:]]*(.+) ]]; then
            _ROUTING_CX_SUBAGENT_MODEL["$current_cx_tier"]="${BASH_REMATCH[1]%%[[:space:]#]*}"
            continue
          fi
          if [[ "$line" =~ ^[[:space:]]{6}dispatch_tier:[[:space:]]*(.+) ]]; then
            _ROUTING_CX_DISPATCH_TIER["$current_cx_tier"]="${BASH_REMATCH[1]%%[[:space:]#]*}"
            continue
          fi
        fi
      fi
    fi

    # --- calibration section (B3) ---
    # --- local_models section (Track B5) ---
    if [[ "$section" == "local_models" ]]; then
      # mode: off | shadow | enforce
      if [[ "$line" =~ ^[[:space:]]{2}mode:[[:space:]]*(.+) ]]; then
        _ROUTING_B5_MODE="${BASH_REMATCH[1]%%[[:space:]#]*}"
        continue
      fi
      # endpoint: http://localhost:8421
      if [[ "$line" =~ ^[[:space:]]{2}endpoint:[[:space:]]*\"?([^\"#]+)\"? ]]; then
        _ROUTING_B5_ENDPOINT="${BASH_REMATCH[1]%%[[:space:]]*}"
        continue
      fi
      # Subsections
      if [[ "$line" =~ ^[[:space:]]{2}tier_mappings: ]]; then
        subsection="b5_tiers"; continue
      fi
      if [[ "$line" =~ ^[[:space:]]{2}complexity_routing: ]]; then
        subsection="b5_cx"; continue
      fi
      if [[ "$line" =~ ^[[:space:]]{2}ineligible_agents: ]]; then
        subsection="b5_ineligible"; continue
      fi
      # Reset subsection on other 2-indent keys
      if [[ "$line" =~ ^[[:space:]]{2}[a-z] && ! "$line" =~ ^[[:space:]]{4} ]]; then
        subsection=""; continue
      fi
      # tier_mappings entries: "local:model": N
      if [[ "$subsection" == "b5_tiers" && "$line" =~ ^[[:space:]]{4}\"?([^\":#]+)\"?:[[:space:]]*([0-9]+) ]]; then
        _ROUTING_B5_TIER_MAP["${BASH_REMATCH[1]}"]="${BASH_REMATCH[2]%%[[:space:]#]*}"
        continue
      fi
      # complexity_routing entries: C1: "local:model"
      if [[ "$subsection" == "b5_cx" && "$line" =~ ^[[:space:]]{4}(C[0-9]+):[[:space:]]*\"?([^\"#]+)\"? ]]; then
        _ROUTING_B5_CX_MODEL["${BASH_REMATCH[1]}"]="${BASH_REMATCH[2]%%[[:space:]]*}"
        continue
      fi
      # ineligible_agents list items: - agent_name
      if [[ "$subsection" == "b5_ineligible" && "$line" =~ ^[[:space:]]{4}-[[:space:]]+(.+) ]]; then
        local inelig="${BASH_REMATCH[1]%%[[:space:]#]*}"
        _ROUTING_B5_INELIGIBLE["$inelig"]=1
        continue
      fi
    fi

    if [[ "$section" == "calibration" ]]; then
      if [[ "$line" =~ ^[[:space:]]{2}mode:[[:space:]]*(.+) ]]; then
        _ROUTING_CAL_MODE="${BASH_REMATCH[1]%%[[:space:]#]*}"
        continue
      fi
    fi
  done < "$_ROUTING_CONFIG_PATH"

  # Env override for calibration mode
  if [[ -n "${INTERSPECT_ROUTING_MODE:-}" ]]; then
    _ROUTING_CAL_MODE="$INTERSPECT_ROUTING_MODE"
  fi

  # Env override for B5 local model mode
  if [[ -n "${INTERFERE_ROUTING_MODE:-}" ]]; then
    _ROUTING_B5_MODE="$INTERFERE_ROUTING_MODE"
  fi

  # Warn if config exists but nothing was parsed (likely malformed)
  if [[ -n "$_ROUTING_CONFIG_PATH" && -z "$_ROUTING_SA_DEFAULT_MODEL" && ${#_ROUTING_SA_DEFAULTS[@]} -eq 0 ]]; then
    echo "Warning: routing.yaml exists but no subagent defaults were parsed — possible malformed config" >&2
  fi

  # --- Parse agent-roles.yaml for safety floors ---
  local roles_path
  roles_path="$(_routing_find_roles_config)" || roles_path=""
  if [[ -n "$roles_path" && -f "$roles_path" ]]; then
    local current_min="" current_domain_cx="" current_max_model="" in_agents=0
    while IFS= read -r line || [[ -n "$line" ]]; do
      # Strip comments and trailing whitespace
      line="${line%%#*}"
      [[ -z "${line// /}" ]] && continue

      # Role name (2-space indent, not 4+) — reset all tracked fields
      if [[ "$line" =~ ^[[:space:]]{2}[a-z] && ! "$line" =~ ^[[:space:]]{4} ]]; then
        current_min="" current_domain_cx="" current_max_model=""
        in_agents=0
        continue
      fi

      # min_model field
      if [[ "$line" =~ ^[[:space:]]+min_model:[[:space:]]* ]]; then
        current_min="${line#*min_model:}"
        current_min="${current_min#"${current_min%%[![:space:]]*}"}"
        current_min="${current_min%"${current_min##*[![:space:]]}"}"
        continue
      fi

      # domain_complexity field
      if [[ "$line" =~ ^[[:space:]]+domain_complexity:[[:space:]]* ]]; then
        current_domain_cx="${line#*domain_complexity:}"
        current_domain_cx="${current_domain_cx#"${current_domain_cx%%[![:space:]]*}"}"
        current_domain_cx="${current_domain_cx%"${current_domain_cx##*[![:space:]]}"}"
        continue
      fi

      # max_model field
      if [[ "$line" =~ ^[[:space:]]+max_model:[[:space:]]* ]]; then
        current_max_model="${line#*max_model:}"
        current_max_model="${current_max_model#"${current_max_model%%[![:space:]]*}"}"
        current_max_model="${current_max_model%"${current_max_model##*[![:space:]]}"}"
        continue
      fi

      # agents: list header (exact match to avoid agents_count: etc.)
      if [[ "$line" =~ ^[[:space:]]+agents:[[:space:]]*$ ]]; then
        in_agents=1
        continue
      fi

      # Agent list item (- agent_name) — populate all three arrays
      if [[ $in_agents -eq 1 && "$line" =~ ^[[:space:]]+-[[:space:]] ]]; then
        local agent_name="${line#*- }"
        agent_name="${agent_name#"${agent_name%%[![:space:]]*}"}"
        agent_name="${agent_name%"${agent_name##*[![:space:]]}"}"
        [[ -n "$current_min" && -n "$agent_name" ]] && _ROUTING_SF_AGENT_MIN["$agent_name"]="$current_min"
        [[ -n "$current_domain_cx" && -n "$agent_name" ]] && _ROUTING_SF_AGENT_DOMAIN_CX["$agent_name"]="$current_domain_cx"
        [[ -n "$current_max_model" && -n "$agent_name" ]] && _ROUTING_SF_AGENT_MAX_MODEL["$agent_name"]="$current_max_model"
        continue
      fi

      # Any other field resets agents context
      if [[ $in_agents -eq 1 && ! "$line" =~ ^[[:space:]]+-[[:space:]] ]]; then
        in_agents=0
      fi
    done < "$roles_path"
  fi

  _ROUTING_CACHE_POPULATED=1
}

# --- Look up agent field from pre-populated cache ---
# Usage: _routing_agent_field <agent> <field>
# Fields: min_model, domain_complexity, max_model
_routing_agent_field() {
  local agent="${1:-}" field="${2:-}"
  [[ -z "$agent" ]] && return 0
  # Strip namespace prefix
  [[ "$agent" == *:* ]] && agent="${agent##*:}"
  case "$field" in
    min_model)          echo "${_ROUTING_SF_AGENT_MIN[$agent]:-}" ;;
    domain_complexity)  echo "${_ROUTING_SF_AGENT_DOMAIN_CX[$agent]:-}" ;;
    max_model)          echo "${_ROUTING_SF_AGENT_MAX_MODEL[$agent]:-}" ;;
    *)                  echo "" ;;
  esac
}

# --- Adjust expansion pool agent model tier ---
# Usage: routing_adjust_expansion_tier <agent> <current_model> <expansion_score> <budget_pressure>
# Pipeline: score adjust → budget pressure → constitutional floor → safety floor → validate
# budget_pressure: "low" | "medium" | "high"
# Returns: adjusted model name
routing_adjust_expansion_tier() {
  local agent="$1" model="$2" score="${3:-2}" pressure="${4:-low}"

  # 1. Score-based tier adjustment
  case "$score" in
    3) # Strong evidence — upgrade haiku checkers if no max_model ceiling blocks it
       local max_ceil max_ceil_tier
       max_ceil=$(_routing_agent_field "$agent" "max_model")
       max_ceil_tier=$(_routing_model_tier "${max_ceil:-}")
       if [[ "$model" == "haiku" || "$model" == "local:qwen3-8b" ]]; then
         # Empty ceiling or unknown ceiling (tier=0) → no ceiling enforced
         if [[ -z "$max_ceil" || $max_ceil_tier -eq 0 || $max_ceil_tier -ge 2 ]]; then
           model="sonnet"
         fi
       fi
       ;;
    2) ;; # Moderate evidence — keep model
    1) # Weak evidence — downgrade unless domain_complexity is high
       local dom_cx; dom_cx=$(_routing_agent_field "$agent" "domain_complexity")
       if [[ "${dom_cx:-low}" != "high" ]]; then
         model=$(_routing_downgrade "$model")
       fi
       ;;
    0) model="haiku" ;; # Should not reach dispatch
    *) ;; # Invalid score — keep model
  esac

  # 2. Budget pressure (applied after score, before floors)
  if [[ "$pressure" == "high" ]]; then
    model=$(_routing_downgrade "$model")
  fi

  # 3. Constitutional floor from agent-roles.yaml
  local const_floor; const_floor=$(_routing_agent_field "$agent" "min_model")
  if [[ -n "$const_floor" ]]; then
    local m_tier f_tier
    m_tier=$(_routing_model_tier "$model")
    f_tier=$(_routing_model_tier "$const_floor")
    [[ $m_tier -lt $f_tier ]] && model="$const_floor"
  fi

  # 4. INVARIANT: empty model guard — default to haiku before safety floor
  [[ -n "$model" ]] || model="haiku"

  # 5. Safety floor (ALWAYS LAST — non-negotiable)
  model=$(_routing_apply_safety_floor "$agent" "$model" "expansion")

  # 6. Final validation
  if [[ ! "$model" =~ ^(haiku|sonnet|opus|local:.+)$ ]]; then
    echo "[routing] WARN: adjust returned invalid '$model' for $agent, falling back to $2" >&2
    model="$2"
    # Re-apply safety floor on fallback — $2 hasn't been through the floor check
    model=$(_routing_apply_safety_floor "$agent" "$model" "expansion-fallback")
  fi

  echo "$model"
}

# --- B3: Read interspect routing calibration (not cached — read fresh each call) ---
# Returns calibrated model for an agent, or empty string if no recommendation.
# Validates: file exists, valid JSON, schema_version=1, model name is valid.
_routing_read_calibration() {
  local agent="$1"
  [[ -z "$agent" ]] && return 0

  # Find calibration file
  local cal_path=""
  local root
  if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
    cal_path="${CLAUDE_PROJECT_DIR}/.clavain/interspect/routing-calibration.json"
  else
    root=$(git rev-parse --show-toplevel 2>/dev/null) || root=""
    [[ -n "$root" ]] && cal_path="${root}/.clavain/interspect/routing-calibration.json"
  fi
  [[ -z "$cal_path" || ! -f "$cal_path" ]] && return 0

  # Strip namespace prefix for lookup (same as safety floor)
  local lookup_key="$agent"
  if [[ "$lookup_key" == *:* ]]; then
    lookup_key="${lookup_key##*:}"
  fi

  # Read and validate with jq (single pass)
  local result
  result=$(jq -r --arg agent "$lookup_key" '
    select(.schema_version == 1 or .schema_version == 2) |
    .agents[$agent] // empty |
    select(.confidence >= 0.7 and .evidence_sessions >= 3) |
    .recommended_model // empty |
    select(. == "haiku" or . == "sonnet" or . == "opus")
  ' "$cal_path" 2>/dev/null) || result=""

  [[ -n "$result" ]] && echo "$result"
}

# --- Internal: read interspect routing overrides ---
# Returns: "exclude" if agent is excluded, model name if agent has an approved
# model recommendation, empty string if no matching override.
# Reads .claude/routing-overrides.json (written by /interspect:propose + /interspect:approve).
_routing_read_override() {
  local agent="$1"
  [[ -z "$agent" ]] && return 0

  # Find override file
  local ovr_path=""
  local root
  if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
    ovr_path="${CLAUDE_PROJECT_DIR}/.claude/routing-overrides.json"
  else
    root=$(git rev-parse --show-toplevel 2>/dev/null) || root=""
    [[ -n "$root" ]] && ovr_path="${root}/.claude/routing-overrides.json"
  fi
  [[ -z "$ovr_path" || ! -f "$ovr_path" ]] && return 0

  # Strip namespace prefix for lookup (same as calibration/safety floor)
  local lookup_key="$agent"
  if [[ "$lookup_key" == *:* ]]; then
    lookup_key="${lookup_key##*:}"
  fi

  # Read and match override with jq (single pass)
  # Only applies: (a) exclude actions, (b) approved model recommendations
  # Skips: pending proposals, expired overrides
  local result
  result=$(jq -r --arg agent "$lookup_key" '
    .overrides // [] | map(
      select(.agent == $agent) |
      select(
        # Skip expired overrides
        (.expires_at // null) == null or
        (.expires_at > (now | todate))
      )
    ) | first //empty |
    if .action == "exclude" then
      "exclude"
    elif .action == "propose" and .status == "approved" and .recommended_model != null then
      .recommended_model |
      select(. == "haiku" or . == "sonnet" or . == "opus")
    else
      empty
    end
  ' "$ovr_path" 2>/dev/null) || result=""

  [[ -n "$result" ]] && echo "$result"
}

# --- B5: Check interfer availability (cached) ---
_routing_b5_available() {
  [[ -z "$_ROUTING_B5_ENDPOINT" ]] && { echo "no"; return; }
  local now
  now=$(date +%s)
  if (( now - _ROUTING_B5_HEALTH_TIME < 30 )); then
    echo "$_ROUTING_B5_HEALTH_CACHE"
    return
  fi
  if curl -sf --max-time 1 "${_ROUTING_B5_ENDPOINT}/health" >/dev/null 2>&1; then
    _ROUTING_B5_HEALTH_CACHE="yes"
  else
    _ROUTING_B5_HEALTH_CACHE="no"
  fi
  _ROUTING_B5_HEALTH_TIME=$now
  echo "$_ROUTING_B5_HEALTH_CACHE"
}

# --- B5: Resolve local model for a cloud model + complexity ---
# Returns the local model that would serve this request, or empty string.
# In shadow mode, logs to stderr and returns empty (caller uses cloud model).
# In enforce mode, returns the local model (caller routes to interfer).
_routing_b5_resolve() {
  local cloud_model="$1" complexity="${2:-}" agent="${3:-}" phase="${4:-}"

  # Quick exit: B5 not active
  local mode="${_ROUTING_B5_MODE:-off}"
  [[ "$mode" == "off" ]] && return 0

  # Ineligible agent check
  if [[ -n "$agent" && -n "${_ROUTING_B5_INELIGIBLE[$agent]:-}" ]]; then
    if [[ "$mode" == "shadow" ]]; then
      echo "[B5-shadow] ineligible: $agent (safety floor)" >&2
    fi
    return 0
  fi

  # Determine which local model would serve this
  local local_model=""
  if [[ -n "$complexity" && -n "${_ROUTING_B5_CX_MODEL[$complexity]:-}" ]]; then
    local_model="${_ROUTING_B5_CX_MODEL[$complexity]}"
  fi

  # No local model for this complexity tier
  if [[ -z "$local_model" ]]; then
    return 0
  fi

  # Check interfer availability
  local available
  available=$(_routing_b5_available)
  if [[ "$available" != "yes" ]]; then
    if [[ "$mode" == "shadow" ]]; then
      echo "[B5-shadow] unavailable: interfer not responding (would route $cloud_model → $local_model)" >&2
    fi
    return 0
  fi

  # Shadow mode: log and return empty (caller uses cloud)
  if [[ "$mode" == "shadow" ]]; then
    echo "[B5-shadow] would route locally: $cloud_model → $local_model (complexity=$complexity phase=$phase agent=$agent)" >&2
    return 0
  fi

  # Enforce mode: return local model
  echo "$local_model"
}

# --- Public: resolve subagent model ---
# resolve_model MUST never return "inherit" — it is an internal sentinel
# meaning "this level has no override, continue to next level."
# Returns "_EXCLUDED_" if the agent is excluded by an interspect routing override.
# Callers (flux-drive triage, quality-gates) MUST check for "_EXCLUDED_" and skip the agent.
routing_resolve_model() {
  # Fast path: delegate to compiled Go router when available.
  # Skips fast path when CLAVAIN_RUN_ID is set (needs kernel-stored overrides
  # that the Go router doesn't support yet).
  # Also skips when routing-overrides.json exists (Go router doesn't support
  # interspect overrides yet — bash implementation handles them).
  local _ovr_check=""
  if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
    [[ -f "${CLAUDE_PROJECT_DIR}/.claude/routing-overrides.json" ]] && _ovr_check="yes"
  else
    local _ovr_root; _ovr_root=$(git rev-parse --show-toplevel 2>/dev/null) || _ovr_root=""
    [[ -n "$_ovr_root" && -f "${_ovr_root}/.claude/routing-overrides.json" ]] && _ovr_check="yes"
  fi
  if [[ -z "${CLAVAIN_RUN_ID:-}" && -z "$_ovr_check" ]] && command -v ic >/dev/null 2>&1; then
    local _ic_result
    _ic_result=$(ic route model "$@" 2>/dev/null) && {
      echo "$_ic_result"
      return 0
    }
    # Fall through on failure — bash implementation is the safety net
  fi

  _routing_load_cache

  local phase="" category="" agent=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --phase)   phase="$2"; shift 2 ;;
      --category) category="$2"; shift 2 ;;
      --agent)   agent="$2"; shift 2 ;;
      *) shift ;;
    esac
  done

  local result=""

  # 0. Kernel-stored per-run model overrides (from agency specs)
  if [[ -z "$result" && -n "${CLAVAIN_RUN_ID:-}" && -n "$phase" ]]; then
    local kernel_model
    kernel_model=$(intercore_state_get "agency.models.${phase}" "$CLAVAIN_RUN_ID" 2>/dev/null) || kernel_model=""
    if [[ -n "$kernel_model" ]]; then
      local km_result=""
      if [[ -n "$category" ]]; then
        km_result=$(printf '%s' "$kernel_model" | jq -r ".categories.\"$category\" // .default // empty" 2>/dev/null) || km_result=""
      else
        km_result=$(printf '%s' "$kernel_model" | jq -r ".default // empty" 2>/dev/null) || km_result=""
      fi
      if [[ -n "$km_result" && "$km_result" != "inherit" ]]; then
        result="$km_result"
      fi
    fi
  fi

  # 1. Per-agent override
  if [[ -z "$result" && -n "$agent" && -n "${_ROUTING_SA_OVERRIDE[$agent]:-}" ]]; then
    result="${_ROUTING_SA_OVERRIDE[$agent]}"
    [[ "$result" == "inherit" ]] && result=""
  fi

  # 1a. Interspect routing overrides (.claude/routing-overrides.json)
  # Read fresh each call. Exclusions return "_EXCLUDED_" sentinel.
  # Model overrides take precedence over calibration but not routing.yaml agent overrides.
  if [[ -z "$result" && -n "$agent" ]]; then
    local ovr_result
    ovr_result=$(_routing_read_override "$agent") || ovr_result=""
    if [[ "$ovr_result" == "exclude" ]]; then
      echo "_EXCLUDED_"
      return 0
    elif [[ -n "$ovr_result" ]]; then
      result="$ovr_result"
    fi
  fi

  # 1b. Interspect routing calibration (B3)
  # Read fresh each call (not cached). Shadow mode logs, enforce mode applies.
  # CRITICAL: assigns to $result and falls through to safety floor — no early return.
  if [[ -z "$result" && -n "$agent" && -n "${_ROUTING_CAL_MODE:-}" && "${_ROUTING_CAL_MODE}" != "off" ]]; then
    local cal_model
    cal_model=$(_routing_read_calibration "$agent") || cal_model=""
    if [[ -n "$cal_model" ]]; then
      if [[ "${_ROUTING_CAL_MODE}" == "enforce" ]]; then
        result="$cal_model"
      else
        # Shadow mode: log what would change (resolve base first for comparison)
        local base_for_shadow=""
        # Peek ahead at what the base resolution would produce
        if [[ -n "$phase" && -n "$category" && -n "${_ROUTING_SA_PHASE_CAT[${phase}:${category}]:-}" ]]; then
          base_for_shadow="${_ROUTING_SA_PHASE_CAT[${phase}:${category}]}"
        elif [[ -n "$phase" && -n "${_ROUTING_SA_PHASE_MODEL[$phase]:-}" ]]; then
          base_for_shadow="${_ROUTING_SA_PHASE_MODEL[$phase]}"
        elif [[ -n "$category" && -n "${_ROUTING_SA_DEFAULTS[$category]:-}" ]]; then
          base_for_shadow="${_ROUTING_SA_DEFAULTS[$category]}"
        else
          base_for_shadow="${_ROUTING_SA_DEFAULT_MODEL:-sonnet}"
        fi
        [[ "$base_for_shadow" == "inherit" ]] && base_for_shadow="sonnet"
        if [[ "$cal_model" != "$base_for_shadow" ]]; then
          echo "[interspect-shadow] ${agent##*:}: base=$base_for_shadow, calibrated=$cal_model" >&2
          command -v ic >/dev/null 2>&1 && ic route record --rule "B3" --agent "${agent##*:}" --selected-model "$base_for_shadow" --meta "calibrated=$cal_model" 2>/dev/null || true
        fi
      fi
    fi
  fi

  # 2. Phase-specific category
  if [[ -z "$result" && -n "$phase" && -n "$category" && -n "${_ROUTING_SA_PHASE_CAT[${phase}:${category}]:-}" ]]; then
    result="${_ROUTING_SA_PHASE_CAT[${phase}:${category}]}"
    [[ "$result" == "inherit" ]] && result=""
  fi

  # 3. Phase-level model
  if [[ -z "$result" && -n "$phase" && -n "${_ROUTING_SA_PHASE_MODEL[$phase]:-}" ]]; then
    result="${_ROUTING_SA_PHASE_MODEL[$phase]}"
    [[ "$result" == "inherit" ]] && result=""
  fi

  # 4. Default category
  if [[ -z "$result" && -n "$category" && -n "${_ROUTING_SA_DEFAULTS[$category]:-}" ]]; then
    result="${_ROUTING_SA_DEFAULTS[$category]}"
    [[ "$result" == "inherit" ]] && result=""
  fi

  # 5. Default model
  if [[ -z "$result" && -n "$_ROUTING_SA_DEFAULT_MODEL" ]]; then
    result="$_ROUTING_SA_DEFAULT_MODEL"
    [[ "$result" == "inherit" ]] && result=""
  fi

  # 6. Ultimate fallback — never return "inherit" or empty from a configured file
  if [[ -z "$result" && -n "$_ROUTING_CONFIG_PATH" ]]; then
    result="sonnet"
  fi

  # Guard: resolve_model MUST never return "inherit"
  [[ "$result" == "inherit" ]] && result="sonnet"

  # Safety floor: clamp up to min_model if agent has one
  if [[ -n "$agent" && -n "$result" ]]; then
    result=$(_routing_apply_safety_floor "$agent" "$result" "routing_resolve_model")
  fi

  [[ -n "$result" ]] && echo "$result"
  return 0
}

# --- Public (B2): classify task complexity → C1..C5 ---
# Returns the highest complexity tier whose ANY threshold is met.
# Evaluates top-down (C5 first). Returns empty string if complexity is off.
routing_classify_complexity() {
  _routing_load_cache

  # Zero-cost bypass: if mode is off or not set, return immediately
  if [[ "${_ROUTING_CX_MODE:-off}" == "off" ]]; then
    return 0
  fi

  local prompt_tokens=0 file_count=0 reasoning_depth=1
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --prompt-tokens)    prompt_tokens="$2"; shift 2 ;;
      --file-count)       file_count="$2"; shift 2 ;;
      --reasoning-depth)  reasoning_depth="$2"; shift 2 ;;
      *) shift ;;
    esac
  done

  # Evaluate top-down: C5, C4, C3, C2, C1
  local tier
  for tier in C5 C4 C3 C2 C1; do
    local thresh_pt="${_ROUTING_CX_PROMPT_TOKENS[$tier]:-}"
    local thresh_fc="${_ROUTING_CX_FILE_COUNT[$tier]:-}"
    local thresh_rd="${_ROUTING_CX_REASONING_DEPTH[$tier]:-}"

    # Skip tiers with no thresholds defined
    [[ -z "$thresh_pt" && -z "$thresh_fc" && -z "$thresh_rd" ]] && continue

    # ANY threshold met → this tier matches
    if [[ -n "$thresh_pt" && "$prompt_tokens" -ge "$thresh_pt" ]]; then
      echo "$tier"; return 0
    fi
    if [[ -n "$thresh_fc" && "$file_count" -ge "$thresh_fc" ]]; then
      echo "$tier"; return 0
    fi
    if [[ -n "$thresh_rd" && "$reasoning_depth" -ge "$thresh_rd" ]]; then
      echo "$tier"; return 0
    fi
  done

  # No tier matched — default to C1 (lowest)
  echo "C1"
  return 0
}

# --- Public (B2): resolve subagent model with complexity override ---
# Wraps routing_resolve_model with complexity tier overrides.
# In shadow mode: resolves both, logs difference to stderr, returns base result.
# In enforce mode: returns complexity-overridden result.
# When complexity is off or tier is empty: delegates directly to routing_resolve_model.
routing_resolve_model_complex() {
  _routing_load_cache

  local complexity="" phase="" category="" agent=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --complexity) complexity="$2"; shift 2 ;;
      --phase)      phase="$2"; shift 2 ;;
      --category)   category="$2"; shift 2 ;;
      --agent)      agent="$2"; shift 2 ;;
      *) shift ;;
    esac
  done

  # Build args for base resolver
  local base_args=()
  [[ -n "$phase" ]]    && base_args+=(--phase "$phase")
  [[ -n "$category" ]] && base_args+=(--category "$category")
  [[ -n "$agent" ]]    && base_args+=(--agent "$agent")

  # Get base B1 result
  local base_result
  base_result="$(routing_resolve_model "${base_args[@]+"${base_args[@]}"}")"

  # Zero-cost bypass: no complexity tier or mode is off
  if [[ -z "$complexity" || "${_ROUTING_CX_MODE:-off}" == "off" ]]; then
    [[ -n "$base_result" ]] && echo "$base_result"
    return 0
  fi

  # Look up complexity override for subagent model
  local cx_model="${_ROUTING_CX_SUBAGENT_MODEL[$complexity]:-}"
  local final_result="$base_result"

  if [[ -n "$cx_model" && "$cx_model" != "inherit" ]]; then
    final_result="$cx_model"
  fi

  # Shadow mode: log but return base result
  if [[ "${_ROUTING_CX_MODE}" == "shadow" ]]; then
    if [[ "$final_result" != "$base_result" ]]; then
      echo "[B2-shadow] complexity=$complexity would change model: $base_result → $final_result (phase=$phase category=$category)" >&2
    fi
    # Safety floor applies even in shadow mode — safety is non-negotiable
    local shadow_result="$base_result"
    if [[ -n "$agent" && -n "$shadow_result" ]]; then
      shadow_result=$(_routing_apply_safety_floor "$agent" "$shadow_result" "routing_resolve_model_complex(shadow)")
    fi
    # B5: check local model routing (shadow logs independently)
    _routing_b5_resolve "$shadow_result" "$complexity" "$agent" "$phase" >/dev/null
    [[ -n "$shadow_result" ]] && echo "$shadow_result"
    return 0
  fi

  # Enforce mode: return overridden result
  # Guard: never return "inherit"
  [[ "$final_result" == "inherit" ]] && final_result="$base_result"

  # Safety floor: clamp up to min_model (post-complexity resolution)
  if [[ -n "$agent" && -n "$final_result" ]]; then
    final_result=$(_routing_apply_safety_floor "$agent" "$final_result" "routing_resolve_model_complex")
  fi

  # B5: attempt local model routing (enforce returns local model, shadow logs only)
  local b5_result
  b5_result=$(_routing_b5_resolve "$final_result" "$complexity" "$agent" "$phase")
  if [[ -n "$b5_result" ]]; then
    final_result="$b5_result"
  fi

  [[ -n "$final_result" ]] && echo "$final_result"
  return 0
}

# --- Public (B2): resolve dispatch tier with complexity override ---
# In enforce mode, complexity tier can promote/demote the dispatch tier.
# In shadow mode, logs what would change. When off, delegates to base.
routing_resolve_dispatch_tier_complex() {
  _routing_load_cache

  local complexity="" tier=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --complexity) complexity="$2"; shift 2 ;;
      *) [[ -z "$tier" ]] && tier="$1"; shift ;;
    esac
  done

  # Zero-cost bypass
  if [[ -z "$complexity" || "${_ROUTING_CX_MODE:-off}" == "off" ]]; then
    routing_resolve_dispatch_tier "$tier"
    return $?
  fi

  # Get base result
  local base_result
  base_result="$(routing_resolve_dispatch_tier "$tier" 2>/dev/null)" || base_result=""

  # Look up complexity dispatch tier override
  local cx_tier="${_ROUTING_CX_DISPATCH_TIER[$complexity]:-}"
  local final_tier="$tier"

  if [[ -n "$cx_tier" && "$cx_tier" != "inherit" ]]; then
    final_tier="$cx_tier"
  fi

  # Shadow mode
  if [[ "${_ROUTING_CX_MODE}" == "shadow" ]]; then
    if [[ "$final_tier" != "$tier" ]]; then
      local shadow_result
      shadow_result="$(routing_resolve_dispatch_tier "$final_tier" 2>/dev/null)" || shadow_result=""
      echo "[B2-shadow] complexity=$complexity would change dispatch: $tier($base_result) → $final_tier($shadow_result)" >&2
    fi
    [[ -n "$base_result" ]] && echo "$base_result"
    return 0
  fi

  # Enforce mode: resolve the overridden tier
  routing_resolve_dispatch_tier "$final_tier"
  return $?
}

# --- Public: resolve dispatch tier to model ---
routing_resolve_dispatch_tier() {
  # Fast path: delegate to compiled Go router when available.
  if command -v ic >/dev/null 2>&1; then
    local _ic_result
    _ic_result=$(ic route dispatch --tier="$1" 2>/dev/null) && {
      echo "$_ic_result"
      return 0
    }
  fi

  _routing_load_cache
  local tier="$1"
  local hops=0

  while [[ $hops -lt 3 ]]; do
    if [[ -n "${_ROUTING_DISPATCH_TIER[$tier]:-}" ]]; then
      echo "${_ROUTING_DISPATCH_TIER[$tier]}"
      return 0
    fi
    # Try fallback
    if [[ -n "${_ROUTING_DISPATCH_FALLBACK[$tier]:-}" ]]; then
      tier="${_ROUTING_DISPATCH_FALLBACK[$tier]}"
      hops=$(( hops + 1 ))
    else
      break
    fi
  done

  # Not found — return empty
  return 1
}

# --- Public: print routing table ---
routing_list_mappings() {
  _routing_load_cache

  if [[ -z "$_ROUTING_CACHE_POPULATED" || -z "$_ROUTING_CONFIG_PATH" ]]; then
    echo "No routing.yaml found. Using agent frontmatter defaults."
    return 0
  fi

  echo "Source: $_ROUTING_CONFIG_PATH"
  echo ""
  echo "Subagent Routing:"
  echo "  Default model: ${_ROUTING_SA_DEFAULT_MODEL:-<not set>}"

  # Categories
  if [[ ${#_ROUTING_SA_DEFAULTS[@]} -gt 0 ]]; then
    local cats=""
    for k in "${!_ROUTING_SA_DEFAULTS[@]}"; do
      cats+="${k}=${_ROUTING_SA_DEFAULTS[$k]}, "
    done
    echo "  Categories: ${cats%, }"
  fi

  # Phases
  echo "  Phases:"
  local printed_phases=()
  for k in "${!_ROUTING_SA_PHASE_MODEL[@]}"; do
    local phase_info="model=${_ROUTING_SA_PHASE_MODEL[$k]}"
    # Check for phase-category overrides
    for pc in "${!_ROUTING_SA_PHASE_CAT[@]}"; do
      if [[ "$pc" == "${k}:"* ]]; then
        local pcat="${pc#*:}"
        phase_info+=", ${pcat}=${_ROUTING_SA_PHASE_CAT[$pc]}"
      fi
    done
    echo "    ${k}: ${phase_info}"
    printed_phases+=("$k")
  done
  # Phases with only category overrides (no model)
  for pc in "${!_ROUTING_SA_PHASE_CAT[@]}"; do
    local ph="${pc%%:*}"
    local already=false
    for pp in ${printed_phases[@]+"${printed_phases[@]}"}; do
      [[ "$pp" == "$ph" ]] && already=true
    done
    if [[ "$already" == false ]]; then
      local pcat="${pc#*:}"
      echo "    ${ph}: ${pcat}=${_ROUTING_SA_PHASE_CAT[$pc]}"
      printed_phases+=("$ph")
    fi
  done

  # Overrides
  if [[ ${#_ROUTING_SA_OVERRIDE[@]} -gt 0 ]]; then
    echo "  Overrides:"
    for k in "${!_ROUTING_SA_OVERRIDE[@]}"; do
      echo "    ${k}: ${_ROUTING_SA_OVERRIDE[$k]}"
    done
  else
    echo "  Overrides: (none)"
  fi

  echo ""
  echo "Dispatch Tiers:"
  for k in "${!_ROUTING_DISPATCH_TIER[@]}"; do
    local desc="${_ROUTING_DISPATCH_DESC[$k]:-}"
    if [[ -n "$desc" ]]; then
      echo "  ${k}: ${_ROUTING_DISPATCH_TIER[$k]} — ${desc}"
    else
      echo "  ${k}: ${_ROUTING_DISPATCH_TIER[$k]}"
    fi
  done

  if [[ ${#_ROUTING_DISPATCH_FALLBACK[@]} -gt 0 ]]; then
    echo "  Fallback:"
    for k in "${!_ROUTING_DISPATCH_FALLBACK[@]}"; do
      echo "    ${k} → ${_ROUTING_DISPATCH_FALLBACK[$k]}"
    done
  fi

  # B2: Complexity routing
  echo ""
  echo "Complexity Routing (B2):"
  echo "  Mode: ${_ROUTING_CX_MODE:-off}"
  if [[ "${_ROUTING_CX_MODE:-off}" != "off" ]]; then
    echo "  Tiers:"
    local cx_tier
    for cx_tier in C5 C4 C3 C2 C1; do
      local cx_desc="${_ROUTING_CX_DESC[$cx_tier]:-}"
      local cx_pt="${_ROUTING_CX_PROMPT_TOKENS[$cx_tier]:-}"
      local cx_fc="${_ROUTING_CX_FILE_COUNT[$cx_tier]:-}"
      local cx_rd="${_ROUTING_CX_REASONING_DEPTH[$cx_tier]:-}"
      local cx_sm="${_ROUTING_CX_SUBAGENT_MODEL[$cx_tier]:-}"
      local cx_dt="${_ROUTING_CX_DISPATCH_TIER[$cx_tier]:-}"
      if [[ -n "$cx_pt" || -n "$cx_fc" || -n "$cx_rd" ]]; then
        local thresh="tokens≥${cx_pt:-_} files≥${cx_fc:-_} depth≥${cx_rd:-_}"
        local override="subagent=${cx_sm:-inherit} dispatch=${cx_dt:-inherit}"
        echo "    ${cx_tier}: ${thresh} → ${override}"
        [[ -n "$cx_desc" ]] && echo "         ${cx_desc}"
      fi
    done
  fi
}

# --- Public: batch-resolve models for a list of agents ---
# Returns JSON map: {"agent-name":"model",...}
# Used by flux-drive to resolve models for all triaged agents at once.
#
# Usage:
#   routing_resolve_agents --phase <phase> --agents "fd-safety,fd-architecture,..." [--category <cat>]
#     [--prompt-tokens <n>] [--file-count <n>] [--reasoning-depth <n>]
#
# When any signal flag (--prompt-tokens, --file-count, --reasoning-depth) is provided,
# classifies complexity internally via routing_classify_complexity and passes the
# resulting tier to routing_resolve_model_complex. Classification stays in lib-routing.sh
# so callers only measure and pass raw numbers.
#
# Agent ID mapping:
#   fd-* review agents     → interflux:review:fd-<name>, category=review
#   fd-* cognitive agents  → interflux:review:fd-<name>, category=review
#   *-researcher agents    → interflux:research:<name>, category=research
#   repo-research-analyst  → interflux:research:<name>, category=research
#   Other agents           → passed as-is, uses provided --category or none
#
# When complexity mode is shadow/enforce, uses routing_resolve_model_complex.
routing_resolve_agents() {
  # Load cache first — idempotent (guarded by _ROUTING_CACHE_POPULATED).
  # Must run before fast-path so _ROUTING_CX_MODE is available for the guard.
  _routing_load_cache

  # Fast path: delegate to compiled Go router when available.
  # Skips when CLAVAIN_RUN_ID is set, complexity mode is active, or Go router unavailable.
  if [[ -z "${CLAVAIN_RUN_ID:-}" && "${_ROUTING_CX_MODE:-off}" == "off" ]] && command -v ic >/dev/null 2>&1; then
    local _phase="" _agents_csv=""
    local _args=("$@")
    for (( _i=0; _i<${#_args[@]}; _i++ )); do
      case "${_args[$_i]}" in
        --phase)  _phase="${_args[$((_i+1))]:-}" ;;
        --agents) _agents_csv="${_args[$((_i+1))]:-}" ;;
      esac
    done
    if [[ -n "$_agents_csv" ]]; then
      # shellcheck disable=SC2086
      local _ic_result
      local IFS=','
      _ic_result=$(ic route batch --json --phase="$_phase" $_agents_csv 2>/dev/null) && {
        echo "$_ic_result"
        return 0
      }
    fi
  fi

  local phase="" agents_csv="" category_override=""
  local cx_prompt_tokens="" cx_file_count="" cx_reasoning_depth=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --phase)           phase="$2"; shift 2 ;;
      --agents)          agents_csv="$2"; shift 2 ;;
      --category)        category_override="$2"; shift 2 ;;
      --prompt-tokens)   cx_prompt_tokens="$2"; shift 2 ;;
      --file-count)      cx_file_count="$2"; shift 2 ;;
      --reasoning-depth) cx_reasoning_depth="$2"; shift 2 ;;
      *) shift ;;
    esac
  done

  # B2: classify complexity from raw signals when any are provided
  local complexity=""
  if [[ -n "$cx_prompt_tokens" || -n "$cx_file_count" || -n "$cx_reasoning_depth" ]]; then
    local cx_args=()
    [[ -n "$cx_prompt_tokens" ]]   && cx_args+=(--prompt-tokens "$cx_prompt_tokens")
    [[ -n "$cx_file_count" ]]      && cx_args+=(--file-count "$cx_file_count")
    [[ -n "$cx_reasoning_depth" ]] && cx_args+=(--reasoning-depth "$cx_reasoning_depth")
    complexity="$(routing_classify_complexity "${cx_args[@]}")"
  fi

  # Graceful degradation: no config → empty JSON
  if [[ -z "$_ROUTING_CONFIG_PATH" ]]; then
    echo "{}"
    return 0
  fi

  # No agents → empty JSON
  if [[ -z "$agents_csv" ]]; then
    echo "{}"
    return 0
  fi

  # Known cognitive agents (document-only, never code/diff)
  local -A _cognitive_agents=(
    [fd-systems]=1 [fd-decisions]=1 [fd-people]=1
    [fd-resilience]=1 [fd-perception]=1
  )

  # Known research agents
  local -A _research_agents=(
    [best-practices-researcher]=1 [framework-docs-researcher]=1
    [git-history-analyzer]=1 [learnings-researcher]=1
    [repo-research-analyst]=1
  )

  local result="{"
  local first=true
  local IFS=','

  for agent_short in $agents_csv; do
    # Trim whitespace
    agent_short="${agent_short#"${agent_short%%[![:space:]]*}"}"
    agent_short="${agent_short%"${agent_short##*[![:space:]]}"}"
    [[ -z "$agent_short" ]] && continue

    # Determine routing agent ID and category
    local agent_id="$agent_short"
    local category="${category_override}"

    if [[ -n "${_research_agents[$agent_short]:-}" ]]; then
      agent_id="interflux:research:${agent_short}"
      [[ -z "$category" ]] && category="research"
    elif [[ "$agent_short" == fd-* ]]; then
      agent_id="interflux:review:${agent_short}"
      [[ -z "$category" ]] && category="review"
    fi

    # Resolve model — use complexity-aware resolver when tier is available or mode is active
    local model=""
    local resolve_args=(--phase "$phase" --agent "$agent_id")
    [[ -n "$category" ]] && resolve_args+=(--category "$category")

    if [[ -n "$complexity" ]]; then
      model="$(routing_resolve_model_complex --complexity "$complexity" "${resolve_args[@]}")"
    elif [[ "${_ROUTING_CX_MODE:-off}" != "off" ]]; then
      model="$(routing_resolve_model_complex --complexity "" "${resolve_args[@]}")"
    else
      model="$(routing_resolve_model "${resolve_args[@]}")"
    fi

    # Build JSON entry
    if [[ "$first" == true ]]; then
      first=false
    else
      result+=","
    fi
    result+="\"${agent_short}\":\"${model}\""
  done

  result+="}"
  echo "$result"

  # Emit routing decisions to intercore kernel (fire-and-forget, background)
  # Uses `ic route record` which writes to the routing_decisions table.
  # Only emits when complexity mode is active (shadow or enforce) — no overhead when off.
  if [[ "${_ROUTING_CX_MODE:-off}" != "off" && -n "$agents_csv" ]]; then
    _routing_emit_decisions "$phase" "$complexity" "$result" &>/dev/null &
  fi

  return 0
}

# --- Internal: emit routing decisions via ic route record ---
# Records one decision per agent to intercore's routing_decisions table.
# Runs in background (&) — must not affect routing latency.
_routing_emit_decisions() {
  command -v ic >/dev/null 2>&1 || return 0

  local phase="$1" complexity="$2" model_json="$3"

  # Determine decision source
  local rule="B1"
  [[ -n "$complexity" ]] && rule="B2"

  local sid
  sid=$(cat /tmp/interstat-session-id 2>/dev/null || echo "${CLAUDE_SESSION_ID:-unknown}")

  # Parse model_json and record each agent's decision
  # model_json format: {"agent1":"model1","agent2":"model2"}
  local stripped="${model_json#\{}"
  stripped="${stripped%\}}"
  local IFS=','
  local entry
  for entry in $stripped; do
    local agent_name="${entry%%:*}"
    local model="${entry#*:}"
    # Strip quotes
    agent_name="${agent_name//\"/}"
    model="${model//\"/}"
    [[ "$model" == "_EXCLUDED_" ]] && continue
    [[ -z "$agent_name" || -z "$model" ]] && continue
    ic route record \
      --agent="$agent_name" \
      --model="$model" \
      --rule="$rule" \
      --phase="${phase:-}" \
      --session="$sid" \
      2>/dev/null || true
  done
}

_ROUTING_LOADED=1
