#!/usr/bin/env bats
setup() {
    load test_helper
    ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
    DISPATCH="$ROOT/scripts/dispatch.sh"
    T="$(mktemp -d)"
    mkdir -p "$T/bin" "$T/repo" "$T/holds"
    chmod 700 "$T/holds"
    git -C "$T/repo" init -q
    git -C "$T/repo" -c user.name=test -c user.email=test@example.invalid commit -q --allow-empty -m fixture
    printf '%s\n' '-payload' '' > "$T/prompt"
    printf '#!/bin/bash\nexit 0\n' > "$T/bin/ic"
    cat > "$T/bin/claude" <<'FAKE'
#!/bin/bash
if [[ "${1:-}" == --help ]]; then echo --tools; exit; fi
printf 'launch\n' >> "$T/count"
cat > "$T/received"
stat -c %d:%i . > "$T/cwd"
jq -cn --arg body "${FAKE_BODY:-done}" '{type:"result",subtype:"success",is_error:false,result:$body}' 
FAKE
    printf '#!/bin/bash\nexit 99\n' > "$T/bin/codex"
    printf '#!/bin/bash\nexit 99\n' > "$T/bin/kimi"
    chmod +x "$T/bin/"*
    export T PATH="$T/bin:$PATH" CLAVAIN_BB_DIRECT_POOL=0 CLAVAIN_CONTEXT_GATEWAY_MODE=off
    export CLAVAIN_DISPATCH_RECEIPT_FILE="$T/receipts"
    POLICY_HASH="$(sha256sum "$ROOT/config/routing.yaml" | cut -d' ' -f1)"
}
teardown() { [[ -z "${golden:-}" ]] || rm -f "$golden"; rm -rf "$T"; }
invoke() {
    local selected=claude previous='' arg
    local -a effort_args=()
    for arg in "$@"; do [[ "$previous" != --to ]] || selected="$arg"; previous="$arg"; done
    [[ "$selected" == kimi ]] || effort_args=(--reasoning-effort high)
    bash "$DISPATCH" --role validation --role-resolved --resolved-profile-ref p1 \
      --resolved-route-json "{\"policy_hash\":\"$POLICY_HASH\"}" --resolved-profile-json '{"profile_ref":"p1"}' \
      --producer-identity gpt-test --to claude --model m1 "${effort_args[@]}" -C "$T/repo" -o "$T/out" "$@"
}
hold() { invoke --prompt-file "$T/prompt" --hold-prompt "$T/holds/p" "$@"; }
submit() { invoke --submit-held "$T/holds/p" --held-manifest-sha256 "$(sha256sum "$T/holds/p.manifest.json" | cut -d' ' -f1)" "$@"; }
@test "1 hold publishes private prompt manifest and state without backend or gateway" {
    CLAVAIN_CONTEXT_GATEWAY_BIN="$T/missing" run hold
    [ "$status" = 0 ]
    [ ! -e "$T/count" ]
    [ "$(stat -c %a "$T/holds/p")" = 600 ]
    [ "$(stat -c %a "$T/holds/p.manifest.json")" = 600 ]
    [ "$(jq -r .state "$T/holds/p.state")" = held ]
    [[ "$output" != *payload* ]]
    jq -e '.outcome=="held" and .context_gateway_invoked==false' "$T/receipts"
}
@test "2 submit delivers exact held bytes including trailing newlines" {
    # Existing Findings Index contract suppresses the optional verdict suffix.
    printf '%s\n' '-payload' '' '## Findings Index' '' > "$T/prompt"
    hold --role routine-execution >/dev/null
    run submit --role routine-execution
    [ "$status" = 0 ]
    cmp "$T/holds/p" "$T/received"
    [ "$(tail -c 2 "$T/received" | od -An -tx1 | xargs)" = '0a 0a' ]
}
@test "2 raw NUL inputs refused before receipt publication" {
    printf 'a\0b' > "$T/nul"
    for source in --prompt-file --template; do
        run invoke "$source" "$T/nul" --hold-prompt "$T/holds/p"
        [ "$status" = 2 ]; [[ "$output" == *'NUL byte'* ]]
        [ ! -e "$T/receipts" ]; [ ! -e "$T/holds/p.state" ]
    done
    cp "$T/nul" "$T/repo/CLAUDE.md"
    run hold --inject-docs
    [ "$status" = 2 ]; [[ "$output" == *'NUL byte'* ]]
}
@test "3 changed isolation or working directory is refused" {
    hold --no-tools >/dev/null
    run submit
    [ "$status" = 2 ]; [ ! -e "$T/count" ]
    mkdir "$T/other"
    run submit --no-tools -C "$T/other"
    [ "$status" = 2 ]; [ ! -e "$T/count" ]
    ln -s "$T/repo" "$T/link"
    run submit --no-tools -C "$T/link"
    [ "$status" = 0 ]
    [ "$(cat "$T/cwd")" = "$(stat -c %d:%i "$T/repo")" ]
}
@test "3 symlink retarget preserves canonical cwd and replacement refuses after claim" {
    ln -s "$T/repo" "$T/link"; mkdir "$T/other"
    hold -C "$T/link" >/dev/null
    printf 'ln -sfn "$T/other" "$T/link"\n' > "$T/hook"
    CLAVAIN_TEST_MODE=1 CLAVAIN_TEST_PRELAUNCH_HOOK="$T/hook" run submit -C "$T/link"
    [ "$status" = 0 ]
    [ "$(cat "$T/cwd")" = "$(stat -c %d:%i "$T/repo")" ]
}
@test "4 decision context and identity drift refused" {
    printf '{"a":1}' > "$T/context"
    CLAVAIN_DECISION_CONTEXT="$T/context" hold >/dev/null
    printf '{"a":2}' > "$T/context"
    CLAVAIN_DECISION_CONTEXT="$T/context" run submit
    [ "$status" = 2 ]; [ ! -e "$T/count" ]
    run submit --producer-identity other --bead mk-other
    [ "$status" = 2 ]
}
@test "5 passthrough cannot change resolved command" {
    for flag in -c --profile --add-dir; do
        run hold "$flag" dummy
        [ "$status" = 2 ]; [ ! -e "$T/holds/p" ]
    done
}
@test "6 metadata digest and prompt tampering refused" {
    hold >/dev/null
    run invoke --submit-held "$T/holds/p" --held-manifest-sha256 "$(printf '%064d' 0)"
    [ "$status" = 2 ]
    printf x >> "$T/holds/p"
    run submit
    [ "$status" = 2 ]; [ ! -e "$T/count" ]
    [ "$(jq -r .state "$T/holds/p.state")" = held ]
}
@test "7 hold can be submitted only once even concurrently" {
    hold >/dev/null
    submit >"$T/s1" 2>&1 & p1=$!
    submit >"$T/s2" 2>&1 & p2=$!
    wait "$p1" || true; wait "$p2" || true
    [ "$(wc -l < "$T/count")" = 1 ]
    run submit
    [ "$status" = 2 ]
}
@test "8 finalizer refuses leaking prompt and unwritable receipt" {
    printf 'dummy-token-0000' > "$T/prompt"
    ANTHROPIC_AUTH_TOKEN=dummy-token-0000 run hold
    [ "$status" = 3 ]; [ ! -e "$T/holds/p" ]
    printf clean > "$T/prompt"; printf file > "$T/block"
    CLAVAIN_DISPATCH_RECEIPT_FILE="$T/block/receipt" run hold
    [ "$status" = 4 ]; [ ! -e "$T/holds/p" ]
}
@test "8 no tokens records no_tokens and never overwrites existing artifacts" {
    real_python="$(command -v python3)"
    cat > "$T/bin/python3" <<'FAKE'
#!/bin/bash
for a in "$@"; do [[ "$a" != *token-leak-scan.py ]] || { echo called >> "$T/scanner"; exit 99; }; done
exec "$REAL_PYTHON" "$@"
FAKE
    chmod +x "$T/bin/python3"; export REAL_PYTHON="$real_python"
    hold >/dev/null
    [ ! -e "$T/scanner" ]
    jq -e '.leak_scan=="no_tokens"' "$T/receipts"
    run hold
    [ "$status" != 0 ]
    [ "$(jq -r .state "$T/holds/p.state")" = held ]
}
@test "12 review scratch refused before clone or other setup" {
    run hold --review-scratch --head dummy
    [ "$status" = 2 ]; [[ "$output" == *'review-scratch selects a disposable clone'* ]]
    run invoke --submit-held "$T/holds/p" --review-scratch
    [ "$status" = 2 ]; [[ "$output" == *'review-scratch selects a disposable clone'* ]]
    [ ! -e "$T/count" ]; [ ! -e "$T/holds/p" ]
}
@test "2 NUL held bytes refused first and leave held state" {
    hold >/dev/null; printf 'a\0b' > "$T/holds/p"
    run submit
    [ "$status" = 2 ]; [[ "$output" == *'NUL byte'* ]]
    [ "$(jq -r .state "$T/holds/p.state")" = held ]
}
@test "3 directory replacement records definite refusal without launch" {
    hold >/dev/null
    printf 'mv "$T/repo" "$T/old"; mkdir "$T/repo"\n' > "$T/hook"
    CLAVAIN_TEST_MODE=1 CLAVAIN_TEST_PRELAUNCH_HOOK="$T/hook" run submit
    [ "$status" = 2 ]; [ ! -e "$T/count" ]
    [ "$(jq -r .state "$T/holds/p.state")" = completed:refused ]
    [ "$(tail -1 "$T/receipts" | jq -r .outcome)" = refused_workdir_changed ]
}
@test "4 context mutation mid-run cannot change snapshot hash" {
    printf '{"a":1}' > "$T/context"
    expected="$(sha256sum "$T/context" | cut -d' ' -f1)"
    printf 'echo changed > "$T/context"\n' > "$T/hook"
    CLAVAIN_DECISION_CONTEXT="$T/context" hold >/dev/null
    CLAVAIN_DECISION_CONTEXT="$T/context" CLAVAIN_TEST_MODE=1 CLAVAIN_TEST_PRELAUNCH_HOOK="$T/hook" run submit
    [ "$status" = 0 ]
    [ "$(tail -1 "$T/receipts" | jq -r .decision_context_sha256)" = "$expected" ]
}
@test "6 resigned metadata changes and expired manifests refused" {
    hold >/dev/null
    jq '.exec_spec.model="changed"' "$T/holds/p.manifest.json" > "$T/m"; cp "$T/m" "$T/holds/p.manifest.json"
    run submit
    [ "$status" = 2 ]; [ ! -e "$T/count" ]
    jq '.created_at=0' "$T/holds/p.manifest.json" > "$T/m"; cp "$T/m" "$T/holds/p.manifest.json"
    run submit
    [ "$status" = 2 ]
}
@test "7 durable claimed state is terminal outcome unknown" {
    hold >/dev/null
    printf '{"state":"claimed","pid":999999}\n' > "$T/holds/p.state"
    run submit
    [ "$status" = 2 ]; [[ "$output" == *outcome_unknown* ]]; [ ! -e "$T/count" ]
}
@test "8 state publication failure cannot publish a prompt" {
    mkdir "$T/holds/p.state"
    run hold
    [ "$status" = 4 ]; [ ! -e "$T/holds/p" ]; [ ! -e "$T/holds/p.manifest.json" ]
}
@test "10 tool enabled Kimi holds refused before launch" {
    printf '#!/bin/bash\nexit 0\n' > "$T/bin/bwrap"
    printf '#!/bin/bash\necho launch >> "$T/count"\n' > "$T/bin/kimi"
    chmod +x "$T/bin/bwrap" "$T/bin/kimi"
    mkdir -p "$T/plans"; printf plan > "$T/plans/plan.md"
    printf 'Read %s\n' "$T/plans/plan.md" > "$T/prompt"
    CLAVAIN_SEAT_BWRAP=1 run hold --to kimi --plan "$T/plans/plan.md"
    [ "$status" = 2 ]; [[ "$output" == *'tool-enabled kimi seat'* ]]
    [ ! -e "$T/count" ]; [ ! -e "$T/holds/p" ]
}
@test "11 ordinary receipt has final hash and gateway invocation with old failure policy" {
    run invoke --prompt-file "$T/prompt"
    [ "$status" = 0 ]
    [ "$(jq -r .final_prompt_sha256 "$T/receipts")" = "$(sha256sum "$T/received" | cut -d' ' -f1)" ]
    jq -e '.schema_version==1 and .context_gateway_invoked==true and .tool_isolation.tool_free==false' "$T/receipts"
    CLAVAIN_CONTEXT_GATEWAY_BIN="$T/missing" run invoke --prompt-file "$T/prompt"
    [ "$status" = 127 ]
}
fake_engines() {
    cat > "$T/bin/codex" <<'FAKE'
#!/bin/bash
if [[ "$1" == --version ]]; then echo probe >> "$T/probes"; echo 'codex-cli 0.1.0'; exit; fi
if [[ "$1" == sandbox ]]; then exit 0; fi
printf 'launch\n' >> "$T/count"
printf '%s\0' "$@" > "$T/argv"
stat -c %d:%i . > "$T/cwd"
args=("$@"); out=''
for ((i=0;i<$#;i++)); do

 [[ "${args[i]}" != -o ]] || out="${args[i+1]}"
 [[ "${args[i]}" == --json ]] || prompt="${args[i]}"
done
printf '%s' "$prompt" > "$T/received"
[[ -z "$out" ]] || echo done > "$out"
echo '{"type":"turn.completed"}'
FAKE
    cat > "$T/bin/kimi" <<'FAKE'
#!/bin/bash
printf 'launch\n' >> "$T/count"
stat -c %d:%i . > "$T/cwd"
for a in "$@"; do [[ "$a" != --prompt=* ]] || printf '%s' "${a#--prompt=}" > "$T/received"; done
echo done
FAKE
    chmod +x "$T/bin/codex" "$T/bin/kimi"
}
@test "2 and 3 Codex and toolless Kimi deliver exact bytes from verified cwd" {
    printf '%s\n' '-payload' '' '## Findings Index' '' > "$T/prompt"
    fake_engines
    for engine in codex kimi; do
        export CLAVAIN_SEAT_BWRAP=0
        run hold --to "$engine" --role routine-execution
        [ "$status" = 0 ]
        run submit --to "$engine" --role routine-execution
        [ "$status" = 0 ]
        cmp "$T/holds/p" "$T/received"
        [ "$(tail -c 2 "$T/received" | od -An -tx1 | xargs)" = '0a 0a' ]
        if [[ "$engine" == codex ]]; then
            ! tr '\0' '\n' < "$T/argv" | grep -qx -- -C
            [ "$(tr '\0' '\n' < "$T/argv" | grep -c '^model_reasoning_effort=')" = 1 ]
            tr '\0' '\n' < "$T/argv" | grep -q '^model_reasoning_effort=high$'
        fi
        [ "$(cat "$T/cwd")" = "$(stat -c %d:%i "$T/repo")" ]
        rm "$T/holds/p" "$T/holds/p.manifest.json" "$T/holds/p.state" "$T/holds/p.lock"
    done
}
@test "9 pinned fallback retains authenticated substitute contract and provenance" {
    fake_engines
    jq -cn --arg h "$POLICY_HASH" '{policy_hash:$h,producer_model:"claude-producer",profile_ref:"primary",profile:{backend:"codex",model:"gpt-test",minimum_codex_version:"99.0.0"},fallback_chain:[{profile_ref:"fallback",profile:{backend:"claude",model:"claude-test",reasoning_effort:"high"}}]}' > "$T/route"
    cat > "$T/bin/ic" <<'FAKE'
#!/bin/bash
if [[ "$*" == *'route dispatch'* ]]; then cat "$T/route"; elif [[ "$1" == version ]]; then echo test; fi
FAKE
    mkdir -p "$T/tracker/.beads"
    export CLAVAIN_RECHECK_BEADS_DIR="$T/tracker"
    cat > "$T/bin/bd" <<'FAKE'
#!/bin/bash
if [[ "$*" == *--help* ]]; then echo --silent; exit; fi
printf '%s\n' "$1" >> "$T/bd-calls"
[[ "$1" != create ]] || echo mk-fake
exit 0
FAKE
    chmod +x "$T/bin/bd"
    export FAKE_BODY=$'VERDICT: PASS\n\n## Re-check by the other lab\n- Confirm the lock behavior.'
    export CLAVAIN_POOL_HEADROOM=0
    outer() { bash "$DISPATCH" --role cross-lab-review --producer-identity claude-producer --bead mk-test -C "$T/repo" -o "$T/out" "$@"; }
    run outer --prompt-file "$T/prompt" --hold-prompt "$T/holds/p"
    [ "$status" = 0 ]
    jq -e '.executed_profile_ref=="fallback" and .capacity_failure_class=="insufficient_codex_version" and .capacity_substitute_json!=null and (.skipped_candidates|length)>0' "$T/holds/p.manifest.json"
    probes="$(wc -l < "$T/probes")"
    run outer --submit-held "$T/holds/p" --held-manifest-sha256 "$(sha256sum "$T/holds/p.manifest.json" | cut -d' ' -f1)"
    [ "$status" = 0 ]
    [ "$(wc -l < "$T/probes")" = "$probes" ]
    cmp "$T/holds/p" "$T/received"
    tail -1 "$T/receipts" | jq -e '.capacity_substitute_source=="held_manifest"'
    grep -qx create "$T/bd-calls"
    [ -s "$T/out.recheck.md" ]
}
@test "7 dispatcher death after durable claim leaves outcome unknown" {
    hold >/dev/null
    mkfifo "$T/fifo"
    cat > "$T/bin/claude" <<'FAKE'
#!/bin/bash
printf 'launch\n' >> "$T/count"
cat > "$T/received"
echo ready > "$T/ready"
read -r x < "$T/fifo"
FAKE
    digest="$(sha256sum "$T/holds/p.manifest.json" | cut -d' ' -f1)"
    setsid bash "$DISPATCH" \
      --role validation --role-resolved --resolved-profile-ref p1 \
      --resolved-route-json "{\"policy_hash\":\"$POLICY_HASH\"}" --resolved-profile-json '{"profile_ref":"p1"}' \
      --producer-identity gpt-test --to claude --model m1 --reasoning-effort high -C "$T/repo" -o "$T/out" \
      --submit-held "$T/holds/p" --held-manifest-sha256 "$digest" >"$T/killed" 2>&1 & pid=$!
    for _ in $(seq 1 100); do [ -e "$T/ready" ] && break; sleep .1; done
    [ -e "$T/ready" ]
    [ "$(jq -r .state "$T/holds/p.state")" = claimed ]
    kill -KILL -- "-$pid"; wait "$pid" || true
    run submit
    [ "$status" = 2 ]; [[ "$output" == *outcome_unknown* ]]
}
@test "8 leak helper errors and missing helper fail closed through real wrapper" {
    real_python="$(command -v python3)"
    cat > "$T/bin/python3" <<'FAKE'
#!/bin/bash
for a in "$@"; do
 if [[ "$a" == *token-leak-scan.py ]]; then exit "${SCAN_RC:-2}"; fi
done
exec "$REAL_PYTHON" "$@"
FAKE
    chmod +x "$T/bin/python3"
    export REAL_PYTHON="$real_python"
    for rc in 2 3 5 127; do
        SCAN_RC="$rc" ANTHROPIC_AUTH_TOKEN=dummy-token-0000 run hold
        [ "$status" = 3 ]; [ ! -e "$T/holds/p" ]; [ ! -e "$T/holds/p.state" ]
    done
}
@test "3 bwrap availability and Codex sandbox drift refuse before claim" {
    fake_engines
    printf '#!/bin/bash\nexit 0\n' > "$T/bin/bwrap"; chmod +x "$T/bin/bwrap"
    CLAVAIN_SEAT_BWRAP=1 hold --to codex >/dev/null
    CLAVAIN_SEAT_BWRAP=0 run submit --to codex
    [ "$status" = 2 ]; [ ! -e "$T/count" ]
    CLAVAIN_SEAT_BWRAP=1 run submit --to codex -s read-only
    [ "$status" = 2 ]; [ ! -e "$T/count" ]
    [ "$(jq -r .state "$T/holds/p.state")" = held ]
}
@test "5 passthrough refused on submit as well as hold" {
    hold >/dev/null
    for flag in -c --profile --add-dir; do
        run submit "$flag" dummy
        [ "$status" = 2 ]; [ ! -e "$T/count" ]
    done
}
@test "8 manifest-link failure rolls back prompt and state" {
    real_ln="$(command -v ln)"
    cat > "$T/bin/ln" <<'FAKE'
#!/bin/bash
[[ "${*: -1}" != *.manifest.json ]] || exit 1
exec "$REAL_LN" "$@"
FAKE
    chmod +x "$T/bin/ln"; export REAL_LN="$real_ln"
    run hold
    [ "$status" = 4 ]; [ ! -e "$T/holds/p" ]; [ ! -e "$T/holds/p.state" ]
    [ "$(tail -1 "$T/receipts" | jq -r .outcome)" = hold_publish_failed ]
}
@test "8 failed hits mktemp reports scan error without publication" {
    real_mktemp="$(command -v mktemp)"
    cat > "$T/bin/mktemp" <<'FAKE'
#!/bin/bash
[[ "$*" != *clavain-token-leak-hits* ]] || exit 1
exec "$REAL_MKTEMP" "$@"
FAKE
    chmod +x "$T/bin/mktemp"; export REAL_MKTEMP="$real_mktemp"
    ANTHROPIC_AUTH_TOKEN=dummy-token-0000 run hold
    [ "$status" = 3 ]; [[ "$output" == *'leak scan could not run'* ]]
    [ ! -e "$T/holds/p" ]
}
@test "4 every governing decision field is authenticated" {
    hold >/dev/null
    for args in '--producer-identity other' '--validator-relationship adversarial' '--bead mk-other' '--policy-profile other'; do
        read -r -a flags <<< "$args"
        run submit "${flags[@]}"
        [ "$status" = 2 ]; [ ! -e "$T/count" ]
    done
    run submit --resolved-route-json "{\"policy_hash\":\"$(printf '%064d' 0)\"}"
    [ "$status" = 2 ]; [ ! -e "$T/count" ]
}
@test "9 resigned capacity provenance cannot disagree with held paragraph" {
    # Authenticated provenance cannot invent a contract absent from held bytes.
    hold >/dev/null
    jq '.capacity_substitute_json={failure_class:"quota_exhausted"}' "$T/holds/p.manifest.json" > "$T/m"; cp "$T/m" "$T/holds/p.manifest.json"
    run submit
    [ "$status" = 2 ]; [[ "$output" == *'capacity contract mismatch'* ]]
    [ ! -e "$T/count" ]
}
@test "7 backend failure completes a claimed hold and never retries quota" {
    cat > "$T/bin/claude" <<'FAKE'
#!/bin/bash
printf 'launch\n' >> "$T/count"
cat > "$T/received"
echo '{"type":"result","is_error":true,"result":"usage limit exceeded"}'
exit 1
FAKE
    hold >/dev/null
    run submit
    [ "$status" != 0 ]
    [ "$(wc -l < "$T/count")" = 1 ]
    [[ "$(jq -r .state "$T/holds/p.state")" == completed:* ]]
    run submit
    [ "$status" = 2 ]; [ "$(wc -l < "$T/count")" = 1 ]
}
@test "8 terminal receipt failure after claim returns evidence status 75" {
    hold >/dev/null
    printf file > "$T/block"
    CLAVAIN_DISPATCH_RECEIPT_FILE="$T/block/receipt" run submit
    [ "$status" = 75 ]; [[ "$output" == *'evidence not recorded'* ]]
    [ "$(wc -l < "$T/count")" = 1 ]
}
@test "3 symlink retarget and directory replacement cover all direct engines" {
    fake_engines; export CLAVAIN_SEAT_BWRAP=0
    for engine in codex kimi; do
        mkdir -p "$T/repo" "$T/other"; ln -sfn "$T/repo" "$T/link"
        hold --to "$engine" -C "$T/link" >/dev/null
        printf 'ln -sfn "$T/other" "$T/link"\n' > "$T/hook"
        CLAVAIN_TEST_MODE=1 CLAVAIN_TEST_PRELAUNCH_HOOK="$T/hook" run submit --to "$engine" -C "$T/link"
        [ "$status" = 0 ]
        [ "$(cat "$T/cwd")" = "$(stat -c %d:%i "$T/repo")" ]
        rm "$T/holds/p" "$T/holds/p.manifest.json" "$T/holds/p.state" "$T/holds/p.lock"
        hold --to "$engine" >/dev/null; rm "$T/count"
        printf 'mv "$T/repo" "$T/old"; mkdir "$T/repo"\n' > "$T/hook"
        CLAVAIN_TEST_MODE=1 CLAVAIN_TEST_PRELAUNCH_HOOK="$T/hook" run submit --to "$engine"
        [ "$status" = 2 ]; [ ! -e "$T/count" ]
        [ "$(jq -r .state "$T/holds/p.state")" = completed:refused ]
        rm "$T/holds/p" "$T/holds/p.manifest.json" "$T/holds/p.state" "$T/holds/p.lock"
        rm -rf "$T/old"
    done
}
@test "3 inherited cwd drift refuses even without a -C argument" {
    without_cd() {
        bash "$DISPATCH" --role validation --role-resolved --resolved-profile-ref p1 \
          --resolved-route-json "{\"policy_hash\":\"$POLICY_HASH\"}" --resolved-profile-json '{"profile_ref":"p1"}' \
          --producer-identity gpt-test --to claude --model m1 --reasoning-effort high -o "$T/out" "$@"
    }
    ( cd "$T/repo" && without_cd --prompt-file "$T/prompt" --hold-prompt "$T/holds/p" ) >/dev/null
    digest="$(sha256sum "$T/holds/p.manifest.json" | cut -d' ' -f1)"
    run without_cd --submit-held "$T/holds/p" --held-manifest-sha256 "$digest"
    [ "$status" = 2 ]; [ ! -e "$T/count" ]
    cd "$T/repo"
    run without_cd --submit-held "$T/holds/p" --held-manifest-sha256 "$digest"
    [ "$status" = 0 ]
    [ "$(cat "$T/cwd")" = "$(stat -c %d:%i "$T/repo")" ]
}
@test "6 metadata-only edit with original digest refused" {
    hold >/dev/null
    digest="$(sha256sum "$T/holds/p.manifest.json" | cut -d' ' -f1)"
    jq '.created_at+=1' "$T/holds/p.manifest.json" > "$T/m"; cp "$T/m" "$T/holds/p.manifest.json"
    run invoke --submit-held "$T/holds/p" --held-manifest-sha256 "$digest"
    [ "$status" = 2 ]; [[ "$output" == *'manifest digest mismatch'* ]]
}
@test "11 ordinary prompt argv cwd gateway NUL and legacy receipts match main" {
    baseline="$(git -C "$ROOT" merge-base HEAD origin/main)"
    golden="$(mktemp "$ROOT/scripts/.dispatch-golden.XXXXXX")"
    git -C "$ROOT" show "$baseline:scripts/dispatch.sh" > "$golden"
    # Dummy binaries capture actual transport input rather than shell displays.
    sed -i '/printf.*launch/i printf "%s\\0" "$@" > "$T/argv"' "$T/bin/claude"
    for source in normal nul; do
        if [[ "$source" == nul ]]; then printf 'a\0b\n' > "$T/prompt"; fi
        run invoke --prompt-file "$T/prompt"
        [ "$status" = 0 ]
        cp "$T/received" "$T/new-prompt"; cp "$T/argv" "$T/new-argv"; cp "$T/cwd" "$T/new-cwd"
        tail -1 "$T/receipts" > "$T/new-receipt"
        current="$DISPATCH"; DISPATCH="$golden"
        run invoke --prompt-file "$T/prompt"
        DISPATCH="$current"
        [ "$status" = 0 ]
        cmp "$T/new-prompt" "$T/received"; cmp "$T/new-argv" "$T/argv"; cmp "$T/new-cwd" "$T/cwd"
        fields='{schema_version,kind,role,backend,model,effort,producer_identity,bead_id,decision_context_sha256,exit_code,outcome,tokens_in,tokens_out,usage_status,usage_basis}'
        [ "$(jq -cS "$fields" "$T/new-receipt")" = "$(tail -1 "$T/receipts" | jq -cS "$fields")" ]
    done
    rm -f "$golden"
}
@test "8 finalizer isolates fresh scan flags and restores sticky earlier results" {
    # Extract functions without executing dispatch's top-level backend path.
    for fn in _token_leak_scan _finalize_hold _hold_write_state; do
        sed -n "/^${fn}() {/,/^}/p" "$DISPATCH" >> "$T/functions"
    done
    source "$T/functions"
    _token_leak_capture() { :; }
    _token_leak_enabled() { return 0; }
    _token_leak_py() { return 0; }
    _hold_hash() { sha256sum | cut -d' ' -f1; }
    _prepare_role_audit() { :; }
    _write_dispatch_run_receipt() { printf '%s %s\n' "$TOKEN_LEAK_FOUND" "$TOKEN_LEAK_DIRTY" > "$T/flags"; }
    TOKEN_LEAK_FOUND=true TOKEN_LEAK_ERROR=false TOKEN_LEAK_DIRTY=true TOKEN_LEAK_HITS=''
    TOKEN_LEAK_TOKENS=(dummy-token-0000)
    HOLD_PROMPT="$T/holds/p" PROMPT=clean HELD_ARGV_SPEC='[]' HELD_EXEC_SPEC='{}' HELD_DECISION='{}'
    DISPATCH_SCRIPT_DIR="$ROOT/scripts" FINAL_PROMPT_SHA256=dummy FINAL_PROMPT_BYTES=5
    RESOLVED_PROFILE_REF=p1 FALLBACK_REASON='' HELD_CAPACITY_FAILURE_CLASS='' HELD_SKIPPED_CANDIDATES='[]'
    CAPACITY_SUBSTITUTE_JSON=null HELD_WORKDIR_GIT=null
    run _finalize_hold
    [ "$status" = 0 ]
    [ "$(cat "$T/flags")" = 'true true' ]
}
@test "7 killing backend alone records completed failure and consumes hold" {
    cat > "$T/bin/claude" <<'FAKE'
#!/bin/bash
printf 'launch\n' >> "$T/count"
echo $$ > "$T/backend-pid"
cat > "$T/received"
sleep 60 & echo $! > "$T/sleep-pid"; wait $!
FAKE
    hold >/dev/null
    submit >"$T/submitted" 2>&1 & parent=$!
    for _ in $(seq 1 100); do [[ -s "$T/backend-pid" && -s "$T/sleep-pid" ]] && break; sleep .1; done
    [ -s "$T/backend-pid" ]; [ -s "$T/sleep-pid" ]
    backend="$(cat "$T/backend-pid")"
    kill -KILL "$backend"
    kill -KILL "$(cat "$T/sleep-pid")" 2>/dev/null || true
    wait "$parent" || true
    [[ "$(jq -r .state "$T/holds/p.state")" == completed:* ]]
    [ "$(jq -r .state "$T/holds/p.state")" != completed:0 ]
    run submit
    [ "$status" = 2 ]; [ "$(wc -l < "$T/count")" = 1 ]
}
@test "3 transport drift from direct to direct pooled is refused" {
    hold >/dev/null
    real_python="$(command -v python3)"
    cat > "$T/bin/python3" <<'FAKE'
#!/bin/bash
case "${1:-}" in */bb-host.py|*/bb-pool-eligibility.py) exit 0 ;; esac
exec "$REAL_PYTHON" "$@"
FAKE
    chmod +x "$T/bin/python3"; export REAL_PYTHON="$real_python"
    CLAVAIN_BB_DIRECT_POOL=1 BB_SERVER_URL=http://example.invalid \
      ANTHROPIC_BASE_URL=http://example.invalid/api/v1/plugins/account-pool/http \
      ANTHROPIC_AUTH_TOKEN=dummy-token-0000 run submit
    [ "$status" = 2 ]; [[ "$output" == *'execution spec changed'* ]]
    [ ! -e "$T/count" ]; [ "$(jq -r .state "$T/holds/p.state")" = held ]
}
@test "10 ordinary tools-enabled Kimi still rewrites the plan path" {
    mkdir "$T/plans"; printf plan > "$T/plans/plan.md"
    cat > "$T/bin/bwrap" <<'FAKE'
#!/bin/bash
while (( $# )); do
 if [[ "$1" == -- ]]; then shift; exec "$@"; fi
 shift
done
exit 0
FAKE
    cat > "$T/bin/kimi" <<'FAKE'
#!/bin/bash
for a in "$@"; do [[ "$a" != --prompt=* ]] || printf '%s' "${a#--prompt=}" > "$T/kimi-prompt"; done
printf '{"role":"assistant","content":"VERDICT: PASS"}\n'
FAKE
    chmod +x "$T/bin/bwrap" "$T/bin/kimi"
    CLAVAIN_SEAT_BWRAP=1 run invoke --to kimi --plan "$T/plans/plan.md" "Read $T/plans/plan.md"
    [ -s "$T/kimi-prompt" ]
    ! grep -qF "$T/plans/plan.md" "$T/kimi-prompt"
    grep -q 'clavain-kimi-sandbox' "$T/kimi-prompt"
}
@test "2 raw NUL fallback works when grep PCRE is unavailable" {
    real_grep="$(command -v grep)"
    cat > "$T/bin/grep" <<'FAKE'
#!/bin/bash
[[ "${1:-}" != -qaP ]] || exit 2
exec "$REAL_GREP" "$@"
FAKE
    chmod +x "$T/bin/grep"; export REAL_GREP="$real_grep"
    printf 'a\0b' > "$T/prompt"
    run hold
    [ "$status" = 2 ]; [[ "$output" == *'NUL byte'* ]]
    [ ! -e "$T/holds/p" ]; [ ! -e "$T/receipts" ]
}
@test "8 writable publication parent and symlink targets are refused" {
    chmod 777 "$T/holds"
    run hold
    [ "$status" = 4 ]; [ ! -e "$T/holds/p" ]
    chmod 700 "$T/holds"
    ln -s "$T/absent" "$T/holds/p"
    run hold
    [ "$status" = 4 ]; [ ! -e "$T/absent" ]
}
@test "7 held outer quota failure never walks the fallback chain" {
    fake_engines
    jq -cn --arg h "$POLICY_HASH" '{policy_hash:$h,producer_model:"gpt-producer",profile_ref:"primary",profile:{backend:"claude",model:"m1",reasoning_effort:"high"},fallback_chain:[{profile_ref:"fallback",profile:{backend:"codex",model:"gpt-fake",reasoning_effort:"high"}}]}' > "$T/route"
    cat > "$T/bin/ic" <<'FAKE'
#!/bin/bash
[[ "$*" != *'route dispatch'* ]] || cat "$T/route"
exit 0
FAKE
    outer_quota() { bash "$DISPATCH" --role validation --producer-identity gpt-producer -C "$T/repo" -o "$T/out" "$@"; }
    outer_quota --prompt-file "$T/prompt" --hold-prompt "$T/holds/p" >/dev/null
    cat > "$T/bin/claude" <<'FAKE'
#!/bin/bash
printf 'launch\n' >> "$T/count"
cat >/dev/null
echo "You've hit your usage limit." >&2
exit 1
FAKE
    run outer_quota --submit-held "$T/holds/p" --held-manifest-sha256 "$(sha256sum "$T/holds/p.manifest.json" | cut -d' ' -f1)"
    [ "$status" != 0 ]; [ "$(wc -l < "$T/count")" = 1 ]
    [ ! -e "$T/probes" ]
    [[ "$(jq -r .state "$T/holds/p.state")" == completed:* ]]
}
@test "7 pool retry is disabled for held candidates even when pool is available" {
    source "$ROOT/scripts/lib-dispatch-audit.sh"
    sed -n '/^_run_candidate_with_policy() {/,/^}/p' "$DISPATCH" > "$T/candidate"
    source "$T/candidate"
    _bb_pool_available() { echo probe >> "$T/pool"; return 0; }
    cat > "$T/bin/failure" <<'FAKE'
#!/bin/bash
echo launch >> "$T/count"
echo quota_exhausted > "$CLAVAIN_DISPATCH_FAILURE_FILE"
exit 1
FAKE
    chmod +x "$T/bin/failure"
    CLAVAIN_HELD_SUBMIT=1 run _run_candidate_with_policy "$T/bin/failure"
    [ "$status" = 1 ]; [ "$(wc -l < "$T/count")" = 1 ]; [ ! -e "$T/pool" ]
}
@test "4 actual resolved policy profile is recorded even without caller override" {
    run hold --resolved-route-json "{\"policy_hash\":\"$POLICY_HASH\",\"policy_profile\":\"default\"}"
    [ "$status" = 0 ]
    [ "$(jq -r .decision.policy_profile "$T/holds/p.manifest.json")" = default ]
    [ "$(jq -r .policy_profile "$T/receipts")" = default ]
}
