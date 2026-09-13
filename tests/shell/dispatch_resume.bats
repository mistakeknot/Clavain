#!/usr/bin/env bats

setup() {
  load test_helper
  DISPATCH="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
  T="$(mktemp -d)"
  T="$(cd "$T" && pwd -P)"
  mkdir -p "$T/bin" "$T/repo" "$T/out"
  git -C "$T/repo" init -q
  printf 'fixture\n' > "$T/repo/input.txt"
  git -C "$T/repo" -c user.name=t -c user.email=t@t add input.txt
  git -C "$T/repo" -c user.name=t -c user.email=t@t commit -q -m base
  export PATH="$T/bin:$PATH"
  export CLAVAIN_CONTEXT_GATEWAY_MODE=off
  export CLAVAIN_CODEX_WRITABLE_ROOTS=""
}

teardown() {
  rm -rf "$T"
  if [[ -n "${FIXTURE_IN_CHECKOUT:-}" && "$FIXTURE_IN_CHECKOUT" == */.native-fixture.* ]]; then
    rm -rf "$FIXTURE_IN_CHECKOUT"
  fi
}

make_native_binding() {
  export REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd -P)"
  export TASK_ROOT="$(cd "$REPO_ROOT/.." && pwd -P)"
  export RECORDS="$T/records.json"
  export AUTH_DB="$T/intercore.db"
  : > "$AUTH_DB"
  python3 - "$T" "$REPO_ROOT" "$TASK_ROOT" <<'PY'
import hashlib,json,pathlib,sys
t,repo,task=map(pathlib.Path,sys.argv[1:])
def h(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def canon(v):return json.dumps(v,sort_keys=True,separators=(",",":"))
manifest=task/'native-schema-manifest.json'; meta=json.loads(manifest.read_text()); exe=pathlib.Path(meta['codex_executable'])
source=t/'source.json'; source.write_text('source-v1\n'); policy=repo/'config/routing.yaml'
events=t/'events.jsonl'; thread='018f47bb-4e58-7abc-8def-0123456789ab'; events.write_text(json.dumps({'type':'thread.started','thread_id':thread})+'\n')
request={'model':'gpt-fixture','modelProvider':'openai','cwd':str(t/'repo'),'runtimeWorkspaceRoots':[str(t/'repo')],
 'approvalPolicy':'never','approvalsReviewer':'user','sandbox':'workspace-write','serviceTier':'default',
 'baseInstructions':'governed base','developerInstructions':'scoped skill body','config':{'model_reasoning_effort':'high'},'excludeTurns':True}
effective={'model':'gpt-fixture','modelProvider':'openai','reasoningEffort':'high','serviceTier':'default','cwd':str(t/'repo'),
 'runtimeWorkspaceRoots':[str(t/'repo')],'approvalPolicy':'never','approvalsReviewer':'user','sandbox':{'type':'workspaceWrite','networkAccess':False},
 'activePermissionProfile':None,'instructionSources':[]}
config={'request':request,'effective':effective};config['sha256']=hashlib.sha256(canon(config).encode()).hexdigest()
cap={'schema_version':1,'status':'verified','native_thread_id':thread,'source_sha256':h(source),'policy_sha256':h(policy),
 'executable_sha256':h(exe),'configuration_sha256':config['sha256'],'native_schema_manifest_sha256':h(manifest),
 'verified':{'model_provider_effort_tier':True,'cwd_and_writable_roots':True,'approval_reviewer_sandbox_network':True,
 'instructions_config_and_skills':True,'exclude_turns_suppresses_history':True}}
capfile=t/'capability.json';capfile.write_text(json.dumps(cap)+'\n')
enrollment={'enrollment_id':'enroll-a','cohort_id':'cohort-a','manifest_sha256':'a'*64}
route={'policy_source':str(policy),'policy_hash':h(policy)}
execution={'schema_version':1,'dispatch_id':'dispatch-seed','attempt_id':'attempt-seed','state':'completed','resolved_route':route,
 'resolved_profile':{'profile':{'role':'routine-execution'}},'execution':{'backend':'codex','model':'gpt-fixture','reasoning_effort':'high',
 'service_tier':'standard','event_log':str(events),'arm_id':'arm-a'},'task_envelope':enrollment,'result':{'exit_code':0}}
receipt=t/'receipt.json';receipt.write_text(json.dumps(execution)+'\n')
native={**enrollment,'arm_id':'arm-a','dispatch_id':'dispatch-seed','attempt_id':'attempt-seed','role':'routine-execution','provider':'codex',
 'model':'gpt-fixture','session_id':thread,'thread_id':thread,'native_thread_id':thread,'source_path':str(source),'source_sha256':h(source),
 'policy_path':str(policy),'policy_sha256':h(policy),'executable':str(exe),'executable_sha256':h(exe),'configuration_sha256':config['sha256'],
 'evidence_path':str(events),'native_schema_manifest':{'path':str(manifest),'sha256':h(manifest)},
 'native_capability_evidence':{'path':str(capfile),'sha256':h(capfile),'status':'verified'}}
compact_native={'operation':'compact','seed_thread_id':thread,'status':'completed','configuration_status':'verified','accounting_status':'complete',
 'native_usage':{'last':{'inputTokens':1},'total':{'inputTokens':2}}}
compact_execution=json.loads(json.dumps(execution));compact_execution.update(dispatch_id='dispatch-compact',attempt_id='attempt-compact')
compact_execution['execution']['native_operation']=compact_native
compact_receipt=t/'compact.receipt.json';compact_receipt.write_text(json.dumps(compact_execution)+'\n')
compact_result=t/'compact.result.json';compact_result.write_text(json.dumps(compact_native)+'\n')
records=[{'id':1,'rule_matched':'measured-delivery-enrollment','context_json':{**enrollment,'arm_id':'arm-a','implementation_dispatched':False,'enrolled_at':'2026-09-12T00:00:00Z'}},
 {'id':2,'rule_matched':'measured-delivery-dispatch-request','context_json':{**enrollment,'dispatch_id':'dispatch-seed','role':'routine-execution'}},
 {'id':3,'rule_matched':'dispatch-profile','context_json':execution},{'id':4,'rule_matched':'measured-delivery-binding','context_json':native},
 {'id':5,'rule_matched':'measured-delivery-dispatch-request','context_json':{**enrollment,'dispatch_id':'dispatch-compact','role':'routine-execution'}},
 {'id':6,'rule_matched':'dispatch-profile','context_json':compact_execution}]
(t/'records.json').write_text(json.dumps(records))
binding={'schema_version':1,'arm_id':'arm-a','authority':{'database':str(t/'intercore.db'),'enrollment_decision_id':1,
 'dispatch_request_decision_id':2,'seed_execution_decision_id':3,'seed_native_binding_decision_id':4,
 'compaction_dispatch_request_decision_id':5,'compaction_execution_decision_id':6},'enrollment':enrollment,
 'seed':{'dispatch_id':'dispatch-seed','attempt_id':'attempt-seed','role':'routine-execution','native_thread_id':thread,
 'receipt':{'path':str(receipt),'sha256':h(receipt)},'events':{'path':str(events),'sha256':h(events)}},
 'source':{'path':str(source),'sha256':h(source)},'policy':{'path':str(policy),'sha256':h(policy)},
 'executable':{'path':str(exe),'sha256':h(exe)},'native_schema':{'manifest_path':str(manifest),'manifest_sha256':h(manifest)},
 'configuration':config,'capability_evidence':{'path':str(capfile),'sha256':h(capfile)},
 'compaction':{'dispatch_id':'dispatch-compact','attempt_id':'attempt-compact','status':'completed','accounting_status':'complete',
 'configuration_status':'verified','receipt':{'path':str(compact_receipt),'sha256':h(compact_receipt)},
 'operation_result':{'path':str(compact_result),'sha256':h(compact_result)}}}
(t/'binding.json').write_text(json.dumps(binding)+'\n')
(t/'route.json').write_text(json.dumps({'policy_source':str(policy),'policy_hash':h(policy)}))
PY
  cat > "$T/bin/ic" <<'SH'
#!/usr/bin/env bash
if [[ " $* " == *" route list "* ]]; then cat "$RECORDS"; else printf '{}\n'; fi
SH
  chmod +x "$T/bin/ic"
}

@test "native operations require an authoritative binding before inference" {
  run bash "$DISPATCH" --operation resume -C "$T/repo" -o "$T/out/x" "prompt"
  [ "$status" -ne 0 ]
  [[ "$output" == *"native-trusted-launcher-unavailable"* ]]
  run bash "$DISPATCH" --operation compact -C "$T/repo" -o "$T/out/x"
  [ "$status" -ne 0 ]
  [[ "$output" == *"native-trusted-launcher-unavailable"* ]]
}

@test "production gate precedes binding adapters role resolution and database effects" {
  cat > "$T/bin/python3" <<'SH'
#!/usr/bin/env bash
touch "$T/out/python-called"
exit 99
SH
  chmod +x "$T/bin/python3"
  run bash "$DISPATCH" --operation resume --resume-from "$T/does-not-exist.json" \
    --role routine-execution -C "$T/repo" -o "$T/out/x" "prompt"
  [ "$status" -ne 0 ]
  [[ "$output" == *"native-trusted-launcher-unavailable"* ]]
  [ ! -e "$T/out/python-called" ]
  [ ! -e "$T/repo/.clavain/intercore.db" ]
}

@test "direct native control transport is unavailable" {
  control="$BATS_TEST_DIRNAME/../../scripts/dispatch_control.py"
  run python3 "$control" compact --binding "$T/missing.json" --output "$T/out/result.json"
  [ "$status" -ne 0 ]
  [[ "$output" == *"native-trusted-launcher-unavailable"* ]]
  [ ! -e "$T/out/result.json" ]
}

@test "native operations reject arbitrary selectors flags transports and backends before inference" {
  printf '{}\n' > "$T/binding.json"
  for args in \
    "--operation resume --resume-from $T/binding.json --last prompt" \
    "--operation resume --resume-from $T/binding.json --name arbitrary prompt" \
    "--operation resume --resume-from $T/binding.json -i image prompt" \
    "--operation resume --resume-from $T/binding.json --dangerously-bypass-approvals-and-sandbox prompt" \
    "--operation resume --resume-from $T/binding.json --via zaka prompt" \
    "--operation compact --resume-from $T/binding.json --to kimi" \
    "--operation compact --resume-from $T/binding.json --report compact"; do
    run bash -c "bash '$DISPATCH' $args"
    [ "$status" -ne 0 ]
    [[ "$output" == *"native-trusted-launcher-unavailable"* || "$output" == *"blocked by dispatch.sh safety policy"* ]]
  done
  [ ! -e "$T/out/launched" ]
}

@test "exec remains the default operation" {
  cat > "$T/bin/codex" <<'SH'
#!/usr/bin/env bash
if [[ "$1" == --version ]]; then echo 'codex-cli 9.9.9'; exit; fi
printf '%s\n' "$@" > "$ARGV_LOG"
while [[ $# -gt 0 ]]; do
  if [[ "$1" == -o ]]; then printf 'fixture\nVERDICT: CLEAN\n' > "$2"; shift 2; else shift; fi
done
SH
  chmod +x "$T/bin/codex"
  export ARGV_LOG="$T/argv"
  bash "$DISPATCH" -C "$T/repo" -o "$T/out/last" "prompt"
  [ "$(sed -n '1p' "$T/argv")" = exec ]
  ! grep -q '^resume$' "$T/argv"
}

@test "resume dry-run is also closed by the production native gate" {
  make_native_binding
  route="$(cat "$T/route.json")"
  profile='{"profile":{"role":"routine-execution"}}'
  run env CLAVAIN_TASK_INTERCORE_DB="$AUTH_DB" CLAVAIN_TASK_ENROLLMENT_ID=enroll-a \
    CLAVAIN_TASK_COHORT_ID=cohort-a CLAVAIN_TASK_MANIFEST_SHA256="$(printf 'a%.0s' {1..64})" \
    bash "$DISPATCH" --dry-run --operation resume --resume-from "$T/binding.json" \
    --role-resolved --role routine-execution --resolved-profile-ref fixture \
    --resolved-route-json "$route" --resolved-profile-json "$profile" \
    --to codex --model gpt-fixture --reasoning-effort high --service-tier standard \
    -C "$T/repo" -o "$T/out/resume.md" "resume prompt"
  [ "$status" -ne 0 ]
  [[ "$output" == *"native-trusted-launcher-unavailable"* ]]
}

@test "native admission records a request without claiming a replayed operation" {
  audit="$BATS_TEST_DIRNAME/../../scripts/lib-dispatch-audit.sh"
  run env OPERATION=compact ENGINE=flere VIA=exec RESUME_FROM="$T/binding.json" \
    DISPATCH_BINDING_SHA256="$(printf 'a%.0s' {1..64})" \
    BOUND_NATIVE_THREAD_ID=018f47bb-4e58-7abc-8def-0123456789ab \
    WORKDIR="$T/repo" OUTPUT="$T/out/result" bash -c \
    'source "$1"; _role_audit_context started 0 ""' bash "$audit"
  [ "$status" -eq 0 ]
  jq -e '.execution.operation_request.operation == "compact"' <<< "$output"
  jq -e '.execution | has("native_operation") | not' <<< "$output"
}

@test "fixture library uses real audit rows and durable election after stale lock recovery" {
  repo="$(cd "$BATS_TEST_DIRNAME/../.." && pwd -P)"
  FIXTURE_IN_CHECKOUT="$(mktemp -d "$repo/.native-fixture.XXXXXX")"
  db="$FIXTURE_IN_CHECKOUT/intercore.db"
  ic init --db="$db"
  lib="$repo/scripts/lib-dispatch-native.sh"
  key="$(python3 - "$repo/scripts/dispatch_control.py" <<'PY'
import importlib.util,sys
s=importlib.util.spec_from_file_location('c',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
print(m.native_operation_key('018f47bb-4e58-7abc-8def-0123456789ab','compact'))
PY
)"
  run env NATIVE_FIXTURE_ROOT="$repo" bash -c '
    source "$1"
    OPERATION=compact ENGINE=codex VIA=exec WORKDIR="$2" OUTPUT="" MODEL=fixture SANDBOX=workspace-write
    DISPATCH_ID=fixture-dispatch ATTEMPT_ID=fixture-attempt ROLE="" ROLE_RESOLVED=false
    RESUME_FROM="" DISPATCH_BINDING_SHA256="" BOUND_NATIVE_THREAD_ID=018f47bb-4e58-7abc-8def-0123456789ab
    phase="$(jq -cn --arg key "$4" --arg thread "$BOUND_NATIVE_THREAD_ID" \
      "{schema_version:2,operation:\"compact\",operation_key:\$key,seed_thread_id:\$thread}")"
    first="$(native_fixture_append_audit "$3" started "$phase" ic)"
    native_fixture_elect "$3" "$4" "$first" ic >/dev/null
    ATTEMPT_ID=fixture-contender
    second="$(native_fixture_append_audit "$3" started "$phase" ic)"
    ! native_fixture_elect "$3" "$4" "$second" ic >/dev/null 2>&1
    printf "%s %s\n" "$first" "$second"
  ' bash "$lib" "$repo" "$db" "$key"
  [ "$status" -eq 0 ]
  [ "$(wc -w <<< "$output")" -eq 2 ]

  run ic --db="$db" lock acquire native-resource "$key" --timeout=1s --owner=999999:fixture-host
  [ "$status" -eq 0 ]
  python3 - "$key" <<'PY'
import json,pathlib,sys
p=pathlib.Path('/tmp/intercore/locks/native-resource')/sys.argv[1]/'owner.json'
v=json.loads(p.read_text());v['created']=0;p.write_text(json.dumps(v))
PY
  run env NATIVE_FIXTURE_ROOT="$repo" bash -c 'source "$1"; native_fixture_lock_acquire "$2" native-resource "$3" ic && native_fixture_lock_release "$2" native-resource "$3" ic' bash "$lib" "$db" "$key"
  [ "$status" -eq 0 ]
}
