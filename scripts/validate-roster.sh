#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

SKILL_FILE="$PROJECT_ROOT/skills/flux-drive/SKILL.md"
PLUGIN_JSON="$PROJECT_ROOT/.claude-plugin/plugin.json"

if [[ ! -f "$SKILL_FILE" ]]; then
  echo "Mismatch: missing skill file: $SKILL_FILE"
  exit 1
fi

if [[ ! -f "$PLUGIN_JSON" ]]; then
  echo "Mismatch: missing plugin manifest: $PLUGIN_JSON"
  exit 1
fi

mapfile -t ROSTER_SUBAGENTS < <(
  awk '
    /^### Plugin Agents \(clavain\)/ { in_section=1; next }
    /^### / && in_section { exit }
    in_section && /^\|/ {
      split($0, cols, "|")
      if (length(cols) >= 4) {
        subagent = cols[3]
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", subagent)
        if (subagent ~ /^clavain:/) {
          print subagent
        }
      }
    }
  ' "$SKILL_FILE"
)

if [[ ${#ROSTER_SUBAGENTS[@]} -eq 0 ]]; then
  echo "Mismatch: no roster subagent_type entries found in $SKILL_FILE"
  exit 1
fi

declare -a ERRORS=()
declare -A PLUGIN_AGENT_PATHS=()

while IFS=$'\t' read -r KIND VALUE EXTRA; do
  case "$KIND" in
    __ERROR__)
      ERRORS+=("Mismatch: plugin.json entry error: $VALUE")
      ;;
    __AGENT__)
      if [[ -n "${PLUGIN_AGENT_PATHS[$VALUE]+x}" ]]; then
        ERRORS+=("Mismatch: duplicate plugin agent name: $VALUE")
      else
        PLUGIN_AGENT_PATHS["$VALUE"]="$EXTRA"
      fi
      ;;
  esac
done < <(
  python3 -c '
import json
import pathlib
import sys

plugin_json = pathlib.Path(sys.argv[1])
project_root = pathlib.Path(sys.argv[2])

data = json.loads(plugin_json.read_text())

if "agents" in data:
    agents = data["agents"]
    if not isinstance(agents, list):
        print("__ERROR__\tagents field is not a list")
        sys.exit(0)

    for index, agent in enumerate(agents):
        if not isinstance(agent, dict):
            print(f"__ERROR__\tagents[{index}] is not an object")
            continue

        name = agent.get("name")
        path = agent.get("path")

        if not isinstance(name, str) or not name.strip():
            print(f"__ERROR__\tagents[{index}] missing valid name")
            continue
        if not isinstance(path, str) or not path.strip():
            print(f"__ERROR__\tagents[{index}] missing valid path")
            continue

        print(f"__AGENT__\t{name.strip()}\t{path.strip()}")
else:
    # Compatibility mode for manifest versions that rely on naming conventions
    # rather than an explicit "agents" array.
    for category in ("review", "workflow", "research"):
        category_dir = project_root / "agents" / category
        if not category_dir.is_dir():
            continue
        for agent_file in sorted(category_dir.glob("*.md")):
            name = f"clavain:{category}:{agent_file.stem}"
            path = str(agent_file.relative_to(project_root))
            print(f"__AGENT__\t{name}\t{path}")
' "$PLUGIN_JSON" "$PROJECT_ROOT"
)

for SUBAGENT in "${ROSTER_SUBAGENTS[@]}"; do
  if [[ -z "${PLUGIN_AGENT_PATHS[$SUBAGENT]+x}" ]]; then
    ERRORS+=("Mismatch: roster subagent_type missing in plugin agents: $SUBAGENT")
  fi
done

for AGENT_NAME in "${!PLUGIN_AGENT_PATHS[@]}"; do
  AGENT_PATH="${PLUGIN_AGENT_PATHS[$AGENT_NAME]}"
  if [[ "$AGENT_PATH" = /* ]]; then
    RESOLVED_PATH="$AGENT_PATH"
  else
    RESOLVED_PATH="$PROJECT_ROOT/$AGENT_PATH"
  fi

  if [[ ! -f "$RESOLVED_PATH" ]]; then
    ERRORS+=("Mismatch: plugin agent path does not exist for $AGENT_NAME: $AGENT_PATH")
  fi
done

if [[ ${#ERRORS[@]} -gt 0 ]]; then
  printf '%s\n' "${ERRORS[@]}"
  exit 1
fi

echo "✓ All ${#ROSTER_SUBAGENTS[@]} roster entries validated"
