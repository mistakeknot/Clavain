#!/usr/bin/env bash
# Run a probe command in a transient systemd user scope with a task cap, a
# wall-clock timeout and an explicit exit check, so a runaway probe cannot
# fork-bomb the host.
#
# Usage: probe-run.sh [--tasks N] [--timeout SECONDS] -- COMMAND [ARGS...]
# Defaults: --tasks 256, --timeout 300.
# Exit: the probe's own status; 124 on timeout (including a forced kill after
# the grace period); 125 if a capped scope could not be started (the probe is
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

rc=0
SECONDS=0
systemd-run --user --scope --quiet -p "TasksMax=$tasks" -- timeout --kill-after=5 "$timeout_s" "$@" || rc=$?
# timeout returns 137 when it had to SIGKILL after the grace period.
if [[ "$rc" -eq 137 && "$SECONDS" -ge "$timeout_s" ]]; then rc=124; fi
case "$rc" in
  0) ;;
  124) echo "probe-run: timed out after ${timeout_s}s" >&2 ;;
  *) echo "probe-run: probe exited with status $rc" >&2 ;;
esac
exit "$rc"
