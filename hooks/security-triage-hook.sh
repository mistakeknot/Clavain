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
# CLAVAIN_TRIAGE_MAX_JOBS detached selections run at once, each holding a kernel
# flock on a slot file (inherited by the detached job, released by the kernel
# when it exits or is killed, so there is no stale-slot bookkeeping and no way
# to release another job's slot). An edit that finds every slot busy, or a host
# without flock, is simply not measured. The event file holds edit text: it
# lives in a private 0700 directory, is removed on every exit path including an
# interrupt or a killed job's catchable signals, and files a SIGKILL abandons
# are swept on the next run.
MAX_JOBS="${CLAVAIN_TRIAGE_MAX_JOBS:-3}"
[[ "$MAX_JOBS" =~ ^[0-9]+$ ]] || MAX_JOBS=3
command -v flock >/dev/null 2>&1 || exit 0
STATE="${CLAVAIN_STATE_DIR:-${TMPDIR:-/tmp}}/selector"
SLOT_ROOT="$STATE/triage-slots"
EVENT_ROOT="$STATE/triage-events"
(umask 077; mkdir -p "$SLOT_ROOT" "$EVENT_ROOT") 2>/dev/null || exit 0
chmod 700 "$EVENT_ROOT" 2>/dev/null
find "$EVENT_ROOT" -maxdepth 1 -type f -name 'event.*' -mmin +2 -delete 2>/dev/null

got=0
for ((i = 1; i <= MAX_JOBS; i++)); do
  exec 8> "$SLOT_ROOT/slot.$i" 2>/dev/null || continue
  if flock -n 8; then
    got=1
    break
  fi
  exec 8>&-
done
[[ "$got" == 1 ]] || exit 0

EVENT_FILE=""
READER=""
cleanup() {
  [[ -n "$READER" ]] && kill "$READER" 2>/dev/null
  [[ -n "$EVENT_FILE" ]] && rm -f "$EVENT_FILE"
}
trap 'cleanup; exit 0' EXIT INT TERM HUP
EVENT_FILE="$(umask 077; mktemp "$EVENT_ROOT/event.XXXXXX" 2>/dev/null)" || exit 0
# Read in the background and `wait`: bash only runs a trap between commands, so a
# foreground `cat` blocked on an open stdin would defer the cleanup indefinitely.
cat <&0 > "$EVENT_FILE" 2>/dev/null &   # explicit <&0: a bare async command would read /dev/null
READER=$!
wait "$READER" || exit 0
READER=""

# Ownership of the file and the slot lock (fd 8) passes to the detached job.
trap - EXIT INT TERM HUP
(
  trap 'rm -f "$EVENT_FILE"; exit 0' TERM INT HUP
  "$SCRIPT_DIR/selector-hook.sh" pre_tool claude-code < "$EVENT_FILE" > /dev/null 2>&1
  rm -f "$EVENT_FILE"
) > /dev/null 2>&1 < /dev/null &
disown 2>/dev/null || true
exit 0
