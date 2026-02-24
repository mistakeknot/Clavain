#!/usr/bin/env bash
# modpack-install.sh — Automated plugin installation driven by agent-rig.json
#
# Usage:
#   modpack-install.sh [--dry-run] [--check-only] [--quiet] [--category=CATEGORY]
#
# Categories: required, recommended, optional, conflicts, all (default: all)
# --dry-run:    Show what would be installed without making changes
# --check-only: Alias for --dry-run
# --quiet:      Suppress progress output, emit JSON only
#
# Output: JSON summary to stdout (progress to stderr when not quiet)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RIG_FILE="${SCRIPT_DIR}/../agent-rig.json"
CACHE_DIR="${HOME}/.claude/plugins/cache"

# Parse arguments
DRY_RUN=false
QUIET=false
CATEGORY="all"

for arg in "$@"; do
    case "$arg" in
        --dry-run|--check-only) DRY_RUN=true ;;
        --quiet) QUIET=true ;;
        --category=*) CATEGORY="${arg#--category=}" ;;
        --help|-h)
            sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
    esac
done

# Validate
if [[ ! -f "$RIG_FILE" ]]; then
    echo '{"error": "agent-rig.json not found at '"$RIG_FILE"'"}'
    exit 1
fi

if ! command -v jq &>/dev/null; then
    echo '{"error": "jq is required but not installed"}'
    exit 1
fi

# Result accumulators
installed=()
already_present=()
failed=()
disabled=()
already_disabled=()
optional_available=()

log() {
    if [[ "$QUIET" != true ]]; then
        echo "$@" >&2
    fi
}

# Check if a plugin is installed by looking in the cache
is_installed() {
    local source="$1"
    local name="${source%%@*}"
    local marketplace="${source#*@}"

    # Check marketplace-specific path first, then any marketplace
    if [[ -d "${CACHE_DIR}/${marketplace}/${name}" ]]; then
        return 0
    fi
    # Also check without marketplace qualifier
    for d in "${CACHE_DIR}"/*/"${name}"; do
        if [[ -d "$d" ]]; then
            return 0
        fi
    done
    return 1
}

# Check if a plugin is explicitly disabled in settings.json
is_disabled() {
    local source="$1"
    local settings="${HOME}/.claude/settings.json"
    if [[ ! -f "$settings" ]]; then
        return 1
    fi
    local val
    val=$(jq -r --arg s "$source" '.enabledPlugins[$s] // "absent"' "$settings" 2>/dev/null)
    [[ "$val" == "false" ]]
}

# Install a single plugin
install_plugin() {
    local source="$1"

    if is_installed "$source"; then
        already_present+=("$source")
        log "  [skip] $source (already installed)"
        return 0
    fi

    if [[ "$DRY_RUN" == true ]]; then
        installed+=("$source")
        log "  [would install] $source"
        return 0
    fi

    log "  [installing] $source ..."
    local output
    if output=$(claude plugin install "$source" 2>&1); then
        installed+=("$source")
        log "  [installed] $source"
        # Show any output from claude CLI (it may be silent — see GitHub #3)
        if [[ -n "$output" ]]; then
            log "    $output"
        fi
    else
        failed+=("$source")
        log "  [FAILED] $source"
        if [[ -n "$output" ]]; then
            log "    $output"
        fi
    fi
}

# Disable a conflicting plugin
disable_plugin() {
    local source="$1"

    if is_disabled "$source"; then
        already_disabled+=("$source")
        log "  [skip] $source (already disabled)"
        return 0
    fi

    if [[ "$DRY_RUN" == true ]]; then
        disabled+=("$source")
        log "  [would disable] $source"
        return 0
    fi

    log "  [disabling] $source ..."
    local output
    if output=$(claude plugin disable "$source" 2>&1); then
        disabled+=("$source")
        log "  [disabled] $source"
    else
        # Not fatal — plugin may not be installed at all
        log "  [skip] $source (not installed, nothing to disable)"
    fi
}

# Process a category from agent-rig.json
process_category() {
    local cat="$1"
    local sources

    case "$cat" in
        core)
            sources=$(jq -r '.plugins.core.source' "$RIG_FILE")
            ;;
        required|recommended|optional|infrastructure)
            sources=$(jq -r ".plugins.${cat}[]?.source" "$RIG_FILE")
            ;;
        conflicts)
            sources=$(jq -r '.plugins.conflicts[]?.source' "$RIG_FILE")
            ;;
        *)
            log "Unknown category: $cat"
            return 1
            ;;
    esac

    if [[ -z "$sources" ]]; then
        return 0
    fi

    while IFS= read -r source; do
        [[ -z "$source" ]] && continue
        if [[ "$cat" == "conflicts" ]]; then
            disable_plugin "$source"
        elif [[ "$cat" == "optional" ]]; then
            # For optional: just report what's available (not installed)
            if ! is_installed "$source"; then
                optional_available+=("$source")
                log "  [optional] $source (available)"
            else
                already_present+=("$source")
                log "  [skip] $source (already installed)"
            fi
        else
            install_plugin "$source"
        fi
    done <<< "$sources"
}

# Main
log "Clavain Modpack Install"
log "  Manifest: $RIG_FILE"
log "  Mode: $(if $DRY_RUN; then echo 'dry-run'; else echo 'live'; fi)"
log ""

case "$CATEGORY" in
    all)
        log "=== Core ==="
        process_category "core"
        log ""
        log "=== Required ==="
        process_category "required"
        log ""
        log "=== Recommended ==="
        process_category "recommended"
        log ""
        log "=== Optional (detection only) ==="
        process_category "optional"
        log ""
        log "=== Conflicts ==="
        process_category "conflicts"
        ;;
    required|recommended|optional|infrastructure|conflicts|core)
        log "=== ${CATEGORY^} ==="
        process_category "$CATEGORY"
        ;;
    *)
        echo '{"error": "Unknown category: '"$CATEGORY"'. Use: required, recommended, optional, infrastructure, conflicts, all"}'
        exit 1
        ;;
esac

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

# Use a heredoc approach to avoid settings-bloat from inline jq
installed_json=$(json_array "${installed[@]}")
present_json=$(json_array "${already_present[@]}")
failed_json=$(json_array "${failed[@]}")
disabled_json=$(json_array "${disabled[@]}")
already_disabled_json=$(json_array "${already_disabled[@]}")
optional_json=$(json_array "${optional_available[@]}")

if [[ "$DRY_RUN" == true ]]; then
    jq -n \
        --argjson would_install "$installed_json" \
        --argjson already_present "$present_json" \
        --argjson would_disable "$disabled_json" \
        --argjson already_disabled "$already_disabled_json" \
        --argjson optional_available "$optional_json" \
        '{would_install: $would_install, already_present: $already_present, would_disable: $would_disable, already_disabled: $already_disabled, optional_available: $optional_available}'
else
    jq -n \
        --argjson installed "$installed_json" \
        --argjson already_present "$present_json" \
        --argjson failed "$failed_json" \
        --argjson disabled "$disabled_json" \
        --argjson already_disabled "$already_disabled_json" \
        --argjson optional_available "$optional_json" \
        '{installed: $installed, already_present: $already_present, failed: $failed, disabled: $disabled, already_disabled: $already_disabled, optional_available: $optional_available}'
fi

log "Done."
