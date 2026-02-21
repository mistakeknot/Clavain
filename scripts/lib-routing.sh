#!/usr/bin/env bash
# lib-routing.sh — Read config/routing.yaml and resolve model tiers.
# Source this file; do not execute directly.
#
# Public API:
#   routing_resolve_model --phase <phase> [--category <cat>] [--agent <name>]
#   routing_resolve_dispatch_tier <tier-name>
#   routing_list_mappings

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
  # 3. Plugin cache
  local cached
  cached="$(find ~/.claude/plugins/cache -path '*/clavain/*/config/routing.yaml' 2>/dev/null | head -1)"
  if [[ -n "$cached" ]]; then
    echo "$cached"
    return 0
  fi
  return 1
}

# --- Parse routing.yaml into cache ---
_routing_load_cache() {
  [[ -n "$_ROUTING_CACHE_POPULATED" ]] && return 0

  _ROUTING_CONFIG_PATH="$(_routing_find_config)" || {
    _ROUTING_CACHE_POPULATED=1
    return 0  # No config — all resolvers return empty
  }

  # State machine for line-by-line YAML parsing (max 3 levels)
  local section=""        # subagents | dispatch
  local subsection=""     # defaults | phases | overrides | tiers | fallback
  local current_phase=""
  local in_categories=""  # true when inside a categories: block
  local current_tier=""

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
        # agent: model (4-space indent)
        if [[ "$line" =~ ^[[:space:]]{4}([a-z][a-z0-9_-]*):[[:space:]]*(.+) ]]; then
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
  done < "$_ROUTING_CONFIG_PATH"

  # Warn if config exists but nothing was parsed (likely malformed)
  if [[ -n "$_ROUTING_CONFIG_PATH" && -z "$_ROUTING_SA_DEFAULT_MODEL" && ${#_ROUTING_SA_DEFAULTS[@]} -eq 0 ]]; then
    echo "Warning: routing.yaml exists but no subagent defaults were parsed — possible malformed config" >&2
  fi

  _ROUTING_CACHE_POPULATED=1
}

# --- Public: resolve subagent model ---
# resolve_model MUST never return "inherit" — it is an internal sentinel
# meaning "this level has no override, continue to next level."
routing_resolve_model() {
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

  # 1. Per-agent override
  if [[ -z "$result" && -n "$agent" && -n "${_ROUTING_SA_OVERRIDE[$agent]:-}" ]]; then
    result="${_ROUTING_SA_OVERRIDE[$agent]}"
    [[ "$result" == "inherit" ]] && result=""
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

  [[ -n "$result" ]] && echo "$result"
  return 0
}

# --- Public: resolve dispatch tier to model ---
routing_resolve_dispatch_tier() {
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
}

_ROUTING_LOADED=1
