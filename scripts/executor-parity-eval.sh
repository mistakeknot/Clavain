#!/usr/bin/env bash
# Process-hygiene wrapper for executor-parity-eval.py.
# Intentionally does not use set -e: the child exit status is collected after
# the liveness loop so progress logging and cleanup still run on failure.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCK_FILE="${TMPDIR:-/tmp}/clavain-executor-parity-eval.pid"
CHILD_PID=""

if [[ -f "$LOCK_FILE" ]]; then
  EXISTING_WRAPPER_PID="$(<"$LOCK_FILE")"
  if [[ "$EXISTING_WRAPPER_PID" =~ ^[0-9]+$ ]] && kill -0 "$EXISTING_WRAPPER_PID" 2>/dev/null; then
    echo "executor-parity-eval: already running (wrapper pid $EXISTING_WRAPPER_PID)" >&2
    exit 1
  fi
  rm -f "$LOCK_FILE"
fi

# The guard records and checks the WRAPPER pid. It never targets CHILD_PID;
# this avoids killing the detached setsid child when cleaning stale state.
printf '%s\n' "$$" > "$LOCK_FILE"

cleanup() {
  if [[ -f "$LOCK_FILE" ]] && [[ "$(<"$LOCK_FILE")" == "$$" ]]; then
    rm -f "$LOCK_FILE"
  fi
}
trap cleanup EXIT INT TERM

if command -v setsid >/dev/null 2>&1; then
  setsid python3 "$SCRIPT_DIR/executor-parity-eval.py" "$@" &
else
  # macOS does not ship util-linux's setsid command. Use the same POSIX
  # session boundary through Python's standard library in that environment.
  python3 -c 'import os, sys; os.setsid(); os.execvp(sys.executable, [sys.executable] + sys.argv[1:])' \
    "$SCRIPT_DIR/executor-parity-eval.py" "$@" &
fi
CHILD_PID=$!
echo "executor-parity-eval: wrapper=$$ child=$CHILD_PID started" >&2

while kill -0 "$CHILD_PID" 2>/dev/null; do
  echo "executor-parity-eval: wrapper=$$ child=$CHILD_PID alive" >&2
  sleep "${EXECUTOR_PARITY_LOG_INTERVAL:-5}"
done

wait "$CHILD_PID"
CHILD_EXIT=$?
echo "executor-parity-eval: wrapper=$$ child=$CHILD_PID exited rc=$CHILD_EXIT" >&2
exit "$CHILD_EXIT"
