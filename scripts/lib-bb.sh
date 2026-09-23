#!/usr/bin/env bash
# Shared BB detection. Environment names alone never enroll a machine.
_clavain_in_bb() {
  local dir
  dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  python3 "$dir/bb-host.py" >/dev/null 2>&1
}

_bb_claude_pooled() {
  [[ -n "${ANTHROPIC_AUTH_TOKEN:-}" && "${ANTHROPIC_BASE_URL:-}" == "${BB_SERVER_URL:-}/api/v1/plugins/account-pool/http" ]]
}

_bb_pool_available() {
  [[ "${CLAVAIN_BB_DIRECT_POOL:-1}" == 1 ]] || return 1
  local borrow=0
  case "${1:-codex}" in
    # BB hands CODEX_POOL_AUTH_TOKEN only to Codex threads. A Claude Code thread
    # carries the same per-machine hub bearer as its Anthropic route token, and
    # the hub accepts it on the Codex route too; without borrowing it, every
    # Codex seat dispatched from a Claude thread fell back to the local
    # ~/.codex login and failed quota_exhausted while pooled accounts had room.
    codex) [[ -n "${CODEX_POOL_AUTH_TOKEN:-}" ]] || { _bb_claude_pooled && borrow=1; } || return 1 ;;
    claude) _bb_claude_pooled || return 1 ;;
    *) return 1 ;;
  esac
  _clavain_in_bb || return 1
  [[ "$borrow" == 0 ]] || export CODEX_POOL_AUTH_TOKEN="$ANTHROPIC_AUTH_TOKEN"
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
