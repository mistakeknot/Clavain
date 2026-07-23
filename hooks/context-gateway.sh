#!/usr/bin/env bash
# Stable UserPromptSubmit adapter for Claude Code, Codex, and Kimi Code.
#
# Plugin hooks auto-detect Kimi through KIMI_PLUGIN_ROOT. Installers pass an
# explicit harness argument for user-level Codex and Kimi config hooks.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATEWAY="${CLAVAIN_CONTEXT_GATEWAY_BIN:-$SCRIPT_DIR/../scripts/context-gateway.py}"
HARNESS="${1:-${CLAVAIN_CONTEXT_GATEWAY_HARNESS:-}}"

if [[ -z "$HARNESS" ]]; then
  if [[ -n "${KIMI_PLUGIN_ROOT:-}" ]]; then
    HARNESS="kimi"
  else
    HARNESS="claude"
  fi
fi

case "$HARNESS" in
  claude|codex|kimi|generic) ;;
  *)
    echo "context-gateway: unsupported harness '$HARNESS' (failing open)" >&2
    exit 0
    ;;
esac

if [[ ! -x "$GATEWAY" ]]; then
  echo "context-gateway: gateway missing or not executable: $GATEWAY (failing open)" >&2
  exit 0
fi

"$GATEWAY" hook --harness "$HARNESS" --mode "${CLAVAIN_CONTEXT_GATEWAY_MODE:-auto}"
status=$?
if [[ "$status" -ne 0 ]]; then
  echo "context-gateway: gateway exited $status (failing open)" >&2
fi
exit 0
