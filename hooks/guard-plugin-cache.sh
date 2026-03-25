#!/usr/bin/env bash
set -uo pipefail
trap 'exit 0' ERR
trap 'exit 0' ERR

input=$(cat)
file_path=$(echo "$input" | jq -r '(.tool_input.file_path // .tool_input.edits[0].file_path) // empty' 2>/dev/null) || exit 0
[[ -z "$file_path" ]] && exit 0

if [[ "$file_path" == */plugins/cache/* ]]; then
  # Extract plugin name: .../plugins/cache/<plugin>/<version>/...
  plugin_name=$(echo "$file_path" | sed -n 's|.*/plugins/cache/\([^/]*\)/.*|\1|p')
  hint=""
  [[ -n "$plugin_name" ]] && hint=" Edit the source repo for '$plugin_name' instead."
  cat <<EOF
{"decision":"block","reason":"This file is in ~/.claude/plugins/cache/ — a cached copy that gets overwritten on plugin install/update. Edits here will be silently lost.${hint}"}
EOF
  exit 0
fi

exit 0
