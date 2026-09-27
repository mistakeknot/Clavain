#!/usr/bin/env bash
# Fail-open, deadline-bounded wrapper for `clavain-select.py hook`: always
# exits 0, and passes the child's stdout through only when the child exits 0.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SELECTOR_BIN="${CLAVAIN_SELECTOR_BIN:-${CLAVAIN_SELECTOR_SCRIPT:-$SCRIPT_DIR/../scripts/clavain-select.py}}"
PYTHON_BIN="${CLAVAIN_SELECTOR_PYTHON:-python3}"
HOOK_TIMEOUT="${CLAVAIN_SELECTOR_WRAPPER_TIMEOUT:-${SELECTOR_HOOK_TIMEOUT:-1.8}}"
STATE_DIR="${CLAVAIN_STATE_DIR:-${HOME:-/tmp}/.clavain}"
TIMEOUT_LOG="$STATE_DIR/selector/wrapper-timeouts.jsonl"

POINT="unknown"
HOST_NAME="unknown"
HOOK_ARGS=("$@")
if [[ "$#" -ge 2 && "${1:-}" != --* && "${2:-}" != --* ]]; then
  POINT="${1:-}"
  HOST_NAME="${2:-}"
  HOOK_ARGS=(--point "$POINT" --host "$HOST_NAME")
fi
previous=""
for argument in "${HOOK_ARGS[@]}"; do
  if [[ "$previous" == "--point" ]]; then
    POINT="$argument"
  elif [[ "$previous" == "--host" ]]; then
    HOST_NAME="$argument"
  fi
  previous="$argument"
done

if [[ ! -x "$SELECTOR_BIN" ]]; then
  exit 0
fi
if [[ "$PYTHON_BIN" == */* ]]; then
  [[ -x "$PYTHON_BIN" ]] || exit 0
elif ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  exit 0
fi
if ! command -v timeout >/dev/null 2>&1; then
  exit 0
fi

# Fail closed: the child's stdout reaches the host only after a clean exit, so
# a nonzero exit, kill, timeout or crash after partial output emits nothing.
OUT_FILE="$(mktemp "${TMPDIR:-/tmp}/clavain-selector-hook.XXXXXX" 2>/dev/null)" || exit 0
trap 'rm -f "$OUT_FILE"' EXIT

timeout "$HOOK_TIMEOUT" "$PYTHON_BIN" "$SELECTOR_BIN" hook "${HOOK_ARGS[@]}" > "$OUT_FILE"
status=$?

if [[ "$status" -eq 0 ]]; then
  cat "$OUT_FILE" 2>/dev/null || true
fi

if [[ "$status" -eq 124 ]]; then
  integration="${CLAVAIN_SELECTOR_INTEGRATION:-unknown}"
  [[ "$POINT" =~ ^[A-Za-z0-9_.-]{1,64}$ ]] || POINT="unknown"
  [[ "$integration" =~ ^[A-Za-z0-9_.-]{1,64}$ ]] || integration="unknown"
  at="$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || true)"
  [[ -n "$at" ]] || at="unknown"
  if mkdir -p "$(dirname "$TIMEOUT_LOG")" 2>/dev/null; then
    chmod 700 "$(dirname "$TIMEOUT_LOG")" 2>/dev/null || true
    printf '{"at":"%s","point":"%s","integration":"%s","kind":"wrapper_timeout"}\n' \
      "$at" "$POINT" "$integration" >> "$TIMEOUT_LOG" 2>/dev/null || true
    chmod 600 "$TIMEOUT_LOG" 2>/dev/null || true
  fi
fi

exit 0
