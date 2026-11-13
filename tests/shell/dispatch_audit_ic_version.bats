#!/usr/bin/env bats
# The audit caller and the dispatch helper share an output-variable contract.
setup() {
    ROOT="$BATS_TEST_DIRNAME/../.."
    T="$(mktemp -d)"
    mkdir -p "$T/bin"
    printf '#!/bin/bash\nprintf "ic fixture-version\\n"\n' > "$T/bin/ic"
    chmod +x "$T/bin/ic"
    export PATH="$T/bin:$PATH"
    source "$ROOT/scripts/lib-dispatch-audit.sh"
    source <(sed -n '/^_dispatch_ic_version() {/,/^}/p' "$ROOT/scripts/dispatch.sh")
    _routing_call() { local destination="$1"; shift; printf -v "$destination" '%s' "$("$@")"; }
    _augment_dispatch_receipt() { cat; }
    ENGINE=claude MODEL=fixture REASONING_EFFORT=high SERVICE_TIER=standard
    SANDBOX=read-only DISPATCH_ID=fixture-dispatch ATTEMPT_ID=fixture-attempt
    DISPATCH_SESSION_ID=fixture-session CHECKOUT_BEFORE= OUTPUT="$T/absent"
    WORKDIR="$T" DISPATCH_RESULT_READY=false
}
teardown() { rm -rf "$T"; }

@test "every review-role audit records the output-variable helper version" {
    for ROLE in plan-review validation cross-lab-review; do
        run _role_audit_context started 0 ''
        [ "$status" -eq 0 ]
        [ "$(jq -r .ic_version <<< "$output")" = 'ic fixture-version' ]
    done
}

@test "non-review audit does not query the review version helper" {
    ROLE=routine-execution
    _dispatch_ic_version() { return 99; }
    run _role_audit_context started 0 ''
    [ "$status" -eq 0 ]
    [ "$(jq -r .ic_version <<< "$output")" = null ]
}
