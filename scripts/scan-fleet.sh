#!/usr/bin/env bash
# scan-fleet.sh — Auto-discover agents and generate/update fleet-registry.yaml.
#
# Scans agent .md files, plugin.json manifests, and agency-spec.yaml companion
# declarations. Merges with existing registry: generated fields overwrite,
# seed-default fields (description, capabilities, roles, etc.) are preserved.
# Stale entries get orphaned_at timestamps.
#
# Requires: yq v4 (mikefarah/yq)
#
# Usage:
#   scan-fleet.sh [--dry-run] [--in-place] [--include-local] [--registry PATH]
#
# Options:
#   --dry-run        Show what would change without modifying anything
#   --in-place       Update fleet-registry.yaml atomically (temp file + mv)
#   --include-local  Include .claude/agents/ project-local agents
#   --registry PATH  Path to fleet-registry.yaml (default: auto-detect)
#
# Known limitation: Agent renames (fd-old → fd-new) orphan the old entry's
# curated fields. No automatic migration. --dry-run makes this visible.

set -euo pipefail

# --- yq dependency ---
_ensure_yq() {
  if ! command -v yq >/dev/null 2>&1; then
    if [[ -x "${HOME}/.local/bin/yq" ]]; then
      export PATH="${HOME}/.local/bin:${PATH}"
    else
      echo "scan-fleet: yq v4 not found. Install: https://github.com/mikefarah/yq" >&2
      exit 1
    fi
  fi
  local ver
  ver="$(yq --version 2>&1 | grep -oE 'v[0-9]+' | head -1)"
  if [[ "$ver" != "v4" ]]; then
    echo "scan-fleet: yq v4 required (found ${ver:-unknown})" >&2
    exit 1
  fi
}

# --- Find project root (where os/clavain lives) ---
_find_project_root() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  # scripts/ is inside os/clavain/
  local clavain_root="${script_dir}/.."
  local project_root="${clavain_root}/../.."
  if [[ -d "$project_root/os/clavain" ]]; then
    echo "$(cd "$project_root" && pwd)"
  else
    echo "$(cd "$clavain_root" && pwd)"
  fi
}

# --- Extract YAML frontmatter from an .md file ---
# Returns empty string if no frontmatter found.
_extract_frontmatter() {
  local file="$1"
  awk '/^---$/{t++; next} t==1{print}' "$file" 2>/dev/null
}

# --- Derive category from directory path ---
# agents/review/foo.md → review
# agents/research/foo.md → research
# agents/workflow/foo.md → workflow
# agents/foo.md (flat) → workflow (default)
_derive_category() {
  local filepath="$1"
  local parent
  parent="$(basename "$(dirname "$filepath")")"
  case "$parent" in
    review|research|workflow|synthesis) echo "$parent" ;;
    *) echo "workflow" ;;
  esac
}

# --- Main scan logic ---
main() {
  _ensure_yq

  local dry_run=false
  local in_place=false
  local include_local=false
  local registry_path=""

  # Parse args
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) dry_run=true; shift ;;
      --in-place) in_place=true; shift ;;
      --include-local) include_local=true; shift ;;
      --registry) registry_path="$2"; shift 2 ;;
      --help|-h)
        sed -n '2,/^$/{ s/^# //; s/^#//; p }' "${BASH_SOURCE[0]}"
        exit 0 ;;
      *) echo "scan-fleet: unknown option: $1" >&2; exit 1 ;;
    esac
  done

  local project_root
  project_root="$(_find_project_root)"

  # Find existing registry
  if [[ -z "$registry_path" ]]; then
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [[ -f "$script_dir/../config/fleet-registry.yaml" ]]; then
      registry_path="$script_dir/../config/fleet-registry.yaml"
    else
      echo "scan-fleet: fleet-registry.yaml not found. Create it first (F1)." >&2
      exit 1
    fi
  fi

  registry_path="$(cd "$(dirname "$registry_path")" && pwd)/$(basename "$registry_path")"

  # Load existing registry into temp file for merging
  local existing_tmp
  existing_tmp="$(mktemp)"
  cp "$registry_path" "$existing_tmp"

  # Track discovered agent IDs
  local -A discovered_agents=()

  # Counters for dry-run output
  local -a added=()
  local -a updated=()
  local -a orphaned=()

  # --- Scan plugin agents ---
  local plugin_dirs=("$project_root/interverse" "$project_root/os")
  for plugin_base in "${plugin_dirs[@]}"; do
    [[ -d "$plugin_base" ]] || continue
    # Find all agent .md files under */agents/**/*.md
    while IFS= read -r agent_file; do
      [[ -f "$agent_file" ]] || continue

      local frontmatter
      frontmatter="$(_extract_frontmatter "$agent_file")"

      # Extract name from frontmatter, fall back to filename
      local agent_name=""
      if [[ -n "$frontmatter" ]]; then
        agent_name="$(echo "$frontmatter" | yq '.name // ""' 2>/dev/null)" || agent_name=""
      fi
      if [[ -z "$agent_name" || "$agent_name" == "null" ]]; then
        agent_name="$(basename "$agent_file" .md)"
      fi

      # Determine source plugin
      local rel_path="${agent_file#"$project_root/"}"
      local plugin_name=""
      # interverse/interflux/agents/... → interflux
      # os/clavain/agents/... → clavain
      if [[ "$rel_path" == interverse/* ]]; then
        plugin_name="$(echo "$rel_path" | cut -d/ -f2)"
      elif [[ "$rel_path" == os/* ]]; then
        plugin_name="$(echo "$rel_path" | cut -d/ -f2)"
      fi

      local category
      category="$(_derive_category "$agent_file")"

      # Determine subagent_type
      local subagent_type="${plugin_name}:${category}:${agent_name}"

      # Check if agent already exists in registry
      local exists
      exists="$(id="$agent_name" yq '.agents[env(id)] != null' "$existing_tmp")"

      discovered_agents["$agent_name"]=1

      if [[ "$exists" == "true" ]]; then
        # Update generated fields only (source, runtime). Category is seed-default (preserved).
        if [[ "$dry_run" == true ]]; then
          updated+=("$agent_name (source=$plugin_name)")
        else
          id="$agent_name" src="$plugin_name" sat="$subagent_type" yq -i '
            .agents[env(id)].source = env(src) |
            .agents[env(id)].runtime.mode = "subagent" |
            .agents[env(id)].runtime.subagent_type = env(sat)
          ' "$existing_tmp"
        fi
      else
        # New agent — write scaffold with seed defaults
        if [[ "$dry_run" == true ]]; then
          added+=("$agent_name (source=$plugin_name, category=$category)")
        else
          local desc=""
          if [[ -n "$frontmatter" ]]; then
            desc="$(echo "$frontmatter" | yq '.description // ""' 2>/dev/null)" || desc=""
          fi
          [[ -z "$desc" || "$desc" == "null" ]] && desc="Auto-discovered agent from ${plugin_name}"

          id="$agent_name" src="$plugin_name" cat="$category" sat="$subagent_type" d="$desc" yq -i '
            .agents[env(id)].source = env(src) |
            .agents[env(id)].category = env(cat) |
            .agents[env(id)].description = env(d) |
            .agents[env(id)].capabilities = [] |
            .agents[env(id)].roles = [env(id)] |
            .agents[env(id)].runtime.mode = "subagent" |
            .agents[env(id)].runtime.subagent_type = env(sat) |
            .agents[env(id)].models.preferred = "sonnet" |
            .agents[env(id)].models.supported = ["haiku", "sonnet", "opus"] |
            .agents[env(id)].tools = [] |
            .agents[env(id)].cold_start_tokens = 500 |
            .agents[env(id)].tags = []
          ' "$existing_tmp"
        fi
      fi
    done < <(find "$plugin_base" -path '*/agents/*.md' -not -path '*/.claude/*' -not -path '*/references/*' 2>/dev/null)
  done

  # --- Optionally scan local agents ---
  if [[ "$include_local" == true && -d "$project_root/.claude/agents" ]]; then
    for agent_file in "$project_root/.claude/agents"/*.md; do
      [[ -f "$agent_file" ]] || continue

      local agent_name
      agent_name="$(basename "$agent_file" .md)"
      local category="workflow"  # default for flat layout

      discovered_agents["$agent_name"]=1

      local exists
      exists="$(id="$agent_name" yq '.agents[env(id)] != null' "$existing_tmp")"

      if [[ "$exists" == "true" ]]; then
        if [[ "$dry_run" == true ]]; then
          updated+=("$agent_name (source=local)")
        else
          id="$agent_name" yq -i '
            .agents[env(id)].source = "local" |
            .agents[env(id)].runtime.mode = "subagent" |
            .agents[env(id)].runtime.subagent_type = env(id)
          ' "$existing_tmp"
        fi
      else
        if [[ "$dry_run" == true ]]; then
          added+=("$agent_name (source=local, category=$category)")
        else
          id="$agent_name" cat="$category" yq -i '
            .agents[env(id)].source = "local" |
            .agents[env(id)].category = env(cat) |
            .agents[env(id)].description = "Project-local agent" |
            .agents[env(id)].capabilities = [] |
            .agents[env(id)].roles = [env(id)] |
            .agents[env(id)].runtime.mode = "subagent" |
            .agents[env(id)].runtime.subagent_type = env(id) |
            .agents[env(id)].models.preferred = "sonnet" |
            .agents[env(id)].models.supported = ["haiku", "sonnet", "opus"] |
            .agents[env(id)].tools = [] |
            .agents[env(id)].cold_start_tokens = 500 |
            .agents[env(id)].tags = []
          ' "$existing_tmp"
        fi
      fi
    done
  fi

  # --- Tombstone orphaned entries ---
  local today
  today="$(date +%Y-%m-%d)"
  local all_registered
  all_registered="$(yq '.agents | keys | .[]' "$existing_tmp")"
  while IFS= read -r registered_id; do
    [[ -z "$registered_id" ]] && continue
    if [[ -z "${discovered_agents[$registered_id]+x}" ]]; then
      # Not discovered — check if already orphaned
      local already_orphaned
      already_orphaned="$(id="$registered_id" yq '.agents[env(id)].orphaned_at // ""' "$existing_tmp")"
      if [[ -z "$already_orphaned" ]]; then
        if [[ "$dry_run" == true ]]; then
          orphaned+=("$registered_id")
        else
          id="$registered_id" d="$today" yq -i '.agents[env(id)].orphaned_at = env(d)' "$existing_tmp"
          orphaned+=("$registered_id")
        fi
      fi
    else
      # Re-discovered — remove orphaned_at if present
      local was_orphaned
      was_orphaned="$(id="$registered_id" yq '.agents[env(id)].orphaned_at // ""' "$existing_tmp")"
      if [[ -n "$was_orphaned" ]]; then
        id="$registered_id" yq -i 'del(.agents[env(id)].orphaned_at)' "$existing_tmp"
      fi
    fi
  done <<< "$all_registered"

  # --- Output ---
  if [[ "$dry_run" == true ]]; then
    echo "=== DRY RUN ==="
    echo ""
    echo "Added (${#added[@]}):"
    for a in "${added[@]}"; do echo "  + $a"; done
    [[ ${#added[@]} -eq 0 ]] && echo "  (none)"
    echo ""
    echo "Updated (${#updated[@]}):"
    for u in "${updated[@]}"; do echo "  ~ $u"; done
    [[ ${#updated[@]} -eq 0 ]] && echo "  (none)"
    echo ""
    echo "Orphaned (${#orphaned[@]}):"
    for o in "${orphaned[@]}"; do echo "  - $o"; done
    [[ ${#orphaned[@]} -eq 0 ]] && echo "  (none)"
    rm -f "$existing_tmp"
  elif [[ "$in_place" == true ]]; then
    # Atomic write: temp file + mv
    local tmpout
    tmpout="$(mktemp "${registry_path}.XXXXXX")"
    cp "$existing_tmp" "$tmpout"
    mv "$tmpout" "$registry_path"
    rm -f "$existing_tmp"
    echo "scan-fleet: updated $registry_path (${#added[@]} added, ${#updated[@]} updated, ${#orphaned[@]} orphaned)"
  else
    # Output to stdout
    cat "$existing_tmp"
    rm -f "$existing_tmp"
  fi
}

main "$@"
