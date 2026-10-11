#!/usr/bin/env bats
# Readers must accept the shapes the real ic emits. The fixtures under
# tests/fixtures/ic are captured ic output; ic's emitter is the contract.

setup() {
    HOOKS_DIR="$BATS_TEST_DIRNAME/../../hooks"
    FIXTURES="$BATS_TEST_DIRNAME/../fixtures/ic"
    export FIXTURES
    # Fake ic on PATH that answers `lane status` from a fixture.
    FAKE_BIN="$BATS_TEST_TMPDIR/bin"
    mkdir -p "$FAKE_BIN"
    cat > "$FAKE_BIN/ic" <<'IC'
#!/usr/bin/env bash
if [[ "$1 $2" == "lane status" ]]; then cat "${LANE_FIXTURE:?}"; else exit 1; fi
IC
    chmod +x "$FAKE_BIN/ic"
    PATH="$FAKE_BIN:$PATH"
    export PATH
    # shellcheck source=/dev/null
    source "$HOOKS_DIR/lib-dispatch.sh"
}

@test "lane metadata emitted as a JSON string: unpaused lane reports nothing" {
    export LANE_FIXTURE="$FIXTURES/lane-status.json"
    run _dispatch_lane_paused fxlane
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "lane metadata emitted as a JSON string: paused lane is detected" {
    # ic's CLI cannot set lane metadata; take the captured real shape and set
    # the string-encoded metadata the emitter would produce for a paused lane.
    export LANE_FIXTURE="$BATS_TEST_TMPDIR/lane-paused.json"
    jq -c '.metadata = ({paused: true} | tojson)' "$FIXTURES/lane-status.json" > "$LANE_FIXTURE"
    jq -e '.metadata | type == "string"' "$LANE_FIXTURE" >/dev/null
    run _dispatch_lane_paused fxlane
    [ "$status" -eq 0 ]
    [ "$output" = "true" ]
}

@test "lane metadata emitted as an object is also detected" {
    export LANE_FIXTURE="$BATS_TEST_TMPDIR/lane-obj.json"
    jq -c '.metadata = {paused: true}' "$FIXTURES/lane-status.json" > "$LANE_FIXTURE"
    run _dispatch_lane_paused fxlane
    [ "$output" = "true" ]
}
