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
#
# Shadow measurement is best-effort, so it is also bounded: at most
# CLAVAIN_TRIAGE_MAX_JOBS detached selections run at once (mkdir slots, stale
# ones reaped after 30s); an edit that finds every slot busy is simply not
# measured. The event file holds edit text, so it is created 0600 and removed on
# every exit path, including an interrupt while stdin is still being read.
MAX_JOBS="${CLAVAIN_TRIAGE_MAX_JOBS:-3}"
[[ "$MAX_JOBS" =~ ^[0-9]+$ ]] || MAX_JOBS=3
SLOT_ROOT="${CLAVAIN_STATE_DIR:-${TMPDIR:-/tmp}}/selector/triage-slots"
mkdir -p "$SLOT_ROOT" 2>/dev/null || exit 0
SLOT=""
for ((i = 1; i <= MAX_JOBS; i++)); do
  if [[ -d "$SLOT_ROOT/slot.$i" && -n "$(find "$SLOT_ROOT/slot.$i" -maxdepth 0 -mmin +0.5 2>/dev/null)" ]]; then
    rmdir "$SLOT_ROOT/slot.$i" 2>/dev/null
  fi
  if mkdir "$SLOT_ROOT/slot.$i" 2>/dev/null; then
    SLOT="$SLOT_ROOT/slot.$i"
    break
  fi
done
[[ -n "$SLOT" ]] || exit 0

EVENT_FILE=""
READER=""
release() {
  [[ -n "$READER" ]] && kill "$READER" 2>/dev/null
  [[ -n "$EVENT_FILE" ]] && rm -f "$EVENT_FILE"
  rmdir "$SLOT" 2>/dev/null
}
trap 'release; exit 0' EXIT INT TERM HUP
EVENT_FILE="$(mktemp "${TMPDIR:-/tmp}/clavain-triage-event.XXXXXX" 2>/dev/null)" || exit 0
# Read in the background and `wait`: bash only runs a trap between commands, so a
# foreground `cat` blocked on an open stdin would defer the cleanup indefinitely.
cat <&0 > "$EVENT_FILE" 2>/dev/null &   # explicit <&0: a bare async command would read /dev/null
READER=$!
wait "$READER" || exit 0
READER=""

# Ownership of the file and the slot passes to the detached job.
trap - EXIT INT TERM HUP
(
  "$SCRIPT_DIR/selector-hook.sh" pre_tool claude-code < "$EVENT_FILE" > /dev/null 2>&1
  rm -f "$EVENT_FILE"
  rmdir "$SLOT" 2>/dev/null
) > /dev/null 2>&1 < /dev/null &
disown 2>/dev/null || true
exit 0
