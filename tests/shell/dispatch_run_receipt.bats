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
jq -cn --arg body "${FAKE_BODY:-done}" '{type:"result",subtype:"success",is_error:false,result:$body}'
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
