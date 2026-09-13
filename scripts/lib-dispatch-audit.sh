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
  if [[ -n "${CLAVAIN_TASK_ENROLLMENT_ID:-}" && "${DISPATCH_OBSERVATION_ATTEMPT_ID:-}" != "$ATTEMPT_ID" ]]; then
    local helper_dir
    helper_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || return 1
    DISPATCH_EXECUTION_OBSERVATION="$(python3 "$helper_dir/task-delivery.py" \
      --db "${CLAVAIN_TASK_INTERCORE_DB:-}" observe-execution --engine "$ENGINE" \
      --workdir "${WORKDIR:-.}" --profile-json "${RESOLVED_PROFILE_JSON:-null}")" || return 1
    DISPATCH_OBSERVATION_ATTEMPT_ID="$ATTEMPT_ID"
  fi
  if [[ -n "${DISPATCH_BINDING_JSON:-}" ]]; then
    DISPATCH_EXECUTION_OBSERVATION="$(jq -cn --argjson observed "${DISPATCH_EXECUTION_OBSERVATION:-null}" \
      --argjson binding "$DISPATCH_BINDING_JSON" '
      (if ($observed|type) == "object" then $observed else {} end) + {
        executable:$binding.executable_pin.path,
        executable_sha256:$binding.executable_pin.sha256,
        executable_identity_basis:"authoritative_native_binding",
        configuration_sha256:$binding.configuration.sha256,
        configuration_coverage:"exact-bound-native-operation",
        source_path:$binding.source.path,
        source_sha256:$binding.source.sha256,
        native_schema_manifest:{path:$binding.native_schema.manifest_path,sha256:$binding.native_schema.manifest_sha256},
        native_capability_evidence:{path:$binding.capability_evidence.path,sha256:$binding.capability_evidence.sha256,status:"verified"}
      }')" || return 1
  fi
}

_role_audit_context() {
  local state="$1" exit_code="$2" failure_class="$3" version="" verdict="" head_after="" native_operation="null" operation_request="null" transport="${VIA:-exec}"
  [[ "${OPERATION:-exec}" != compact ]] || transport="app-server-control"
  if [[ "$ENGINE" == codex ]]; then
    version="$("${DISPATCH_EXECUTABLE:-codex}" --version 2>/dev/null || true)"
  fi
  # A reused output path may still contain a previous attempt's sidecar.
  # Pending states have no verdict; App Server verdicts come from collection.
  if [[ "$state" == completed || "$state" == failed ]] && [[ "${DISPATCH_RESULT_READY:-false}" == true && "${VIA:-exec}" != zaka && -n "${OUTPUT:-}" && -f "${OUTPUT}.verdict" ]]; then
    verdict="$(head -c 4096 "${OUTPUT}.verdict")"
  fi
  head_after="$(git -C "${WORKDIR:-.}" rev-parse HEAD 2>/dev/null || true)"
  if [[ "${OPERATION:-exec}" != exec ]]; then
    operation_request="$(jq -cn --arg operation "$OPERATION" --arg binding "${RESUME_FROM:-}" \
      --arg binding_sha256 "${DISPATCH_BINDING_SHA256:-}" --arg seed_thread "${BOUND_NATIVE_THREAD_ID:-}" \
      --arg result_path "${DISPATCH_CONTROL_RESULT:-}" \
      '{operation:$operation,binding_path:$binding,binding_sha256:$binding_sha256,seed_thread_id:$seed_thread,operation_result_path:(if $result_path == "" then null else $result_path end)}')"
    # Admission records the request without claiming an operation attempt.
    # Replay protection treats native_operation as terminal attempt evidence,
    # so publishing it in the started record would reject this same dispatch
    # when the control adapter revalidates admission immediately before RPC.
    if [[ "$state" == completed || "$state" == failed ]]; then
      native_operation="$operation_request"
    fi
    if [[ "$state" == completed || "$state" == failed ]] && [[ -n "${DISPATCH_CONTROL_RESULT:-}" && -f "$DISPATCH_CONTROL_RESULT" ]]; then
      native_operation="$(jq -c --arg binding "${RESUME_FROM:-}" --arg binding_sha256 "${DISPATCH_BINDING_SHA256:-}" \
        --arg result_path "$DISPATCH_CONTROL_RESULT" \
        '. + {binding_path:$binding,binding_sha256:$binding_sha256,operation_result_path:$result_path}' \
        "$DISPATCH_CONTROL_RESULT" 2>/dev/null || printf '%s' "$native_operation")"
    elif [[ "$state" == completed || "$state" == failed ]] && [[ "$OPERATION" == resume && -n "${CLAVAIN_REVIEW_EVENTS:-}" && -f "$CLAVAIN_REVIEW_EVENTS" ]]; then
      local resume_native
      resume_native="$(python3 "$DISPATCH_SCRIPT_DIR/dispatch_control.py" validate-resume-events \
        --binding "$RESUME_FROM" --events "$CLAVAIN_REVIEW_EVENTS" 2>/dev/null || true)"
      if [[ -n "$resume_native" ]]; then
        native_operation="$(jq -cn --argjson base "$native_operation" --argjson observed "$resume_native" '$base + $observed')"
      fi
    fi
  fi
  jq -cn --argjson route "${RESOLVED_ROUTE_JSON:-null}" --argjson profile "${RESOLVED_PROFILE_JSON:-null}" \
    --arg dispatch_id "$DISPATCH_ID" --arg attempt_id "$ATTEMPT_ID" --arg state "$state" \
    --arg backend "$ENGINE" --arg model "$MODEL" --arg effort "$REASONING_EFFORT" \
    --arg service "$SERVICE_TIER" --arg version "$version" --arg sandbox "$SANDBOX" \
    --arg transport "$transport" --arg parent "$DISPATCH_SESSION_ID" \
    --arg run "${CLAVAIN_RUN_ID:-}" --arg bead "${CLAVAIN_BEAD_ID:-}" \
    --arg session "${ZAKA_SESSION:-}" --arg events "${ZAKA_EVENT_LOG:-${COMPACT_EVENTS:-${CLAVAIN_REVIEW_EVENTS:-}}}" \
    --arg before "$CHECKOUT_BEFORE" --arg after "$head_after" \
    --arg output "$OUTPUT" --arg verdict "$verdict" --arg failure "$failure_class" \
    --arg enrollment "${CLAVAIN_TASK_ENROLLMENT_ID:-}" --arg manifest "${CLAVAIN_TASK_MANIFEST_SHA256:-}" \
    --arg cohort "${CLAVAIN_TASK_COHORT_ID:-}" \
    --argjson exit_code "$exit_code" --argjson observation "${DISPATCH_EXECUTION_OBSERVATION:-null}" \
    --argjson operation_request "$operation_request" \
    --argjson native_operation "$native_operation" \
    --argjson usage_collection "${DISPATCH_USAGE_COLLECTION:-null}" \
    '{schema_version:1,dispatch_id:$dispatch_id,attempt_id:$attempt_id,state:$state,
      resolved_route:$route,resolved_profile:$profile,parent_session_id:$parent,
      run_id:$run,bead_id:$bead,
      execution:({backend:$backend,model:$model,reasoning_effort:$effort,service_tier:$service,
        codex_version:$version,sandbox:$sandbox,transport:$transport,session_id:$session,event_log:$events}
        + (if $observation | type == "object" then $observation else {} end)
        + (if $operation_request | type == "object" then {operation_request:$operation_request} else {} end)
        + (if $native_operation | type == "object" then {native_operation:$native_operation} else {} end)
        + (if $usage_collection | type == "object" then {usage_collection:$usage_collection} else {} end)),
      checkout:{before:$before,after:$after},
      terminal:($state == "completed" or $state == "failed"),
      result:{exit_code:$exit_code,failure_class:$failure,output_path:$output,verdict:$verdict}}
      + (if $enrollment != "" then {task_envelope:{enrollment_id:$enrollment,manifest_sha256:$manifest,cohort_id:$cohort}} else {} end)'
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
  _prepare_role_audit || return 1
  if [[ -n "${CLAVAIN_USAGE_OUTPUT_DIR:-}" && "$ENGINE" == codex && "${VIA:-exec}" == exec && "${OPERATION:-exec}" != compact &&
        ( "$state" == completed || "$state" == failed ) && "${DISPATCH_USAGE_ATTEMPT:-}" != "$ATTEMPT_ID" ]]; then
    local collector_dir collector_events
    collector_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || return 1
    collector_events="${COMPACT_EVENTS:-${CLAVAIN_REVIEW_EVENTS:-}}"
    # Runs after native completion, never in a trap or host startup path. No
    # delayed reconciliation here. Collection failure is observational only.
    if ! DISPATCH_USAGE_COLLECTION="$(python3 "$collector_dir/usage_collector.py" --phase completion \
        --output-dir "$CLAVAIN_USAGE_OUTPUT_DIR/completion-$ATTEMPT_ID" --events "$collector_events" 2>/dev/null)"; then
      DISPATCH_USAGE_COLLECTION='{"status":"unavailable"}'
      echo "Warning: optional completion usage collection unavailable" >&2
    fi
    DISPATCH_USAGE_ATTEMPT="$ATTEMPT_ID"
  fi
  context="$(_role_audit_context "$state" "$exit_code" "$failure_class")" || return 1
  local -a record_cmd=(ic route record "--agent=${NAME:-$ROLE}" "--model=$MODEL"
    --rule=dispatch-profile "--role=$ROLE" "--profile=$RESOLVED_PROFILE_REF"
    "--dispatch=$DISPATCH_ID" "--context=$context"
    "--policy-hash=$(jq -r '.policy_hash // empty' <<< "${RESOLVED_ROUTE_JSON:-null}")"
    "--excluded=$(jq -c '.excluded // []' <<< "${RESOLVED_ROUTE_JSON:-null}")")
  [[ -z "$DISPATCH_SESSION_ID" ]] || record_cmd+=("--session=$DISPATCH_SESSION_ID")
  [[ -z "${CLAVAIN_RUN_ID:-}" ]] || record_cmd+=("--run=$CLAVAIN_RUN_ID")
  [[ -z "${CLAVAIN_BEAD_ID:-}" ]] || record_cmd+=("--bead=$CLAVAIN_BEAD_ID")
  [[ -z "$reason" || "$reason" == success ]] || record_cmd+=("--fallback-reason=$reason")
  [[ -z "$PRODUCER_IDENTITY" ]] || record_cmd+=("--producer-identity=$PRODUCER_IDENTITY")
  [[ -z "$VALIDATOR_RELATIONSHIP" ]] || record_cmd+=("--validator-relationship=$VALIDATOR_RELATIONSHIP")
  local audit_workdir="${WORKDIR:-.}" task_db="${CLAVAIN_INTERCORE_DB:-}" project_dir
  if [[ -n "${CLAVAIN_TASK_ENROLLMENT_ID:-}" ]]; then
    if [[ -z "${CLAVAIN_TASK_MANIFEST_SHA256:-}" || -z "${CLAVAIN_TASK_COHORT_ID:-}" || -z "${CLAVAIN_TASK_INTERCORE_DB:-}" ]]; then
      echo "Error: enrolled dispatch requires complete task envelope and explicit Intercore database" >&2
      return 1
    fi
    # ic requires an explicit DB path under its cwd. Preserve the actual project
    # identity while invoking from the authoritative database's parent directory.
    if [[ -n "$task_db" && "$task_db" != "$CLAVAIN_TASK_INTERCORE_DB" ]]; then
      echo "Error: preparation and task Intercore database bindings differ" >&2
      return 1
    fi
    task_db="$CLAVAIN_TASK_INTERCORE_DB"
  fi
  if [[ -n "$task_db" ]]; then
    if [[ "$task_db" != /* || ! -f "$task_db" ]]; then
      echo "Error: dispatch requires an absolute path to its existing Intercore database" >&2
      return 1
    fi
    if ! project_dir="$(cd "${WORKDIR:-.}" && pwd -P)"; then
      echo "Error: enrolled dispatch cannot resolve its project working directory" >&2
      return 1
    fi
    record_cmd+=("--db=$task_db" "--project=$project_dir")
    audit_workdir="$(dirname "$task_db")"
  fi
  if ! (cd "$audit_workdir" && "${record_cmd[@]}") >/dev/null 2>&1; then
    echo "Error: cannot persist $state routing decision for '$ROLE/$RESOLVED_PROFILE_REF'" >&2
    return 1
  fi
}
