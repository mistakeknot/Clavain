#!/usr/bin/env bash
# Append one row to a show-me-your-work decision log (TSV).
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
    [=+@-]*) cell="'$cell" ;;
  esac
  printf '%s' "$cell"
}

if [ ! -s "$log" ]; then
  printf 'ts\tphase\tdecision\twhy\tevidence\tresult\n' >> "$log"
fi

printf '%s' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$log"
for cell in "$@"; do
  printf '\t%s' "$(clean "$cell")" >> "$log"
done
printf '\n' >> "$log"
