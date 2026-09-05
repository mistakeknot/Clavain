#!/usr/bin/env bash
# Collect one asynchronous turn without replaying it or taking release authority.
# Exit 0: completed; 1: failed/invalid/unrecorded; 3: still pending. JSON on stdout.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT/lib-dispatch-audit.sh"
[[ $# == 1 && "$1" == as-* ]] || { echo 'Usage: bash collect-zaka.sh as-<handle>' >&2; exit 1; }
status="$(zaka status "$1" --json)"
# Metadata comes from dispatch, not the model. Reject incomplete or substituted
# execution identities; never re-resolve a route against today's configuration.
jq -e --arg session "$1" '
  .session == $session and .transport == "app-server" and
  (.config.metadata | .schema_version == 1 and (.dispatch_id | length > 0) and
    (.attempt_id | length > 0) and (.resolved_route.requested_role | length > 0)) and
  .config.model == .config.metadata.resolved_profile.profile.model and
  (.config.workdir | startswith("/")) and (.event_log | startswith("/"))
' <<< "$status" >/dev/null || { echo 'Error: missing or mismatched role dispatch provenance' >&2; exit 1; }
phase="$(jq -r '.phase' <<< "$status")"
events="$(jq -r '.event_log' <<< "$status")"
turn="$(jq -r '.turn_id' <<< "$status")"
[[ -r "$events" ]] || { echo 'Error: async event log is unavailable' >&2; exit 1; }
# Serialize collectors for this session. A stale lock fails closed and must be
# inspected by the integrator; never steal it using a PID from disk.
lock="$(dirname "$events")/.collect.lock"
mkdir "$lock" 2>/dev/null || { echo 'Error: another collector or stale collection lock exists' >&2; exit 1; }
error_file=""
trap '[[ -z "$error_file" ]] || rm -f "$error_file"; rmdir "$lock"' EXIT
log="$(jq -sc '.' "$events")"
if jq -e --arg turn "$turn" 'any(.[]; .direction == "receive" and .message.method == "turn/completed" and .message.params.turn.id == $turn and .message.params.turn.status == "completed")' <<< "$log" >/dev/null \
  && jq -e '.turn_status == "completed" and (.pending_requests | length == 0)' <<< "$status" >/dev/null; then
  # Session liveness and turn outcome differ. A completed turn can be collected
  # after shutdown/reboot, but only with its exact durable completion event.
  case "$phase" in completed|disconnected|stale|killed) phase=completed ;; esac
elif [[ "$phase" == completed ]] && jq -e '.pending_requests | length == 0' <<< "$status" >/dev/null; then
  echo 'Error: completed status lacks exact durable turn completion' >&2
  exit 1
fi
case "$phase" in
  completed)
    if ! jq -e '.turn_status == "completed" and (.pending_requests | length == 0)' <<< "$status" >/dev/null; then
      jq -cn --argjson s "$status" '{state:"pending",terminal:false,session:$s.session,turn_id:$s.turn_id,phase:$s.phase}'
      exit 3
    fi
    rc=0; failure=success; state=completed ;;
  error|disconnected|stale|killed|interrupted)
    rc=1; state=failed
    error_file="$(mktemp)"
    jq -r '.error // .phase' <<< "$status" > "$error_file"
    failure="$(_classify_dispatch_failure "$error_file" 1)" ;;
  *)
    jq -cn --argjson s "$status" '{state:"pending",terminal:false,session:$s.session,turn_id:$s.turn_id,phase:$s.phase}'
    exit 3 ;;
esac
# Read only final assistant messages from this exact turn; prior turns and tool
# outputs are not verdicts. The full evidence remains in the private event log.
verdict="$(jq -r --arg turn "$turn" '[.[] | select(.direction == "receive" and .message.method == "item/completed" and .message.params.turnId == $turn and .message.params.item.type == "agentMessage" and ((.message.params.item.phase // "final_answer") == "final_answer")) | .message.params.item.text] | last // "" | .[0:4096]' <<< "$log")"
workdir="$(jq -r '.config.workdir' <<< "$status")"
head_after="$(git -C "$workdir" rev-parse HEAD 2>/dev/null || true)"
context="$(jq -c --arg state "$state" --arg failure "$failure" --arg verdict "$verdict" --arg after "$head_after" --argjson rc "$rc" '
  . as $s | .config.metadata | .state=$state | .terminal=true |
  .execution.session_id=$s.session | .execution.event_log=$s.event_log |
  .execution.thread_id=$s.thread_id | .execution.turn_id=$s.turn_id |
  .execution.session_phase=$s.phase |
  .execution.turn_status=$s.turn_status | .checkout.after=$after |
  .result={exit_code:$rc,failure_class:$failure,verdict:$verdict,
    error:(if $rc == 0 then "" else ($s.error // "") end),session_error:($s.error // ""),observed_at:$s.updated_at,automatic_replay:false}
' <<< "$status")"
role="$(jq -r '.resolved_route.requested_role' <<< "$context")"
model="$(jq -r '.resolved_profile.profile.model' <<< "$context")"
profile="$(jq -r '.resolved_profile.profile_ref' <<< "$context")"
dispatch="$(jq -r '.dispatch_id' <<< "$context")"
existing="$(cd "$workdir" && ic --json route list "--dispatch=$dispatch" --limit=10000)"
prior="$(jq -c --arg turn "$turn" --argjson current "$context" '[(. // [])[] | .context_json | fromjson | select(.terminal == true and .attempt_id == $current.attempt_id and .execution.thread_id == $current.execution.thread_id and .execution.turn_id == $turn)] | first // empty' <<< "$existing")"
if [[ -n "$prior" ]]; then
  printf '%s\n' "$prior"
  exit "$(jq -r '.result.exit_code' <<< "$prior")"
fi
record=(ic route record "--agent=$role" "--model=$model" --rule=dispatch-profile
  "--role=$role" "--profile=$profile" "--dispatch=$dispatch" "--context=$context")
for key in parent_session_id run_id bead_id resolved_route.producer_identity resolved_route.validator_relationship; do
  value="$(jq -r ".$key // empty" <<< "$context")"
  [[ -n "$value" ]] || continue
  case "$key" in
    parent_session_id) record+=("--session=$value") ;;
    run_id) record+=("--run=$value") ;;
    bead_id) record+=("--bead=$value") ;;
    resolved_route.producer_identity) record+=("--producer-identity=$value") ;;
    resolved_route.validator_relationship) record+=("--validator-relationship=$value") ;;
  esac
done
reason="$(jq -r '.resolved_route.fallback_reason // empty' <<< "$context")"
[[ "$rc" == 0 ]] || reason="$failure"
[[ -z "$reason" ]] || record+=("--fallback-reason=$reason")
if ! (cd "$workdir" && "${record[@]}") >/dev/null; then
  echo 'Error: terminal result could not be persisted; do not accept this dispatch' >&2
  exit 1
fi
printf '%s\n' "$context"
exit "$rc"
