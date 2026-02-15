#!/usr/bin/env bash
# shadow-review.sh — dispatch a single review agent and capture findings
#
# Usage: shadow-review.sh <agent_subtype> <input_path> <output_file>
#
# Dispatches the agent via Claude Code Task tool pattern (codex exec),
# captures structured findings output.

set -euo pipefail

AGENT="$1"
INPUT="$2"
OUTPUT="$3"

# Agent display name (strip prefix)
AGENT_NAME="${AGENT##*:}"

PROMPT_FILE=$(mktemp /tmp/shadow-review-XXXXXX.md)
trap 'rm -f "$PROMPT_FILE"' EXIT INT TERM

cat > "$PROMPT_FILE" << PROMPT_EOF
You are a code review agent. Review the following input and report findings.

**Input to review:** $INPUT

**Instructions:**
1. Read the input (file or directory)
2. Identify issues by severity: P0 (critical/wrong), P1 (important/should fix), P2 (minor/nice to have)
3. Focus on your domain expertise as $AGENT_NAME

**Output format — write ONLY valid JSON to your output, no markdown, no explanation:**
{"agent":"$AGENT_NAME","findings":[{"severity":"P0","title":"...","section":"..."}]}
PROMPT_EOF

# Dispatch via codex exec
DISPATCH=$(find ~/.claude/plugins/cache -path '*/clavain/*/scripts/dispatch.sh' 2>/dev/null | head -1)
if [[ -z "$DISPATCH" ]]; then
    DISPATCH=$(find ~/projects/Clavain -name dispatch.sh -path '*/scripts/*' 2>/dev/null | head -1)
fi

if [[ -n "$DISPATCH" ]]; then
    if ! bash "$DISPATCH" \
        --prompt-file "$PROMPT_FILE" \
        -C "$(pwd)" \
        --name "shadow-${AGENT_NAME}" \
        -o "$OUTPUT" \
        -s read-only \
        --tier fast \
        2>/tmp/shadow-review-err-$$.log; then
        echo "WARN: dispatch.sh failed for $AGENT_NAME (see /tmp/shadow-review-err-$$.log)" >&2
    fi
    rm -f "/tmp/shadow-review-err-$$.log"
else
    echo "WARN: dispatch.sh not found, skipping agent $AGENT_NAME" >&2
fi
