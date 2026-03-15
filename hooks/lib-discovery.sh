#!/usr/bin/env bash
# shellcheck: sourced library — no set -euo pipefail (would alter caller's error policy)
# Shim: delegates to interphase plugin if installed, otherwise provides no-op stubs.
# Original implementation lives in the interphase companion plugin.

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
else
    # No-op stubs — all functions return safe defaults
    discovery_scan_beads() { echo "DISCOVERY_UNAVAILABLE"; }
    infer_bead_action() { echo "brainstorm|"; }
    discovery_log_selection() { return 0; }
fi
