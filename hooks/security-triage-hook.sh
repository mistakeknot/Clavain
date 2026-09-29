#!/usr/bin/env bash
# PreToolUse entry for the security-review triage integration (mk-42j9.9),
# SHADOW ONLY. Flag off (the default) costs one bash start and nothing else:
# no python, no stdin read, no state. Flag on hands off to the fail-open
# selector wrapper: detached in shadow (the edit never waits), inline in
# active. This hook never prints a decision of its own and always exits 0, so
# it cannot block, allow or skip anything.

set -u

kill_switch="$(printf '%s' "${CLAVAIN_SELECTOR:-}" | tr '[:upper:]' '[:lower:]')"
mode="$(printf '%s' "${CLAVAIN_SELECTOR_SECURITY_TRIAGE:-}" | tr '[:upper:]' '[:lower:]')"
[[ "$kill_switch" == "off" ]] && exit 0
[[ "$mode" == "shadow" || "$mode" == "active" ]] || exit 0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CLAVAIN_SELECTOR_INTEGRATION="security_triage"

if [[ "$mode" == "active" ]]; then
  "$SCRIPT_DIR/selector-hook.sh" pre_tool claude-code || true
  exit 0
fi

# Shadow never prints anything the host acts on, so the edit must not wait for
# Jev: capture the event, detach the selection (stdout and stderr discarded,
# still bounded by the wrapper's own timeout) and return at once.
EVENT_FILE="$(mktemp "${TMPDIR:-/tmp}/clavain-triage-event.XXXXXX" 2>/dev/null)" || exit 0
if ! cat > "$EVENT_FILE" 2>/dev/null; then
  rm -f "$EVENT_FILE"
  exit 0
fi
(
  "$SCRIPT_DIR/selector-hook.sh" pre_tool claude-code < "$EVENT_FILE" > /dev/null 2>&1
  rm -f "$EVENT_FILE"
) > /dev/null 2>&1 < /dev/null &
disown 2>/dev/null || true
exit 0
