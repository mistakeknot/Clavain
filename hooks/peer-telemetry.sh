#!/usr/bin/env bash
# peer-telemetry.sh — Append one JSONL record per session with peer-rig detection state.
#
# Opt out:
#   - env: CLAVAIN_PEER_TELEMETRY=0
#   - config: telemetry.peers: false in ~/.clavain/config.json
#
# Capture point is session start; we record which peer rigs are present, not
# which using-* skill ultimately won the routing decision (that requires a
# session-end hook which is fragile under crash and `/clear` paths).
#
# Used to gate B'/C' scope expansion (sylveste-fj1w / sylveste-yofd).
set -euo pipefail

[[ "${CLAVAIN_PEER_TELEMETRY:-1}" == "0" ]] && exit 0
if [[ -f "$HOME/.clavain/config.json" ]] && \
   jq -e '.telemetry.peers == false' "$HOME/.clavain/config.json" >/dev/null 2>&1; then
    exit 0
fi

LOG="${CLAVAIN_PEER_TELEMETRY_FILE:-$HOME/.clavain/peer-telemetry.jsonl}"
mkdir -p "$(dirname "$LOG")" 2>/dev/null || exit 0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RIG="$SCRIPT_DIR/../agent-rig.json"
[[ -f "$RIG" ]] || exit 0

peers_detected="[]"
if command -v jq &>/dev/null; then
    peers_detected=$(jq -c '[.plugins.peers[]?.source]' "$RIG" 2>/dev/null || echo "[]")
fi

SID="${CLAUDE_SESSION_ID:-${CODEX_SESSION_ID:-unknown}}"
SID_HASH=$(printf '%s' "$SID" | sha256sum | cut -c1-12)

TS=$(date +%s)
RECORD=$(jq -nc \
    --arg ts "$TS" \
    --arg sid "$SID_HASH" \
    --argjson peers "$peers_detected" \
    '{ts:($ts|tonumber), session:$sid, peers_detected:$peers, using_skill_invoked:null}')

echo "$RECORD" >> "$LOG" 2>/dev/null || true
