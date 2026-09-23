#!/usr/bin/env bash
# Shared BB detection. Environment names alone never enroll a machine.
# Threat model: enrollment asks the BB CLI (BB_CLI or PATH) for the thread and
# host. A process that controls those can forge the answer, so this gate selects
# a transport; it is not an authorization boundary. It never grants a bearer the
# process does not already hold: the borrowed Codex token is the process's own
# ANTHROPIC_AUTH_TOKEN. CLAVAIN_BB_DIRECT_POOL=0 disables pooled transport.
_clavain_in_bb() {
  local dir
  dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  python3 "$dir/bb-host.py" >/dev/null 2>&1
}

_bb_claude_pooled() {
  [[ -n "${ANTHROPIC_AUTH_TOKEN:-}" && "${ANTHROPIC_BASE_URL:-}" == "${BB_SERVER_URL:-}/api/v1/plugins/account-pool/http" ]]
}

# Side-effect free: the retry loop calls this from the parent role shell, and
# anything exported there would reach every later candidate, Claude and Kimi
# seats included.
_bb_pool_available() {
  [[ "${CLAVAIN_BB_DIRECT_POOL:-1}" == 1 ]] || return 1
  case "${1:-codex}" in
    # BB hands CODEX_POOL_AUTH_TOKEN only to Codex threads. A Claude Code thread
    # carries the same per-machine hub bearer as its Anthropic route token, and
    # the hub accepts it on the Codex route too; without it, every Codex seat
    # dispatched from a Claude thread fell back to the local ~/.codex login and
    # failed quota_exhausted while pooled accounts had room.
    codex) [[ -n "${CODEX_POOL_AUTH_TOKEN:-}" ]] || _bb_claude_pooled || return 1 ;;
    claude) _bb_claude_pooled || return 1 ;;
    *) return 1 ;;
  esac
  _clavain_in_bb
}

# Call only while building the codex command, after _bb_pool_available passed.
# Role candidates run as child dispatch processes, so the alias lives and dies
# with the one Codex attempt. A Codex thread's own token always wins.
_bb_codex_pool_token() {
  [[ -z "${CODEX_POOL_AUTH_TOKEN:-}" ]] || return 0
  _bb_claude_pooled || return 1
  export CODEX_POOL_AUTH_TOKEN="$ANTHROPIC_AUTH_TOKEN"
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
