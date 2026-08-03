#!/usr/bin/env bash
# Shared helpers for auto-proceed gate wrappers.
#
# Each gate wrapper:
#   1. Resolves one explicit authz project root and requires a ready signer.
#   2. Calls `clavain-cli policy check <op>` with the op context.
#   3. Exit code 0 → auto, 1 → confirm (prompt if tty, else abort),
#      2 → block (abort), 3 → malformed (abort).
#   4. Records and signs the exact decision with the pinned policy hash.
#   5. Runs the underlying op.
#
# This file is sourced by individual gate scripts; callers must have:
#     set -euo pipefail

# Capture a one-shot token in a shell-only variable before any subprocess is
# launched. Only the trusted consume command receives it as an argument.
_gate_incoming_token="${CLAVAIN_AUTHZ_TOKEN:-}"
unset CLAVAIN_AUTHZ_TOKEN GATE_AUTHZ_TOKEN
GATE_AUTHZ_TOKEN="$_gate_incoming_token"
unset _gate_incoming_token
export -n GATE_AUTHZ_TOKEN 2>/dev/null || true

# gate_resolve_authz_root [target-dir] [target|beads]
# Selects one authorization domain for the whole wrapper invocation. Explicit
# env wins. Bead operations then consult the active tracker; push/publish
# operations bind directly to their target Git root.
gate_resolve_authz_root() {
  local target="${1:-$PWD}" scope="${2:-target}"
  local root="${CLAVAIN_AUTHZ_PROJECT_ROOT:-}" context=""

  if [[ -z "$root" && "$scope" == "beads" && -n "${BEADS_DIR:-}" ]]; then
    local beads_dir="$BEADS_DIR"
    [[ "$beads_dir" != /* ]] && beads_dir="$PWD/$beads_dir"
    if [[ "$(basename "$beads_dir")" == ".beads" ]]; then
      root="$(dirname "$beads_dir")"
    fi
  fi

  if [[ -z "$root" && "$scope" == "beads" ]] && command -v bd >/dev/null 2>&1; then
    context="$(env -u CLAVAIN_AUTHZ_TOKEN bd context --json 2>/dev/null || true)"
    if command -v jq >/dev/null 2>&1; then
      root="$(printf '%s' "$context" | jq -r '.repo_root // empty' 2>/dev/null || true)"
    else
      root="$(printf '%s' "$context" | sed -n 's/.*"repo_root"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)"
    fi
  fi

  if [[ -z "$root" ]]; then
    [[ -d "$target" ]] || target="$(dirname "$target")"
    root="$(git -C "$target" rev-parse --show-toplevel 2>/dev/null || true)"
  fi
  if [[ -z "$root" && -f "$target/.clavain/intercore.db" ]]; then
    root="$target"
  fi
  if [[ -z "$root" || ! -d "$root" ]]; then
    echo "policy: cannot resolve authz project root; set CLAVAIN_AUTHZ_PROJECT_ROOT" >&2
    return 1
  fi

  CLAVAIN_AUTHZ_PROJECT_ROOT="$(cd "$root" && pwd -P)"
  export CLAVAIN_AUTHZ_PROJECT_ROOT
}

gate_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 | awk '{print $1}'
  else
    openssl dgst -sha256 | awk '{print $NF}'
  fi
}

gate_require_jq() {
  if ! command -v jq >/dev/null 2>&1 || ! jq --version >/dev/null 2>&1; then
    echo "policy: jq is required for fail-closed authorization parsing" >&2
    return 1
  fi
}

# gate_require_signer
# Fails before any proof-state mutation, token consumption, or irreversible op
# when the selected DB/keypair is missing, stale, mismatched, or unsafe.
gate_require_signer() {
  # Schemas 37–39 add tables/columns outside the signed authorization ledger
  # (v39: goal containment, audited 2026-07-21). Keep this range closed so a
  # future Intercore migration requires another audit.
  local out min_schema=36 max_schema=39
  gate_require_jq || return 1
  if ! out="$(clavain-cli policy doctor --require-signer \
      --project-root="$CLAVAIN_AUTHZ_PROJECT_ROOT" 2>&1)"; then
    echo "policy: signer preflight failed for $CLAVAIN_AUTHZ_PROJECT_ROOT" >&2
    [[ -n "$out" ]] && echo "$out" >&2
    return 1
  fi
  if ! printf '%s' "$out" | jq -e \
      --arg root "$CLAVAIN_AUTHZ_PROJECT_ROOT" \
      --argjson min_schema "$min_schema" \
      --argjson max_schema "$max_schema" '
    .status == "ok" and .role == "signer" and
    (.schema | type == "number") and
    (.schema == (.schema | floor)) and
    .schema >= $min_schema and .schema <= $max_schema and
    .project_root == $root and
    (.fingerprint | type == "string" and test("^[0-9a-f]{16}$")) and
    (.manifest_sha256 | type == "string" and test("^[0-9a-f]{64}$"))
  ' >/dev/null 2>&1; then
    echo "policy: malformed signer preflight response; operation not run" >&2
    return 1
  fi
}

# gate_bd_state <bead> <dimension>
# Queries `bd state <bead> <dim>` and echoes the value (empty on miss).
# Best-effort — silent on bd-not-installed, empty result, or non-zero exit.
gate_bd_state() {
  local bead="$1" dim="$2"
  if [[ -z "$bead" ]] || ! command -v bd >/dev/null 2>&1; then
    return 0
  fi
  env -u CLAVAIN_AUTHZ_TOKEN bd state "$bead" "$dim" 2>/dev/null || true
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

# gate_check <op> [extra policy check flags...]
# Emits the JSON output on stdout (caller captures) and returns the numeric
# exit code from `clavain-cli policy check`.
#
# Sets globals on success:
#   GATE_POLICY_HASH
#   GATE_POLICY_MATCH
#   GATE_POLICY_REASON       human-facing explanation of the decision
#   GATE_DELEGATION_CAPPED   "true" when the delegation level, not the policy,
#                            is what withheld authorization
gate_check() {
  local op="$1"
  shift || true
  local raw rc policy_mode=""
  # Remember the target so a refusal can be recorded against it. The abort path
  # runs in gate_prompt_or_abort, which only receives the op.
  GATE_TARGET=""
  local _a
  for _a in "$@"; do
    case "$_a" in --target=*) GATE_TARGET="${_a#--target=}" ;; esac
  done
  export GATE_TARGET
  raw="$(clavain-cli policy check "$op" \
      --project-root="$CLAVAIN_AUTHZ_PROJECT_ROOT" "$@" 2>&1)" && rc=0 || rc=$?

  GATE_POLICY_HASH="$(printf '%s' "$raw" | jq -r '.policy_hash // empty' 2>/dev/null || true)"
  GATE_POLICY_MATCH="$(printf '%s' "$raw" | jq -r '.policy_match // empty' 2>/dev/null || true)"
  GATE_POLICY_REASON="$(printf '%s' "$raw" | jq -r '.reason // empty' 2>/dev/null || true)"
  GATE_DELEGATION_CAPPED="$(printf '%s' "$raw" | jq -r '.delegation.capped // false' 2>/dev/null || echo false)"
  policy_mode="$(printf '%s' "$raw" | jq -r '.mode // empty' 2>/dev/null || true)"
  # schema >= 2 carries `delegation`. Requiring it is what makes the delegation
  # ceiling non-optional: a clavain-cli old enough to omit that field cannot
  # apply a ceiling at all, so pairing it with this gate must abort rather than
  # push under an authority level nothing consulted.
  #
  # Three unrelated failures used to arrive as the same "malformed policy (rc=3)":
  # a CLI that printed something other than JSON, a CLI too old to speak this
  # schema, and a response missing required fields. The operator's next move
  # differs for each -- upgrade the CLI, versus fix a config -- and the old
  # wording named the policy file, which is usually the one thing not at fault.
  # Diagnosed on zklw 2026-08-02: schema 1 there against >= 2 here, reported as
  # "malformed policy" (Sylveste-tozs). Record which failure it was, with numbers.
  GATE_MALFORMED_REASON=""
  GATE_OBSERVED_SCHEMA=""
  local _req_schema=2 _missing=""
  if ! printf '%s' "$raw" | jq -e . >/dev/null 2>&1; then
    GATE_MALFORMED_REASON="clavain-cli returned no parseable JSON (its exit was ${rc}); first bytes: $(printf '%s' "$raw" | tr '\n' ' ' | cut -c1-140)"
    rc=3
  else
    GATE_OBSERVED_SCHEMA="$(printf '%s' "$raw" | jq -r '.schema // "absent"' 2>/dev/null || echo absent)"
    if ! printf '%s' "$raw" | jq -e '(.schema | type == "number") and .schema >= 2' >/dev/null 2>&1; then
      GATE_MALFORMED_REASON="response failed schema validation: clavain-cli reports schema ${GATE_OBSERVED_SCHEMA}, this gate requires >= ${_req_schema} (clavain-cli too old for this gate -- it cannot report a delegation ceiling, so proceeding would authorize under an authority level nothing consulted). The policy file is not implicated. Upgrade clavain-cli on this host."
      rc=3
    else
      _missing="$(printf '%s' "$raw" | jq -r '
        [ (if (.mode == "auto" or .mode == "force_auto" or .mode == "confirm" or .mode == "block") then empty else "mode" end),
          (if ((.policy_hash | type) == "string" and (.policy_hash | length) > 0) then empty else "policy_hash" end),
          (if ((.policy_match | type) == "string" and (.policy_match | length) > 0) then empty else "policy_match" end),
          (if ((.delegation | type) == "object") then empty else "delegation" end),
          (if ((.delegation | type) == "object" and (.delegation.level | type) == "number") then empty else "delegation.level" end),
          (if ((.delegation | type) == "object" and (.delegation.declared | type) == "boolean") then empty else "delegation.declared" end)
        ] | join(", ")' 2>/dev/null || echo "unknown")"
      if [ -n "$_missing" ]; then
        GATE_MALFORMED_REASON="response failed schema validation: schema ${GATE_OBSERVED_SCHEMA} is acceptable, but these fields are absent or mistyped: ${_missing}. The policy file is not implicated."
        rc=3
      fi
    fi
  fi

  case "$rc:$policy_mode" in
    0:auto|0:force_auto|1:confirm|2:block|3:*) ;;
    *)
      if [ -z "$GATE_MALFORMED_REASON" ]; then
        GATE_MALFORMED_REASON="clavain-cli exit ${rc} does not agree with the mode it reported (mode=${policy_mode:-absent}); the response validated, so this is an engine disagreement rather than a schema or policy problem"
      fi
      rc=3
      ;;
  esac

  export GATE_POLICY_HASH GATE_POLICY_MATCH GATE_POLICY_REASON GATE_DELEGATION_CAPPED
  export GATE_MALFORMED_REASON GATE_OBSERVED_SCHEMA
  return "$rc"
}

# gate_explain_withholding <op>
# Prints why authorization was withheld, on stderr. A delegation-capped decision
# is called out separately from a policy one: the operator's next move differs
# — raise the declared level versus satisfy the rule's requires.
gate_explain_withholding() {
  local op="$1"
  if [[ "${GATE_DELEGATION_CAPPED:-false}" == "true" ]]; then
    echo "policy: ${op} withheld by the delegation level, not by the policy rule" >&2
    [[ -n "${GATE_POLICY_REASON:-}" ]] && echo "  ${GATE_POLICY_REASON}" >&2
    echo "  raise it with: ic config set autonomy.delegation_level <0-5>" >&2
    echo "  see docs/canon/autonomy.md for what each level means" >&2
  elif [[ -n "${GATE_POLICY_REASON:-}" ]]; then
    echo "policy: ${op} — ${GATE_POLICY_REASON}" >&2
  fi
}

# gate_prompt_or_abort <op>
# Called when policy check exits 1 (confirm). Prompts on tty, aborts otherwise.
# Sets GATE_MODE=confirmed on accept.
# gate_record_withheld <op>
#
# Records a decision that did NOT proceed. Without this the audit table holds
# only granted authorizations, so "how often did the ceiling withhold a push"
# has no rows to count — the refusal path exits before gate_record_signed ever
# runs, which is exactly the case the evidence is meant to capture.
#
# Best-effort by construction: the operation is already being refused, and a
# failure to write the audit row must never be able to change that. The grant
# path deliberately keeps the opposite rule (record failure aborts the op).
gate_record_withheld() {
  local op="$1"
  local target="${GATE_TARGET:-}"
  # No target means nothing stable to key the row to; skip rather than invent
  # one. Gates that do not pass --target simply contribute no refusal rows.
  [[ -n "$target" ]] || return 0
  local agent
  agent="$(gate_resolve_agent)"
  local args=(
    --op="$op"
    --target="$target"
    --agent="$agent"
    --mode=blocked
    --policy-match="${GATE_POLICY_MATCH:-}"
    --policy-hash="${GATE_POLICY_HASH:-}"
  )
  if [[ "${GATE_DELEGATION_CAPPED:-false}" == "true" ]]; then
    args+=( --delegation-capped )
  fi
  if ! clavain-cli policy record-signed \
      --project-root="$CLAVAIN_AUTHZ_PROJECT_ROOT" "${args[@]}" >/dev/null 2>&1; then
    echo "policy: could not record the withheld ${op} decision; the refusal stands" >&2
  fi
  return 0
}

gate_prompt_or_abort() {
  local op="$1"
  gate_explain_withholding "$op"
  if [[ -t 0 ]]; then
    local ans
    read -rp "policy: ${op} requires confirmation. Proceed? [y/N] " ans
    if [[ "$ans" =~ ^[yY]$ ]]; then
      GATE_MODE=confirmed
      export GATE_MODE
      return 0
    fi
    echo "aborted" >&2
    gate_record_withheld "$op"
    return 1
  fi
  echo "policy: ${op} requires confirmation; no tty available" >&2
  gate_record_withheld "$op"
  return 1
}

# gate_decide_mode <rc> <op>
# Translates policy check rc into action. On success, sets GATE_MODE to one of
# auto | confirmed. On failure, exits with a user-facing message.
gate_decide_mode() {
  local rc="$1" op="$2"
  case "$rc" in
    0) GATE_MODE=auto; export GATE_MODE; return 0 ;;
    1) gate_prompt_or_abort "$op" || exit 1; return 0 ;;
    2) echo "policy: ${op} blocked" >&2; exit 1 ;;
    3)
      # "malformed policy" named the policy file for a failure that is almost
      # never the policy file's. Say which of the three it was, and show the
      # numbers, so the fix is readable from the refusal itself.
      if [ -n "${GATE_MALFORMED_REASON:-}" ]; then
        echo "policy: ${op} not authorized -- ${GATE_MALFORMED_REASON}" >&2
      else
        echo "policy: ${op} could not be authorized: the signer response did not validate and no reason was recorded (rc=3)" >&2
      fi
      exit 1 ;;
    *) echo "policy: ${op} engine error (rc=${rc})" >&2; exit 1 ;;
  esac
}

# gate_record_signed <op> <target> <bead-or-empty> [extra flags...]
# Records and signs exactly one authorization decision before the operation.
gate_record_signed() {
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
  # Whether the ceiling changed this decision is the one delegation fact the
  # recorder cannot re-derive later: it depends on what the policy would have
  # said, which only the check that already ran knows. Everything else about
  # the level is re-read from kernel state at record time.
  if [[ "${GATE_DELEGATION_CAPPED:-false}" == "true" ]]; then
    args+=( --delegation-capped )
  fi
  local raw
  if ! raw="$(clavain-cli policy record-signed \
      --project-root="$CLAVAIN_AUTHZ_PROJECT_ROOT" "${args[@]}" "$@" 2>&1)"; then
    echo "policy: signed authorization record failed (op=${op} target=${target}); operation not run" >&2
    [[ -n "$raw" ]] && echo "$raw" >&2
    return 1
  fi
  if ! printf '%s' "$raw" | jq -e '.status == "ok" and .signed == 1 and (.id | type == "string" and length > 0)' >/dev/null 2>&1; then
    echo "policy: malformed record-signed response; operation not run" >&2
    return 1
  fi
}

# gate_token_consume <op> <target>
# If a token was captured from $CLAVAIN_AUTHZ_TOKEN, attempts to consume it
# against the given
# op/target scope. Sets GATE_CONSUMED=1 on success and unsets the env var to
# prevent child-process leakage. Exit contract (per authz v2 plan r3):
#
#   CLI exit 0 (success)     → GATE_CONSUMED=1, GATE_MODE=auto, return 0.
#   CLI exit 2 (token-state) → already-consumed OR expired — passive drift,
#                              safe to fall through. GATE_CONSUMED=0, return 0.
#   CLI exit 3 (not-found)   → malformed string or stale ULID — fall through.
#                              GATE_CONSUMED=0, return 0.
#   CLI exit 4 (auth-fail)   → sig-verify | POP | scope-widen | caller-mismatch
#                              | cross-project | expect-mismatch | REVOKED |
#                              cascade-on-non-root. HARD FAIL — caller exits.
#                              An operator-invoked revoke is stronger intent
#                              than passive state; falling through to legacy
#                              policy would let a legacy rule silently
#                              override the revoke. Return 1.
#   CLI exit 1/other         → unexpected (DB/IO/programmer). HARD FAIL. Return 1.
#
# An empty captured token is a no-op: GATE_CONSUMED=0, return 0 (legacy
# path runs). The caller MUST check this function's return code BEFORE
# checking $GATE_CONSUMED.
gate_token_consume() {
  local op="$1" target="$2"
  GATE_CONSUMED=0
  export GATE_CONSUMED
  if [[ -z "${GATE_AUTHZ_TOKEN:-}" ]]; then
    return 0
  fi

  local out rc
  out="$(clavain-cli policy token consume \
          --project-root="$CLAVAIN_AUTHZ_PROJECT_ROOT" \
          --token="$GATE_AUTHZ_TOKEN" \
          --expect-op="$op" \
          --expect-target="$target" 2>&1)" && rc=0 || rc=$?

  case "$rc" in
    0)
      local receipt_line receipt_json receipt_tail
      receipt_line="${out%%$'\n'*}"
      receipt_json="${receipt_line#\# authz-receipt }"
      receipt_tail="${out#*$'\n'}"
      if [[ "$receipt_line" == "$out" || "$receipt_line" != '# authz-receipt '* ]] ||
         ! printf '%s' "$receipt_json" | jq -e --arg op "$op" --arg target "$target" '
           .schema == 1 and .status == "consumed" and
           .op == $op and .target == $target and
           (.audit_id | type == "string" and length > 0) and .signed == true
         ' >/dev/null 2>&1 ||
         [[ "$receipt_tail" != $'# authz-unset-begin\nunset CLAVAIN_AUTHZ_TOKEN\n# authz-unset-end' ]]; then
        echo "authz: malformed token-consume success receipt; gate hard-fails" >&2
        return 1
      fi
      GATE_CONSUMED=1
      GATE_MODE=auto
      export GATE_CONSUMED GATE_MODE
      # Belt: unset in this process so child ops don't re-see a consumed
      # token. The CLI also emits an eval-friendly `unset CLAVAIN_AUTHZ_TOKEN`
      # block to stdout for interactive shells.
      unset GATE_AUTHZ_TOKEN CLAVAIN_AUTHZ_TOKEN
      echo "authz: token consumed for ${op} ${target}" >&2
      return 0
      ;;
    2)
      echo "authz: token unusable (state — consumed or expired): ${out}" >&2
      echo "authz: falling back to policy check" >&2
      return 0
      ;;
    3)
      echo "authz: token unusable (not-found or malformed): ${out}" >&2
      echo "authz: falling back to policy check" >&2
      return 0
      ;;
    4)
      echo "authz: AUTH FAILURE — token rejected for ${op} ${target}: ${out}" >&2
      echo "authz: gate hard-fails; resolve the mismatch and retry" >&2
      return 1
      ;;
    *)
      echo "authz: unexpected token consume error (rc=${rc}): ${out}" >&2
      echo "authz: gate hard-fails; this is a bug — check intercore DB" >&2
      return 1
      ;;
  esac
}
