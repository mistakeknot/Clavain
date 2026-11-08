#!/usr/bin/env bash
# phase-evidence.sh — observe-mode phase evidence hook (mk-4xzwm.1).
# Usage: phase-evidence.sh pre|post|stop. Records tool use in a per-session
# ledger and warns on missing evidence. Never blocks: exits 0 on every path.
# CLAVAIN_PHASE_EVIDENCE_MODE=off disables it.
[[ "${CLAVAIN_PHASE_EVIDENCE_MODE:-observe}" == off ]] && exit 0
exec python3 "${BASH_SOURCE[0]%/*}/../scripts/phase-evidence.py" hook "${1:-post}" 2>/dev/null || exit 0
