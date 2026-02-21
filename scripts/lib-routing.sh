#!/usr/bin/env bash
# lib-routing.sh — Read config/routing.yaml and resolve model tiers.
# Source this file; do not execute directly.
#
# Public API (B1 — static routing):
#   routing_resolve_model --phase <phase> [--category <cat>] [--agent <name>]
#   routing_resolve_dispatch_tier <tier-name>
#   routing_list_mappings
#
# Public API (B2 — complexity-aware routing):
#   routing_classify_complexity --prompt-tokens <n> [--file-count <n>] [--reasoning-depth <n>]
#   routing_resolve_model_complex --complexity <tier> [--phase ...] [--category ...] [--agent ...]
#   routing_resolve_dispatch_tier_complex --complexity <tier> <tier-name>

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
    [[ -n "$base_result" ]] && echo "$base_result"
    return 0
  fi

  # Enforce mode: return overridden result
  # Guard: never return "inherit"
  [[ "$final_result" == "inherit" ]] && final_result="$base_result"
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

_ROUTING_LOADED=1
