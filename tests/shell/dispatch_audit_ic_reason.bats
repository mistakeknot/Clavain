#!/usr/bin/env bats
# mk-8m26b: when ic cannot record a routing decision (for example a temporary
# -C workdir with no database), the recording message names one of three fixed
# reasons chosen from ic's stderr; no byte of that stderr reaches the message.
# Only dummy values are used.

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

@test "ic stderr never reaches the message: dummy 8-digit, 40-hex, 64-hex and PEM bytes" {
    H40=$(printf 'a1b2c3d4e5%.0s' 1 2 3 4)
    H64=$(printf '0f1e2d3c%.0s' 1 2 3 4 5 6 7 8)
    # PEM armor lines are built at run time so the source holds no key-shaped literal.
    PEM_BEGIN=$(printf -- '-----BEGIN %s-----' 'PRIVATE KEY')
    PEM_END=$(printf -- '-----END %s-----' 'PRIVATE KEY')
    export FAKE_IC_STDERR="unable to open database file (14) 12345678
$H40
$H64
$PEM_BEGIN
DUMMYPEMBODYLINE
$PEM_END
extra-dummy-words"
    run env PATH="$T/bin:$PATH" bash "$T/run.sh"
    [ "$status" -eq 1 ]
    [ "$output" = "Error: cannot persist terminal routing decision for 'r/p': ic: database could not be opened" ]
    [[ "$output" != *12345678* ]]
    [[ "$output" != *"$H40"* ]]
    [[ "$output" != *"$H64"* ]]
    [[ "$output" != *"PRIVATE"* ]]
    [[ "$output" != *DUMMYPEMBODYLINE* ]]
    [[ "$output" != *"extra-dummy-words"* ]]
    [[ "$output" != *"(14)"* ]]
}

@test "open failure is classified as: database could not be opened" {
    export FAKE_IC_STDERR="Unable To Open Database File"
    run env PATH="$T/bin:$PATH" bash "$T/run.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"cannot persist terminal routing decision for 'r/p': ic: database could not be opened" ]]
}

@test "lock or busy is classified as: database locked" {
    export FAKE_IC_STDERR="Error: DATABASE IS LOCKED"
    run env PATH="$T/bin:$PATH" bash "$T/run.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"ic: database locked" ]]
    export FAKE_IC_STDERR="the database is busy"
    run env PATH="$T/bin:$PATH" bash "$T/run.sh"
    [[ "$output" == *"ic: database locked" ]]
}

@test "anything else is classified as: ic failed; stderr withheld" {
    export FAKE_IC_STDERR="surprising-dummy-failure 12345678"
    run env PATH="$T/bin:$PATH" bash "$T/run.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"ic: ic failed; stderr withheld" ]]
    [[ "$output" != *surprising* ]]
    export FAKE_IC_STDERR=''
    run env PATH="$T/bin:$PATH" bash "$T/run.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"ic: ic failed; stderr withheld" ]]
}

@test "a large multiline capture prints no broken-pipe or write-error text" {
    cat > "$T/bin/ic" <<'SH'
#!/usr/bin/env bash
seq 1 50000 >&2
exit 1
SH
    run env PATH="$T/bin:$PATH" bash "$T/run.sh"
    [ "$status" -eq 1 ]
    [[ "$output" != *"Broken pipe"* ]]
    [[ "$output" != *"write error"* ]]
    [ "$(printf '%s\n' "$output" | wc -l)" -eq 1 ]
    [[ "$output" == *"ic: ic failed; stderr withheld" ]]
}
