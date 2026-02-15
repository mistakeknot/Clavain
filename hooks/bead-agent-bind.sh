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

# Don't re-bind if already has our agent metadata
CURRENT_META=$(bd show "$ISSUE_ID" --format '{{.Metadata}}' 2>/dev/null) || CURRENT_META=""
if echo "$CURRENT_META" | grep -q "$INTERMUTE_AGENT_ID" 2>/dev/null; then
    exit 0
fi

# Bind agent identity to bead metadata
AGENT_NAME="${INTERMUTE_AGENT_NAME:-unknown}"
bd update "$ISSUE_ID" --metadata "{\"agent_id\":\"${INTERMUTE_AGENT_ID}\",\"agent_name\":\"${AGENT_NAME}\"}" 2>/dev/null || true

exit 0
