#!/usr/bin/env bash
# DEPRECATED: Gate enforcement now uses ic gate check/override via lib-intercore.sh.
# This shim is retained for backward compatibility with non-sprint code that
# still calls check_phase_gate or advance_phase directly.
# Sprint gate enforcement goes through enforce_gate() in lib-sprint.sh → intercore_gate_check.
#
# Shim: delegates to interphase plugin if installed, otherwise provides no-op stubs.
# Original implementation lives in the interphase companion plugin.

# Guard against double-sourcing
[[ -n "${_GATES_LOADED:-}" ]] && return 0
_GATES_LOADED=1

_GATES_SHIM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${_GATES_SHIM_DIR}/lib.sh"

_BEADS_ROOT=$(_discover_beads_plugin)

if [[ -n "$_BEADS_ROOT" && -f "${_BEADS_ROOT}/hooks/lib-gates.sh" ]]; then
    # Delegate to interphase plugin
    unset _GATES_LOADED  # let the real library set its own guard
    export GATES_PROJECT_DIR="${GATES_PROJECT_DIR:-.}"; source "${_BEADS_ROOT}/hooks/lib-gates.sh"
else
    # No-op stubs — all functions are fail-safe (never block workflow)
    CLAVAIN_PHASES=(brainstorm brainstorm-reviewed strategized planned plan-reviewed executing shipping done)
    VALID_TRANSITIONS=()
    ARTIFACT_PHASE_DIRS=()
    is_valid_transition() { return 1; }
    check_phase_gate() { return 0; }
    advance_phase() { return 0; }
    phase_get_with_fallback() { echo ""; }
    phase_set() { return 0; }
    phase_get() { echo ""; }
    phase_infer_bead() { echo ""; }
fi
