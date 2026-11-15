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

# mk-wyvz6: a thread can inherit the exact bb pool route without the bearer
# that goes with it (the route variable survives, the token variable does not).
# Sending requests to the route without a bearer only produces a 401, so the
# provider's own non-pooled login is the correct transport. This is narrow on
# purpose: it matches only the exact pool route for this bb server with an
# ABSENT (unset or empty) token. A present token, a different endpoint, a
# missing server URL or a failed eligibility probe never match, so they keep
# their existing terminal handling. It reads only whether a variable is empty;
# it never expands, prints or logs a value.
_bb_pool_route_without_token() {
  local server_url="${BB_SERVER_URL:-}"
  [[ -n "$server_url" ]] || return 1
  case "$1" in
    claude) [[ -z "${ANTHROPIC_AUTH_TOKEN:-}" &&
      "${ANTHROPIC_BASE_URL:-}" == "${server_url%/}/api/v1/plugins/account-pool/http" ]] ;;
    codex) [[ -z "${CODEX_POOL_AUTH_TOKEN:-}" &&
      "${CODEX_OPENAI_BASE_URL:-}" == "${server_url%/}/api/v1/plugins/account-pool/http/v1" ]] ;;
    *) return 1 ;;
  esac
}

# Call only after _bb_pool_available returned 1 for this provider. Drops the
# stale route variable from the (per-candidate) dispatch shell so the child
# falls back to its own login, and says so on stderr. The notice carries no
# environment values. Selects no account and borrows no token.
_bb_drop_tokenless_pool_route() {
  _bb_pool_route_without_token "$1" || return 0
  case "$1" in
    claude) unset ANTHROPIC_BASE_URL ;;
    codex) unset CODEX_OPENAI_BASE_URL ;;
  esac
  # A Claude child that still has ANTHROPIC_API_KEY (kept for the seat by
  # SEAT_KEEP_CLAUDE) authenticates with that metered key, not the subscription
  # login, so the notice says which one applies. Only "set" or "not set" is
  # tested and printed, never the value.
  if [[ "$1" == claude && -n "${ANTHROPIC_API_KEY:-}" ]]; then
    echo "dispatch: the bb account-pool route is set for claude but no pool token is available; ANTHROPIC_API_KEY is set, so the claude child will use that API key (metered) instead of the subscription login" >&2
  elif [[ "$1" == claude ]]; then
    echo "dispatch: the bb account-pool route is set for claude but no pool token is available; ANTHROPIC_API_KEY is not set, so the claude child will use the non-pooled subscription login" >&2
  else
    echo "dispatch: the bb account-pool route is set for $1 but no pool token is available; using the non-pooled $1 login" >&2
  fi
}

# Environment-side-effect free: the retry loop calls this from the parent role
# shell, and anything exported there would reach later candidates. The check
# reads current bb eligibility and can report an enrollment or transport error.
_bb_pool_available() {
  [[ "${CLAVAIN_BB_DIRECT_POOL:-1}" == 1 ]] || return 1
  local provider="${1:-codex}" dir status=0 attempt=0
  _bb_pool_candidate "$provider" || return 1
  _clavain_in_bb || { echo "Error: cannot verify bb host enrollment for pooled $provider dispatch" >&2; return 2; }
  dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local retries="${CLAVAIN_BB_POOL_PROBE_RETRIES:-2}"
  local backoff="${CLAVAIN_BB_POOL_PROBE_BACKOFF:-0.2}"
  # Keep overrides bounded: at most two retries and one second per backoff.
  if [[ ! "$retries" =~ ^[012]$ || ! "$backoff" =~ ^(0(\.[0-9]+)?|1(\.0+)?)$ ]]; then
    echo "Error: invalid bb pool probe retry settings" >&2
    return 2
  fi
  while true; do
    status=0
    python3 "$dir/bb-pool-eligibility.py" "$provider" || status=$?
    [[ "$status" == 4 ]] || break
    if (( attempt >= retries )); then
      echo "Warning: transient bb pool eligibility failure for $provider after $((attempt + 1)) attempts; falling back to non-pooled dispatch" >&2
      return 1
    fi
    attempt=$((attempt + 1))
    sleep "$backoff"
  done
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
