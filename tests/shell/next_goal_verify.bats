#!/usr/bin/env bats
# Tests for scripts/next-goal-verify.sh
#
# The load-bearing case is "bead does not exist". `bd show <missing> --json`
# EXITS 0 and prints {"error": ...}, so a gate that trusted $? would clear
# exactly the fabricated IDs it exists to catch. That is asserted below rather
# than assumed.

setup() {
    load test_helper
    SCRIPT="$BATS_TEST_DIRNAME/../../scripts/next-goal-verify.sh"
    STUB_DIR="$(mktemp -d)"
    WORK_DIR="$(mktemp -d)"
    RECEIPTS="$(mktemp -d)"
    mkdir -p "$WORK_DIR/.beads"
    export PATH="$STUB_DIR:$PATH"
    export CLAVAIN_NEXT_GOAL_ROOTS="$WORK_DIR"
    export CLAVAIN_VERIFY_DIR="$RECEIPTS"
    export CLAUDE_SESSION_ID="test-session"
}

teardown() {
    rm -rf "$STUB_DIR" "$WORK_DIR" "$RECEIPTS"
}

# $1 = the JSON `bd show` should print for ANY id
make_bd_stub() {
    cat > "$STUB_DIR/bd" <<EOF
#!/usr/bin/env bash
if [[ "\$1" == "show" ]]; then cat <<'JSON'
$1
JSON
exit 0
fi
exit 0
EOF
    chmod +x "$STUB_DIR/bd"
}

bead_json() {
    # $1 = status, $2 = extra fields (optional)
    printf '[{"id":"x-1","title":"t","status":"%s","issue_type":"task","priority":2%s}]' \
        "$1" "${2:-}"
}

@test "an open bead is usable" {
    make_bd_stub "$(bead_json open)"
    run bash "$SCRIPT" x-1
    [ "$status" -eq 0 ]
    [ "$(jq -r '.ok' <<<"$output")" = "true" ]
    [ "$(jq -r '.beads[0].verdict' <<<"$output")" = "ok" ]
}

@test "a CLOSED bead is disqualified — the 2026-08-14 failure" {
    make_bd_stub "$(bead_json closed ',"closed_at":"2026-07-26T01:53:08Z"')"
    run bash "$SCRIPT" x-1
    [ "$status" -eq 3 ]
    [ "$(jq -r '.ok' <<<"$output")" = "false" ]
    [ "$(jq -r '.beads[0].verdict' <<<"$output")" = "disqualified" ]
    [[ "$(jq -r '.beads[0].reason' <<<"$output")" == *"already closed"* ]]
    [ "$(jq -r '.disqualified[0]' <<<"$output")" = "x-1" ]
}

@test "a missing bead is disqualified even though bd exits 0" {
    # bd's own behaviour, reproduced: error payload, zero exit status.
    make_bd_stub '{"error":"no issues found matching the provided IDs","schema_version":1}'
    run bash "$SCRIPT" x-1
    [ "$status" -eq 3 ]
    [ "$(jq -r '.beads[0].verdict' <<<"$output")" = "disqualified" ]
    [[ "$(jq -r '.beads[0].reason' <<<"$output")" == *"no such bead"* ]]
}

@test "a deferred bead is disqualified, not merely flagged" {
    make_bd_stub "$(bead_json deferred)"
    run bash "$SCRIPT" x-1
    [ "$status" -eq 3 ]
    [ "$(jq -r '.beads[0].verdict' <<<"$output")" = "disqualified" ]
}

@test "an in_progress bead warns but does not disqualify" {
    make_bd_stub "$(bead_json in_progress)"
    run bash "$SCRIPT" x-1
    [ "$status" -eq 0 ]
    [ "$(jq -r '.ok' <<<"$output")" = "true" ]
    [ "$(jq -r '.beads[0].verdict' <<<"$output")" = "warn" ]
    [ "$(jq -r '.warnings[0]' <<<"$output")" = "x-1" ]
}

@test "an existing path disqualifies a build-it candidate" {
    make_bd_stub "$(bead_json open)"
    mkdir -p "$WORK_DIR/already-here"
    touch "$WORK_DIR/already-here/Component.tsx"
    run bash "$SCRIPT" --path "$WORK_DIR/already-here" x-1
    [ "$status" -eq 3 ]
    [ "$(jq -r '.paths[0].exists' <<<"$output")" = "true" ]
    [ "$(jq -r '.paths[0].verdict' <<<"$output")" = "disqualified" ]
}

@test "an absent path is the case where there is something to build" {
    make_bd_stub "$(bead_json open)"
    run bash "$SCRIPT" --path "$WORK_DIR/not-there" x-1
    [ "$status" -eq 0 ]
    [ "$(jq -r '.paths[0].verdict' <<<"$output")" = "ok" ]
}

@test "missing bd fails OPEN but reports ok:null, never true" {
    # An unrun check is not a passed one. If this ever returns ok:true the
    # caller cannot distinguish "verified" from "could not verify".
    #
    # Unavailability is provoked by REMOVING THE TRACKER, not by hiding a
    # binary. Two earlier attempts hid bd via PATH and both tested the host
    # rather than the script: `PATH=/usr/bin:/bin` is bd-free only where bd is
    # not installed there, and a hand-built PATH still lost to a `bd` resolved
    # from the environment. Pointing at a root with no .beads is hermetic
    # everywhere, and it exercises the same contract.
    make_bd_stub "$(bead_json open)"
    CLAVAIN_NEXT_GOAL_ROOTS="$WORK_DIR/no-tracker-here" run bash "$SCRIPT" x-1
    [ "$status" -eq 0 ]
    [ "$(jq -r '.available' <<<"$output")" = "false" ]
    [ "$(jq -r '.ok' <<<"$output")" = "null" ]
}

@test "no reachable root must NOT disqualify — could-not-look is not not-there" {
    # The defect this whole gate exists to prevent, found in the gate itself:
    # with no root reachable every id fell through to "no such bead in any
    # reachable tracker" and the run exited 3, condemning live candidates on
    # the strength of never having looked at them.
    make_bd_stub "$(bead_json open)"
    CLAVAIN_NEXT_GOAL_ROOTS="$WORK_DIR/no-tracker-here" run bash "$SCRIPT" x-1
    [ "$status" -ne 3 ]
    [ "$(jq -r '.disqualified | length' <<<"$output")" = "0" ]
    [[ "$(jq -r '.reason' <<<"$output")" == *"no bead root reachable"* ]]
}

@test "paths are still answerable with no tracker — they never needed bd" {
    mkdir -p "$WORK_DIR/present"
    CLAVAIN_NEXT_GOAL_ROOTS="$WORK_DIR/no-tracker-here" run bash "$SCRIPT" --path "$WORK_DIR/present"
    [ "$status" -eq 3 ]
    [ "$(jq -r '.paths[0].verdict' <<<"$output")" = "disqualified" ]
}

@test "with CLAUDE_SESSION_ID unset the receipt is keyed on CLAUDE_CODE_SESSION_ID" {
    make_bd_stub "$(bead_json open)"
    unset CLAUDE_SESSION_ID
    CLAUDE_CODE_SESSION_ID="alt-session" run bash "$SCRIPT" x-1
    [ "$status" -eq 0 ]
    [ -f "$RECEIPTS/alt-session.json" ]
    [ ! -f "$RECEIPTS/unknown.json" ]
}

@test "CLAUDE_SESSION_ID wins when both are set" {
    # session-start.sh writes it from the hook's own stdin when it runs, which
    # is the more authoritative register; the Bash tool's export is the fallback.
    make_bd_stub "$(bead_json open)"
    CLAUDE_CODE_SESSION_ID="alt-session" run bash "$SCRIPT" x-1
    [ -f "$RECEIPTS/test-session.json" ]
    [ ! -f "$RECEIPTS/alt-session.json" ]
}

@test "a receipt is left for the session, keyed by session id" {
    make_bd_stub "$(bead_json closed)"
    run bash "$SCRIPT" x-1
    [ -f "$RECEIPTS/test-session.json" ]
    [ "$(jq -r '.schema_version' "$RECEIPTS/test-session.json")" = "clavain.next-goal-verify/v1" ]
    [ "$(jq -r '.ok' "$RECEIPTS/test-session.json")" = "false" ]
}

@test "verdicts are per-candidate, so one bad ID does not clear the rest" {
    # Guards the shape of the whole gate: a block citing four candidates must
    # get four independent answers, not one aggregate verdict.
    cat > "$STUB_DIR/bd" <<'EOF'
#!/usr/bin/env bash
if [[ "$1" == "show" ]]; then
  case "$2" in
    good-1) echo '[{"id":"good-1","title":"t","status":"open","issue_type":"task","priority":2}]' ;;
    dead-1) echo '[{"id":"dead-1","title":"t","status":"closed","issue_type":"task","priority":2}]' ;;
    *)      echo '{"error":"no issues found matching the provided IDs","schema_version":1}' ;;
  esac
fi
exit 0
EOF
    chmod +x "$STUB_DIR/bd"
    run bash "$SCRIPT" good-1 dead-1 ghost-1
    [ "$status" -eq 3 ]
    [ "$(jq -r '.beads | length' <<<"$output")" = "3" ]
    [ "$(jq -r '.beads[] | select(.id=="good-1") | .verdict' <<<"$output")" = "ok" ]
    [ "$(jq -r '.beads[] | select(.id=="dead-1") | .verdict' <<<"$output")" = "disqualified" ]
    [ "$(jq -r '.beads[] | select(.id=="ghost-1") | .verdict' <<<"$output")" = "disqualified" ]
    [ "$(jq -r '.disqualified | length' <<<"$output")" = "2" ]
}
