#!/usr/bin/env bats
# mk-8m26b: when ic cannot record a routing decision (for example a temporary
# -C workdir with no database), the terminal_recording message keeps a bounded,
# redacted, single-line excerpt of ic's stderr instead of discarding it. Only
# dummy values are used.

setup() {
    ROOT="$BATS_TEST_DIRNAME/../.."
    T="$(mktemp -d)"
    mkdir -p "$T/bin" "$T/work"
    cat > "$T/bin/ic" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$FAKE_IC_STDERR" >&2
exit 1
SH
    chmod +x "$T/bin/ic"
    cat > "$T/run.sh" <<SH
set -u
DISPATCH_SCRIPT_DIR="$ROOT/scripts"
source "$ROOT/scripts/lib-dispatch-audit.sh"
source <(sed -n '/^_redact_provider_text() {/,/^}/p' "$ROOT/scripts/dispatch.sh")
_prepare_role_audit() { return 0; }
_role_audit_context() { printf '{}'; }
ROLE=r RESOLVED_PROFILE_REF=p ROLE_RESOLVED=true MODEL=m NAME=n FALLBACK_REASON= WORKDIR="$T/work"
DISPATCH_ID=d DISPATCH_SESSION_ID= PRODUCER_IDENTITY= VALIDATOR_RELATIONSHIP=
_record_role_routing_decision 1 terminal_recording terminal
SH
}
teardown() { rm -rf "$T"; }

@test "ic stderr reason appears, redacted, in the terminal_recording message" {
    LEAK=leaky-dummy-text
    export FAKE_IC_STDERR="route record failed: unable to open database file (14) $LEAK"
    run env PATH="$T/bin:$PATH" bash "$T/run.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"cannot persist terminal routing decision"* ]]
    [[ "$output" == *"ic: "*"unable to open"*"file (14)"* ]]
    [[ "$output" != *"$LEAK"* ]]
    [ "$(printf '%s\n' "$output" | wc -l)" -eq 1 ]
}

@test "excerpt is a single bounded line even for long multi-line stderr" {
    export FAKE_IC_STDERR="$(printf 'line one\nline two\n%0400d' 0)"
    run env PATH="$T/bin:$PATH" bash "$T/run.sh"
    [ "$status" -eq 1 ]
    [ "$(printf '%s\n' "$output" | wc -l)" -eq 1 ]
    [[ "$output" == *"ic: "* ]]
    [ "${#output}" -lt 400 ]
}

@test "message stays the same shape when ic prints nothing" {
    export FAKE_IC_STDERR=''
    run env PATH="$T/bin:$PATH" bash "$T/run.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"cannot persist terminal routing decision for 'r/p'"* ]]
}

@test "redaction runs before truncation: a long token past the old cut is not left as a 40-hex prefix" {
    HEX=$(printf 'abcdef0123%.0s' 1 2 3 4 5 6 7 8)
    export FAKE_IC_STDERR="$(printf '%960s' '')$HEX"
    run env PATH="$T/bin:$PATH" bash "$T/run.sh"
    [ "$status" -eq 1 ]
    ! [[ "$output" =~ [0-9a-f]{40} ]]
}

@test "long token-like runs (bare hex, base64-like) are replaced, alone and in a sentence" {
    H40=$(printf 'a1b2c3d4e5%.0s' 1 2 3 4)
    H64=$(printf '0f1e2d3c%.0s' 1 2 3 4 5 6 7 8)
    B32=$(printf 'Zm9vYmFy+/Zm9vYmFy%.0s' 1 2)
    B32="${B32:0:32}"
    for V in "$H40" "$H64" "$B32"; do
        for MSG in "$V" "token was $V here, retry"; do
            export FAKE_IC_STDERR="unable to open database
$MSG"
            run env PATH="$T/bin:$PATH" bash "$T/run.sh"
            [ "$status" -eq 1 ]
            [[ "$output" != *"$V"* ]]
            for ((i = 0; i + 20 <= ${#V}; i++)); do
                [[ "$output" != *"${V:i:20}"* ]]
            done
        done
    done
}

@test "control: ordinary diagnostic words still appear after the long-run pass" {
    export FAKE_IC_STDERR="route record failed: unable to open database file (14)"
    run env PATH="$T/bin:$PATH" bash "$T/run.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"ic: "*"unable to open"*"file (14)"* ]]
}
