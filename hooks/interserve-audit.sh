#!/usr/bin/env bash
set -euo pipefail

main() {
  local project_dir flag_file log_file payload file_path base
  project_dir="${CLAUDE_PROJECT_DIR:-.}"
  flag_file="$project_dir/.claude/clodex-toggle.flag"
  log_file="$project_dir/.claude/interserve-audit.log"

  [[ -f "$flag_file" ]] || exit 0
  command -v jq >/dev/null 2>&1 || exit 0

  payload="$(cat || true)"
  [[ -n "$payload" ]] || exit 0

  file_path="$(jq -r '(.tool_input.file_path // .tool_input.notebook_path // empty)' \
    <<<"$payload" 2>/dev/null || true)"
  [[ -n "$file_path" ]] || exit 0

  [[ "$file_path" == /tmp/* ]] && exit 0

  base="$(basename "$file_path")"
  [[ "$base" == .* ]] && exit 0

  case "$file_path" in
    *.md|*.json|*.yaml|*.yml|*.toml|*.txt|*.csv|*.xml|*.html|*.css|*.svg|*.lock|*.cfg|*.ini|*.conf|*.env)
      exit 0
      ;;
  esac

  mkdir -p "$project_dir/.claude"
  printf '[%s] VIOLATION: Edit/Write to source file: %s\n' \
    "$(date -Iseconds)" "$file_path" >>"$log_file"
}

main "$@" || true
exit 0
