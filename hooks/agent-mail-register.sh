#!/usr/bin/env bash
# SessionStart hook: auto-register with MCP Agent Mail
#
# Calls macro_start_session to:
#   1. Ensure the project exists
#   2. Register this session as an agent (auto-generated name)
#   3. Fetch the inbox
#
# Injects the agent name + inbox status as additionalContext so the LLM
# knows its identity for multi-agent coordination.
#
# Gracefully no-ops if Agent Mail is not running.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck source=hooks/lib.sh
source "${SCRIPT_DIR}/lib.sh"

AGENT_MAIL_URL="${AGENT_MAIL_URL:-http://127.0.0.1:8765/mcp/}"
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-}"

# Skip if no project directory (shouldn't happen, but be safe)
if [[ -z "$PROJECT_DIR" ]]; then
    exit 0
fi

# Read stdin to consume it (required by hook protocol), extract session info
input=$(cat)
session_id=$(printf '%s' "$input" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id','unknown'))" 2>/dev/null || echo "unknown")

# Check if Agent Mail is reachable (fast fail — 2s timeout)
if ! curl -sf --max-time 2 "${AGENT_MAIL_URL}" -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":"health","method":"tools/call","params":{"name":"health_check","arguments":{}}}' \
    >/dev/null 2>&1; then
    # Agent Mail not running — silently skip
    exit 0
fi

# Build JSON payload safely using python3 to escape values
json_payload=$(python3 -c "
import json, sys
print(json.dumps({
    'jsonrpc': '2.0',
    'id': 'register-' + sys.argv[1],
    'method': 'tools/call',
    'params': {
        'name': 'macro_start_session',
        'arguments': {
            'human_key': sys.argv[2],
            'program': 'claude-code',
            'model': 'claude-opus-4-6',
            'task_description': 'session ' + sys.argv[1]
        }
    }
}))" "$session_id" "$PROJECT_DIR" 2>/dev/null) || {
    exit 0
}

# Call macro_start_session
response=$(curl -sf --max-time 5 "${AGENT_MAIL_URL}" \
    -H "Content-Type: application/json" \
    -d "$json_payload" 2>/dev/null) || {
    # Registration failed — silently skip
    exit 0
}

# Extract agent name and inbox from response
agent_info=$(printf '%s' "$response" | python3 -c "
import json, sys
try:
    r = json.load(sys.stdin)
    # structuredContent is the parsed version; fall back to text content
    sc = r.get('result', {}).get('structuredContent')
    if not sc:
        text = r['result']['content'][0]['text']
        sc = json.loads(text)
    name = sc['agent']['name']
    inbox = sc.get('inbox', [])
    inbox_count = len(inbox)
    reservations = sc.get('file_reservations', {})
    conflicts = reservations.get('conflicts', [])

    # Build summary
    parts = [f'Agent Mail identity: **{name}** on project \`{sc[\"project\"][\"human_key\"]}\`']
    if inbox_count > 0:
        subjects = [m.get('subject', '(no subject)') for m in inbox[:5]]
        parts.append(f'{inbox_count} message(s) in inbox: ' + ', '.join(subjects))
    else:
        parts.append('Inbox empty.')
    if conflicts:
        conflict_paths = [c.get('path', '?') for c in conflicts]
        parts.append(f'File reservation CONFLICTS: {conflict_paths}')

    print('\\n'.join(parts))
except Exception as e:
    print(f'Agent Mail registered (details unavailable: {e})')
" 2>/dev/null) || agent_info="Agent Mail registered (parse error)"

context_escaped=$(escape_for_json "$agent_info")

cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "${context_escaped}"
  }
}
EOF

exit 0
