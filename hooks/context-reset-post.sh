#!/usr/bin/env bash
# context-reset-post.sh — SessionStart + PostToolUse, observe-mode context-reset
# telemetry (mk-42j9.40).
#
# NOT A SECURITY BOUNDARY. On SessionStart it opens or carries a context epoch.
# After a tool call it records exposure to untrusted content (web, remote
# commands, MCP, browser, uncovered child agents), coalesced into accounting
# batches. It prints nothing on stdout, never blocks, and never performs or
# requests a reset. It fails open: any internal error exits 0. Rollback:
# `mode: off` in config/context-reset.yaml.
set -uo pipefail
trap 'exit 0' ERR

payload=$(cat 2>/dev/null) || payload=""
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || exit 0
# shellcheck source=hooks/lib-context-reset.sh
source "$script_dir/lib-context-reset.sh" 2>/dev/null || exit 0

cr_should_record_for "$payload" || exit 0
cr_handle_post "$payload" >/dev/null || true
exit 0
