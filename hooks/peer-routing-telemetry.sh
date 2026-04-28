#!/usr/bin/env bash
# peer-routing-telemetry.sh — PostToolUse(Skill) hook recording which namespace
# Claude routes to when invoking a Skill tool. Sharpens sylveste-fj1w (B′)
# unblock decision by distinguishing peer-installed-but-unused from
# peer-installed-and-routed-to.
#
# Schema: {ts, session, namespace, skill_name}
# Privacy: no args, no prompt content, no tool result.
# Opt out: CLAVAIN_PEER_TELEMETRY=0 (shared with peer-telemetry.sh) or
#          telemetry.peers: false in ~/.clavain/config.json
set -uo pipefail
trap 'exit 0' ERR

[[ "${CLAVAIN_PEER_TELEMETRY:-1}" == "0" ]] && exit 0
if [[ -f "$HOME/.clavain/config.json" ]] && \
   jq -e '.telemetry.peers == false' "$HOME/.clavain/config.json" >/dev/null 2>&1; then
    exit 0
fi

INPUT=$(cat)
[[ -n "$INPUT" ]] || exit 0

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null) || exit 0
[[ "$TOOL_NAME" == "Skill" ]] || exit 0

SKILL=$(echo "$INPUT" | jq -r '.tool_input.skill // empty' 2>/dev/null) || exit 0
[[ -n "$SKILL" ]] || exit 0

# Parse namespace:name. Skills without ":" prefix are uncategorized — record
# namespace as empty so analysis can still count them.
if [[ "$SKILL" == *":"* ]]; then
    NAMESPACE="${SKILL%%:*}"
    SKILL_NAME="${SKILL#*:}"
else
    NAMESPACE=""
    SKILL_NAME="$SKILL"
fi

LOG="${CLAVAIN_PEER_ROUTING_FILE:-$HOME/.clavain/peer-routing.jsonl}"
mkdir -p "$(dirname "$LOG")" 2>/dev/null || exit 0

SID="${CLAUDE_SESSION_ID:-${CODEX_SESSION_ID:-unknown}}"
SID_HASH=$(printf '%s' "$SID" | sha256sum | cut -c1-12)

TS=$(date +%s)
RECORD=$(jq -nc \
    --arg ts "$TS" \
    --arg sid "$SID_HASH" \
    --arg ns "$NAMESPACE" \
    --arg name "$SKILL_NAME" \
    '{ts:($ts|tonumber), session:$sid, namespace:$ns, skill_name:$name}')

echo "$RECORD" >> "$LOG" 2>/dev/null || true
