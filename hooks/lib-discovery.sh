#!/usr/bin/env bash
# shellcheck: sourced library — no set -euo pipefail (would alter caller's error policy)
# Shim: delegates to interphase plugin if installed, otherwise provides no-op stubs.
# Original implementation lives in the interphase companion plugin.
#
# DISCOVERY_ROOTS support:
#   Set DISCOVERY_ROOTS to a colon-separated list of additional project directories
#   to scan alongside the current project (DISCOVERY_PROJECT_DIR).
#   Example: DISCOVERY_ROOTS="/home/mk/projects/Foo:/home/mk/projects/Bar"
#
#   When set, discovery_scan_beads runs once per root directory and merges the
#   results into a single JSON array sorted by score DESC.  Each result gains a
#   "project_root" field so consumers can show which project a bead belongs to.
#
#   Implementation:
#     After sourcing interphase the shim wraps discovery_scan_beads.  For each
#     root in DISCOVERY_ROOTS it temporarily sets DISCOVERY_PROJECT_DIR and calls
#     the real _discovery_scan_beads_single, then merges via jq and re-sorts.
#     DISCOVERY_LANE filtering is already applied per-root inside the real function.
#
#   bd cross-project support:
#     bd list operates on the .beads directory found relative to CWD (or via
#     BEADS_DIR env).  To query a different project we either (a) set BEADS_DIR
#     or (b) cd to the root before invoking bd.  The wrapper uses a subshell
#     with `cd` for isolation so the caller's CWD is never affected.

# Guard against double-sourcing
[[ -n "${_DISCOVERY_LOADED:-}" ]] && return 0
_DISCOVERY_LOADED=1

_DISCOVERY_SHIM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${_DISCOVERY_SHIM_DIR}/lib.sh"

_BEADS_ROOT=$(_discover_beads_plugin)

if [[ -n "$_BEADS_ROOT" && -f "${_BEADS_ROOT}/hooks/lib-discovery.sh" ]]; then
    # Delegate to interphase plugin
    unset _DISCOVERY_LOADED  # let the real library set its own guard
    export DISCOVERY_PROJECT_DIR="${DISCOVERY_PROJECT_DIR:-.}"; source "${_BEADS_ROOT}/hooks/lib-discovery.sh"

    # ── DISCOVERY_ROOTS wrapper ───────────────────────────────────────────────
    # Only wrap when DISCOVERY_ROOTS is non-empty; otherwise behaviour is
    # identical to the bare interphase implementation.
    #
    # We rename the real function so the wrapper can call it, then define a new
    # discovery_scan_beads that fans out across all roots and merges.
    if [[ -n "${DISCOVERY_ROOTS:-}" ]]; then
        # Alias the real scanner under a private name (idempotent — guard second source)
        if ! declare -f _discovery_scan_beads_single &>/dev/null; then
            eval "$(declare -f discovery_scan_beads | sed 's/^discovery_scan_beads/_discovery_scan_beads_single/')"
        fi

        discovery_scan_beads() {
            local primary_dir="${DISCOVERY_PROJECT_DIR:-.}"

            # Collect results from the primary project
            local primary_results
            primary_results=$(DISCOVERY_PROJECT_DIR="$primary_dir" _discovery_scan_beads_single)

            # Tag each result with its project root (abs path)
            local primary_abs
            primary_abs="$(cd "$primary_dir" 2>/dev/null && pwd || echo "$primary_dir")"

            case "$primary_results" in
                DISCOVERY_UNAVAILABLE|DISCOVERY_ERROR)
                    primary_results="[]"
                    ;;
                *)
                    if echo "$primary_results" | jq empty 2>/dev/null; then
                        primary_results=$(echo "$primary_results" | jq \
                            --arg root "$primary_abs" \
                            '[.[] | .project_root = $root]')
                    else
                        primary_results="[]"
                    fi
                    ;;
            esac

            # Merge results from each DISCOVERY_ROOTS entry
            local merged="$primary_results"
            local root
            # Split colon-separated list
            IFS=: read -ra _DISCOVERY_EXTRA_ROOTS <<< "$DISCOVERY_ROOTS"
            for root in "${_DISCOVERY_EXTRA_ROOTS[@]}"; do
                [[ -z "$root" ]] && continue
                # Skip if same as primary (avoid duplicates)
                local root_abs
                root_abs="$(cd "$root" 2>/dev/null && pwd 2>/dev/null || echo "$root")"
                [[ "$root_abs" == "$primary_abs" ]] && continue

                # Run the real scanner in a subshell so DISCOVERY_PROJECT_DIR
                # and CWD changes don't leak back to the caller.
                local extra_results
                extra_results=$(
                    cd "$root" 2>/dev/null || { echo "[]"; exit 0; }
                    DISCOVERY_PROJECT_DIR="$root" _discovery_scan_beads_single
                )

                case "$extra_results" in
                    DISCOVERY_UNAVAILABLE|DISCOVERY_ERROR)
                        continue
                        ;;
                    *)
                        if echo "$extra_results" | jq empty 2>/dev/null; then
                            extra_results=$(echo "$extra_results" | jq \
                                --arg root "$root_abs" \
                                '[.[] | .project_root = $root]')
                            merged=$(jq -n \
                                --argjson a "$merged" \
                                --argjson b "$extra_results" \
                                '$a + $b | sort_by(-.score, .id)')
                        fi
                        ;;
                esac
            done

            echo "$merged"
        }
    fi
    # ── end DISCOVERY_ROOTS wrapper ───────────────────────────────────────────
else
    # No-op stubs — all functions return safe defaults
    discovery_scan_beads() { echo "DISCOVERY_UNAVAILABLE"; }
    infer_bead_action() { echo "brainstorm|"; }
    discovery_log_selection() { return 0; }
fi
