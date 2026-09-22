#!/usr/bin/env bash
# Shared BB detection. Environment names alone never enroll a machine.
_clavain_in_bb() {
  local dir
  dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  python3 "$dir/bb-host.py" >/dev/null 2>&1
}

_bb_pool_available() {
  [[ "${CLAVAIN_BB_DIRECT_POOL:-1}" == 1 ]] || return 1
  case "${1:-codex}" in
    codex) [[ -n "${CODEX_POOL_AUTH_TOKEN:-}" ]] || return 1 ;;
    claude) [[ -n "${ANTHROPIC_AUTH_TOKEN:-}" && "${ANTHROPIC_BASE_URL:-}" == "${BB_SERVER_URL:-}/api/v1/plugins/account-pool/http" ]] || return 1 ;;
    *) return 1 ;;
  esac
  _clavain_in_bb
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
