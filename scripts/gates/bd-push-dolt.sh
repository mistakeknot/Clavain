#!/usr/bin/env bash
# Gate wrapper for `dolt push origin main` on the per-project beads DB.
#
# Usage: bd-push-dolt.sh [dolt-db-dir]
# Default: <project-root>/.beads/dolt/<project-name>
#
# Intended to be called by .beads/push.sh after a `clavain-cli` check.
set -euo pipefail

DOLT="${DOLT:-/home/mk/.local/bin/dolt}"
DB_DIR="${1:-}"

# shellcheck source=/dev/null
source "$(dirname "$0")/_common.sh"

# Resolve db dir by walking up from CWD to find .beads/dolt/<project>/.
if [[ -z "$DB_DIR" ]]; then
  dir="$PWD"
  while [[ "$dir" != "/" ]]; do
    if [[ -d "${dir}/.beads/dolt" ]]; then
      candidate="$(find "${dir}/.beads/dolt" -mindepth 1 -maxdepth 1 -type d | head -n1)"
      if [[ -n "$candidate" ]]; then
        DB_DIR="$candidate"
        break
      fi
    fi
    dir="$(dirname "$dir")"
  done
fi

if [[ -z "$DB_DIR" || ! -d "$DB_DIR" ]]; then
  echo "bd-push-dolt: no .beads/dolt/<project>/ dir found" >&2
  exit 1
fi

if ! gate_token_consume bd-push-dolt "$DB_DIR"; then
  exit 1
fi

if [[ "${GATE_CONSUMED:-0}" != "1" ]]; then
  check_flags=( --target="$DB_DIR" )
  if [[ "${CLAVAIN_SPRINT_OR_WORK:-0}" == "1" ]]; then check_flags+=( --sprint-or-work-flow ); fi

  rc=0
  gate_check bd-push-dolt "${check_flags[@]}" >/dev/null || rc=$?
  gate_decide_mode "$rc" bd-push-dolt
fi

cd "$DB_DIR"
output="$("$DOLT" push origin main 2>&1)"
status=$?
if [[ "$status" != "0" ]]; then
  echo "bd-push-dolt: dolt push failed" >&2
  echo "$output" >&2
  exit "$status"
fi
echo "bd-push-dolt: ok"

gate_record bd-push-dolt "$DB_DIR" ""
gate_sign   bd-push-dolt "$DB_DIR" ""
