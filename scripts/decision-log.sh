#!/usr/bin/env bash
# Append one row to a show-me-your-work decision log (TSV).
# Adapted from the log helper in pstack (MIT, Lauren Tan); see THIRD-PARTY-NOTICES.md.
# Usage: decision-log.sh <logfile> <phase> <decision> <why> <evidence> <result>
set -euo pipefail

if [ "$#" -ne 6 ]; then
  echo "usage: decision-log.sh <logfile> <phase> <decision> <why> <evidence> <result>" >&2
  exit 2
fi

log=$1
shift

clean() {
  local cell=${1//$'\t'/ }
  cell=${cell//$'\r'/ }
  cell=${cell//$'\n'/ }
  case "$cell" in
    [=+@\"-]*) cell="'$cell" ;;
  esac
  printf '%s' "$cell"
}

row=$(date -u +%Y-%m-%dT%H:%M:%SZ)
for cell in "$@"; do
  row+=$'\t'$(clean "$cell")
done

append() {
  if [ ! -s "$log" ]; then
    printf 'ts\tphase\tdecision\twhy\tevidence\tresult\n'
  fi
  printf '%s\n' "$row"
}

# One locked write for header and row, so concurrent callers cannot interleave.
# flock is absent on macOS, so fall back to a mkdir lock there.
if command -v flock >/dev/null 2>&1; then
  { flock 9; append; } 9>>"$log" >>"$log"
else
  lockdir="$log.lock.d"
  tries=0
  until mkdir "$lockdir" 2>/dev/null; do
    tries=$((tries + 1))
    if [ "$tries" -gt 600 ]; then
      echo "decision-log.sh: could not take $lockdir" >&2
      exit 1
    fi
    sleep 0.05
  done
  trap 'rmdir "$lockdir"' EXIT
  append >>"$log"
fi
