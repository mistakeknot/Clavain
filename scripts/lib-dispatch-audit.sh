#!/usr/bin/env bash
# Immutable role resolution and per-attempt lifecycle evidence. No prompts or
# credentials are recorded. A missing audit store prevents model execution.

_dispatch_audit_id() {
  if command -v uuidgen >/dev/null 2>&1; then uuidgen; else printf '%s-%s-%s-%s\n' "$(date +%s)" "$$" "$RANDOM" "$RANDOM"; fi
}

_classify_dispatch_failure() {
  local stderr_file="$1" exit_code="${2:-1}"
  [[ "$exit_code" == 0 ]] && { echo success; return 0; }
  if [[ -f "$stderr_file" ]]; then
    # A final denial dominates earlier transport/account failures in this attempt.
    if grep -qiE '\b403\b|misalignment|policy[^[:alnum:]]+(block|den)' "$stderr_file"; then echo terminal_policy
    elif grep -qiE '\b429\b|too many requests|rate.?limit' "$stderr_file"; then echo rate_limited
    elif grep -qiE 'not supported when using Codex with a ChatGPT account|not available (to|for) (this|your) account|account[^[:alnum:]]+access' "$stderr_file"; then echo account_access_absent
    elif grep -qiE 'model_not_found|model[^[:alnum:]]+(not found|does not exist|unavailable)|unknown model' "$stderr_file"; then echo model_unavailable
    elif grep -qiE '\b4[0-9]{2}\b|bad request|unauthorized|forbidden' "$stderr_file"; then echo terminal_configuration
    else echo terminal_error
    fi
  else echo terminal_error
  fi
}

_prepare_role_audit() {
  DISPATCH_ID="${DISPATCH_ID:-$(_dispatch_audit_id)}"
  if [[ -z "${ATTEMPT_ID:-}" ]]; then
    ATTEMPT_ID="$(_dispatch_audit_id)"
    CHECKOUT_BEFORE="$(git -C "${WORKDIR:-.}" rev-parse HEAD 2>/dev/null || true)"
  fi
}

_role_audit_context() {
  local state="$1" exit_code="$2" failure_class="$3" version="" verdict="" head_after=""
  [[ "$ENGINE" != codex ]] || version="$(codex --version 2>/dev/null || true)"
  # A reused output path may still contain a previous attempt's sidecar.
  # Pending states have no verdict; App Server verdicts come from collection.
  if [[ "$state" == completed || "$state" == failed ]] && [[ "${DISPATCH_RESULT_READY:-false}" == true && "${VIA:-exec}" != zaka && -n "${OUTPUT:-}" && -f "${OUTPUT}.verdict" ]]; then
    verdict="$(head -c 4096 "${OUTPUT}.verdict")"
  fi
  head_after="$(git -C "${WORKDIR:-.}" rev-parse HEAD 2>/dev/null || true)"
  jq -cn --argjson route "${RESOLVED_ROUTE_JSON:-null}" --argjson profile "${RESOLVED_PROFILE_JSON:-null}" \
    --arg dispatch_id "$DISPATCH_ID" --arg attempt_id "$ATTEMPT_ID" --arg state "$state" \
    --arg backend "$ENGINE" --arg model "$MODEL" --arg effort "$REASONING_EFFORT" \
    --arg service "$SERVICE_TIER" --arg version "$version" --arg sandbox "$SANDBOX" \
    --arg transport "${VIA:-exec}" --arg parent "$DISPATCH_SESSION_ID" \
    --arg run "${CLAVAIN_RUN_ID:-}" --arg bead "${CLAVAIN_BEAD_ID:-}" \
    --arg session "${ZAKA_SESSION:-}" --arg events "${ZAKA_EVENT_LOG:-}" \
    --arg before "$CHECKOUT_BEFORE" --arg after "$head_after" \
    --arg output "$OUTPUT" --arg verdict "$verdict" --arg failure "$failure_class" \
    --argjson exit_code "$exit_code" \
    '{schema_version:1,dispatch_id:$dispatch_id,attempt_id:$attempt_id,state:$state,
      resolved_route:$route,resolved_profile:$profile,parent_session_id:$parent,
      run_id:$run,bead_id:$bead,
      execution:{backend:$backend,model:$model,reasoning_effort:$effort,service_tier:$service,
        codex_version:$version,sandbox:$sandbox,transport:$transport,session_id:$session,event_log:$events},
      checkout:{before:$before,after:$after},
      terminal:($state == "completed" or $state == "failed"),
      result:{exit_code:$exit_code,failure_class:$failure,output_path:$output,verdict:$verdict}}'
}

_record_role_routing_decision() {
  local exit_code="$1" failure_class="$2" state="${3:-}" reason="$FALLBACK_REASON" context
  [[ -n "$ROLE" && "$ROLE_RESOLVED" == true ]] || return 0
  command -v ic >/dev/null 2>&1 || return 1
  if [[ -z "$state" ]]; then
    state=completed
    [[ "$exit_code" == 0 ]] || state=failed
  fi
  [[ "$exit_code" == 0 ]] || reason="$failure_class"
  _prepare_role_audit
  context="$(_role_audit_context "$state" "$exit_code" "$failure_class")" || return 1
  local -a record_cmd=(ic route record "--agent=${NAME:-$ROLE}" "--model=$MODEL"
    --rule=dispatch-profile "--role=$ROLE" "--profile=$RESOLVED_PROFILE_REF"
    "--dispatch=$DISPATCH_ID" "--context=$context")
  [[ -z "$DISPATCH_SESSION_ID" ]] || record_cmd+=("--session=$DISPATCH_SESSION_ID")
  [[ -z "${CLAVAIN_RUN_ID:-}" ]] || record_cmd+=("--run=$CLAVAIN_RUN_ID")
  [[ -z "${CLAVAIN_BEAD_ID:-}" ]] || record_cmd+=("--bead=$CLAVAIN_BEAD_ID")
  [[ -z "$reason" || "$reason" == success ]] || record_cmd+=("--fallback-reason=$reason")
  [[ -z "$PRODUCER_IDENTITY" ]] || record_cmd+=("--producer-identity=$PRODUCER_IDENTITY")
  [[ -z "$VALIDATOR_RELATIONSHIP" ]] || record_cmd+=("--validator-relationship=$VALIDATOR_RELATIONSHIP")
  if ! (cd "${WORKDIR:-.}" && "${record_cmd[@]}") >/dev/null 2>&1; then
    echo "Error: cannot persist $state routing decision for '$ROLE/$RESOLVED_PROFILE_REF'" >&2
    return 1
  fi
}
