#!/usr/bin/env bash
# Run a probe command in a transient systemd user scope with a task cap, a
# wall-clock timeout and an explicit exit check, so a runaway probe cannot
# fork-bomb the host.
#
# Usage: probe-run.sh [--tasks N] [--timeout SECONDS] -- COMMAND [ARGS...]
# Defaults: --tasks 256, --timeout 300.
# Exit: the probe's own status; 124 on timeout (whatever the probe's status
# after the deadline); 125 if a capped scope could not be started (the probe is
# then NOT run); 2 on usage errors.
set -euo pipefail

tasks=256
timeout_s=300
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tasks|--timeout)
      [[ $# -ge 2 ]] || { echo "probe-run: $1 needs a value" >&2; exit 2; }
      if [[ "$1" == "--tasks" ]]; then tasks="$2"; else timeout_s="$2"; fi
      shift 2 ;;
    --) shift; break ;;
    *) echo "probe-run: unknown option $1" >&2; exit 2 ;;
  esac
done
[[ $# -gt 0 ]] || { echo "usage: probe-run.sh [--tasks N] [--timeout S] -- CMD..." >&2; exit 2; }
[[ "$tasks" =~ ^[0-9]+$ && "$tasks" -ge 1 ]] || { echo "probe-run: bad --tasks" >&2; exit 2; }
[[ "$timeout_s" =~ ^[0-9]+$ && "$timeout_s" -ge 1 ]] || { echo "probe-run: bad --timeout" >&2; exit 2; }

command -v systemd-run >/dev/null || { echo "probe-run: systemd-run not found; refusing to run unconfined" >&2; exit 125; }

# Preflight: prove a capped scope can start, so a scope failure is never
# confused with a probe failure and the probe never runs unconfined.
systemd-run --user --scope --quiet -p "TasksMax=$tasks" -- true >/dev/null 2>&1 \
  || { echo "probe-run: cannot start a TasksMax-capped user scope; refusing to run" >&2; exit 125; }

# The wrapper itself enforces the deadline (rather than timeout(1)) so that a
# timeout is distinguishable from a probe that was killed for another reason.
unit="probe-run-$$-$RANDOM"
flag="$(mktemp)"
started="$(mktemp)"
rm -f "$flag" "$started"
trap 'rm -f "$flag" "$started"' EXIT

# The inner shell drops a marker once the scope is running the probe, so a
# scope start-up failure (no marker) can be told apart from a probe failure.
systemd-run --user --scope --quiet --unit="$unit" -p "TasksMax=$tasks" -- \
  sh -c ': > "$0"; exec "$@"' "$started" "$@" &
probe=$!
(
  sleep "$timeout_s"
  : > "$flag"
  systemctl --user kill --signal=SIGTERM "$unit.scope" 2>/dev/null || true
  sleep 5
  systemctl --user kill --signal=SIGKILL "$unit.scope" 2>/dev/null || true
) &
watchdog=$!

rc=0
wait "$probe" || rc=$?
pkill -P "$watchdog" 2>/dev/null || true
kill "$watchdog" 2>/dev/null || true
wait "$watchdog" 2>/dev/null || true

if [[ -e "$flag" ]]; then
  # Deadline fired: the grace period only applies to the leader, so remove
  # anything left in the scope, and report a timeout whatever the exit status.
  systemctl --user kill --signal=SIGKILL "$unit.scope" 2>/dev/null || true
  echo "probe-run: timed out after ${timeout_s}s" >&2
  exit 124
fi
if [[ "$rc" -ne 0 && ! -e "$started" ]]; then
  echo "probe-run: capped scope failed to start; probe not run" >&2
  exit 125
fi
if [[ "$rc" -ne 0 ]]; then
  echo "probe-run: probe exited with status $rc" >&2
fi
exit "$rc"
