#!/usr/bin/env bash
# modpack-associate.sh — Associate autodiscovered plugins with their marketplace entries
#
# Plugins loaded via monorepo autodiscovery (walking .claude-plugin/plugin.json) appear
# in /plugin/installed but lack marketplace association in installed_plugins.json.
# This script reads the marketplace manifest and agent-rig.json to backfill entries.
#
# Usage:
#   modpack-associate.sh [--dry-run] [--quiet]
#
# --dry-run:  Show what would be associated without making changes
# --quiet:    Suppress progress output, emit JSON only
#
# Output: JSON summary to stdout (progress to stderr when not quiet)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RIG_FILE="${SCRIPT_DIR}/../agent-rig.json"
INSTALLED_FILE="${HOME}/.claude/plugins/installed_plugins.json"
CACHE_DIR="${HOME}/.claude/plugins/cache"
# Marketplace manifest — source of truth for plugin names/versions
MARKETPLACE_JSON="${SCRIPT_DIR}/../../../core/marketplace/.claude-plugin/marketplace.json"

# Parse arguments
DRY_RUN=false
QUIET=false

for arg in "$@"; do
    case "$arg" in
        --dry-run|--check-only) DRY_RUN=true ;;
        --quiet) QUIET=true ;;
        --help|-h)
            sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
    esac
done

# Validate
if ! command -v jq &>/dev/null; then
    echo '{"error": "jq is required but not installed"}'
    exit 1
fi

if [[ ! -f "$INSTALLED_FILE" ]]; then
    echo '{"error": "installed_plugins.json not found"}'
    exit 1
fi

log() {
    if [[ "$QUIET" != true ]]; then
        echo "$@" >&2
    fi
}

# Collect all interagency-marketplace plugin sources from agent-rig.json
get_rig_plugins() {
    if [[ ! -f "$RIG_FILE" ]]; then
        return
    fi
    # Extract all sources that end with @interagency-marketplace
    jq -r '
        [
            .plugins.core.source // empty,
            (.plugins.required[]?.source // empty),
            (.plugins.recommended[]?.source // empty),
            (.plugins.optional[]?.source // empty)
        ] | .[] | select(endswith("@interagency-marketplace"))
    ' "$RIG_FILE" 2>/dev/null
}

# Get version for a plugin from marketplace.json
get_marketplace_version() {
    local name="$1"
    if [[ -f "$MARKETPLACE_JSON" ]]; then
        jq -r --arg n "$name" '.plugins[] | select(.name==$n) | .version // empty' "$MARKETPLACE_JSON" 2>/dev/null
    fi
}

# Get version from the cache directory (newest version dir)
get_cache_version() {
    local name="$1"
    local cache_path="${CACHE_DIR}/interagency-marketplace/${name}"
    if [[ -d "$cache_path" ]]; then
        ls -d "$cache_path"/*/ 2>/dev/null | sort -V | tail -1 | xargs basename 2>/dev/null
    fi
}

# Check if a plugin already has a marketplace entry in installed_plugins.json
has_marketplace_entry() {
    local key="$1"
    jq -e --arg k "$key" '.plugins[$k] | length > 0' "$INSTALLED_FILE" &>/dev/null
}

# Result accumulators
associated=()
already_ok=()
no_cache=()
skipped=()

log "Clavain Marketplace Association"
log "  Mode: $(if $DRY_RUN; then echo 'dry-run'; else echo 'live'; fi)"
log ""

# Build list of plugins to check
declare -A plugins_to_check

# From agent-rig.json
while IFS= read -r source; do
    [[ -z "$source" ]] && continue
    name="${source%%@*}"
    plugins_to_check["$name"]=1
done < <(get_rig_plugins)

# Also scan the cache directory for any interagency-marketplace plugins not in the rig
for dir in "${CACHE_DIR}/interagency-marketplace"/*/; do
    [[ -d "$dir" ]] || continue
    name=$(basename "$dir")
    plugins_to_check["$name"]=1
done

log "Checking ${#plugins_to_check[@]} plugins..."
log ""

# Process each plugin
for name in $(echo "${!plugins_to_check[@]}" | tr ' ' '\n' | sort); do
    key="${name}@interagency-marketplace"

    # Already has an entry?
    if has_marketplace_entry "$key"; then
        already_ok+=("$name")
        log "  [ok]   $name"
        continue
    fi

    # Has cache directory?
    cache_path="${CACHE_DIR}/interagency-marketplace/${name}"
    if [[ ! -d "$cache_path" ]]; then
        no_cache+=("$name")
        log "  [skip] $name (no cache dir)"
        continue
    fi

    # Determine version: prefer marketplace.json, fall back to cache dir name
    version=$(get_marketplace_version "$name")
    if [[ -z "$version" ]]; then
        version=$(get_cache_version "$name")
    fi
    if [[ -z "$version" ]]; then
        skipped+=("$name")
        log "  [skip] $name (no version found)"
        continue
    fi

    # Determine install path
    install_path="${cache_path}/${version}"
    if [[ ! -d "$install_path" ]]; then
        # Version dir doesn't match — use whatever's there
        actual_version=$(get_cache_version "$name")
        if [[ -n "$actual_version" ]]; then
            install_path="${cache_path}/${actual_version}"
            version="$actual_version"
        else
            skipped+=("$name")
            log "  [skip] $name (no version dir in cache)"
            continue
        fi
    fi

    if [[ "$DRY_RUN" == true ]]; then
        associated+=("$name")
        log "  [would associate] $name v${version}"
        continue
    fi

    # Write the entry to installed_plugins.json
    now=$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")
    tmp=$(mktemp)
    if jq --arg key "$key" \
          --arg path "$install_path" \
          --arg ver "$version" \
          --arg now "$now" \
          '.plugins[$key] = [{
              scope: "user",
              installPath: $path,
              version: $ver,
              installedAt: $now,
              lastUpdated: $now
          }]' "$INSTALLED_FILE" > "$tmp" 2>/dev/null; then
        mv "$tmp" "$INSTALLED_FILE"
        associated+=("$name")
        log "  [associated] $name v${version}"
    else
        rm -f "$tmp"
        skipped+=("$name")
        log "  [FAILED] $name"
    fi
done

log ""

# Build JSON output
json_array() {
    local arr=("$@")
    if [[ ${#arr[@]} -eq 0 ]]; then
        echo "[]"
        return
    fi
    printf '%s\n' "${arr[@]}" | jq -R . | jq -s .
}

associated_json=$(json_array "${associated[@]}")
ok_json=$(json_array "${already_ok[@]}")
no_cache_json=$(json_array "${no_cache[@]}")
skipped_json=$(json_array "${skipped[@]}")

if [[ "$DRY_RUN" == true ]]; then
    jq -n \
        --argjson would_associate "$associated_json" \
        --argjson already_ok "$ok_json" \
        --argjson no_cache "$no_cache_json" \
        --argjson skipped "$skipped_json" \
        '{would_associate: $would_associate, already_ok: $already_ok, no_cache: $no_cache, skipped: $skipped}'
else
    jq -n \
        --argjson associated "$associated_json" \
        --argjson already_ok "$ok_json" \
        --argjson no_cache "$no_cache_json" \
        --argjson skipped "$skipped_json" \
        '{associated: $associated, already_ok: $already_ok, no_cache: $no_cache, skipped: $skipped}'
fi

log "Done."
