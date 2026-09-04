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

# Lineage fixtures. $1 = c2's status (open|closed); $2 = "labeled" or
# "unlabeled": whether g2 has beads carrying ic_goal_id:g2, the second way a
# goal joins a lineage. E1, E5, E9 are top-level epics; M1 sits under E1; c1
# under M1 (a two-step walk); c2 under E9; c3 directly under E1; b21 and b22
# are g2's closed work under E1. Answers `show <id>` per id and
# `list --label <l>` per label, like the real bd.
make_lineage_bd_stub() {
    local c2_status="${1:-open}" g2_list='[]'
    if [[ "${2:-labeled}" == "labeled" ]]; then
        g2_list='[{"id":"b21","status":"closed","parent":"E1"},{"id":"b22","status":"closed","parent":"E1"}]'
    fi
    cat > "$STUB_DIR/bd" <<EOF
#!/usr/bin/env bash
if [[ "\$1" == "show" ]]; then
  case "\$2" in
    E1)  echo '[{"id":"E1","title":"epic one","status":"open","issue_type":"epic","priority":1,"parent":null,"labels":[]}]' ;;
    E5)  echo '[{"id":"E5","title":"epic five","status":"open","issue_type":"epic","priority":1,"parent":null,"labels":[]}]' ;;
    E9)  echo '[{"id":"E9","title":"epic nine","status":"open","issue_type":"epic","priority":1,"parent":null,"labels":[]}]' ;;
    M1)  echo '[{"id":"M1","title":"middle","status":"open","issue_type":"feature","priority":2,"parent":"E1","labels":[]}]' ;;
    c1)  echo '[{"id":"c1","title":"cand one","status":"open","issue_type":"task","priority":2,"parent":"M1","labels":[]}]' ;;
    c2)  echo '[{"id":"c2","title":"cand two","status":"${c2_status}","issue_type":"task","priority":2,"parent":"E9","labels":[]}]' ;;
    c3)  echo '[{"id":"c3","title":"cand three","status":"open","issue_type":"task","priority":2,"parent":"E1","labels":[]}]' ;;
    b21) echo '[{"id":"b21","title":"g2 work","status":"closed","issue_type":"task","priority":2,"parent":"E1","labels":["ic_goal_id:g2"]}]' ;;
    b22) echo '[{"id":"b22","title":"g2 work","status":"closed","issue_type":"task","priority":2,"parent":"E1","labels":["ic_goal_id:g2"]}]' ;;
    *)   echo '{"error":"no issues found matching the provided IDs","schema_version":1}' ;;
  esac
  exit 0
fi
if [[ "\$1" == "list" && "\$2" == "--label" ]]; then
  case "\$3" in
    ic_goal_id:g2) echo '${g2_list}' ;;
    *)             echo '[]' ;;
  esac
  exit 0
fi
exit 0
EOF
    chmod +x "$STUB_DIR/bd"
}

# $1 = g1's BeadID as a JSON literal ('"E1"' or 'null'). Goals, newest first:
# g1, g2 (BeadID null, so it joins a lineage only through labeled beads), g3
# (epic E5, a different lineage). g0 is still open and must be ignored.
make_ic_stub() {
    local g1_bead="${1:-\"E1\"}"
    cat > "$STUB_DIR/ic" <<EOF
#!/usr/bin/env bash
if [[ "\$1" == "goal" && "\$2" == "list" ]]; then
  echo '[{"ID":"g0","Status":"open","ClosedAt":0,"BeadID":null,"SuccessorRef":"","Title":"still open"},
         {"ID":"g3","Status":"closed","ClosedAt":1788000100,"BeadID":"E5","SuccessorRef":"","Title":"third"},
         {"ID":"g1","Status":"closed","ClosedAt":1788000300,"BeadID":${g1_bead},"SuccessorRef":"g2","Title":"first"},
         {"ID":"g2","Status":"closed","ClosedAt":1788000200,"BeadID":null,"SuccessorRef":"","Title":"second"}]'
  exit 0
fi
exit 1
EOF
    chmod +x "$STUB_DIR/ic"
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

@test "a receipt is left for the session, keyed by session id" {
    make_bd_stub "$(bead_json closed)"
    run bash "$SCRIPT" x-1
    [ -f "$RECEIPTS/test-session.json" ]
    [ "$(jq -r '.schema_version' "$RECEIPTS/test-session.json")" = "clavain.next-goal-verify/v3" ]
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

# ------------------------------------------------------------------- lineage
#
# The 2026-09-03 failure: three consecutive goals under one epic each named the
# next as successor, and the fourth recommendation passed every check above.
# The window here is g1 (BeadID E1), g2 (labeled beads under E1), g3 (E5).
# c1's chain is c1 -> M1 -> E1, so it continues the g1/g2 lineage.

@test "lineage: a recommendation that continues the streak is refused" {
    make_lineage_bd_stub open labeled
    make_ic_stub '"E1"'
    run bash "$SCRIPT" --recommend c1
    [ "$status" -eq 3 ]
    [ "$(jq -r '.ok' <<<"$output")" = "false" ]
    [ "$(jq -r '.lineage.available' <<<"$output")" = "true" ]
    [ "$(jq -r '.lineage.verdict' <<<"$output")" = "disqualified" ]
    [ "$(jq -r '.beads[] | select(.id=="c1") | .verdict' <<<"$output")" = "disqualified" ]
    reason="$(jq -r '.beads[] | select(.id=="c1") | .reason' <<<"$output")"
    [[ "$reason" == *"g1"* && "$reason" == *"g2"* && "$reason" == *"E1"* ]]
    [ "$(jq -r '.disqualified[0]' <<<"$output")" = "c1" ]
    [ "$(jq -r '.lineage.candidates[] | select(.id=="c1") | .root_epic' <<<"$output")" = "E1" ]
    [ "$(jq -r '.lineage.candidates[] | select(.id=="c1") | .streak | length' <<<"$output")" = "2" ]
}

@test "lineage: --beat naming an open out-of-lineage candidate allows it, as a warning" {
    make_lineage_bd_stub open labeled
    make_ic_stub '"E1"'
    run bash "$SCRIPT" --recommend c1 --beat c2 c1 c2
    [ "$status" -eq 0 ]
    [ "$(jq -r '.ok' <<<"$output")" = "true" ]
    [ "$(jq -r '.lineage.verdict' <<<"$output")" = "warn" ]
    [ "$(jq -r '.beads[] | select(.id=="c1") | .verdict' <<<"$output")" = "warn" ]
    [[ "$(jq -r '.beads[] | select(.id=="c1") | .reason' <<<"$output")" == *"beat c2"* ]]
    [ "$(jq -r '.beads[] | select(.id=="c2") | .verdict' <<<"$output")" = "ok" ]
    [ "$(jq -r '.warnings[0]' <<<"$output")" = "c1" ]
    [ "$(jq -r '.lineage.beat' <<<"$output")" = "c2" ]
}

@test "lineage: --beat naming an in-lineage candidate does not allow it" {
    make_lineage_bd_stub open labeled
    make_ic_stub '"E1"'
    run bash "$SCRIPT" --recommend c1 --beat c3
    [ "$status" -eq 3 ]
    [ "$(jq -r '.lineage.verdict' <<<"$output")" = "disqualified" ]
    [ "$(jq -r '.beads[] | select(.id=="c1") | .verdict' <<<"$output")" = "disqualified" ]
    [ "$(jq -r '.lineage.candidates[] | select(.id=="c3") | .in_streak' <<<"$output")" = "true" ]
}

@test "lineage: --beat naming a closed candidate does not allow it" {
    make_lineage_bd_stub closed labeled
    make_ic_stub '"E1"'
    run bash "$SCRIPT" --recommend c1 --beat c2
    [ "$status" -eq 3 ]
    [ "$(jq -r '.lineage.verdict' <<<"$output")" = "disqualified" ]
    [ "$(jq -r '.beads[] | select(.id=="c1") | .verdict' <<<"$output")" = "disqualified" ]
    [ "$(jq -r '.beads[] | select(.id=="c2") | .verdict' <<<"$output")" = "disqualified" ]
    [ "$(jq -r '.disqualified | length' <<<"$output")" = "2" ]
}

@test "lineage: a run whose every candidate continues the streak is refused as a whole" {
    make_lineage_bd_stub open labeled
    make_ic_stub '"E1"'
    run bash "$SCRIPT" c1 c3
    [ "$status" -eq 3 ]
    [ "$(jq -r '.ok' <<<"$output")" = "false" ]
    [ "$(jq -r '.lineage.verdict' <<<"$output")" = "disqualified" ]
    [ "$(jq -r '[.disqualified[] | select(contains("add one from next-goal-candidates.sh"))] | length' <<<"$output")" = "1" ]
    [ "$(jq -r '.beads[] | select(.id=="c1") | .verdict' <<<"$output")" = "warn" ]
    [ "$(jq -r '.beads[] | select(.id=="c3") | .verdict' <<<"$output")" = "warn" ]
}

@test "lineage: a goal whose lineage cannot be read never counts toward the streak" {
    make_lineage_bd_stub open unlabeled
    make_ic_stub null
    run bash "$SCRIPT" --recommend c1
    [ "$status" -eq 0 ]
    [ "$(jq -r '.ok' <<<"$output")" = "true" ]
    [ "$(jq -r '.lineage.available' <<<"$output")" = "true" ]
    [ "$(jq -r '.lineage.window[0].id' <<<"$output")" = "g1" ]
    [ "$(jq -r '.lineage.window[0].unknown' <<<"$output")" = "true" ]
    [ "$(jq -r '.lineage.window[1].unknown' <<<"$output")" = "true" ]
    [ "$(jq -r '.lineage.window[2].unknown' <<<"$output")" = "false" ]
    [ "$(jq -r '.lineage.candidates[0].in_streak' <<<"$output")" = "false" ]
    [ "$(jq -r '.lineage.verdict' <<<"$output")" = "ok" ]
}

@test "lineage: no ic anywhere reports lineage unavailable and leaves the verdict standing" {
    make_lineage_bd_stub open labeled
    # No ic stub. On a host with a real ic it runs in $WORK_DIR, which has no
    # goal store, and answers with an error object, not an array, so no store
    # answered. Either way lineage must say unavailable, never guess.
    run bash "$SCRIPT" --recommend c1
    [ "$status" -eq 0 ]
    [ "$(jq -r '.ok' <<<"$output")" = "true" ]
    [ "$(jq -r '.lineage.available' <<<"$output")" = "false" ]
    [ "$(jq -r '.schema_version' <<<"$output")" = "clavain.next-goal-verify/v3" ]
}

# ------------------------------------------------------------------ OUT clause
#
# 2026-09-04: the block that closed `jawnomicon ia-preview` recommended
# "export currency 646 to 694", the second item of that goal's own OUT clause.
# The pick was free text, so no bead was read back, and nothing compared a
# recommendation against what the user had just excluded.

OUT_TEXT='OUTCOME: a site. GATE 1 (mk): words. DONE WHEN: green. OUT: index density, export currency 646 to 694, families v31 naming, any edit to data, vocab, or committed batch records, any harvest.'

@test "out-clause: a free-text pick named in the OUT clause is disqualified" {
    run bash "$SCRIPT" --text "jawnomicon export-currency — OUTCOME: the site builds from an export at canon 694" --out-of "$OUT_TEXT"
    [ "$status" -eq 3 ]
    [ "$(jq -r '.ok' <<<"$output")" = "false" ]
    [ "$(jq -r '.out_clause.verdict' <<<"$output")" = "disqualified" ]
    [ "$(jq -r '.out_clause.matched[0].item' <<<"$output")" = "export currency 646 to 694" ]
    [ "$(jq -r '.out_clause.matched[0].source' <<<"$output")" = "text" ]
    [ "$(jq -r '.disqualified | length' <<<"$output")" -eq 1 ]
}

@test "out-clause: words gate the match, numbers and word forms do not" {
    # "families v31 naming" vs "family ... naming": families/family share a
    # prefix, v31 is a tag and rides free.
    run bash "$SCRIPT" --text "Family and kind naming pass — 44 family names and 19 cluster labels" --out-of "$OUT_TEXT"
    [ "$status" -eq 3 ]
    [ "$(jq -r '.out_clause.matched[0].item' <<<"$output")" = "families v31 naming" ]
}

@test "out-clause: a pick outside the OUT clause passes" {
    run bash "$SCRIPT" --text "constellation-nav — every figure page leads to its nearest figures" --out-of "$OUT_TEXT"
    [ "$status" -eq 0 ]
    [ "$(jq -r '.ok' <<<"$output")" = "true" ]
    [ "$(jq -r '.out_clause.verdict' <<<"$output")" = "ok" ]
    [ "$(jq -r '.out_clause.items' <<<"$output")" -ge 3 ]
}

@test "out-clause: --out-override downgrades the refusal to a warning and records the reason" {
    run bash "$SCRIPT" --text "export currency 646 to 694" --out-of "$OUT_TEXT" --out-override "xjq landed and the hold was lifted"
    [ "$status" -eq 0 ]
    [ "$(jq -r '.ok' <<<"$output")" = "true" ]
    [ "$(jq -r '.out_clause.verdict' <<<"$output")" = "warn" ]
    [ "$(jq -r '.out_clause.override' <<<"$output")" = "xjq landed and the hold was lifted" ]
    [ "$(jq -r '.warnings | index("<text>")' <<<"$output")" != "null" ]
}

@test "out-clause: the clause is read from a bead's description and the recommended bead is disqualified" {
    make_bd_stub "$(bead_json open ',"description":"jawnomicon ia-preview — OUTCOME: a site. OUT: index density, export currency 646 to 694, any harvest.\n\nFinding at intake: unrelated prose that mentions harvest twice."')"
    run bash "$SCRIPT" --recommend x-1 --text "/goal x-1 — export currency: bring the site to canon 694" --out-of x-9 x-1
    [ "$status" -eq 3 ]
    [ "$(jq -r '.out_clause.matched[0].source' <<<"$output")" = "bead x-9" ]
    [ "$(jq -r '.out_clause.subject' <<<"$output")" = "x-1" ]
    [ "$(jq -r '.beads[0].verdict' <<<"$output")" = "disqualified" ]
    [ "$(jq -r '.beads[0].reason' <<<"$output")" != "open" ]
    [ "$(jq -r '.out_clause.items' <<<"$output")" -eq 3 ]
}

@test "out-clause: prose after the OUT paragraph is not part of the clause" {
    # "harvest" appears in the intake paragraph below the clause; only the
    # clause's own items count, and "harvest" is one of them here — so a pick
    # about harvest is caught, but a pick about "intake" is not.
    make_bd_stub "$(bead_json open ',"description":"OUT: any harvest.\n\nFinding at intake: the intake pass found nothing."')"
    run bash "$SCRIPT" --text "intake pass: rerun the intake" --out-of x-9
    [ "$status" -eq 0 ]
    [ "$(jq -r '.out_clause.verdict' <<<"$output")" = "ok" ]
}

@test "out-clause: no source at all is reported as not evaluated, not as a pass" {
    run bash "$SCRIPT" --text "anything"
    [ "$status" -eq 0 ]
    [ "$(jq -r '.out_clause.available' <<<"$output")" = "false" ]
    [ "$(jq -r '.out_clause.verdict' <<<"$output")" = "null" ]
}

@test "out-clause: a source with no OUT clause passes and says so" {
    run bash "$SCRIPT" --text "anything" --out-of "OUTCOME: a goal with no exclusions."
    [ "$status" -eq 0 ]
    [ "$(jq -r '.out_clause.verdict' <<<"$output")" = "ok" ]
    [[ "$(jq -r '.out_clause.reason' <<<"$output")" == "no OUT clause found in"* ]]
}

# ------------------------------------------------------------------- worktrees

@test "worktree: a root inside a linked git worktree resolves to the main checkout" {
    command -v git >/dev/null || skip "git not installed"
    local main="$WORK_DIR/main"
    mkdir -p "$main/.beads"
    git -C "$WORK_DIR" init -q main
    git -C "$main" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
    git -C "$main" worktree add -q "$main/wt" -b wt
    mkdir -p "$main/wt/.beads"
    make_bd_stub "$(bead_json open)"
    unset CLAVAIN_NEXT_GOAL_ROOTS
    pushd "$main/wt" >/dev/null
    HOME="$WORK_DIR" run bash "$SCRIPT" x-1
    popd >/dev/null
    [ "$status" -eq 0 ]
    [ "$(jq -r '.beads[0].root' <<<"$output")" = "$(cd "$main" && pwd -P)" ]
}
