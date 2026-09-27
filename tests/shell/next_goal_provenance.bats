#!/usr/bin/env bats
# Tests for hooks/lib-next-goal-provenance.sh
#
# The predicate under test: a Next-goal block that does not disclose
# degradation is implicitly claiming tracker provenance, and needs a receipt
# from scripts/next-goal-candidates.sh to back that claim.

setup() {
    load test_helper
    CACHE_DIR="$(mktemp -d)"
    export CLAVAIN_PROVENANCE_DIR="$CACHE_DIR"
    source "$HOOKS_DIR/lib-next-goal-provenance.sh"
    # Re-point after sourcing: the library defaults the variable at load time.
    CLAVAIN_PROVENANCE_DIR="$CACHE_DIR"
}

teardown() {
    rm -rf "$CACHE_DIR"
}

# ------------------------------------------------------------------ fixtures

# A transcript line as Claude Code writes it: assistant text inside a JSON
# string, so the words are intact but newlines are escaped.
assistant_line() {
    printf '{"type":"assistant","message":{"content":[{"type":"text","text":"%s"}]}}\n' "$1"
}

user_line() {
    printf '{"type":"user","message":{"content":"%s"}}\n' "$1"
}

# A block that reads as tracker-ranked: names a Next goal, carries paste-ready
# /goal text, says nothing about degradation.
block_claiming_provenance() {
    assistant_line "## Next goal\\n\\n1. Close mk-i43y\\n\\n/goal Ship it.\\n\\nOUTCOME: the thing is live. Stop after 5 turns."
}

block_disclosing_degradation() {
    assistant_line "## Next goal\\n\\nno tracker reachable — the sylveste root did not answer, so these are improvised.\\n\\n/goal Ship it.\\n\\nOUTCOME: the thing is live. Stop after 5 turns."
}

write_receipt() {
    # $1 = tracker_reachable literal (true|false)
    cat > "$CLAVAIN_PROVENANCE_DIR/sess-1.json" <<EOF
{"schema_version":"clavain.next-goal-provenance/v1","session_id":"sess-1",
 "recorded_at":"2026-08-07T12:00:00Z","tracker_reachable":$1,
 "roots_ok":["sylveste","mk"],"lookup_failures":[],"candidate_count":40,
 "roadmap_status":"fresh"}
EOF
}

# ------------------------------------------------- the flagged cases (the point)

@test "flags a block that claims provenance when the helper never ran" {
    run next_goal_provenance_warning "sess-1" "$(block_claiming_provenance)"
    [ "$status" -eq 0 ]
    [[ "$output" == *"never ran in this session"* ]]
}

@test "flags a block that reads as tracker-ranked when no tracker was reached" {
    write_receipt false
    run next_goal_provenance_warning "sess-1" "$(block_claiming_provenance)"
    [ "$status" -eq 0 ]
    [[ "$output" == *"reached NO tracker"* ]]
    [[ "$output" == *"no tracker reachable"* ]]
}

@test "the two failure modes get distinguishable messages" {
    run next_goal_provenance_warning "sess-1" "$(block_claiming_provenance)"
    missing_msg="$output"
    write_receipt false
    run next_goal_provenance_warning "sess-1" "$(block_claiming_provenance)"
    unreachable_msg="$output"
    [ -n "$missing_msg" ]
    [ -n "$unreachable_msg" ]
    [ "$missing_msg" != "$unreachable_msg" ]
}

@test "flags a receipt that exists but cannot be parsed" {
    printf 'not json at all\n' > "$CLAVAIN_PROVENANCE_DIR/sess-1.json"
    run next_goal_provenance_warning "sess-1" "$(block_claiming_provenance)"
    [ "$status" -eq 0 ]
    [[ "$output" == *"could not be parsed"* ]]
}

@test "a receipt missing the tracker_reachable key is unreadable, not reachable" {
    printf '{"schema_version":"x","session_id":"sess-1"}\n' > "$CLAVAIN_PROVENANCE_DIR/sess-1.json"
    run next_goal_receipt_state "sess-1"
    [ "$output" = "unreadable" ]
}

# ------------------------------------------------------------- the silent cases

@test "silent when a receipt vouches for the block" {
    write_receipt true
    run next_goal_provenance_warning "sess-1" "$(block_claiming_provenance)"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "silent when the block honestly discloses degradation" {
    write_receipt false
    run next_goal_provenance_warning "sess-1" "$(block_disclosing_degradation)"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "silent when no Next-goal block was emitted at all" {
    run next_goal_provenance_warning "sess-1" "$(assistant_line "Just an ordinary reply with no block.")"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "silent on an empty transcript" {
    run next_goal_provenance_warning "sess-1" ""
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "receipts are per session: another session's receipt does not vouch" {
    write_receipt true   # written for sess-1
    run next_goal_provenance_warning "sess-2" "$(block_claiming_provenance)"
    [ "$status" -eq 0 ]
    [[ "$output" == *"never ran in this session"* ]]
}

# --------------------------------------------- detection must not self-trigger

@test "the goal-cadence instruction is not itself mistaken for a block" {
    # auto-stop-actions.sh injects this text, and the injection lands in the
    # transcript. Matching on the phrase alone would make the hook audit its
    # own request and always find a violation.
    injected=$(assistant_line "Goal-cadence: your completion message to the user MUST end with a Next goal block. Run /clavain:next-goal to generate it.")
    run next_goal_provenance_warning "sess-1" "$injected"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "a user pasting a /goal is not the assistant claiming provenance" {
    pasted=$(user_line "/goal Ship the thing. OUTCOME: it is live. Next goal after that.")
    run next_goal_provenance_warning "sess-1" "$pasted"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "a Next-goal mention without paste-ready goal text is not a block" {
    run next_goal_provenance_warning "sess-1" \
        "$(assistant_line "I will add a Next goal block at the end of the next reply.")"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

# ---------------------------------------------------------------- escape hatch

@test "audit can be disabled outright" {
    CLAVAIN_PROVENANCE_AUDIT_DISABLE=1 run next_goal_provenance_warning \
        "sess-1" "$(block_claiming_provenance)"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "receipt state is missing when the cache dir does not exist" {
    CLAVAIN_PROVENANCE_DIR="$CACHE_DIR/nope"
    run next_goal_receipt_state "sess-1"
    [ "$output" = "missing" ]
}

# ------------------------------------------------- helper writes what hook reads
#
# The contract has two ends. Above asserts the hook reads a receipt correctly;
# this asserts the helper actually produces one in that shape, so the two
# cannot drift apart silently.

@test "the helper writes a receipt the hook can read" {
    stub_dir="$(mktemp -d)"
    cat > "$stub_dir/bd" <<'EOF'
#!/usr/bin/env bash
if [[ "$1" == "where" ]]; then
    echo "$PWD/.beads"; echo "  prefix: tst"; echo "  database: $PWD/.beads/tst.db"; exit 0
fi
if [[ "$1" == "ready" ]]; then echo '[{"id":"tst-1","title":"a ready bead"}]'; exit 0; fi
exit 0
EOF
    chmod +x "$stub_dir/bd"
    root="$(mktemp -d)"; mkdir -p "$root/.beads"

    (
        cd "$root" || exit 1
        PATH="$stub_dir:$PATH" \
        CLAUDE_SESSION_ID="sess-helper" \
        CLAVAIN_PROVENANCE_DIR="$CACHE_DIR" \
        CLAVAIN_NEXT_GOAL_ROOTS="$root" \
            "$BATS_TEST_DIRNAME/../../scripts/next-goal-candidates.sh" >/dev/null
    )

    [ -f "$CACHE_DIR/sess-helper.json" ]
    run next_goal_receipt_state "sess-helper"
    [ "$output" = "reachable" ]

    rm -rf "$stub_dir" "$root"
}

# ------------------------------------------------------- hook wiring, end to end
#
# The unit tests above prove the predicate. These prove auto-stop-actions.sh
# actually reaches it. That wiring is its own risk: the provenance tier was
# inserted ABOVE a goal-cadence tier that had assigned REASON unconditionally
# for as long as it had been first in the waterfall.

run_stop_hook() {
    # $1 = transcript body, $2 = session id
    local body="$1" session="$2"
    local tmp; tmp="$(mktemp -d)"
    printf '%s\n' "$body" > "$tmp/transcript.jsonl"

    cat > "$tmp/ic" <<'EOF'
#!/usr/bin/env bash
case "$1" in
    health)   exit 0 ;;
    sentinel) exit 0 ;;   # 0 = allowed, never throttled
esac
exit 0
EOF
    chmod +x "$tmp/ic"

    (
        cd "$tmp" || exit 1
        printf '{"session_id":"%s","transcript_path":"%s","stop_hook_active":false}' \
            "$session" "$tmp/transcript.jsonl" \
        | env -u CLAUDE_SESSION_ID -u CLAUDE_CODE_SESSION_ID -u BB_THREAD_ID \
              ${HOOK_ENV:-} \
              PATH="$tmp:$PATH" CLAVAIN_PROVENANCE_DIR="$CLAVAIN_PROVENANCE_DIR" \
              CLAVAIN_LOOP_BREAKER_DIR="$tmp/loop-breaker" \
              bash "$BATS_TEST_DIRNAME/../../hooks/auto-stop-actions.sh"
    )
    rm -rf "$tmp"
}

@test "hook reports an unbacked block to the user without blocking" {
    run run_stop_hook "$(block_claiming_provenance)" "sess-1"
    [ "$status" -eq 0 ]
    [[ "$output" == *'"systemMessage"'* ]]
    [[ "$output" == *"Next-goal provenance"* ]]
    [[ "$output" != *'"decision"'* ]]
}

@test "hook stays quiet when a receipt vouches for the block" {
    write_receipt true
    run run_stop_hook "$(block_claiming_provenance)" "sess-1"
    [ "$status" -eq 0 ]
    [[ "$output" != *"Next-goal provenance"* ]]
}

@test "a receipt filed under this session's bb thread id vouches (thr_xg8t59tfba)" {
    # The helper ran from a Bash tool in bb, which has BB_THREAD_ID and no
    # CLAUDE_SESSION_ID, so the receipt is keyed by thread id. The hook is
    # handed the Claude session id. Both name this session.
    write_receipt true
    mv "$CLAVAIN_PROVENANCE_DIR/sess-1.json" "$CLAVAIN_PROVENANCE_DIR/thr_test.json"
    HOOK_ENV="BB_THREAD_ID=thr_test" run run_stop_hook "$(block_claiming_provenance)" "claude-uuid-1"
    [ "$status" -eq 0 ]
    [[ "$output" != *"Next-goal provenance"* ]]
}

@test "a met goal whose Next-goal block is already written is not re-demanded" {
    write_receipt true
    transcript="$(printf '{"type":"attachment","attachment":{"type":"goal_status","met":true}}')
$(block_claiming_provenance)"
    run run_stop_hook "$transcript" "sess-1"
    [ "$status" -eq 0 ]
    [[ "$output" != *"Goal-cadence:"* ]]
}

@test "a met goal with no block yet gets the goal-cadence request" {
    transcript="$(printf '{"type":"attachment","attachment":{"type":"goal_status","met":true}}')"
    run run_stop_hook "$transcript" "sess-cadence"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Goal-cadence:"* ]]
}

@test "a Next-goal block for an earlier goal does not answer a newer one" {
    write_receipt true
    transcript="$(block_claiming_provenance)
$(printf '{"type":"attachment","attachment":{"type":"goal_status","met":true}}')"
    run run_stop_hook "$transcript" "sess-stale-block"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Goal-cadence:"* ]]
}

# End to end for jawnomicon thr_cf7b863d3f (2026-09-27): a turn that files a
# bead under an epic and closes nothing must stop cleanly, even when the
# tracker confirms the parent is an epic and the texts say "epic" and "closed".
@test "a turn that creates a bead under an epic and closes nothing stops cleanly" {
    local stub; stub="$(mktemp -d)"
    printf '#!/usr/bin/env bash\necho "[{\\"id\\":\\"proj-ep1\\",\\"issue_type\\":\\"epic\\",\\"status\\":\\"closed\\",\\"closed_at\\":\\"2026-09-27T12:00:00Z\\"}]"\n' > "$stub/bd"
    chmod +x "$stub/bd"
    local create
    create=$(jq -cn --arg c 'cd /tmp && bd create --parent jawnomicon-dv5p --title "Rewrite review tool" --description "Google-only, closed registration"' \
        '{type:"assistant",message:{content:[{type:"tool_use",name:"Bash",input:{command:$c,description:"File the review-tool bead under the de-slop epic"}}]}}')
    PATH="$stub:$PATH" run run_stop_hook "$create"$'\n'"$(assistant_line 'Filed jawnomicon-dv5p.5. No /goal was met and no epic closed.')" "sess-create-only"
    rm -rf "$stub"
    [ "$status" -eq 0 ]
    [[ "$output" != *"Goal-cadence:"* ]]
    [[ "$output" != *'"decision"'* ]]
}

@test "a turn that closes an epic gets the goal-cadence request" {
    local stub; stub="$(mktemp -d)"
    printf '#!/usr/bin/env bash\necho "[{\\"id\\":\\"proj-ep1\\",\\"issue_type\\":\\"epic\\",\\"status\\":\\"closed\\",\\"closed_at\\":\\"2026-09-27T12:00:00Z\\"}]"\n' > "$stub/bd"
    chmod +x "$stub/bd"
    PATH="$stub:$PATH" run run_stop_hook "$(jq -cn '{type:"assistant",timestamp:"2026-09-27T11:59:58Z",message:{content:[{type:"tool_use",name:"Bash",input:{command:"bd close proj-ep1"}}]}}')" "sess-epic-close"
    rm -rf "$stub"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Goal-cadence:"* ]]
}

# ---------------------------------------------------- verification (2026-08-14)
#
# The second claim a block makes. Provenance asks whether a tracker answered;
# these ask whether the candidates it named are still live. A block cited a bead
# that had been closed for two weeks and every provenance signal read clean.

verify_receipt() {
    # $1 = session, $2 = the `ok` value, $3 = compact JSON array of disqualified
    mkdir -p "$VERIFY_DIR"
    printf '{"schema_version":"clavain.next-goal-verify/v1","ok":%s,"disqualified":%s}\n' \
        "$2" "${3:-[]}" > "$VERIFY_DIR/$1.json"
}

setup_verify_dir() {
    VERIFY_DIR="$(mktemp -d)"
    CLAVAIN_VERIFY_DIR="$VERIFY_DIR"
}

@test "verification: silent when every cited candidate verified clean" {
    setup_verify_dir
    verify_receipt "v-ok" true '[]'
    run next_goal_verification_warning "v-ok" "$(block_claiming_provenance)"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
    rm -rf "$VERIFY_DIR"
}

@test "verification: flags a block whose candidates were never re-read" {
    setup_verify_dir
    run next_goal_verification_warning "v-missing" "$(block_claiming_provenance)"
    [ "$status" -eq 0 ]
    [[ "$output" == *"never ran in this session"* ]]
    rm -rf "$VERIFY_DIR"
}

@test "verification: names the disqualified candidates — the w46q case" {
    setup_verify_dir
    verify_receipt "v-bad" false '["solwend-w46q","apps/web/components/thing/"]'
    run next_goal_verification_warning "v-bad" "$(block_claiming_provenance)"
    [ "$status" -eq 0 ]
    [[ "$output" == *"DISQUALIFIED"* ]]
    [[ "$output" == *"solwend-w46q"* ]]
    rm -rf "$VERIFY_DIR"
}

@test "verification: ok:null is reported as unverified, never as passing" {
    setup_verify_dir
    verify_receipt "v-null" null '[]'
    run next_goal_verification_warning "v-null" "$(block_claiming_provenance)"
    [ "$status" -eq 0 ]
    [[ "$output" == *"could not reach bd"* ]]
    rm -rf "$VERIFY_DIR"
}

@test "verification: says nothing when no Next-goal block was emitted" {
    setup_verify_dir
    run next_goal_verification_warning "v-none" "$(assistant_line "Just a normal reply.")"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
    rm -rf "$VERIFY_DIR"
}
