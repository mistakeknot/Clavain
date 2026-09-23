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
  local server_url="${BB_SERVER_URL:-}"
  [[ -n "$server_url" && -n "${ANTHROPIC_AUTH_TOKEN:-}" && "${ANTHROPIC_BASE_URL:-}" == "${server_url%/}/api/v1/plugins/account-pool/http" ]]
}

_bb_codex_pooled() {
  local server_url="${BB_SERVER_URL:-}"
  [[ -n "$server_url" && -n "${CODEX_POOL_AUTH_TOKEN:-}" && "${CODEX_OPENAI_BASE_URL:-}" == "${server_url%/}/api/v1/plugins/account-pool/http/v1" ]]
}

_bb_pool_candidate() {
  case "$1" in
    codex) _bb_codex_pooled || {
      [[ ! ${CODEX_POOL_AUTH_TOKEN+x} && ! ${CODEX_OPENAI_BASE_URL+x} ]] && _bb_claude_pooled
    } ;;
    claude) _bb_claude_pooled || {
      [[ ! ${ANTHROPIC_AUTH_TOKEN+x} && ! ${ANTHROPIC_BASE_URL+x} ]] && _bb_codex_pooled
    } ;;
    *) return 1 ;;
  esac
}

_bb_native_pooled() {
  case "$1" in
    codex) _bb_codex_pooled ;;
    claude) _bb_claude_pooled ;;
    *) return 1 ;;
  esac
}

# Environment-side-effect free: the retry loop calls this from the parent role
# shell, and anything exported there would reach later candidates. The check
# reads current bb eligibility and can report an enrollment or transport error.
_bb_pool_available() {
  [[ "${CLAVAIN_BB_DIRECT_POOL:-1}" == 1 ]] || return 1
  local provider="${1:-codex}" dir status=0
  _bb_pool_candidate "$provider" || return 1
  _clavain_in_bb || { echo "Error: cannot verify bb host enrollment for pooled $provider dispatch" >&2; return 2; }
  dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  python3 "$dir/bb-pool-eligibility.py" "$provider" || status=$?
  if [[ "$status" == 3 ]]; then
    _bb_native_pooled "$provider" && return 0
    echo "Error: this bb server cannot verify cross-provider pool eligibility for $provider" >&2
    return 2
  fi
  return "$status"
}

# Call only while building the codex command, after _bb_pool_available passed.
# Role candidates run as child dispatch processes, so the alias lives and dies
# with the one Codex attempt. A Codex thread's own token always wins.
_bb_codex_pool_token() {
  _bb_codex_pooled && return 0
  [[ ! ${CODEX_POOL_AUTH_TOKEN+x} && ! ${CODEX_OPENAI_BASE_URL+x} ]] || return 1
  _bb_claude_pooled || return 1
  export CODEX_POOL_AUTH_TOKEN="$ANTHROPIC_AUTH_TOKEN"
}

_bb_claude_pool_env() {
  _bb_claude_pooled && return 0
  _bb_codex_pooled || return 1
  export ANTHROPIC_AUTH_TOKEN="$CODEX_POOL_AUTH_TOKEN"
  export ANTHROPIC_BASE_URL="${BB_SERVER_URL%/}/api/v1/plugins/account-pool/http"
  [[ ${ENABLE_TOOL_SEARCH+x} ]] || export ENABLE_TOOL_SEARCH=true
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
