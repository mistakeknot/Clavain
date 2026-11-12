#!/usr/bin/env bats
# A governed dispatch appends one attribution receipt (JSONL, schema_version 1)
# per run. It carries identifiers and counts only, and a failure to write it
# never changes the dispatch exit status.

setup() {
    # Each fixture selects its own policy and context, independent of its parent.
    unset CLAVAIN_ROUTING_POLICY CLAVAIN_DECISION_CONTEXT CLAVAIN_SELECTED_ROOT
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

@test "packaged codex dispatch appends observed identity from its captured provider events" {
    export CODEX_HOME="$T/codex"
    local tid=01a0f12b-4441-7732-b494-da5347122cea
    mkdir -p "$CODEX_HOME/sessions/2026/11/06"
    printf '{"type":"session_meta","payload":{"id":"%s"}}\n{"type":"turn_context","payload":{"model":"gpt-6-astra","effort":"high"}}\n{"type":"response_item","payload":{"type":"message","role":"assistant"}}\n' "$tid" > "$CODEX_HOME/sessions/2026/11/06/rollout-test-$tid.jsonl"
    cat > "$T/bin/codex" <<'FAKE'
#!/usr/bin/env bash
if [[ "$*" == *--version* ]]; then echo codex-test; exit; fi
printf '{"type":"thread.started","thread_id":"01a0f12b-4441-7732-b494-da5347122cea"}\n{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}\n'
FAKE
    chmod +x "$T/bin/codex"
    run bash "$DISPATCH" --role validation --role-resolved --resolved-profile-ref p1 \
        --resolved-route-json "{\"policy_hash\":\"$POLICY_HASH\"}" \
        --resolved-profile-json '{"profile_ref":"p1"}' --producer-identity prod-model \
        --to codex --model gpt-6.1-sol --reasoning-effort high -C "$T/repo" \
        --prompt-file "$T/prompt.md" -o "$T/out.md"
    [ "$status" -eq 0 ]
    [ "$(jq -r .observed_model "$T/state/receipts.jsonl")" = gpt-6-astra ]
    [ "$(jq -r .observed_model_matches_requested "$T/state/receipts.jsonl")" = false ]
    [ "$(jq -r .observed_thread_id "$T/state/receipts.jsonl")" = "$tid" ]
}

@test "final prompt hash and isolation are additive schema one evidence" {
    run governed
    [ "$status" -eq 0 ]
    jq -e '.schema_version == 1 and (.final_prompt_sha256 | test("^[a-f0-9]{64}$")) and .final_prompt_bytes > 0 and .tool_isolation.transport == "direct" and .context_gateway_mode == "off" and .context_gateway_invoked == true' "$T/state/receipts.jsonl" >/dev/null
}

@test "ordinary receipt bytes match main with experiment hooks loaded" {
    mkdir -p "$T/main/scripts"
    git -C "$ROOT" show origin/main:scripts/lib-dispatch-audit.sh > "$T/main/scripts/lib-dispatch-audit.sh"
    ln -s "$ROOT/scripts/provider_usage.py" "$T/main/scripts/provider_usage.py"
    sed -n '/^_experiment_receipt_fields() {/,/^}/p' "$DISPATCH" > "$T/experiment-hook.sh"
    # Both builders receive identical inputs, a frozen clock and the real
    # experiment hook. cmp checks key order and newlines as well as values.
    printf '%s\n' '{"final_prompt_sha256":"fixture-prompt","policy_hash":"fixture-policy","executed_profile_ref":"p1","policy_profile":"default"}' > "$T/hold-fields.json"
    for entry in empty unset; do
        for held in false true; do
            for version in main current; do
                lib="$ROOT/scripts/lib-dispatch-audit.sh"
                [[ "$version" != main ]] || lib="$T/main/scripts/lib-dispatch-audit.sh"
                run bash -eu -c '
                    source "$1"
                    source "$2"
                    date() { printf "1700000000\n"; }
                    HOLD_FIELDS="$6"
                    _hold_receipt_fields() { cat "$HOLD_FIELDS"; }
                    ROLE=validation ENGINE=claude MODEL=m1 REASONING_EFFORT=high
                    PRODUCER_IDENTITY=fixture-producer STARTED_TS=1699999999
                    DISPATCH_ID=fixture-dispatch ATTEMPT_ID=fixture-attempt
                    CLAVAIN_BEAD_ID=mk-fixture BB_THREAD_ID="" DISPATCH_SESSION_ID=""
                    CLAVAIN_DECISION_CONTEXT="" CLAVAIN_REQUIRE_USAGE=0 CLAVAIN_REVIEW_EVENTS=""
                    SUMMARY_FILE="" PROVIDER_EVENTS="" VIA="" DISPATCH_RESULT_READY=false
                    HELD_MODE="$4"
                    if [[ "$3" == unset ]]; then unset EXPERIMENT_ENTRY; else EXPERIMENT_ENTRY=""; fi
                    _build_dispatch_run_receipt 0 > "$5"
                ' _ "$lib" "$T/experiment-hook.sh" "$entry" "$held" "$T/$version.json" "$T/hold-fields.json"
                [ "$status" -eq 0 ]
            done
            cmp -s "$T/main.json" "$T/current.json"
        done
    done
}
