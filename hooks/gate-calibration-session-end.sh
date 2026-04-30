#!/usr/bin/env bash
# SessionEnd hook - recalibrates autonomous learning loops.
# Exit 0 always: never block session exit on calibration failure.
set -u

_run_bounded() {
    local seconds="$1"
    shift

    if command -v timeout >/dev/null 2>&1; then
        timeout "$seconds" "$@" 2>&1 | head -20 || true
    else
        "$@" 2>&1 | head -20 || true
    fi
}

_run_bounded 10 clavain-cli calibrate-gate-tiers --auto
_run_bounded 10 clavain-cli calibrate-phase-costs
_run_bounded 5 clavain-cli calibration-streak record-session-end

exit 0
