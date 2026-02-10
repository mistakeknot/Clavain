#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

SKILL_FILE="$PROJECT_ROOT/skills/flux-drive/SKILL.md"
EXPECTED_COUNT=6

if [[ ! -f "$SKILL_FILE" ]]; then
  echo "Mismatch: missing skill file: $SKILL_FILE"
  exit 1
fi

mapfile -t ROSTER_AGENTS < <(
  awk '
    /^### Plugin Agents \(clavain\)/ { in_section=1; next }
    /^### / && in_section { exit }
    in_section && /^\|/ {
      split($0, cols, "|")
      if (length(cols) >= 4) {
        agent = cols[2]
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", agent)
        if (agent != "" && agent != "Agent" && agent !~ /^-+$/) {
          print agent
        }
      }
    }
  ' "$SKILL_FILE"
)

if [[ ${#ROSTER_AGENTS[@]} -eq 0 ]]; then
  echo "Mismatch: no roster agent entries found in $SKILL_FILE"
  exit 1
fi

declare -a ERRORS=()
declare -A SEEN_AGENTS=()

if [[ ${#ROSTER_AGENTS[@]} -ne $EXPECTED_COUNT ]]; then
  ERRORS+=("Mismatch: expected $EXPECTED_COUNT roster entries in Plugin Agents table, found ${#ROSTER_AGENTS[@]}")
fi

for AGENT_NAME in "${ROSTER_AGENTS[@]}"; do
  if [[ -n "${SEEN_AGENTS[$AGENT_NAME]+x}" ]]; then
    ERRORS+=("Mismatch: duplicate roster agent name: $AGENT_NAME")
    continue
  fi
  SEEN_AGENTS["$AGENT_NAME"]=1

  AGENT_PATH="$PROJECT_ROOT/agents/review/$AGENT_NAME.md"
  if [[ ! -f "$AGENT_PATH" ]]; then
    ERRORS+=("Mismatch: missing review agent file for roster entry $AGENT_NAME: agents/review/$AGENT_NAME.md")
  fi
done

if [[ ${#ERRORS[@]} -gt 0 ]]; then
  printf '%s\n' "${ERRORS[@]}"
  exit 1
fi

echo "✓ All 6 roster entries validated"
