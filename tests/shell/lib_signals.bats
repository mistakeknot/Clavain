#!/usr/bin/env bats
# Tests for hooks/lib-signals.sh

setup() {
    load test_helper
    source "$HOOKS_DIR/lib-signals.sh"
}

teardown() {
    unset CLAVAIN_SIGNALS CLAVAIN_SIGNAL_WEIGHT
}

@test "lib-signals: detect_signals sets CLAVAIN_SIGNALS and CLAVAIN_SIGNAL_WEIGHT" {
    local transcript='{"role":"assistant","content":"Running \"git commit -m fix\""}'
    detect_signals "$transcript"
    [[ -n "$CLAVAIN_SIGNALS" ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -ge 1 ]]
}

@test "lib-signals: detects commit signal (weight 1)" {
    local transcript='{"role":"assistant","content":"Running \"git commit -m fix\""}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"commit"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 1 ]]
}

@test "lib-signals: detects bead-closed signal (weight 1)" {
    local transcript='{"role":"assistant","content":"Running \"bd close Clavain-abc1\""}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"bead-closed"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 1 ]]
}

@test "lib-signals: detects resolution signal (weight 2)" {
    local transcript='{"role":"user","content":"that worked, thanks!"}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"resolution"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 2 ]]
}

@test "lib-signals: detects investigation signal (weight 2)" {
    local transcript='{"role":"assistant","content":"the issue was a race condition in the cache layer"}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"investigation"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 2 ]]
}

@test "lib-signals: insight signal was removed (no detection)" {
    local transcript='Insight ─ The key realization is that X causes Y'
    detect_signals "$transcript"
    [[ -z "$CLAVAIN_SIGNALS" ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 0 ]]
}

@test "lib-signals: detects recovery signal (weight 2)" {
    local transcript=$'test FAILED: expected 5 got 3\nAll tests passed after fix'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"recovery"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 2 ]]
}

@test "lib-signals: detects version-bump signal (weight 2)" {
    local transcript='{"role":"assistant","content":"Running bump-version.sh 0.7.0"}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"version-bump"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 2 ]]
}

@test "lib-signals: detects interpub:release as version-bump (weight 2)" {
    local transcript='{"role":"assistant","content":"Running /interpub:release 1.0.0"}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"version-bump"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 2 ]]
}

@test "lib-signals: accumulates weights from multiple signals" {
    local transcript=$'Running "git commit -m fix"\n"the issue was a cache bug"'
    detect_signals "$transcript"
    # commit(1) + investigation(2) = 3 (insight signal was removed)
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 3 ]]
}

@test "lib-signals: no signals returns weight 0 and empty SIGNALS" {
    local transcript='{"role":"user","content":"What is Python?"}'
    detect_signals "$transcript"
    [[ -z "$CLAVAIN_SIGNALS" ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 0 ]]
}

@test "lib-signals: empty string returns weight 0" {
    detect_signals ""
    [[ -z "$CLAVAIN_SIGNALS" ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 0 ]]
}

@test "lib-signals: CLAVAIN_SIGNALS has no trailing comma" {
    local transcript=$'Running "git commit -m fix"\nRunning "bd close Clavain-abc1"'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" != *"," ]]  # no trailing comma
    [[ "$CLAVAIN_SIGNALS" == *","* ]]  # but has internal comma (2 signals)
}

@test "lib-signals: detects goal-completed from a met goal_status (weight 0, structural)" {
    local transcript='{"type":"attachment","attachment":{"type":"goal_status","met":true,"condition":"x"}}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"goal-completed"* ]]
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 0 ]]
}

@test "lib-signals: an unmet goal_status is not goal-completed" {
    local transcript='{"type":"attachment","attachment":{"type":"goal_status","met":false,"condition":"x"}}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" != *"goal-completed"* ]]
}

# A Bash tool call as Claude Code records it, stamped 2s before the stub
# tracker's closed_at.
bash_call() {
    jq -cn --arg c "$1" --arg id "${2:-toolu_1}" \
        '{type:"assistant",timestamp:"2026-09-27T11:59:58.000Z",message:{content:[{type:"tool_use",id:$id,name:"Bash",input:{command:$c}}]}}'
}

# The tool_result Claude Code records for a call.
tool_result() {
    jq -cn --arg t "$2" --arg id "$1" '{type:"user",message:{content:[{type:"tool_result",tool_use_id:$id,content:$t}]}}'
}

# A bd on PATH that answers `bd show ID... --json` like the real one: the IDs in
# $STUB_EPICS are epics, the rest tasks; the IDs in $STUB_OPEN are open, the
# rest closed at $STUB_CLOSED_AT. Every call is logged.
stub_bd() {
    STUB_DIR="$(mktemp -d)"
    cat > "$STUB_DIR/bd" <<'EOF'
#!/usr/bin/env bash
echo "$*" >> "$STUB_DIR/calls"
[[ "$1" == show ]] || exit 0
shift; sep=""; printf '['
for id in "$@"; do
    [[ "$id" == -* ]] && continue
    t=task; [[ " $STUB_EPICS " == *" $id "* ]] && t=epic
    st=closed; [[ " ${STUB_OPEN:-} " == *" $id "* ]] && st=open
    printf '%s{"id":"%s","issue_type":"%s","status":"%s","closed_at":"%s"}' "$sep" "$id" "$t" "$st" "${STUB_CLOSED_AT:-2026-09-27T12:00:00Z}"; sep=,
done
printf ']\n'
EOF
    chmod +x "$STUB_DIR/bd"
    export STUB_DIR PATH="$STUB_DIR:$PATH"
}

@test "lib-signals: detects goal-completed when bd close closes an epic" {
    stub_bd; export STUB_EPICS="proj-ep1"
    detect_signals "$(bash_call 'cd /tmp && export BEADS_ACTOR=x && bd close proj-ep1 --reason "all children closed" 2>&1 | tail -3')"
    [[ "$CLAVAIN_SIGNALS" == *"goal-completed"* ]]
    [[ "$CLAVAIN_GOAL_COMPLETED_LINE" -eq 2 ]]   # a block answers it from the next line
    rm -rf "$STUB_DIR"
}

@test "lib-signals: closing a task is not goal-completed" {
    stub_bd; export STUB_EPICS="proj-ep1"
    detect_signals "$(bash_call 'bd close proj-t1.2')"
    [[ "$CLAVAIN_SIGNALS" != *"goal-completed"* ]]
    [[ "$CLAVAIN_GOAL_COMPLETED_LINE" -eq 0 ]]
    grep -q "show proj-t1.2" "$STUB_DIR/calls"
    rm -rf "$STUB_DIR"
}

@test "lib-signals: a close that left the epic open is not goal-completed" {
    stub_bd; export STUB_EPICS="proj-ep1" STUB_OPEN="proj-ep1"
    detect_signals "$(bash_call 'bd close proj-ep1')"
    [[ "$CLAVAIN_SIGNALS" != *"goal-completed"* ]]
    rm -rf "$STUB_DIR"
}

@test "lib-signals: closing an epic that was already closed is not goal-completed" {
    stub_bd; export STUB_EPICS="proj-ep1" STUB_CLOSED_AT="2026-09-20T09:00:00Z"
    detect_signals "$(bash_call 'false && bd close proj-ep1')"
    [[ "$CLAVAIN_SIGNALS" != *"goal-completed"* ]]
    rm -rf "$STUB_DIR"
}

@test "lib-signals: a call with no timestamp is not goal-completed" {
    stub_bd; export STUB_EPICS="proj-ep1"
    detect_signals "$(jq -cn '{type:"assistant",message:{content:[{type:"tool_use",name:"Bash",input:{command:"bd close proj-ep1"}}]}}')"
    [[ "$CLAVAIN_SIGNALS" != *"goal-completed"* ]]
    rm -rf "$STUB_DIR"
}

@test "lib-signals: the newest IDs are kept when there are more than 20" {
    stub_bd; export STUB_EPICS="proj-ep21"
    detect_signals "$(bash_call "bd close $(printf 'proj-t%d ' $(seq 1 20)) proj-ep21")"
    [[ "$CLAVAIN_SIGNALS" == *"goal-completed"* ]]
    rm -rf "$STUB_DIR"
}

@test "lib-signals: a tracker that hangs is abandoned within the budget" {
    stub_bd; export STUB_EPICS="proj-ep1"
    printf '#!/usr/bin/env bash\nsleep 10\n' > "$STUB_DIR/bd"
    local start=$SECONDS
    detect_signals "$(bash_call 'bd close proj-ep1')"
    [[ "$CLAVAIN_SIGNALS" != *"goal-completed"* ]]
    (( SECONDS - start <= 3 ))
    rm -rf "$STUB_DIR"
}

@test "lib-signals: an epic closed long after the call is not goal-completed" {
    stub_bd; export STUB_EPICS="proj-ep1" STUB_CLOSED_AT="2026-09-27T12:10:00Z"
    detect_signals "$(bash_call 'bd close proj-ep1')"
    [[ "$CLAVAIN_SIGNALS" != *"goal-completed"* ]]
    rm -rf "$STUB_DIR"
}

@test "lib-signals: a tracker that ignores TERM is still abandoned within the budget" {
    stub_bd; export STUB_EPICS="proj-ep1"
    printf '#!/usr/bin/env bash\ntrap "" TERM\nsleep 10\n' > "$STUB_DIR/bd"
    local start=$SECONDS
    detect_signals "$(bash_call 'bd close proj-ep1')"
    [[ "$CLAVAIN_SIGNALS" != *"goal-completed"* ]]
    (( SECONDS - start <= 3 ))
    rm -rf "$STUB_DIR"
}

@test "lib-signals: IDs after close flags and past the twentieth are read" {
    stub_bd; export STUB_EPICS="proj-ep1"
    detect_signals "$(bash_call 'bd close --reason "all done" proj-ep1 2>&1 | tail -3')"
    [[ "$CLAVAIN_SIGNALS" == *"goal-completed"* ]]
    detect_signals "$(bash_call "bd close proj-ep1 $(printf 'proj-t%d ' $(seq 2 21))")"
    [[ "$CLAVAIN_SIGNALS" == *"goal-completed"* ]]
    rm -rf "$STUB_DIR"
}

@test "lib-signals: a separator inside quotes does not start a bd command" {
    stub_bd; export STUB_EPICS="proj-ep1"
    detect_signals "$(printf '%s\n' "$(bash_call 'echo "x; bd close proj-ep1"')" \
        "$(bash_call "printf 'x && bd close proj-ep1'")")"
    [[ "$CLAVAIN_SIGNALS" != *"goal-completed"* ]]
    [[ ! -e "$STUB_DIR/calls" ]]
    rm -rf "$STUB_DIR"
}

@test "lib-signals: quoted IDs, -C and a sixth ID are all read, in one lookup" {
    stub_bd; export STUB_EPICS="proj-ep6"
    detect_signals "$(bash_call 'bd -C /tmp close "proj-t1" proj-t2 proj-t3 proj-t4 proj-t5 '\''proj-ep6'\''')"
    [[ "$CLAVAIN_SIGNALS" == *"goal-completed"* ]]
    [[ "$(wc -l < "$STUB_DIR/calls")" -eq 1 ]]
    rm -rf "$STUB_DIR"
}

@test "lib-signals: bd not run as the command, or run for help, is not read" {
    stub_bd; export STUB_EPICS="proj-ep1"
    detect_signals "$(printf '%s\n' "$(bash_call 'echo bd close proj-ep1')" \
        "$(bash_call 'bd close proj-ep1 --help')" \
        "$(bash_call 'bd epic close-eligible -h')" \
        "$(bash_call 'bd --help close proj-ep1')" \
        "$(jq -cn '{type:"assistant",message:{content:[{type:"tool_use",name:"Monitor",input:{command:"bd close proj-ep1"}}]}}')")"
    [[ "$CLAVAIN_SIGNALS" != *"goal-completed"* ]]
    [[ ! -e "$STUB_DIR/calls" ]]
    rm -rf "$STUB_DIR"
}

@test "lib-signals: bd epic close-eligible counts the epics it closed, its dry run does not" {
    stub_bd; export STUB_EPICS="proj-ep1"
    detect_signals "$(printf '%s\n' "$(bash_call 'bd epic close-eligible --dry-run' t1)" \
        "$(tool_result t1 $'Would close 1 epic(s):\n  - proj-ep1: Ship it')")"
    [[ "$CLAVAIN_SIGNALS" != *"goal-completed"* ]]
    detect_signals "$(printf '%s\n' "$(bash_call 'bd epic close-eligible' t2)" \
        "$(tool_result t2 $'Closed 1 epic(s):\n  - proj-ep1: Ship it')")"
    [[ "$CLAVAIN_SIGNALS" == *"goal-completed"* ]]
    rm -rf "$STUB_DIR"
}

@test "lib-signals: bd epic close-eligible that closed nothing is not goal-completed" {
    stub_bd; export STUB_EPICS="proj-ep1"
    detect_signals "$(printf '%s\n' "$(bash_call 'bd epic close-eligible' t1)" \
        "$(tool_result t1 'No epics eligible for closure')")"
    [[ "$CLAVAIN_SIGNALS" != *"goal-completed"* ]]
    rm -rf "$STUB_DIR"
}

@test "lib-signals: CLAVAIN_GOAL_COMPLETED_LINE follows the last completion" {
    stub_bd; export STUB_EPICS="proj-ep1"
    detect_signals "$(printf '%s\n' '{"type":"attachment","attachment":{"type":"goal_status","met":true}}' \
        '{"type":"assistant","message":{"content":[{"type":"text","text":"x"}]}}' \
        "$(bash_call 'bd close proj-ep1')")"
    [[ "$CLAVAIN_GOAL_COMPLETED_LINE" -eq 4 ]]
    rm -rf "$STUB_DIR"
}

# Claude Code writes goal_status at stop time, after the reply that met the
# goal, so that reply is where a Next-goal block answering it sits.
@test "lib-signals: a met goal is answered from the reply before its goal_status" {
    detect_signals "$(printf '%s\n' '{"type":"user","message":{"content":"go"}}' \
        '{"type":"assistant","message":{"content":[{"type":"text","text":"Done."}]}}' \
        '{"type":"attachment","attachment":{"type":"hook_success"}}' \
        '{"type":"attachment","attachment":{"type":"goal_status","met":true}}')"
    [[ "$CLAVAIN_SIGNALS" == *"goal-completed"* ]]
    [[ "$CLAVAIN_GOAL_COMPLETED_LINE" -eq 2 ]]
}

# Regression, jawnomicon thr_cf7b863d3f (2026-09-27): the turn filed a bead
# under an epic and closed nothing. "epic" in the tool description and
# "closed registration" in the bead description sat in one JSONL record, and
# the prose pattern read that as an epic closing and blocked the stop.
@test "lib-signals: creating a bead under an epic, closing nothing, is not goal-completed" {
    stub_bd; export STUB_EPICS="jawnomicon-dv5p"
    local create
    create=$(jq -cn --arg c 'cd /home/mk/projects/jawnomicon && bd create --type feature --parent jawnomicon-dv5p --title "Rewrite review tool" --description "Auth: Logto (Google-only, closed registration). The epic is complete when mk signs off."' \
        '{type:"assistant",message:{content:[{type:"tool_use",name:"Bash",input:{command:$c,description:"File the review-tool bead under the de-slop epic"}}]}}')
    local transcript
    transcript=$(printf '%s\n%s\n%s\n' "$create" \
        '{"type":"user","message":{"content":[{"type":"tool_result","content":"✓ Created issue: jawnomicon-dv5p.5"}]}}' \
        '{"type":"assistant","message":{"content":[{"type":"text","text":"Filed jawnomicon-dv5p.5 under the epic. No /goal was met and no epic closed."}]}}')
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" != *"goal-completed"* ]]
    [[ ! -e "$STUB_DIR/calls" ]]   # no close, so the tracker is never asked
    rm -rf "$STUB_DIR"
}

@test "lib-signals: goal_status outside an attachment is not goal-completed" {
    detect_signals '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Other","input":{"type":"goal_status","met":true}}]}}'
    [[ "$CLAVAIN_SIGNALS" != *"goal-completed"* ]]
    detect_signals '{"type":"attachment","attachment":{"type":"goal_status","condition":"x","met":true}}'
    [[ "$CLAVAIN_SIGNALS" == *"goal-completed"* ]]
}

@test "lib-signals: prose about an epic closing is not goal-completed" {
    detect_signals '{"type":"assistant","message":{"content":[{"type":"text","text":"Closed the last child, so the epic is now closed."}]}}'
    [[ "$CLAVAIN_SIGNALS" != *"goal-completed"* ]]
}

@test "lib-signals: milestone and goal wording alone is not goal-completed" {
    local transcript=$'The goal is complete.\nRan /goal review and it landed successfully\nThis goal-scale milestone landed after three sprints\n/goal Ship it. DONE WHEN tests pass.'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" != *"goal-completed"* ]]
}

@test "lib-signals: goal-completed does not fire on unrelated text" {
    local transcript='Just fixed a typo in the README, nothing goal-related'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" != *"goal-completed"* ]]
}

@test "lib-signals: goal-completed does not add to weight ladder alongside other signals" {
    local transcript=$'Running "git commit -m fix"\n{"type":"attachment","attachment":{"type":"goal_status","met":true}}'
    detect_signals "$transcript"
    [[ "$CLAVAIN_SIGNALS" == *"goal-completed"* ]]
    [[ "$CLAVAIN_SIGNALS" == *"commit"* ]]
    # commit(1) + goal-completed(0) = 1
    [[ "$CLAVAIN_SIGNAL_WEIGHT" -eq 1 ]]
}
