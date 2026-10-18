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

# One locked write for header and row, so concurrent callers cannot interleave.
{
  flock 9
  if [ ! -s "$log" ]; then
    printf 'ts\tphase\tdecision\twhy\tevidence\tresult\n'
  fi
  printf '%s\n' "$row"
} 9>>"$log" >>"$log"
