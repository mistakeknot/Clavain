#!/usr/bin/env bats

# Regression for the audit recording gap (Sylveste-ymp2 stage B, goal 14539da7).
#
# bead-close.sh passes --vetted-sha to `policy check`, and `policy record-signed`
# has always accepted --vetted-sha, but gate_record_signed never forwarded it.
# Every signed row therefore stored an empty vetted_sha while the evaluator had
# a real one: 20 of 20 rows on zklw, which reads as a fail-open and is not one.
# The audit trail is the estate's record of what authority was used, so this is
# the field that makes a close auditable at all.

setup() {
    load test_helper
    COMMON="$BATS_TEST_DIRNAME/../../scripts/gates/_common.sh"
    TMPDIR_T="$(mktemp -d)"
    ARGV_LOG="$TMPDIR_T/argv.txt"

    # Fake clavain-cli: record the argv it is handed, answer the shape the
    # caller validates with jq.
    mkdir -p "$TMPDIR_T/bin"
    cat > "$TMPDIR_T/bin/clavain-cli" <<FAKE
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$ARGV_LOG"
printf '{"status":"ok","signed":1,"id":"rec-1"}'
FAKE
    chmod +x "$TMPDIR_T/bin/clavain-cli"
    PATH="$TMPDIR_T/bin:$PATH"
    export PATH
    export CLAVAIN_AUTHZ_PROJECT_ROOT="$TMPDIR_T"
}

teardown() { rm -rf "$TMPDIR_T"; }

record_with() {
    # shellcheck disable=SC1090
    ( set -euo pipefail
      export CLAVAIN_VETTED_SHA="$1"
      source "$COMMON"
      gate_record_signed bead-close some-target Sylveste-ymp2 >/dev/null 2>&1 )
}

@test "a set vetted SHA reaches the signed record" {
    record_with "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    run cat "$ARGV_LOG"
    [[ "$output" == *"--vetted-sha=deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"* ]]
    [[ "$output" == *"--op=bead-close"* ]]
}

@test "[negative control] an unset vetted SHA adds no empty flag" {
    record_with ""
    run cat "$ARGV_LOG"
    [[ "$output" != *"--vetted-sha="* ]]
    [[ "$output" == *"--op=bead-close"* ]]
}

@test "the recorder still accepts the flag it is being handed" {
    # If policy record-signed ever drops --vetted-sha from its strict parser,
    # this forwarding turns every signed record into a hard failure. Pin it.
    grep -q 'parseAuthzArgsStrict("policy record-signed".*"vetted-sha"' \
        "$BATS_TEST_DIRNAME/../../cmd/clavain-cli/authz_sign.go"
}
