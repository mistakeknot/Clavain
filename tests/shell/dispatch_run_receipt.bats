#!/usr/bin/env bats
# A governed dispatch appends one attribution receipt (JSONL, schema_version 1)
# per run. It carries identifiers and counts only, and a failure to write it
# never changes the dispatch exit status.

setup() {
    load test_helper
    ROOT="$BATS_TEST_DIRNAME/../.."
    DISPATCH="$ROOT/scripts/dispatch.sh"
    T="$(mktemp -d)"
    mkdir -p "$T/bin" "$T/repo"
    git -C "$T/repo" init -q
    printf 'x\n' > "$T/repo/f.txt"
    git -C "$T/repo" -c user.name=t -c user.email=t@t add f.txt
    git -C "$T/repo" -c user.name=t -c user.email=t@t commit -q -m base
    printf 'SECRET-PROMPT-TEXT\n' > "$T/prompt.md"
    printf '{"decision":"x"}\n' > "$T/ctx.json"
    POLICY_HASH="$(sha256sum "$ROOT/config/routing.yaml" | awk '{print $1}')"
    # Fake `ic` accepts every call; fake `claude` answers with one result event.
    printf '#!/usr/bin/env bash\nexit 0\n' > "$T/bin/ic"
    cat > "$T/bin/claude" <<'FAKE'
#!/usr/bin/env bash
cat > /dev/null
if [[ -n "${FAKE_SLEEP:-}" ]]; then echo $$ > "$FAKE_PIDFILE"; sleep "$FAKE_SLEEP" & wait $!; fi
jq -cn --arg body "${FAKE_BODY:-done}" --argjson u "${FAKE_USAGE:-null}" '{type:"result",subtype:"success",is_error:false,result:$body} + (if $u then {usage:$u} else {} end)'
exit "${FAKE_EXIT:-0}"
FAKE
    chmod +x "$T/bin/ic" "$T/bin/claude"
    export PATH="$T/bin:$PATH"
    export CLAVAIN_CONTEXT_GATEWAY_MODE=off CLAVAIN_BB_DIRECT_POOL=0
    export CLAVAIN_DISPATCH_RECEIPT_FILE="$T/state/receipts.jsonl"
    unset CLAVAIN_BEAD_ID BB_THREAD_ID CLAUDE_SESSION_ID CODEX_THREAD_ID DISPATCH_SESSION_ID
}

teardown() { rm -rf "$T"; }

governed() {
    bash "$DISPATCH" --role validation --role-resolved --resolved-profile-ref p1 \
        --resolved-route-json "{\"policy_hash\":\"$POLICY_HASH\"}" \
        --resolved-profile-json '{"profile_ref":"p1"}' --producer-identity prod-model \
        --to claude --model m1 --reasoning-effort high -C "$T/repo" \
        --prompt-file "$T/prompt.md" -o "$T/out.md" "$@"
}

@test "a governed dispatch appends one receipt with the attribution fields" {
    CLAVAIN_DECISION_CONTEXT="$T/ctx.json" BB_THREAD_ID=thr_x CLAUDE_SESSION_ID=sess_1 \
        run governed --bead mk-test
    [ "$status" -eq 0 ]
    [ "$(wc -l < "$T/state/receipts.jsonl")" -eq 1 ]
    r="$(cat "$T/state/receipts.jsonl")"
    [ "$(jq -r .schema_version <<< "$r")" = 1 ]
    [ "$(jq -r .role <<< "$r")" = validation ]
    [ "$(jq -r .backend <<< "$r")" = claude ]
    [ "$(jq -r .model <<< "$r")" = m1 ]
    [ "$(jq -r .effort <<< "$r")" = high ]
    [ "$(jq -r .producer_identity <<< "$r")" = prod-model ]
    [ "$(jq -r .bead_id <<< "$r")" = mk-test ]
    [ "$(jq -r .thread_id <<< "$r")" = thr_x ]
    [ "$(jq -r .session_id <<< "$r")" = sess_1 ]
    [ "$(jq -r .outcome <<< "$r")" = completed ]
    [ "$(jq -r .decision_context_sha256 <<< "$r")" = "$(sha256sum "$T/ctx.json" | awk '{print $1}')" ]
    jq -e '.started_at | test("^[0-9]{4}-.*Z$")' <<< "$r" >/dev/null
    jq -e '.ended_at | test("^[0-9]{4}-.*Z$")' <<< "$r" >/dev/null
}

@test "receipt holds no prompt text and absent bead and thread are null" {
    run governed
    [ "$status" -eq 0 ]
    r="$(cat "$T/state/receipts.jsonl")"
    [ "$(jq -r .bead_id <<< "$r")" = null ]
    [ "$(jq -r .thread_id <<< "$r")" = null ]
    [ "$(jq -r .decision_context_sha256 <<< "$r")" = null ]
    ! grep -q 'SECRET-PROMPT-TEXT' "$T/state/receipts.jsonl"
}

@test "a failed backend records outcome failed and keeps its exit status" {
    FAKE_EXIT=3 run governed
    [ "$status" -ne 0 ]
    [ "$(jq -r .outcome "$T/state/receipts.jsonl")" = failed ]
}

@test "an unwritable receipt location never changes the dispatch result" {
    printf 'file\n' > "$T/blocker"
    CLAVAIN_DISPATCH_RECEIPT_FILE="$T/blocker/sub/receipts.jsonl" run governed
    [ "$status" -eq 0 ]
}

@test "an ungoverned dispatch writes no receipt" {
    run bash "$DISPATCH" --to claude --model m1 -C "$T/repo" --prompt-file "$T/prompt.md" -o "$T/out.md"
    [ "$status" -eq 0 ]
    [ ! -e "$T/state/receipts.jsonl" ]
}

@test "the receipt directory is created 0700 and the file 0600 whatever the umask" {
    umask 022
    run governed
    [ "$status" -eq 0 ]
    [ "$(stat -c %a "$T/state")" = 700 ]
    [ "$(stat -c %a "$T/state/receipts.jsonl")" = 600 ]
}

@test "concurrent appends with very large records stay one valid JSON object per line" {
    source "$ROOT/scripts/lib-dispatch-audit.sh"
    ROLE=validation ENGINE=claude REASONING_EFFORT=high
    MODEL="$(head -c 24576 /dev/zero | tr '\0' 'm')"
    export ROLE ENGINE REASONING_EFFORT MODEL
    n=40
    for i in $(seq 1 $n); do
        ( _write_dispatch_run_receipt 0 ) &
    done
    wait
    [ "$(wc -l < "$T/state/receipts.jsonl")" -eq $n ]
    [ "$(jq -c . "$T/state/receipts.jsonl" | wc -l)" -eq $n ]
}

@test "a TERM-signalled run is receipted once as failed with the signal status" {
    FAKE_PIDFILE="$T/claude.pid" FAKE_SLEEP=30 governed >/dev/null 2>&1 &
    pid=$!
    for _ in $(seq 1 50); do [ -s "$T/claude.pid" ] && break; sleep 0.2; done
    [ -s "$T/claude.pid" ]
    pkill -TERM -P "$pid"
    kill -TERM "$(cat "$T/claude.pid")" 2>/dev/null || true
    wait "$pid" || true
    [ "$(wc -l < "$T/state/receipts.jsonl")" -eq 1 ]
    [ "$(jq -r .outcome "$T/state/receipts.jsonl")" = failed ]
    [ "$(jq -r .exit_code "$T/state/receipts.jsonl")" -ne 0 ]
}

@test "without flock no receipt is written, nothing is corrupted and the status is preserved" {
    mkdir -p "$T/nolock"
    for tool in bash jq date sha256sum awk sed head dirname mkdir sleep cat wc tr rm seq mktemp; do
        ln -s "$(command -v $tool)" "$T/nolock/$tool"
    done
    export ROOT
    run env PATH="$T/nolock" bash -c '
        command -v flock && exit 9
        source "$ROOT/scripts/lib-dispatch-audit.sh"
        ROLE=validation ENGINE=claude REASONING_EFFORT=high
        export ROLE ENGINE REASONING_EFFORT
        _write_dispatch_run_receipt 0 && exit 8
        exit 3
    '
    [ "$status" -eq 3 ]
    [ ! -s "$T/state/receipts.jsonl" ]
}

@test "TERM while the receipt append waits on the lock leaves exit status and receipt in agreement" {
    command -v flock >/dev/null
    mkdir -p "$T/state"
    ( exec 8>>"$T/state/receipts.jsonl.lock"; flock 8; sleep 8 ) &
    holder=$!
    sleep 0.5
    governed >/dev/null 2>&1 &
    pid=$!
    # The wrapper has finished the model run and blocks on the receipt lock.
    sleep 3
    pkill -TERM -P "$pid" -f dispatch.sh
    sleep 0.5
    kill "$holder" 2>/dev/null || true
    pkill -P "$holder" 2>/dev/null || true
    rc=0
    wait "$pid" || rc=$?
    [ "$(wc -l < "$T/state/receipts.jsonl")" -eq 1 ]
    [ "$(jq -r .exit_code "$T/state/receipts.jsonl")" -eq "$rc" ]
}

@test "a result without usage evidence is receipted as unavailable, not guessed" {
    run governed
    [ "$status" -eq 0 ]
    r="$(cat "$T/state/receipts.jsonl")"
    [ "$(jq -r .usage_status <<< "$r")" = unavailable ]
    [ "$(jq -r .tokens_cached_in <<< "$r")" = null ]
}

@test "claude provider usage lands in the receipt with its basis" {
    FAKE_USAGE='{"input_tokens":10,"output_tokens":5,"cache_read_input_tokens":30,"cache_creation_input_tokens":20}' run governed
    [ "$status" -eq 0 ]
    r="$(cat "$T/state/receipts.jsonl")"
    [ "$(jq -r .usage_status <<< "$r")" = complete ]
    [ "$(jq -r .usage_basis <<< "$r")" = claude-input-excludes-cache ]
    [ "$(jq -r .tokens_cached_in <<< "$r")" = 30 ]
    [ "$(jq -r .tokens_cache_write_in <<< "$r")" = 20 ]
    [ "$(jq -r .tokens_in <<< "$r")" = 10 ]
    [ "$(jq -r .tokens_out <<< "$r")" = 5 ]
}
