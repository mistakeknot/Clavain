#!/usr/bin/env bash
set -euo pipefail

# Interserve toggle — switches interserve execution mode on/off.
# When ON, Claude routes source code changes through Codex agents.
# State persists across sessions via flag file.

# Validate environment
if [[ -z "${PROJECT_DIR:-}" ]]; then
  echo "Error: PROJECT_DIR not set. Run from Claude Code or set manually." >&2
  exit 1
fi

if [[ ! -d "$PROJECT_DIR" ]]; then
  echo "Error: PROJECT_DIR does not exist: $PROJECT_DIR" >&2
  exit 1
fi

FLAG_FILE="$PROJECT_DIR/.claude/clodex-toggle.flag"

if [[ -f "$FLAG_FILE" ]]; then
  # Currently ON → turn OFF
  rm "$FLAG_FILE"
  echo 'Clodex mode: **OFF**'
  echo ''
  echo 'Direct file editing restored. Edit/Write will work normally for all files.'
else
  # Currently OFF → turn ON
  mkdir -p "$PROJECT_DIR/.claude"
  date -Iseconds > "$FLAG_FILE"
  echo 'Clodex mode: **ON**'
  echo ''
  echo 'Route source code changes through Codex (preserves Claude token budget for orchestration).'
  echo ''
  echo '- **Plan**: Read/Grep/Glob freely to understand the codebase'
  echo '- **Prompt**: Write task descriptions to /tmp/ files'
  echo '- **Dispatch**: Use /interserve skill → Codex agents implement'
  echo '- **Verify**: Read output, run tests, review diffs'
  echo '- **Git ops**: add/commit/push are yours — do directly'
  echo ''
  echo 'Direct-edit OK: .md, .json, .yaml, .yml, .toml, .txt, .csv, .xml, .html, .css, .svg, .lock, .cfg, .ini, .conf, .env, /tmp/*'
  echo 'Bash: read-only for source files (no redirects, sed -i, tee). Git and test/build commands are fine.'
  echo ''
  echo 'Clavain-interserve routing policy is available:'
  echo '- Default interserve mode keeps --tier fast|deep as configured in config/dispatch/tiers.yaml.'
  echo '- For Clavain-in-Codex routing, set `CLAVAIN_DISPATCH_PROFILE=interserve` before dispatch calls.'
  echo '- Then --tier fast resolves to gpt-5.3-codex-spark-xhigh; --tier deep resolves to gpt-5.3-codex-xhigh.'
  echo ''
  echo 'Run /clodex-toggle to turn off.'
fi
