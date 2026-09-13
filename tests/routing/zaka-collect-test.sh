#!/usr/bin/env bash
# Real resolver and SQLite ledger; fixture is the documented Zaka status wire shape.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT
mkdir -p "$TEST_ROOT/bin" "$TEST_ROOT/work"
export FIXTURE="$TEST_ROOT/status.json"
printf '#!/usr/bin/env bash\ncat "$FIXTURE"\n' > "$TEST_ROOT/bin/zaka"
chmod +x "$TEST_ROOT/bin/zaka"
export PATH="$TEST_ROOT/bin:$PATH"
(cd "$TEST_ROOT/work" && ic init >/dev/null)
route="$(cd "$ROOT" && ic route dispatch --role=deep-execution --json)"
jq -n --argjson route "$route" --arg cwd "$TEST_ROOT/work" --arg events "$TEST_ROOT/events.jsonl" '
  {session:"as-123456789012345678901234",transport:"app-server",thread_id:"thread-1",turn_id:"turn-1",
   phase:"completed",turn_status:"completed",pending_requests:[],event_log:$events,updated_at:"2026-09-05T00:00:00Z",
   config:{workdir:$cwd,model:"gpt-6-astra",sandbox:"read-only",metadata:{schema_version:1,
     dispatch_id:"dispatch-1",attempt_id:"attempt-1",parent_session_id:"parent-1",run_id:"run-1",bead_id:"bead-1",
     resolved_route:$route,resolved_profile:{profile_ref:$route.profile_ref,profile:$route.profile},
     checkout:{before:"initial"},execution:{backend:"codex",model:"gpt-6-astra",codex_version:"0.153.3"}}}}
' > "$FIXTURE"
printf '%s\n' '{"direction":"receive","message":{"method":"item/completed","params":{"turnId":"turn-1","item":{"type":"agentMessage","text":"VERDICT: CLEAN"}}}}' > "$TEST_ROOT/events.jsonl"
printf '%s\n' '{"direction":"receive","message":{"method":"turn/completed","params":{"turn":{"id":"turn-1","status":"completed"}}}}' >> "$TEST_ROOT/events.jsonl"
bash "$ROOT/scripts/collect-zaka.sh" as-123456789012345678901234 > "$TEST_ROOT/result.json"
jq -e '.state == "completed" and .result.verdict == "VERDICT: CLEAN" and .execution.turn_id == "turn-1"' "$TEST_ROOT/result.json" >/dev/null
records="$(cd "$TEST_ROOT/work" && ic --json route list --limit=10)"
jq -e 'length == 1 and .[0].session_id == "parent-1" and .[0].run_id == "run-1" and .[0].bead_id == "bead-1" and (.[0].context_json | fromjson | .attempt_id == "attempt-1" and .execution.thread_id == "thread-1" and .execution.turn_id == "turn-1" and .state == "completed" and .resolved_profile.profile.model == "gpt-6-astra")' <<< "$records" >/dev/null
# Collecting the same finished turn must not inflate count-based gates.
bash "$ROOT/scripts/collect-zaka.sh" as-123456789012345678901234 >/dev/null
[[ "$(cd "$TEST_ROOT/work" && ic --json route list --limit=10 | jq length)" == 1 ]]
# An uncollected turn survived a worker exit: exact durable completion wins.
jq '.phase="stale" | .error="worker unavailable" | .turn_id="turn-late"' "$FIXTURE" > "$TEST_ROOT/next.json"
mv -f "$TEST_ROOT/next.json" "$FIXTURE"
printf '%s\n' '{"direction":"receive","message":{"method":"turn/completed","params":{"turn":{"id":"turn-late","status":"completed"}}}}' >> "$TEST_ROOT/events.jsonl"
bash "$ROOT/scripts/collect-zaka.sh" as-123456789012345678901234 > "$TEST_ROOT/result.json"
jq -e '.state == "completed" and .execution.session_phase == "stale"' "$TEST_ROOT/result.json" >/dev/null
jq '.phase="error" | .turn_id="turn-failed" | .error="429 then HTTP 403 policy denied" | .turn_status="failed"' "$FIXTURE" > "$TEST_ROOT/next.json"
mv -f "$TEST_ROOT/next.json" "$FIXTURE"
rc=0
bash "$ROOT/scripts/collect-zaka.sh" as-123456789012345678901234 > "$TEST_ROOT/result.json" || rc=$?
[[ "$rc" == 1 ]]
jq -e '.state == "failed" and .result.failure_class == "terminal_policy" and .result.automatic_replay == false' "$TEST_ROOT/result.json" >/dev/null
jq '.phase="running" | .error="" | .turn_status="inProgress"' "$FIXTURE" > "$TEST_ROOT/next.json"
mv -f "$TEST_ROOT/next.json" "$FIXTURE"
rc=0
bash "$ROOT/scripts/collect-zaka.sh" as-123456789012345678901234 > "$TEST_ROOT/result.json" || rc=$?
[[ "$rc" == 3 ]]
jq -e '.state == "pending" and .terminal == false' "$TEST_ROOT/result.json" >/dev/null
records="$(cd "$TEST_ROOT/work" && ic --json route list --limit=10)"
jq -e 'length == 3 and any(.[]; .context_json | fromjson | .result.failure_class == "terminal_policy" and .fallback_reason == "terminal_policy" and .dispatch_id == "dispatch-1")' <<< "$records" >/dev/null
# Nonblocking questions can survive a completed turn; those are not acceptance.
jq '.phase="completed" | .turn_status="completed" | .pending_requests=[{id:0,method:"item/tool/requestUserInput",params:{isBlocking:false}}]' "$FIXTURE" > "$TEST_ROOT/next.json"
mv -f "$TEST_ROOT/next.json" "$FIXTURE"
rc=0
bash "$ROOT/scripts/collect-zaka.sh" as-123456789012345678901234 >/dev/null || rc=$?
[[ "$rc" == 3 ]]
export REAL_IC="$(command -v ic)"
printf '#!/usr/bin/env bash\n[[ "$*" != *"route record"* ]] || exit 99\nexec "$REAL_IC" "$@"\n' > "$TEST_ROOT/bin/ic"
chmod +x "$TEST_ROOT/bin/ic"
jq '.phase="error" | .turn_id="turn-unrecordable" | .error="HTTP 400 configuration rejected" | .pending_requests=[]' "$FIXTURE" > "$TEST_ROOT/next.json"
mv -f "$TEST_ROOT/next.json" "$FIXTURE"
rc=0
bash "$ROOT/scripts/collect-zaka.sh" as-123456789012345678901234 > "$TEST_ROOT/unrecorded.json" 2> "$TEST_ROOT/record-error" || rc=$?
[[ "$rc" == 1 && ! -s "$TEST_ROOT/unrecorded.json" ]]
grep -q 'could not be persisted' "$TEST_ROOT/record-error"
echo 'PASS: async terminal collection preserves identity, verdict, policy precedence and pending state'
