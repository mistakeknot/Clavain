#!/usr/bin/env bash
# Shared helpers for auto-proceed gate wrappers.
#
# Each gate wrapper:
#   1. Calls `clavain-cli policy check <op>` with the op context.
#   2. Exit code 0 → auto, 1 → confirm (prompt if tty, else abort),
#      2 → block (abort), 3 → malformed (abort).
#   3. Runs the underlying op.
#   4. Calls `clavain-cli policy record` with the policy_hash pinned from check.
#
# This file is sourced by individual gate scripts; callers must have:
#     set -euo pipefail

# gate_bd_state <bead> <dimension>
# Queries `bd state <bead> <dim>` and echoes the value (empty on miss).
# Best-effort — silent on bd-not-installed, empty result, or non-zero exit.
gate_bd_state() {
  local bead="$1" dim="$2"
  if [[ -z "$bead" ]] || ! command -v bd >/dev/null 2>&1; then
    return 0
  fi
  bd state "$bead" "$dim" 2>/dev/null || true
}

# gate_populate_vetting <bead>
# Populates CLAVAIN_VETTED_AT / CLAVAIN_VETTED_SHA / CLAVAIN_TESTS_PASSED /
# CLAVAIN_SPRINT_OR_WORK from bd state if not already set in the env. Called
# by wrappers that accept a bead context.
gate_populate_vetting() {
  local bead="$1"
  if [[ -z "${CLAVAIN_VETTED_AT:-}" ]]; then
    local v; v="$(gate_bd_state "$bead" vetted_at)"
    [[ -n "$v" ]] && CLAVAIN_VETTED_AT="$v"
  fi
  if [[ -z "${CLAVAIN_VETTED_SHA:-}" ]]; then
    local v; v="$(gate_bd_state "$bead" vetted_sha)"
    [[ -n "$v" ]] && CLAVAIN_VETTED_SHA="$v"
  fi
  if [[ -z "${CLAVAIN_TESTS_PASSED:-}" ]]; then
    local v; v="$(gate_bd_state "$bead" tests_passed)"
    [[ "$v" == "true" ]] && CLAVAIN_TESTS_PASSED=1
  fi
  if [[ -z "${CLAVAIN_SPRINT_OR_WORK:-}" ]]; then
    local v; v="$(gate_bd_state "$bead" sprint_or_work_flow)"
    [[ "$v" == "true" ]] && CLAVAIN_SPRINT_OR_WORK=1
  fi
  export CLAVAIN_VETTED_AT CLAVAIN_VETTED_SHA CLAVAIN_TESTS_PASSED CLAVAIN_SPRINT_OR_WORK
}

# gate_resolve_agent returns a stable identity for this invocation.
# Preference order: $CLAVAIN_AGENT_ID → $USER@$HOSTNAME → fallback.
gate_resolve_agent() {
  if [[ -n "${CLAVAIN_AGENT_ID:-}" ]]; then
    printf '%s' "$CLAVAIN_AGENT_ID"
    return
  fi
  local user="${USER:-$(whoami 2>/dev/null || echo unknown)}"
  local host
  host="$(hostname 2>/dev/null || echo unknown)"
  printf '%s@%s' "$user" "$host"
}

# gate_check <op> [extra policy-check flags...]
# Emits the JSON output on stdout (caller captures) and returns the numeric
# exit code from `clavain-cli policy check`.
#
# Sets globals on success:
#   GATE_POLICY_HASH
#   GATE_POLICY_MATCH
gate_check() {
  local op="$1"
  shift || true
  local raw rc
  raw="$(clavain-cli policy check "$op" "$@" 2>&1)" && rc=0 || rc=$?

  # jq is optional; fall back to sed if missing. We only need two fields.
  if command -v jq >/dev/null 2>&1; then
    GATE_POLICY_HASH="$(printf '%s' "$raw" | jq -r '.policy_hash // empty' 2>/dev/null || true)"
    GATE_POLICY_MATCH="$(printf '%s' "$raw" | jq -r '.policy_match // empty' 2>/dev/null || true)"
  else
    GATE_POLICY_HASH="$(printf '%s' "$raw" | sed -n 's/.*"policy_hash":"\([^"]*\)".*/\1/p' | head -n1)"
    GATE_POLICY_MATCH="$(printf '%s' "$raw" | sed -n 's/.*"policy_match":"\([^"]*\)".*/\1/p' | head -n1)"
  fi

  export GATE_POLICY_HASH GATE_POLICY_MATCH
  return "$rc"
}

# gate_prompt_or_abort <op>
# Called when policy check exits 1 (confirm). Prompts on tty, aborts otherwise.
# Sets GATE_MODE=confirmed on accept.
gate_prompt_or_abort() {
  local op="$1"
  if [[ -t 0 ]]; then
    local ans
    read -rp "policy: ${op} requires confirmation. Proceed? [y/N] " ans
    if [[ "$ans" =~ ^[yY]$ ]]; then
      GATE_MODE=confirmed
      export GATE_MODE
      return 0
    fi
    echo "aborted" >&2
    return 1
  fi
  echo "policy: ${op} requires confirmation; no tty available" >&2
  return 1
}

# gate_decide_mode <rc> <op>
# Translates policy-check rc into action. On success, sets GATE_MODE to one of
# auto | confirmed. On failure, exits with a user-facing message.
gate_decide_mode() {
  local rc="$1" op="$2"
  case "$rc" in
    0) GATE_MODE=auto; export GATE_MODE; return 0 ;;
    1) gate_prompt_or_abort "$op" || exit 1; return 0 ;;
    2) echo "policy: ${op} blocked" >&2; exit 1 ;;
    3) echo "policy: ${op} malformed policy (rc=3)" >&2; exit 1 ;;
    *) echo "policy: ${op} engine error (rc=${rc})" >&2; exit 1 ;;
  esac
}

# gate_record <op> <target> <bead-or-empty> [extra flags...]
# Writes the authorization audit row. Uses GATE_MODE, GATE_POLICY_MATCH,
# GATE_POLICY_HASH set by earlier gate_check/gate_decide_mode calls.
gate_record() {
  local op="$1" target="$2" bead="$3"
  shift 3 || true
  local agent
  agent="$(gate_resolve_agent)"
  local args=(
    --op="$op"
    --target="$target"
    --agent="$agent"
    --mode="${GATE_MODE:-auto}"
    --policy-match="${GATE_POLICY_MATCH:-}"
    --policy-hash="${GATE_POLICY_HASH:-}"
  )
  if [[ -n "$bead" ]]; then
    args+=( --bead="$bead" )
  fi
  if ! clavain-cli policy record "${args[@]}" "$@"; then
    # Recording is best-effort; never block the op on audit-write failure
    # (the op has already succeeded by this point).
    echo "policy: record failed (op=${op} target=${target}); op succeeded" >&2
  fi
}
