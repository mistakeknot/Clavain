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
  # The production gate must reject without reading these deliberately invalid
  # inputs. Full schema and executed argv coverage lives in the composed fixture.
  export AUTH_DB="$T/intercore.db"
  printf '{}\n' > "$T/binding.json"
  printf '{}\n' > "$T/route.json"
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
  (cd "$FIXTURE_IN_CHECKOUT" && ic init --db="$db")
  thread="$(python3 -c 'import uuid; print(uuid.uuid4())')"
  lib="$repo/scripts/lib-dispatch-native.sh"
  key="$(python3 - "$repo/scripts/dispatch_control.py" "$thread" <<'PY'
import importlib.util,sys
s=importlib.util.spec_from_file_location('c',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
print(m.native_operation_key(sys.argv[2],'compact'))
PY
)"
  run env NATIVE_FIXTURE_ROOT="$repo" bash -c '
    source "$1"
    OPERATION=compact ENGINE=flere VIA=exec WORKDIR="$2" OUTPUT="" MODEL=fixture SANDBOX=workspace-write
    DISPATCH_ID=fixture-dispatch ATTEMPT_ID=fixture-attempt ROLE="" ROLE_RESOLVED=false
    RESUME_FROM="" DISPATCH_BINDING_SHA256="" BOUND_NATIVE_THREAD_ID="$5"
    phase="$(jq -cn --arg key "$4" --arg thread "$BOUND_NATIVE_THREAD_ID" \
      "{schema_version:2,operation:\"compact\",operation_key:\$key,seed_thread_id:\$thread}")"
    first="$(native_fixture_append_audit "$3" started "$phase" ic)"
    native_fixture_elect "$3" "$4" "$first" ic >/dev/null
    ATTEMPT_ID=fixture-contender
    second="$(native_fixture_append_audit "$3" started "$phase" ic)"
    ! native_fixture_elect "$3" "$4" "$second" ic >/dev/null 2>&1
    printf "%s %s\n" "$first" "$second"
  ' bash "$lib" "$repo" "$db" "$key" "$thread"
  [ "$status" -eq 0 ]
  [ "$(wc -w <<< "$output")" -eq 2 ]
  second="$(awk '{print $2}' <<< "$output")"

  run bash -c 'cd "$1"; ic --db="$2" lock acquire native-resource "$3" --timeout=1s --owner=999999:fixture-host' bash "$FIXTURE_IN_CHECKOUT" "$db" "$key"
  [ "$status" -eq 0 ]
  python3 - "$key" <<'PY'
import json,pathlib,sys
p=pathlib.Path('/tmp/intercore/locks/native-resource')/sys.argv[1]/'owner.json'
v=json.loads(p.read_text());v['created']=0;p.write_text(json.dumps(v))
PY
  run env NATIVE_FIXTURE_ROOT="$repo" bash -c 'source "$1"; native_fixture_lock_acquire "$2" native-resource "$3" ic && native_fixture_lock_release "$2" native-resource "$3" ic' bash "$lib" "$db" "$key"
  [ "$status" -eq 0 ]
  run env NATIVE_FIXTURE_ROOT="$repo" bash -c 'source "$1"; native_fixture_elect "$2" "$3" "$4" ic' bash "$lib" "$db" "$key" "$second"
  [ "$status" -ne 0 ]
}
