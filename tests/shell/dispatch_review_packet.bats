#!/usr/bin/env bats
# Step 4 (mk-42j9.34): opt-in review-packet boundary in dispatch.sh.
# --review-input/--review-packet are inert unless a caller explicitly passes
# one; every other role/plan path must be byte-for-byte unchanged.

setup() {
    load test_helper
    DISPATCH="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
    REAL_POLICY_HASH="$(sha256sum "$REPO_ROOT/config/routing.yaml" | cut -d' ' -f1)"
    load "$BATS_TEST_DIRNAME/review_packet_helper.bash"
    review_packet_fixture_setup
    export LC_ALL=C
    export CLAVAIN_CONTEXT_GATEWAY_MODE=off
    export CLAVAIN_BB_DIRECT_POOL=0
    T="$FIXTURE_DIR"
    mkdir -p "$T/bin" "$T/repo"
    git -C "$T/repo" init -q
    printf 'x\n' > "$T/repo/f.txt"
    git -C "$T/repo" -c user.name=t -c user.email=t@t add f.txt
    git -C "$T/repo" -c user.name=t -c user.email=t@t commit -q -m base
}

teardown() {
    review_packet_fixture_teardown
}

# A richer fake `ic` than the builder's own helper: answers `route list`
# (producer receipt lookup), `route identity` (always resolves to the
# fixture's gpt-6-astra producer unless IC_IDENTITY_OVERRIDE says otherwise
# for a given --model), `route dispatch` (candidate resolution, driven by
# $IC_ROUTE_DISPATCH_JSON), and `route record` (audit persistence, logged
# verbatim to ic.log so a test can grep its --context= payload).
install_fake_ic() {
    IC_BIN_DIR="$T/bin"
    export IC_ROUTE_LIST_JSON="$T/ic-route-list.json"
    local context
    context="$(cat "$INPUT_DIR/producer_receipt.json")"
    jq -n --argjson ctx "$context" '[{"context_json": ($ctx | tostring)}]' > "$IC_ROUTE_LIST_JSON"

    cat > "$IC_BIN_DIR/ic" <<'SH'
#!/usr/bin/env bash
echo "$*" >> "$IC_LOG"
if [[ "$*" == *"route list"* ]]; then
    cat "$IC_ROUTE_LIST_JSON"
elif [[ "$*" == *"route identity"* ]]; then
    for a in "$@"; do
        case "$a" in
            --model=*)
                model="${a#--model=}"
                ;;
        esac
    done
    if [[ -n "${IC_IDENTITY_OVERRIDE:-}" && "$model" == "${IC_IDENTITY_OVERRIDE_MODEL:-}" ]]; then
        printf '{"model_identity":"%s"}\n' "$IC_IDENTITY_OVERRIDE"
    else
        printf '{"model_identity":"gpt-6-astra"}\n'
    fi
elif [[ "$*" == *"route dispatch"* ]]; then
    cat "$IC_ROUTE_DISPATCH_JSON"
elif [[ "$*" == *"route record"* ]]; then
    exit 0
else
    exit 3
fi
SH
    chmod +x "$IC_BIN_DIR/ic"
    export IC_LOG="$T/ic.log"
    export PATH="$IC_BIN_DIR:$PATH"
    : > "$IC_LOG"
}

build_packet() {
    run python3 "$REPO_ROOT/scripts/build-review-packet.py" --input "$INPUT_JSON" --output-dir "$OUTPUT_DIR"
    [ "$status" -eq 0 ]
    PACKET="$output"
}

# Counts real builder invocations (--input mode only) without altering their
# behavior: a fake python3 that logs a marker then execs the real interpreter.
install_builder_spy() {
    BUILD_COUNT_FILE="$T/build-count"
    : > "$BUILD_COUNT_FILE"
    REAL_PYTHON3="$(command -v python3)"
    cat > "$T/bin/python3" <<EOF
#!/usr/bin/env bash
for a in "\$@"; do
    if [[ "\$a" == *build-review-packet.py ]]; then
        for b in "\$@"; do [[ "\$b" == "--input" ]] && echo x >> "$BUILD_COUNT_FILE"; done
        break
    fi
done
exec "$REAL_PYTHON3" "\$@"
EOF
    chmod +x "$T/bin/python3"
    export PATH="$T/bin:$PATH"
}

fake_backend() {
    # $1 = binary name (claude|codex), $2 = exit code, $3 = extra shell run first
    cat > "$T/bin/$1" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$@" > "$T/$1.argv.\$\$"
cat > "$T/$1.stdin.\$\$"
${3:-}
exit ${2:-0}
EOF
    chmod +x "$T/bin/$1"
}

@test "packet opt-in requires complete evidence before backend start" {
    review_packet_fixture_patch '.beads_file = "beads_empty.json"'
    jq '.[0].acceptance_criteria = ""' "$INPUT_DIR/beads.json" > "$INPUT_DIR/beads_empty.json"
    install_fake_ic
    fake_backend claude 0

    PATH="$T/bin:$PATH" run bash "$DISPATCH" --dry-run --role-resolved --role plan-review \
        --to claude --model gpt-6-astra --review-input "$INPUT_JSON" -C "$T/repo"
    [ "$status" -ne 0 ]
    [[ "$output" == *"failed to build review packet"* ]]
    # No backend should ever start on a build failure.
    [ -z "$(find "$T" -maxdepth 1 -name 'claude.argv.*' 2>/dev/null)" ]
}

@test "plan flag cannot bypass opted-in packet validation" {
    install_fake_ic
    build_packet

    run bash "$DISPATCH" --dry-run --role-resolved --role validation \
        --to claude --model gpt-6-astra --review-packet "$PACKET" --plan "$T/repo/f.txt" -C "$T/repo"
    [ "$status" -ne 0 ]
    [[ "$output" == *"--plan cannot be combined"* ]]
}

@test "packet reaches Claude stdin and Codex prompt exactly once" {
    install_fake_ic
    build_packet

    local route_json
    route_json="$(jq -n --arg policy "$REAL_POLICY_HASH" \
        '{policy_hash:$policy, profile_ref:"primary", profile:{backend:"claude",model:"gpt-6-astra",model_identity:"gpt-6-astra"}}')"

    fake_backend claude 0
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --role-resolved --role validation \
        --to claude --model gpt-6-astra --resolved-route-json "$route_json" \
        --review-packet "$PACKET" -C "$T/repo"
    [ "$status" -eq 0 ]
    cat "$T"/claude.stdin.* > "$T/claude_stdin.captured" 2>/dev/null
    # Claude receives the packet verbatim on stdin (no positional prompt arg),
    # and the full packet body appears exactly once -- not duplicated by the
    # reasoning-contract wrapper's own resolved-route-json echo. Command
    # substitution when assembling PROMPT strips the packet's trailing
    # newline, so compare against the packet content rstrip'd of trailing
    # newlines rather than the raw file bytes.
    [ "$(python3 -c "print(open('$T/claude_stdin.captured').read().count(open('$PACKET').read().rstrip(chr(10))))")" -eq 1 ]
    rm -f "$T"/claude.stdin.* "$T"/claude.argv.*

    route_json="$(jq -n --arg policy "$REAL_POLICY_HASH" \
        '{policy_hash:$policy, profile_ref:"primary", profile:{backend:"codex",model:"gpt-6-astra",model_identity:"gpt-6-astra"}}')"
    fake_backend codex 0
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --role-resolved --role validation \
        --to codex --model gpt-6-astra --resolved-route-json "$route_json" \
        --review-packet "$PACKET" -C "$T/repo"
    [ "$status" -eq 0 ]
    cat "$T"/codex.argv.* > "$T/codex_argv.captured" 2>/dev/null
    [ "$(python3 -c "print(open('$T/codex_argv.captured').read().count(open('$PACKET').read().rstrip(chr(10))))")" -eq 1 ]
}

@test "fallback and pool retry reuse one packet" {
    install_fake_ic
    install_builder_spy
    fake_backend codex 1 'echo "429 rate limited" >&2'
    fake_backend claude 0

    IC_ROUTE_DISPATCH_JSON="$T/route-dispatch.json"
    jq -n --arg policy "$REAL_POLICY_HASH" \
        '{policy_hash:$policy,
          profile_ref:"primary", profile:{backend:"codex",model:"gpt-6-astra",model_identity:"gpt-6-astra"},
          fallback_chain:[{profile_ref:"fallback",profile:{backend:"claude",model:"gpt-6-astra",model_identity:"gpt-6-astra"}}]}' \
        > "$IC_ROUTE_DISPATCH_JSON"
    export IC_ROUTE_DISPATCH_JSON

    PATH="$T/bin:$PATH" run bash "$DISPATCH" --role plan-review \
        --producer-identity gpt-6-astra --review-input "$INPUT_JSON" -C "$T/repo" -o "$T/out.md"
    [ "$status" -eq 0 ]

    # Built exactly once (from --review-input), never rebuilt across candidates.
    [ "$(wc -l < "$BUILD_COUNT_FILE" | tr -d ' ')" -eq 1 ]
    codex_argv="$(cat "$T"/codex.argv.* 2>/dev/null)"
    claude_stdin="$(cat "$T"/claude.stdin.* 2>/dev/null)"
    packet_path="$(find "$T/repo/.clavain/review-packets" -name packet.md)"
    [ -f "$packet_path" ]
    packet_content="$(cat "$packet_path")"
    # A role-resolved dispatch wraps PROMPT in the mandatory reasoning
    # contract, so match the packet content as a substring, not the whole
    # payload -- both candidates still carry the identical, unrebuilt packet.
    [[ "$codex_argv" == *"$packet_content"* ]]
    [[ "$claude_stdin" == *"$packet_content"* ]]
}

@test "producer flag mismatch fails before resolution" {
    install_fake_ic
    build_packet
    export IC_IDENTITY_OVERRIDE="claude-opus-5-5"
    export IC_IDENTITY_OVERRIDE_MODEL="claude-opus-5-5"

    run bash "$DISPATCH" --dry-run --role validation \
        --producer-identity claude-opus-5-5 --review-packet "$PACKET" -C "$T/repo"
    [ "$status" -ne 0 ]
    [[ "$output" == *"does not match the review packet's producer"* ]]
    # Resolution (route dispatch) must never have been attempted.
    ! grep -q "route dispatch" "$IC_LOG"
}

@test "resolved child verifies packet without rebuilding" {
    install_fake_ic
    build_packet
    install_builder_spy

    PATH="$T/bin:$PATH" run bash "$DISPATCH" --dry-run --role-resolved --role validation \
        --to claude --model gpt-6-astra --review-packet "$PACKET" -C "$T/repo"
    [ "$status" -eq 0 ]
    [ ! -s "$BUILD_COUNT_FILE" ]
    grep -q "route identity" "$IC_LOG"
}

@test "context gateway cannot expand review evidence" {
    install_fake_ic
    build_packet
    # Spy-count invocations rather than grep dry-run's truncated preview: a
    # role-resolved dispatch wraps PROMPT in a multi-KB reasoning contract, so
    # a small marker appended near the end never appears in the 200-byte
    # preview regardless of whether the gateway ran.
    GATEWAY_COUNT_FILE="$T/gateway-count"
    : > "$GATEWAY_COUNT_FILE"
    cat > "$T/bin/gateway.py" <<EOF
#!/usr/bin/env python3
import sys
sys.stdin.read()
open("$GATEWAY_COUNT_FILE", "a").write("x\n")
print("GATEWAY-MUTATED")
EOF
    chmod +x "$T/bin/gateway.py"
    export CLAVAIN_CONTEXT_GATEWAY_BIN="$T/bin/gateway.py"
    export CLAVAIN_CONTEXT_GATEWAY_MODE=on

    run bash "$DISPATCH" --dry-run --role-resolved --role validation \
        --to claude --model gpt-6-astra --review-packet "$PACKET" -C "$T/repo"
    [ "$status" -eq 0 ]
    [ ! -s "$GATEWAY_COUNT_FILE" ]

    # Control: the same gateway DOES run for an ordinary (non-packet) prompt.
    run bash "$DISPATCH" --dry-run --role-resolved --role validation \
        --to claude --model gpt-6-astra -C "$T/repo" "ordinary prompt"
    [ "$status" -eq 0 ]
    [ -s "$GATEWAY_COUNT_FILE" ]
}

@test "audit records bind each attempt to the packet" {
    install_fake_ic
    build_packet
    manifest_path="$(dirname "$PACKET")/manifest.json"
    packet_id="$(jq -r '.packet_id' "$manifest_path")"
    packet_sha="$(jq -r '.packet_sha256' "$manifest_path")"

    load "$BATS_TEST_DIRNAME/../../scripts/lib-dispatch-audit.sh" 2>/dev/null || \
        source "$REPO_ROOT/scripts/lib-dispatch-audit.sh"
    REVIEW_PACKET="$PACKET"
    REVIEW_PACKET_JSON="$(cat "$manifest_path")"
    ROLE=validation; ROLE_RESOLVED=true; ENGINE=claude; MODEL=gpt-6-astra
    REASONING_EFFORT=""; SERVICE_TIER=""; SANDBOX=""
    DISPATCH_ID=d1; ATTEMPT_ID=a1; WORKDIR="$T/repo"; OUTPUT=""
    DISPATCH_SESSION_ID=""; CLAVAIN_RUN_ID=""; CLAVAIN_BEAD_ID=""; CLAVAIN_BEAD_SOURCE="none"
    RESOLVED_PROFILE_REF="p1"; CHECKOUT_BEFORE=""

    ctx="$(_role_audit_context started 0 "")"
    [ "$(jq -r '.review_packet.packet_id' <<< "$ctx")" = "$packet_id" ]
    [ "$(jq -r '.review_packet.sha256' <<< "$ctx")" = "$packet_sha" ]
    [ "$(jq -r '.review_packet.path' <<< "$ctx")" = "$PACKET" ]
}

@test "review roles without packet flags retain their existing argv and prompt behavior" {
    install_fake_ic
    printf 'unchanged prompt\n' > "$T/prompt.md"
    fake_backend claude 0
    local route_json
    route_json="$(jq -n --arg policy "$REAL_POLICY_HASH" \
        '{policy_hash:$policy, profile_ref:"primary", profile:{backend:"claude",model:"gpt-6-astra",model_identity:"gpt-6-astra"}}')"
    # Real (non-dry) run: a role-resolved dispatch wraps PROMPT in a multi-KB
    # reasoning contract, so a dry-run's truncated preview can't be trusted to
    # surface a marker placed at the end of the assembled prompt.
    PATH="$T/bin:$PATH" run bash "$DISPATCH" --role-resolved --role validation \
        --to claude --model gpt-6-astra --resolved-route-json "$route_json" \
        --plan "$T/repo/f.txt" --prompt-file "$T/prompt.md" -C "$T/repo"
    [ "$status" -eq 0 ]
    claude_argv="$(cat "$T"/claude.argv.* 2>/dev/null)"
    claude_stdin="$(cat "$T"/claude.stdin.* 2>/dev/null)"
    [[ "$claude_stdin" == *"unchanged prompt"* ]]
    # fake_backend logs argv one element per line, so --add-dir and its value
    # land on separate lines, not space-joined.
    [[ "$claude_argv" == *$'--add-dir\n'"$T/repo"* ]]
}

@test "nonreview plan behavior is unchanged" {
    run bash "$DISPATCH" --dry-run --to claude --model m --plan "$T/repo/f.txt" -C "$T/repo" "a plain prompt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"a plain prompt"* ]]
    [[ "$output" == *"--add-dir $T/repo"* ]]
}
