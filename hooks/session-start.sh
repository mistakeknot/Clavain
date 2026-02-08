#!/usr/bin/env bash
# SessionStart hook for Clavain plugin

set -euo pipefail

# Determine plugin root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# shellcheck source=hooks/lib.sh
source "${SCRIPT_DIR}/lib.sh"

# Read using-clavain content
using_clavain_content=$(cat "${PLUGIN_ROOT}/skills/using-clavain/SKILL.md" 2>&1 || echo "Error reading using-clavain skill")

using_clavain_escaped=$(escape_for_json "$using_clavain_content")

# Detect companion plugins and build integration context
companions=""

# Codex dispatch — resolve dispatch.sh path for codex-first mode
dispatch_path=$(find "${PLUGIN_ROOT}/scripts" -name dispatch.sh 2>/dev/null | head -1)
if [[ -n "$dispatch_path" ]]; then
    companions="${companions}\\n- **codex dispatch**: dispatch.sh at \`${dispatch_path}\`"
fi

# Beads — detect if project uses beads
if [[ -d "${PLUGIN_ROOT}/../../.beads" ]] || [[ -d ".beads" ]]; then
    companions="${companions}\\n- **beads**: .beads/ detected — use \`bd\` for task tracking (not TaskCreate)"
fi

# Agent Mail — check if server is running
if curl -s -o /dev/null -w '' --connect-timeout 1 http://127.0.0.1:8765/health 2>/dev/null; then
    companions="${companions}\\n- **agent-mail**: server running at localhost:8765"
fi

# Gurgeh — needed for flux-drive T1 agents
if ls ~/.claude/plugins/cache/interagency-marketplace/gurgeh-plugin/*/agents/ >/dev/null 2>&1; then
    companions="${companions}\\n- **gurgeh-plugin**: T1 codebase-aware agents available for /flux-drive"
fi

# Oracle — check if available for cross-AI review
if command -v oracle &>/dev/null && pgrep -f "Xvfb :99" &>/dev/null; then
    companions="${companions}\\n- **oracle**: available for cross-AI review (GPT-5.2 Pro)"
fi

companion_context=""
if [[ -n "$companions" ]]; then
    companion_context="\\n\\n**Detected companions:**${companions}"
fi

# Check upstream staleness (local file check only — no network calls)
upstream_warning=""
VERSIONS_FILE="${PLUGIN_ROOT}/docs/upstream-versions.json"
if [[ -f "$VERSIONS_FILE" ]]; then
    # Check if the file is older than 7 days
    file_age_days=$(( ($(date +%s) - $(stat -c %Y "$VERSIONS_FILE" 2>/dev/null || echo 0)) / 86400 ))
    if [[ $file_age_days -gt 7 ]]; then
        upstream_warning="\\n\\n**Upstream sync stale** (${file_age_days} days since last check). Run \`/clavain:upstream-sync\` to check for updates from beads, oracle, agent-mail, and other upstream tools."
    fi
else
    upstream_warning="\\n\\n**No upstream baseline found.** Run \`bash scripts/upstream-check.sh --update\` in the Clavain repo to establish baseline."
fi

# Output context injection as JSON
cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "<EXTREMELY_IMPORTANT>\nYou have Clavain.\n\n**Below is the full content of your 'clavain:using-clavain' skill - your introduction to using skills. For all other skills, use the 'Skill' tool:**\n\n${using_clavain_escaped}${companion_context}${upstream_warning}\n</EXTREMELY_IMPORTANT>"
  }
}
EOF

exit 0
