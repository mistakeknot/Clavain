#!/usr/bin/env bash
# Run a probe command in a transient systemd user scope with a task cap and a
# runtime limit, so a runaway probe cannot fork-bomb the host.
#
# Usage: probe-run.sh [--tasks N] [--timeout SECONDS] -- COMMAND [ARGS...]
# Defaults: --tasks 256, --timeout 300.
#
# systemd enforces both limits on the whole scope: TasksMax caps every
# descendant, and at RuntimeMaxSec the scope is stopped (SIGTERM, then SIGKILL
# after 5s to every process in it). Exit status is systemd-run's, which is the
# probe's own status; a probe stopped at the limit reports a signal status
# (typically 143 or 137). Exit 2 is a usage error; 125 means systemd-run is
# not installed (the probe is not run).
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

exec systemd-run --user --scope --quiet \
  -p "TasksMax=$tasks" -p "RuntimeMaxSec=$timeout_s" -p TimeoutStopSec=5 -- "$@"
