#!/usr/bin/env bash
# shellcheck: sourced library — no set -euo pipefail (would alter caller's error policy)
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
    CLAVAIN_PHASES=(brainstorm brainstorm-reviewed strategized planned plan-reviewed executing shipping reflect done)
    VALID_TRANSITIONS=()
    ARTIFACT_PHASE_DIRS=()
    is_valid_transition() { return 1; }
    _pe_bounded() {
        # Run phase-evidence.py with a 5 s deadline that needs no `timeout`
        # command: the child runs in the background and a bash watchdog kills
        # it. Its stderr is read from a temp file and only the intended
        # warning lines are relayed, so a python start-up failure stays silent.
        local tmp pid dog line show=0
        tmp="$(mktemp "${TMPDIR:-/tmp}/clavain-phase-evidence.XXXXXX" 2>/dev/null)" || return 0
        python3 "$@" </dev/null >/dev/null 2>"$tmp" &
        pid=$!
        ( read -rt 5 <> <(:); kill -9 "$pid" ) >/dev/null 2>&1 &
        dog=$!
        { wait "$pid"; } 2>/dev/null || true
        kill "$dog" 2>/dev/null || true
        { wait "$dog"; } 2>/dev/null || true
        while IFS= read -r line; do
            if [[ "$line" == 'phase evidence missing (observe mode, not blocking): '* ]]; then
                show=1; printf '%s\n' "$line" >&2
            elif [[ "$show" == 1 && "$line" == '  - '* ]]; then
                printf '%s\n' "$line" >&2
            else
                show=0
            fi
        done <"$tmp"
        rm -f "$tmp"
        return 0
    }
    # Observe mode (mk-4xzwm.1): report missing phase evidence for the OODARC
    # leg the target phase maps to, but never block (always returns 0).
    check_phase_gate() {
        local _pe="${_GATES_SHIM_DIR}/../scripts/phase-evidence.py"
        if [[ -f "$_pe" ]] && command -v python3 >/dev/null 2>&1; then
            _pe_bounded "$_pe" check --phase "${2:-}"
        fi
        return 0
    }
    advance_phase() { return 0; }
    phase_get_with_fallback() { echo ""; }
    phase_set() { return 0; }
    phase_get() { echo ""; }
    phase_infer_bead() { echo ""; }
fi
