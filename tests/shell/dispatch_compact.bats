#!/usr/bin/env bats

setup() {
    load test_helper
    DISPATCH="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    T="$(mktemp -d)"
    mkdir -p "$T/bin" "$T/repo" "$T/out"
    git -C "$T/repo" init -q
    printf 'fixture\n' > "$T/repo/input.txt"
    git -C "$T/repo" -c user.name=t -c user.email=t@t add input.txt
    git -C "$T/repo" -c user.name=t -c user.email=t@t commit -q -m base
    export CLAVAIN_CONTEXT_GATEWAY_MODE=off
    export CLAVAIN_CODEX_WRITABLE_ROOTS=""
    export FIXTURE_MODE=success
    export FIXTURE_PID_FILE="$T/fixture.pid"
    export PATH="$T/bin:$PATH"
    cat > "$T/bin/codex" <<'SH'
#!/usr/bin/env bash
if [[ "${1:-}" == "--version" ]]; then
  echo 'codex-cli 9.9.9'
  exit 0
fi
output=""
json=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o) output="$2"; shift 2 ;;
    --json) json=true; shift ;;
    -s|-C|-m|-c|-i|--add-dir|--output-schema|-p|--profile|--config|--color|-a|--ask-for-approval|--enable|--disable|--local-provider) shift 2 ;;
    exec|--full-auto|--skip-git-repo-check|--oss|--search|--no-alt-screen) shift ;;
    *) shift ;;
  esac
done
printf '%s\n' "$$" > "$FIXTURE_PID_FILE"
case "${FIXTURE_MODE:-success}" in
  plain)
    printf 'legacy stdout bytes\n'
    printf 'legacy last message\nVERDICT: CLEAN\n' > "$output"
    ;;
  nonzero)
    printf '{"type":"thread.started","thread_id":"thread-fail"}\n'
    printf 'partial last message\n' > "$output"
    printf 'fixture backend failure\n' >&2
    exit 7
    ;;
  malformed)
    printf '{"type":"thread.started","thread_id":"thread-a"}\n'
    printf 'broken-json\n'
    printf '{"type":"thread.started","thread_id":"thread-b"}\n'
    printf 'malformed fixture\n' > "$output"
    ;;
  oversized)
    printf '{"type":"thread.started","thread_id":"thread-big","detail":"'
    i=0; while [[ $i -lt 6000 ]]; do printf '雪'; i=$((i + 1)); done
    printf '"}\n'
    printf 'large fixture ☃\nVERDICT: CLEAN\n' > "$output"
    ;;
  no_artifacts)
    printf '{"type":"thread.started","thread_id":"thread-missing"}\n'
    ;;
  nonregular)
    printf '{"type":"thread.started","thread_id":"thread-link"}\n'
    printf 'elsewhere\n' > "${output}.target"
    ln -s "${output}.target" "$output"
    ;;
  cancel)
    trap 'exit 143' TERM INT
    printf '{"type":"thread.started","thread_id":"thread-cancel"}\n'
    printf '{"type":"turn.started"}\n'
    while :; do :; done
    ;;
  ignore_then_zero)
    trap '' TERM INT
    printf '{"type":"thread.started","thread_id":"thread-ignore-zero"}\n'
    sleep 0.4
    printf 'completed after cancellation\nVERDICT: CLEAN\n' > "$output"
    ;;
  ignore_forever)
    trap '' TERM INT
    printf '{"type":"thread.started","thread_id":"thread-ignore-forever"}\n'
    sh -c 'trap "" TERM INT; printf "%s\n" "$$" > "$FIXTURE_DESCENDANT_PID_FILE"; while :; do sleep 1; done' &
    while :; do sleep 1; done
    ;;
  stdin_echo)
    IFS= read -r input
    printf '{"type":"thread.started","thread_id":"thread-stdin"}\n'
    printf 'stdin:%s\nVERDICT: CLEAN\n' "$input" > "$output"
    ;;
  inherited_stdout)
    printf '{"type":"thread.started","thread_id":"thread-held-pipe"}\n'
    sleep 20 &
    printf 'backend complete\nVERDICT: CLEAN\n' > "$output"
    ;;
  delayed_descendant)
    printf '{"type":"thread.started","thread_id":"thread-delayed"}\n'
    printf 'backend complete\nVERDICT: CLEAN\n' > "$output"
    exec python3 -c 'import os,time; pid=os.fork(); pid and os._exit(0); time.sleep(2.3); print("{\"type\":\"turn.started\"}", flush=True)'
    ;;
  *)
    printf '{"type":"thread.started","thread_id":"thread-123"}\n'
    printf '{"type":"turn.started"}\n'
    printf '{"type":"item.completed","item":{"type":"agent_message"}}\n'
    printf '{"type":"turn.completed","usage":{"input_tokens":12,"cached_input_tokens":3,"output_tokens":5}}\n'
    printf 'fixture stderr\n' >&2
    printf 'full last message ☃\nVERDICT: CLEAN\n' > "$output"
    ;;
esac
SH
    chmod +x "$T/bin/codex"
}

teardown() {
    if [[ -f "$T/fixture.pid" ]]; then
        kill "$(cat "$T/fixture.pid")" 2>/dev/null || true
    fi
    rm -rf "$T"
}

run_dispatch() {
    local report="$T/report.json" stderr="$T/dispatch.stderr"
    DISPATCH_STATUS=0
    bash "$DISPATCH" --report compact -C "$T/repo" -o "$T/out/last.md" "fixture prompt" >"$report" 2>"$stderr" || DISPATCH_STATUS=$?
}

artifact_dir() {
    find "$T/out" -maxdepth 1 -type d -name '.clavain-dispatch-compact.*' | head -1
}

@test "compact wrapper preserves full evidence and emits a bounded report" {
    run_dispatch
    [ "$DISPATCH_STATUS" -eq 0 ]
    python3 - "$T/report.json" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
raw = p.read_bytes()
assert len(raw) <= 4096 and raw.endswith(b"\n")
r = json.loads(raw)
assert r["backend_process_code"] == 0
assert r["dispatcher_code"] == 0
assert r["native"]["thread_id"] == "thread-123"
assert r["native_coverage"]["status"] == "complete"
PY
    grep -q 'full last message ☃' "$T/out/last.md"
    grep -q '^STATUS: pass$' "$T/out/last.md.verdict"
    dir="$(artifact_dir)"
    [ -n "$dir" ]
    [ "$(stat -f '%Lp' "$dir" 2>/dev/null || stat -c '%a' "$dir")" = 700 ]
    cmp "$T/out/last.md" "$dir/last-message.txt"
    grep -q 'fixture stderr' "$dir/stderr.log"
    grep -q 'thread.started' "$dir/stdout.events.jsonl"
    python3 "$BATS_TEST_DIRNAME/../../scripts/dispatch_report.py" replay --artifacts-dir "$dir" > "$T/replayed.json"
    cmp "$T/report.json" "$T/replayed.json"
}

@test "report defaults to full and explicit full is byte-compatible" {
    export FIXTURE_MODE=plain
    bash "$DISPATCH" -C "$T/repo" -o "$T/out/default.md" "fixture" >"$T/default.stdout" 2>"$T/default.stderr"
    bash "$DISPATCH" --report full -C "$T/repo" -o "$T/out/full.md" "fixture" >"$T/full.stdout" 2>"$T/full.stderr"
    cmp "$T/default.stdout" "$T/full.stdout"
    sed -E 's#/tmp/clavain-dispatch-[0-9]+\.json#STATE_FILE#g' "$T/default.stderr" > "$T/default.stderr.normalized"
    sed -E 's#/tmp/clavain-dispatch-[0-9]+\.json#STATE_FILE#g' "$T/full.stderr" > "$T/full.stderr.normalized"
    cmp "$T/default.stderr.normalized" "$T/full.stderr.normalized"
    cmp "$T/out/default.md" "$T/out/full.md"
    [ -z "$(find "$T/out" -maxdepth 1 -type d -name '.clavain-dispatch-compact.*' -print -quit)" ]
}

@test "compact rejects unsupported backend via and missing output before launch" {
    run bash "$DISPATCH" --report compact --to kimi -o "$T/out/x" "fixture"
    [ "$status" -ne 0 ]
    [[ "$output" == *"compact reporting supports only Codex exec"* ]]
    [ ! -f "$FIXTURE_PID_FILE" ]

    run bash "$DISPATCH" --report compact --via zaka --to codex -o "$T/out/x" "fixture"
    [ "$status" -ne 0 ]
    [[ "$output" == *"compact reporting supports only Codex exec"* ]]
    [ ! -f "$FIXTURE_PID_FILE" ]

    run bash "$DISPATCH" --report compact --to codex "fixture"
    [ "$status" -ne 0 ]
    [[ "$output" == *"requires -o/--output-last-message"* ]]
    [ ! -f "$FIXTURE_PID_FILE" ]

    printf 'target\n' > "$T/out/target"
    ln -s "$T/out/target" "$T/out/link"
    run bash "$DISPATCH" --report compact --to codex -o "$T/out/link" "fixture"
    [ "$status" -ne 0 ]
    [[ "$output" == *"regular non-symlink"* ]]
    [ ! -f "$FIXTURE_PID_FILE" ]

    rm -f "$T/out/link"
    ln -s "$T/out/target" "$T/out/clean.summary"
    run bash "$DISPATCH" --report compact --to codex -o "$T/out/clean" "fixture"
    [ "$status" -ne 0 ]
    [[ "$output" == *"regular non-symlink"* ]]
    [ ! -f "$FIXTURE_PID_FILE" ]
}

@test "compact attempts never overwrite an earlier artifact directory" {
    run_dispatch
    [ "$DISPATCH_STATUS" -eq 0 ]
    first="$(artifact_dir)"
    first_manifest="$(shasum -a 256 "$first/manifest.json" | awk '{print $1}')"
    run_dispatch
    [ "$DISPATCH_STATUS" -eq 0 ]
    [ "$(find "$T/out" -maxdepth 1 -type d -name '.clavain-dispatch-compact.*' | wc -l | tr -d ' ')" -eq 2 ]
    [ "$(shasum -a 256 "$first/manifest.json" | awk '{print $1}')" = "$first_manifest" ]
}

@test "CLAVAIN_REVIEW_EVENTS remains an independent full event consumer" {
    printf 'existing-event\n' > "$T/review.events"
    export CLAVAIN_REVIEW_EVENTS="$T/review.events"
    run_dispatch
    [ "$DISPATCH_STATUS" -eq 0 ]
    dir="$(artifact_dir)"
    python3 - "$T/review.events" "$dir/stdout.events.jsonl" <<'PY'
from pathlib import Path
import sys
assert Path(sys.argv[1]).read_bytes() == b"existing-event\n" + Path(sys.argv[2]).read_bytes()
PY
}

@test "event consumer failure preserves backend status and fails presentation" {
    export CLAVAIN_REVIEW_EVENTS="$T/missing/events.jsonl"
    run_dispatch
    [ "$DISPATCH_STATUS" -eq 1 ]
    python3 - "$T/report.json" <<'PY'
import json, sys
r=json.load(open(sys.argv[1]))
assert r["backend_process_code"] == 0
assert r["dispatcher_code"] == 1
assert r["classification"] == "presentation_failure"
assert r["unusable"] is True
assert "event_capture_failed" in r.get("diagnostics", [])
PY
    dir="$(artifact_dir)"
    grep -q 'thread.started' "$dir/stdout.events.jsonl"
}

@test "compact gawk path runs when GNU awk is installed" {
    command -v gawk >/dev/null 2>&1 || skip "gawk unavailable"
    cat > "$T/bin/awk" <<'SH'
#!/usr/bin/env bash
exec gawk "$@"
SH
    chmod +x "$T/bin/awk"
    run_dispatch
    [ "$DISPATCH_STATUS" -eq 0 ]
    python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["native_coverage"]["status"] == "complete"' "$T/report.json"
    grep -q '^Turns: 1 | Commands: 0 | Messages: 1$' "$T/out/last.md.summary"
}

@test "nonzero backend is retained separately from the compact presentation" {
    export FIXTURE_MODE=nonzero
    run_dispatch
    [ "$DISPATCH_STATUS" -eq 7 ]
    python3 - "$T/report.json" <<'PY'
import json, sys
r=json.load(open(sys.argv[1]))
assert r["backend_process_code"] == 7
assert r["dispatcher_code"] == 7
assert r["classification"] == "terminal_error"
assert r["unusable"] is False
PY
    dir="$(artifact_dir)"
    grep -q 'fixture backend failure' "$dir/stderr.log"
    grep -q 'partial last message' "$dir/last-message.txt"
}

@test "malformed contradictory events preserve unknown counters" {
    export FIXTURE_MODE=malformed
    run_dispatch
    [ "$DISPATCH_STATUS" -eq 0 ]
    python3 - "$T/report.json" <<'PY'
import json, sys
r=json.load(open(sys.argv[1]))
assert r["native_coverage"]["status"] == "incomplete"
assert "native" not in r
assert all(c["value"] is None and c["status"] == "unknown" for c in r["counters"])
PY
}

@test "unicode oversized event input is retained without oversized report" {
    export FIXTURE_MODE=oversized
    run_dispatch
    [ "$DISPATCH_STATUS" -eq 0 ]
    [ "$(wc -c < "$T/report.json" | tr -d ' ')" -le 4096 ]
    dir="$(artifact_dir)"
    [ "$(wc -c < "$dir/stdout.events.jsonl" | tr -d ' ')" -gt 12000 ]
    python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$T/report.json"
}

@test "missing or nonregular output yields unusable recovery evidence" {
    export FIXTURE_MODE=no_artifacts
    run_dispatch
    [ "$DISPATCH_STATUS" -eq 1 ]
    python3 - "$T/report.json" <<'PY'
import json, sys
r=json.load(open(sys.argv[1]))
assert r["unusable"] is True
assert r["dispatcher_code"] == 1
assert r["recovery"] == "full artifacts in output parent"
assert r["digests"]["last_message"]["status"] == "missing"
PY

    rm -f "$T/out/last.md" "$T/report.json" "$T/dispatch.stderr"
    export FIXTURE_MODE=nonregular
    run_dispatch
    [ "$DISPATCH_STATUS" -eq 1 ]
    python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["unusable"] and r["digests"]["last_message"]["status"] == "nonregular"' "$T/report.json"
}

@test "renderer failure keeps artifacts and becomes an unusable diagnostic" {
    export CLAVAIN_DISPATCH_REPORT_BIN=/bin/false
    run_dispatch
    [ "$DISPATCH_STATUS" -eq 1 ]
    python3 - "$T/report.json" <<'PY'
import json, sys
r=json.load(open(sys.argv[1]))
assert r["unusable"] is True
assert r["classification"] == "presentation_failure"
assert "renderer_failed" in r.get("diagnostics", [])
PY
    dir="$(artifact_dir)"
    grep -q 'thread.started' "$dir/stdout.events.jsonl"
    grep -q 'fixture stderr' "$dir/stderr.log"
    grep -q 'full last message' "$T/out/last.md"
}

@test "renderer failure cannot mask an existing backend failure" {
    export FIXTURE_MODE=nonzero
    export CLAVAIN_DISPATCH_REPORT_BIN=/bin/false
    run_dispatch
    [ "$DISPATCH_STATUS" -eq 7 ]
    python3 - "$T/report.json" <<'PY'
import json, sys
r=json.load(open(sys.argv[1]))
assert r["backend_process_code"] == 7
assert r["dispatcher_code"] == 7
assert r["classification"] == "terminal_error"
assert r["unusable"] is True
assert "renderer_failed" in r.get("diagnostics", [])
PY
}

@test "compact cancellation forwards TERM, reaps backend, and keeps partial logs" {
    export FIXTURE_MODE=cancel
    bash "$DISPATCH" --report compact -C "$T/repo" -o "$T/out/last.md" "fixture" >"$T/report.json" 2>"$T/dispatch.stderr" &
    wrapper_pid=$!
    i=0
    while [[ ! -s "$FIXTURE_PID_FILE" && $i -lt 200 ]]; do
        sleep 0.01
        i=$((i + 1))
    done
    [ -s "$FIXTURE_PID_FILE" ]
    backend_pid="$(cat "$FIXTURE_PID_FILE")"
    kill -TERM "$wrapper_pid"
    rc=0
    wait "$wrapper_pid" || rc=$?
    [ "$rc" -eq 143 ]
    ! kill -0 "$backend_pid" 2>/dev/null
    dir="$(artifact_dir)"
    grep -q 'thread-cancel' "$dir/stdout.events.jsonl"
    python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["backend_process_code"] == 143 and r["dispatcher_code"] == 143' "$T/report.json"
}

@test "compact cancellation retains backend zero after ignored TERM completion" {
    export FIXTURE_MODE=ignore_then_zero
    bash "$DISPATCH" --report compact -C "$T/repo" -o "$T/out/last.md" "fixture" >"$T/report.json" 2>"$T/dispatch.stderr" &
    wrapper_pid=$!
    while [[ ! -s "$FIXTURE_PID_FILE" ]]; do sleep 0.01; done
    kill -TERM "$wrapper_pid"
    set +e
    wait "$wrapper_pid"
    rc=$?
    set -e
    [ "$rc" -eq 143 ]
    python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["backend_process_code"] == 0 and r["dispatcher_code"] == 143' "$T/report.json"
    grep -q 'completed after cancellation' "$T/out/last.md"
}

@test "compact cancellation kills an unresponsive process group within a bound" {
    export FIXTURE_MODE=ignore_forever
    export FIXTURE_DESCENDANT_PID_FILE="$T/fixture.descendant.pid"
    started="$(date +%s)"
    bash "$DISPATCH" --report compact -C "$T/repo" -o "$T/out/last.md" "fixture" >"$T/report.json" 2>"$T/dispatch.stderr" &
    wrapper_pid=$!
    while [[ ! -s "$FIXTURE_DESCENDANT_PID_FILE" ]]; do sleep 0.01; done
    backend_pid="$(cat "$FIXTURE_PID_FILE")"
    descendant_pid="$(cat "$FIXTURE_DESCENDANT_PID_FILE")"
    kill -TERM "$wrapper_pid"
    kill -TERM "$wrapper_pid" 2>/dev/null || true
    rc=0
    wait "$wrapper_pid" || rc=$?
    [ "$rc" -eq 143 ]
    [ $(( $(date +%s) - started )) -lt 8 ]
    ! kill -0 "$backend_pid" 2>/dev/null
    i=0
    while kill -0 "$descendant_pid" 2>/dev/null && [[ $i -lt 100 ]]; do sleep 0.01; i=$((i + 1)); done
    ! kill -0 "$descendant_pid" 2>/dev/null
    python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["backend_process_code"] == 137 and r["dispatcher_code"] == 143' "$T/report.json"
    dir="$(artifact_dir)"
    python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); assert p["termination_escalated"] is True' "$dir/process.json"
    replay_rc=0
    python3 "$BATS_TEST_DIRNAME/../../scripts/dispatch_report.py" replay --artifacts-dir "$dir" > "$T/replayed.json" || replay_rc=$?
    [ "$replay_rc" -eq 2 ]
    cmp "$T/report.json" "$T/replayed.json"
}

@test "no-gawk usage observation captures native JSON events" {
    cat > "$T/bin/awk" <<'SH'
#!/usr/bin/env bash
if [[ "${1:-}" == "--version" ]]; then
  echo 'awk version 20200816'
  exit 0
fi
exec /usr/bin/awk "$@"
SH
    chmod +x "$T/bin/awk"
    export CLAVAIN_USAGE_OUTPUT_DIR="$T/usage"
    export CLAVAIN_REVIEW_EVENTS="$T/observed.events.jsonl"
    bash "$DISPATCH" -C "$T/repo" -o "$T/out/full.md" "fixture" >"$T/full.stdout" 2>"$T/full.stderr"
    grep -q 'thread-123' "$T/observed.events.jsonl"
    grep -q 'thread-123' "$T/full.stdout"
}

@test "compact preserves backend stdin bytes like full mode" {
    export FIXTURE_MODE=stdin_echo
    printf 'input from caller\n' | bash "$DISPATCH" -C "$T/repo" -o "$T/out/full.md" "fixture" >"$T/full.stdout" 2>"$T/full.stderr"
    printf 'input from caller\n' | bash "$DISPATCH" --report compact -C "$T/repo" -o "$T/out/compact.md" "fixture" >"$T/report.json" 2>"$T/compact.stderr"
    cmp "$T/out/full.md" "$T/out/compact.md"
    grep -q '^stdin:input from caller$' "$T/out/compact.md"
}

@test "nonregular review event FIFO cannot block backend launch" {
    mkfifo "$T/review.events.fifo"
    export CLAVAIN_REVIEW_EVENTS="$T/review.events.fifo"
    bash "$DISPATCH" --report compact -C "$T/repo" -o "$T/out/last.md" "fixture" >"$T/report.json" 2>"$T/dispatch.stderr" &
    wrapper_pid=$!
    i=0
    while kill -0 "$wrapper_pid" 2>/dev/null && [[ $i -lt 500 ]]; do sleep 0.01; i=$((i + 1)); done
    ! kill -0 "$wrapper_pid" 2>/dev/null
    rc=0
    wait "$wrapper_pid" || rc=$?
    [ "$rc" -eq 1 ]
    python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["backend_process_code"] == 0 and r["dispatcher_code"] == 1 and r["native"]["thread_id"] == "thread-123"' "$T/report.json"
}

@test "cancelled descendant-held event pipe is bounded and cleaned up" {
    export FIXTURE_MODE=inherited_stdout
    started="$(date +%s)"
    bash "$DISPATCH" --report compact -C "$T/repo" -o "$T/out/last.md" "fixture" >"$T/report.json" 2>"$T/dispatch.stderr" &
    wrapper_pid=$!
    while [[ ! -s "$FIXTURE_PID_FILE" ]]; do sleep 0.01; done
    sleep 0.1
    kill -TERM "$wrapper_pid"
    rc=0
    wait "$wrapper_pid" || rc=$?
    [ "$rc" -eq 143 ]
    [ $(( $(date +%s) - started )) -lt 8 ]
    python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["backend_process_code"] == 0 and r["dispatcher_code"] == 143' "$T/report.json"
    dir="$(artifact_dir)"
    python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); assert p["capture_status"] == "complete"' "$dir/process.json"
}

@test "normal descendant output after the cancellation grace is preserved" {
    export FIXTURE_MODE=delayed_descendant
    started="$(date +%s)"
    run_dispatch
    [ "$DISPATCH_STATUS" -eq 0 ]
    [ $(( $(date +%s) - started )) -ge 2 ]
    dir="$(artifact_dir)"
    grep -q 'turn.started' "$dir/stdout.events.jsonl"
    python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["backend_process_code"] == 0 and r["dispatcher_code"] == 0 and r["unusable"] is False' "$T/report.json"
}
