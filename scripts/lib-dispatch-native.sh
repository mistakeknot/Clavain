#!/usr/bin/env bash
# Fixture-only native continuation orchestration. Production dispatch.sh never
# sources this file while its unconditional native-trusted-launcher-unavailable
# gate is closed. Every record and handoff created here is permanently
# ineligible for measured work.

_native_fixture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib-dispatch-audit.sh
source "$_native_fixture_dir/lib-dispatch-audit.sh"

native_fixture_metadata() {
  jq -cn '{schema_version:2,fixture_only:true,eligible:false,reason:"test-only-native-orchestration"}'
}

_native_fixture_require_db() {
  local database="$1" root="${NATIVE_FIXTURE_ROOT:-$PWD}" parent physical_root physical_parent
  [[ "$database" == /* && -f "$database" ]] || {
    echo "native fixture requires an explicit existing absolute database" >&2
    return 1
  }
  physical_root="$(cd "$root" && pwd -P)" || return 1
  parent="$(dirname "$database")"
  physical_parent="$(cd "$parent" && pwd -P)" || return 1
  [[ ! -L "$database" && "$database" == "$physical_parent/$(basename "$database")" ]] || {
    echo "native fixture database aliases are forbidden" >&2; return 1;
  }
  case "$physical_parent/" in
    "$physical_root/"*) ;;
    *) echo "native fixture database must remain beneath the physical fixture root" >&2; return 1 ;;
  esac
}

native_fixture_records() {
  local database="$1" ic_bin="${2:-ic}" rows
  _native_fixture_require_db "$database" || return 1
  rows="$(cd "$(dirname "$database")" && "$ic_bin" "--db=$database" --json route list --limit=1000000)" || return 1
  jq -e '
    type == "array" and length < 1000000 and length != 1000 and
    all(.[]; type == "object" and (.id|type) == "number" and (.id|floor) == .id) and
    ((map(.id)|length) == (map(.id)|unique|length))
  ' <<< "$rows" >/dev/null || {
    echo "native fixture authoritative export malformed or truncated" >&2
    return 1
  }
  printf '%s\n' "$rows"
}

native_fixture_lock_acquire() {
  local database="$1" name="$2" scope="$3" ic_bin="${4:-ic}" owner
  _native_fixture_require_db "$database" || return 1
  [[ "$name" =~ ^[a-z0-9-]+$ && "$scope" =~ ^[0-9a-f]{64}$ ]] || {
    echo "native fixture lock name/scope is unsafe" >&2
    return 1
  }
  owner="$$:$(hostname)"
  (cd "$(dirname "$database")" && "$ic_bin" "--db=$database" lock acquire "$name" "$scope" --timeout=1s "--owner=$owner")
}

native_fixture_lock_release() {
  local database="$1" name="$2" scope="$3" ic_bin="${4:-ic}" owner
  _native_fixture_require_db "$database" || return 1
  owner="$$:$(hostname)"
  (cd "$(dirname "$database")" && "$ic_bin" "--db=$database" lock release "$name" "$scope" "--owner=$owner")
}

native_fixture_append_audit() {
  local database="$1" phase="$2" phase_json="$3" ic_bin="${4:-ic}" context response ident rows actual project
  _native_fixture_require_db "$database" || return 1
  jq -e 'type == "object"' <<< "$phase_json" >/dev/null || return 1
  phase_json="$(jq -c '. + {fixture_only:true,eligible:false}' <<< "$phase_json")" || return 1
  DISPATCH_NATIVE_ADMISSION_JSON=null
  DISPATCH_NATIVE_SEND_INTENT_JSON=null
  DISPATCH_NATIVE_FIXTURE=true
  case "$phase" in
    started) DISPATCH_NATIVE_ADMISSION_JSON="$phase_json" ;;
    send-intent) DISPATCH_NATIVE_SEND_INTENT_JSON="$phase_json" ;;
    terminal) phase=completed; [[ "${NATIVE_FIXTURE_EXIT_CODE:-0}" == 0 ]] || phase=failed ;;
    *) echo "unknown native fixture audit phase" >&2; return 1 ;;
  esac
  CLAVAIN_INTERCORE_DB="$database"
  DISPATCH_NATIVE_IC="$ic_bin"
  ROLE="${ROLE:-routine-execution}" ROLE_RESOLVED=true RESOLVED_PROFILE_REF="${RESOLVED_PROFILE_REF:-fixture}"
  context="$(_role_audit_context "${phase/send-intent/started}" "${NATIVE_FIXTURE_EXIT_CODE:-0}" "${NATIVE_FIXTURE_FAILURE_CLASS:-}")" || return 1
  response="$(_record_role_routing_decision "${NATIVE_FIXTURE_EXIT_CODE:-0}" "${NATIVE_FIXTURE_FAILURE_CLASS:-}" "${phase/send-intent/started}")" || return 1
  ident="$(jq -er '.id | select(type == "number" and floor == .)' <<< "$response")" || return 1
  rows="$(native_fixture_records "$database" "$ic_bin")" || return 1
  actual="$(jq -cer --argjson ident "$ident" '.[] | select(.id == $ident) | .context_json | fromjson' <<< "$rows")" || return 1
  jq -en --argjson actual "$actual" --argjson expected "$context" '$expected | to_entries | all(.[]; $actual[.key] == .value)' >/dev/null || {
    echo "native fixture audit readback mismatch" >&2
    return 1
  }
  printf '%s\n' "$ident"
}

native_fixture_elect() {
  local database="$1" operation_key="$2" reservation_id="$3" ic_bin="${4:-ic}" rows module
  rows="$(native_fixture_records "$database" "$ic_bin")" || return 1
  module="$_native_fixture_dir/dispatch_control.py"
  python3 - "$module" "$operation_key" "$reservation_id" "$rows" <<'PY'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("dispatch_control", sys.argv[1])
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
records = module.strict_json(sys.argv[4].encode())
module.elect_native_reservation(records, sys.argv[2], int(sys.argv[3]))
print(json.dumps({"fixture_only": True, "eligible": False, "winner": int(sys.argv[3])}, separators=(",", ":")))
PY
}

native_fixture_handoff_to_python() {
  local packet="$1" result_path="$2" child_pid child_rc old_int old_term native_signal=0 writer_pid handoff_fd
  packet="$(jq -c --argjson parent "$$" '. + {fixture_only:true,eligible:false,parent_pid:$parent}' <<< "$packet")" || return 1
  old_int="$(trap -p INT)"; old_term="$(trap -p TERM)"
  trap 'native_signal=130; [[ -z "${child_pid:-}" ]] || kill -INT "$child_pid" 2>/dev/null || true' INT
  trap 'native_signal=143; [[ -z "${child_pid:-}" ]] || kill -TERM "$child_pid" 2>/dev/null || true' TERM
  exec {handoff_fd}< <(
    printf '%s' "$packet" | python3 -c 'import importlib.util,sys
s=importlib.util.spec_from_file_location("control",sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
raw=sys.stdin.buffer.read(m.MAX_FRAME+1)
if len(raw)>m.MAX_FRAME: raise ValueError("oversized fixture handoff")
m.write_framed_handoff(1,m.strict_json(raw))' "$_native_fixture_dir/dispatch_control.py"
  )
  writer_pid=$!
  python3 -c 'import importlib.util,sys; s=importlib.util.spec_from_file_location("dispatch_control",sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); r=m.run_fixture_handoff(0,sys.argv[2]); sys.exit(r["process"]["exit_code"] or 0)' \
    "$_native_fixture_dir/dispatch_control.py" "$result_path" <&"$handoff_fd" &
  child_pid=$!
  exec {handoff_fd}<&-
  if (( native_signal )); then kill -"$((native_signal-128))" "$child_pid" 2>/dev/null || true; fi
  child_rc=0
  while :; do
    wait "$child_pid" && child_rc=0 || child_rc=$?
    kill -0 "$child_pid" 2>/dev/null || break
  done
  wait "$writer_pid" || true
  [[ -z "$old_int" ]] && trap - INT || eval "$old_int"
  [[ -z "$old_term" ]] && trap - TERM || eval "$old_term"
  (( native_signal == 0 )) || return "$native_signal"
  return "$child_rc"
}

_native_fixture_python() {
  local operation="$1"; shift
  # Bash's builtin printf streams data without the OS per-argument limit.
  # This private helper channel is separate from the digested native handoff.
  printf '%s\0' "$@" | python3 -c 'import importlib.util,sys
s=importlib.util.spec_from_file_location("c",sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
raw=sys.stdin.buffer.read(4*m.MAX_FRAME+1)
if len(raw)>4*m.MAX_FRAME or not raw.endswith(b"\0"): raise ValueError("invalid private helper input")
arguments=[v.decode() for v in raw[:-1].split(b"\0")]
print(m.canonical(getattr(m,sys.argv[2])(*arguments)))' "$_native_fixture_dir/dispatch_control.py" "$operation"
}

native_fixture_run() {
  # Deliberately source-only; dispatch.sh never sources this library. No fixture
  # output can establish production eligibility, including failed audit rows.
  local spec="$1" prepared admission database key reservation intent packet rc=0 terminal rows ic_bin
  prepared="$(_native_fixture_python prepare_fixture_operation "$spec" "$$")" || return 1
  admission="$(jq -c .admission <<< "$prepared")"
  database="$(jq -r .database_identity.path <<< "$admission")"
  ic_bin="$(jq -r .ic <<< "$prepared")"
  _native_fixture_require_db "$database" || return 1
  OPERATION="$(jq -r .operation <<< "$admission")" ENGINE=codex VIA=exec
  DISPATCH_NATIVE_FIXTURE=true
  DISPATCH_ID="$(jq -r .dispatch_id <<< "$admission")" ATTEMPT_ID="$(jq -r .attempt_id <<< "$admission")"
  WORKDIR="$(jq -r .workdir <<< "$prepared")" RESUME_FROM="$(jq -r .snapshot.path <<< "$prepared")"
  DISPATCH_BINDING_SHA256="$(jq -r .snapshot.sha256 <<< "$prepared")" BOUND_NATIVE_THREAD_ID="$(jq -r .seed_thread_id <<< "$admission")"
  RESOLVED_ROUTE_JSON="$(jq -c .route <<< "$prepared")" RESOLVED_PROFILE_JSON="$(jq -c .profile <<< "$prepared")"
  MODEL="$(jq -r .configuration.request.model <<< "$prepared")" REASONING_EFFORT="$(jq -r .configuration.request.config.model_reasoning_effort <<< "$prepared")"
  SERVICE_TIER="$(jq -r .configuration.request.serviceTier <<< "$prepared")" SANDBOX="$(jq -r .configuration.request.sandbox <<< "$prepared")"
  DISPATCH_EXECUTABLE="$(jq -r .executable <<< "$prepared")" OUTPUT="$(jq -r .directory <<< "$prepared")/last-message"
  key="$(jq -r .operation_key <<< "$admission")"
  reservation="$(native_fixture_append_audit "$database" started "$admission" "$ic_bin")" || return 1
  # No authoritative check/append retry. A lost append response burns the right.
  if ! packet="$(_native_fixture_python continue_fixture_operation "$prepared" "$reservation")"; then
    _native_fixture_python seal_fixture_admission_failure "$prepared" "$reservation" admission >/dev/null || return 1
    native_fixture_finish "$prepared" 1 || return 1
    return 1
  fi
  intent="$(jq -c .send_intent <<< "$packet")"
  if ! intent="$(native_fixture_append_audit "$database" send-intent "$intent" "$ic_bin")"; then
    _native_fixture_python seal_fixture_admission_failure "$prepared" "$reservation" send-intent-recording >/dev/null || return 1
    native_fixture_finish "$prepared" 1 || return 1
    return 1
  fi
  packet="$(jq -c --argjson id "$intent" '. + {send_intent_decision_id:$id}' <<< "$packet")"
  DISPATCH_CONTROL_RESULT="$(jq -r .directory <<< "$prepared")/envelope.json"
  native_fixture_handoff_to_python "$packet" "$DISPATCH_CONTROL_RESULT" || rc=$?
  native_fixture_finish "$prepared" "$rc" || return 1
  return "$rc"
}

native_fixture_finish() {
  local prepared="$1" database ic_bin terminal rows
  NATIVE_FIXTURE_EXIT_CODE="$2"
  database="$(jq -r .admission.database_identity.path <<< "$prepared")"
  ic_bin="$(jq -r .ic <<< "$prepared")"
  DISPATCH_CONTROL_RESULT="$(jq -r .directory <<< "$prepared")/envelope.json"
  NATIVE_FIXTURE_FAILURE_CLASS="$(jq -r '.operation_result.path' "$DISPATCH_CONTROL_RESULT" | xargs -I '{}' jq -r '.failure.class // empty' '{}')"
  terminal="$(native_fixture_append_audit "$database" terminal '{}' "$ic_bin")" || return 1
  rows="$(native_fixture_records "$database" "$ic_bin")" || return 1
  _native_fixture_python export_fixture_receipt "$rows" "$terminal" "$(jq -r .directory <<< "$prepared")/receipt.json" >/dev/null || return 1
}
