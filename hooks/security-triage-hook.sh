#!/usr/bin/env bash
# PreToolUse entry for the security-review triage integration (mk-42j9.9),
# SHADOW ONLY. Flag off (the default) costs one bash start and nothing else:
# no python, no stdin read, no state. Flag on hands off to the fail-open
# selector wrapper. This hook never prints a decision of its own and always
# exits 0, so it cannot block, allow or skip anything.

set -u

kill_switch="$(printf '%s' "${CLAVAIN_SELECTOR:-}" | tr '[:upper:]' '[:lower:]')"
mode="$(printf '%s' "${CLAVAIN_SELECTOR_SECURITY_TRIAGE:-}" | tr '[:upper:]' '[:lower:]')"
[[ "$kill_switch" == "off" ]] && exit 0
[[ "$mode" == "shadow" || "$mode" == "active" ]] || exit 0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CLAVAIN_SELECTOR_INTEGRATION="security_triage"
"$SCRIPT_DIR/selector-hook.sh" pre_tool claude-code || true
exit 0
