#!/usr/bin/env bash
# Shared BB detection. Environment names alone never enroll a machine.
_clavain_in_bb() {
  local dir
  dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  python3 "$dir/bb-host.py" >/dev/null 2>&1
}

_bb_pool_available() {
  [[ "${CLAVAIN_BB_DIRECT_POOL:-0}" == 1 && -n "${CODEX_POOL_AUTH_TOKEN:-}" ]] && _clavain_in_bb
}

_clavain_session_id() {
  if [[ -n "${CLAUDE_SESSION_ID:-}" ]]; then
    printf '%s\n' "$CLAUDE_SESSION_ID"
  elif _clavain_in_bb; then
    printf '%s\n' "$BB_THREAD_ID"
  else
    printf 'unknown\n'
  fi
}
