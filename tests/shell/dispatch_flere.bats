#!/usr/bin/env bats

setup() {
    DISPATCH_SCRIPT="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    TMPDIR_T="$(mktemp -d)"
    mkdir -p "$TMPDIR_T/project" "$TMPDIR_T/profile"
    printf '{}\n' > "$TMPDIR_T/profile/models.json"
    export CLAVAIN_CONTEXT_GATEWAY_MODE=off
    export CLAVAIN_FLERE_BIN=/usr/bin/true
    export CLAVAIN_FLERE_PROFILE="$TMPDIR_T/profile"
    export IC_DISPATCH_ID=fixture-dispatch IC_RUN_ID=fixture-run IC_PROMPT_HASH=fixture
}

teardown() { rm -rf "$TMPDIR_T"; }

@test "flere: explicit provider/model and admitted identity reach the fixed supervisor" {
    run bash "$DISPATCH_SCRIPT" --to flere --dry-run -C "$TMPDIR_T/project" -o "$TMPDIR_T/out" -m provider/model/with/slash "inspect files"
    [ "$status" -eq 0 ]
    [[ "$output" == *'"backend": "flere"'* ]]
    [[ "$output" == *'"model": "model/with/slash"'* ]]
    [[ "$output" == *'"dispatch_id": "fixture-dispatch"'* ]]
}

@test "flere: fixed policy rejects routing, mutable sandbox, and extra arguments" {
    for option in "--tier deep" "--role reviewer" "--via zaka" "-s workspace-write" "--extension evil"; do
        read -r -a parts <<< "$option"
        run bash "$DISPATCH_SCRIPT" --to flere --dry-run -C "$TMPDIR_T/project" -o "$TMPDIR_T/out" -m provider/model "${parts[@]}" "inspect"
        [ "$status" -ne 0 ]
    done
}

@test "flere: missing admission cannot silently fall back to another backend" {
    unset IC_RUN_ID
    run bash "$DISPATCH_SCRIPT" --to flere --dry-run -C "$TMPDIR_T/project" -o "$TMPDIR_T/out" -m provider/model "inspect"
    [ "$status" -ne 0 ]
    [[ "$output" == *"Intercore-admitted run and dispatch"* ]]
}
