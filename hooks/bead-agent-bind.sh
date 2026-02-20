#!/usr/bin/env bash
# PostToolUse:Bash hook — bind agent identity to beads claimed with bd update/claim.
# When a session claims a bead (status=in_progress or --claim), this records the
# INTERMUTE_AGENT_ID in bead metadata so other sessions see who's working on what.
#
# Fast-path: exits immediately if not a bd command or no agent ID.

set -euo pipefail

# Fast guards — exit before reading stdin if possible
[[ -n "${INTERMUTE_AGENT_ID:-}" ]] || exit 0
command -v bd &>/dev/null || exit 0

# Read hook input
INPUT=$(cat)

# Extract the command that was run
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null) || exit 0
[[ -n "$COMMAND" ]] || exit 0

# Only act on bd update/claim commands that set in_progress or use --claim
case "$COMMAND" in
    *bd\ update*--status=in_progress*|*bd\ update*--claim*|*bd\ claim*)
        ;;
    *)
        exit 0
        ;;
esac

# Check if command succeeded
EXIT_CODE=$(echo "$INPUT" | jq -r '.tool_result.exit_code // .stdout // ""' 2>/dev/null) || exit 0

# Extract issue ID from the command (first argument after bd update/claim)
ISSUE_ID=$(echo "$COMMAND" | grep -oP '(?<=bd (?:update|claim) )\S+' 2>/dev/null) || exit 0
[[ -n "$ISSUE_ID" ]] || exit 0

# Check if command succeeded — don't bind on failed claims
[[ "$EXIT_CODE" == "0" || -z "$EXIT_CODE" ]] || exit 0

# Check existing agent metadata for conflicts
CURRENT_META=$(bd show "$ISSUE_ID" --json 2>/dev/null | jq -r '.metadata // empty' 2>/dev/null) || CURRENT_META=""
EXISTING_AGENT=$(echo "$CURRENT_META" | jq -r '.agent_id // empty' 2>/dev/null) || EXISTING_AGENT=""

# If same agent already bound, nothing to do
if [[ -n "$EXISTING_AGENT" && "$EXISTING_AGENT" == "$INTERMUTE_AGENT_ID" ]]; then
    exit 0
fi

# If a *different* agent is already bound, check if they're still online and warn
if [[ -n "$EXISTING_AGENT" && "$EXISTING_AGENT" != "$INTERMUTE_AGENT_ID" ]]; then
    EXISTING_NAME=$(echo "$CURRENT_META" | jq -r '.agent_name // empty' 2>/dev/null) || EXISTING_NAME="${EXISTING_AGENT:0:8}"
    [[ -n "$EXISTING_NAME" ]] || EXISTING_NAME="${EXISTING_AGENT:0:8}"
    OVERLAP_WARNING=""

    # Check if the other agent is still online
    INTERMUTE_URL="${INTERMUTE_URL:-http://127.0.0.1:7338}"
    PROJECT=$(basename "$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null) || PROJECT=""
    if [[ -n "$PROJECT" ]]; then
        AGENTS_JSON=$(curl -sf --connect-timeout 1 --max-time 2 "${INTERMUTE_URL}/api/agents?project=${PROJECT}" 2>/dev/null) || AGENTS_JSON=""
        if [[ -n "$AGENTS_JSON" ]] && command -v jq &>/dev/null; then
            IS_ONLINE=$(echo "$AGENTS_JSON" | jq -r --arg aid "$EXISTING_AGENT" '.agents[]? | select(.id == $aid) | .id' 2>/dev/null) || IS_ONLINE=""
            if [[ -n "$IS_ONLINE" ]]; then
                OVERLAP_WARNING="Bead ${ISSUE_ID} is already claimed by agent ${EXISTING_NAME} (online). You may be duplicating work."
                # Notify the other agent about the overlap
                MSG_PAYLOAD=$(jq -nc \
                    --arg from "$INTERMUTE_AGENT_ID" \
                    --arg to "$EXISTING_AGENT" \
                    --arg project "$PROJECT" \
                    --arg subject "overlap:${ISSUE_ID}" \
                    --arg body "Agent ${INTERMUTE_AGENT_NAME:-unknown} is also claiming bead ${ISSUE_ID}." \
                    '{from:$from,to:[$to],project:$project,subject:$subject,body:$body}' 2>/dev/null) || MSG_PAYLOAD=""
                if [[ -n "$MSG_PAYLOAD" ]]; then
                    curl -sf --max-time 2 -X POST \
                        -H "Content-Type: application/json" \
                        -d "$MSG_PAYLOAD" \
                        "${INTERMUTE_URL}/api/messages" 2>/dev/null || true
                fi
            else
                OVERLAP_WARNING="Bead ${ISSUE_ID} was previously claimed by agent ${EXISTING_NAME} (now offline). Re-binding to you."
            fi
        fi
    fi

    if [[ -n "$OVERLAP_WARNING" ]]; then
        cat <<ENDJSON
{"additionalContext": "INTERLOCK: ${OVERLAP_WARNING}"}
ENDJSON
    fi
fi

# Bind agent identity to bead metadata
AGENT_NAME="${INTERMUTE_AGENT_NAME:-unknown}"
bd update "$ISSUE_ID" --metadata "{\"agent_id\":\"${INTERMUTE_AGENT_ID}\",\"agent_name\":\"${AGENT_NAME}\"}" 2>/dev/null || true

exit 0
