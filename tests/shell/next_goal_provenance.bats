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

# Timestamped variants, in the shape Claude Code 2.1.x writes: a human prompt is
# a user line with STRING content and no isMeta; a skill expansion or the Stop
# hook's own injected feedback is also a user line, but isMeta:true. The
# distinction is what next_goal_turn_started_at keys on.
user_line_ts() {
    printf '{"type":"user","timestamp":"%s","message":{"content":"%s"}}\n' "$1" "$2"
}
meta_user_line_ts() {
    printf '{"type":"user","isMeta":true,"timestamp":"%s","message":{"content":"%s"}}\n' "$1" "$2"
}
assistant_line_ts() {
    printf '{"type":"assistant","timestamp":"%s","message":{"content":[{"type":"text","text":"%s"}]}}\n' "$1" "$2"
}

# The 2026-09-01 shape: a real block, ranked and recommended, with paste-ready
# /goal text — and NO "OUTCOME:" anywhere. 19 of 24 minted goals look like this,
# and the old detector (which required the literal OUTCOME:) saw none of them.
block_without_outcome() {
    assistant_line "## Next goal\n\n1. **Merge PR #26** — lands the close protocol\n2. **Close mk-i43y** — unblocks the wave\n\n**Recommendation:** 2\n\n/goal Close mk-i43y so the wave can run."
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
    # $1 = tracker_reachable literal (true|false), $2 = recorded_at (optional)
    cat > "$CLAVAIN_PROVENANCE_DIR/sess-1.json" <<EOF
{"schema_version":"clavain.next-goal-provenance/v1","session_id":"sess-1",
 "recorded_at":"${2:-2026-08-07T12:00:00Z}","tracker_reachable":$1,
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

# ------------------------------------------ detection keys on the /goal line (W2)
#
# The old detector required the literal "OUTCOME:". Only 5 of 24 minted goals
# carry it, so from 2026-08-14 to 2026-09-01 every real block was invisible to
# both audits and the hook fired goal-cadence seven times at blocks that were
# already there. The paste-ready /goal line is the marker every block has.

@test "detects a block that carries a /goal line and no OUTCOME: (the 2026-09-01 shape)" {
    run next_goal_block_emitted "$(block_without_outcome)"
    [ "$status" -eq 0 ]
    run next_goal_provenance_warning "sess-1" "$(block_without_outcome)"
    [[ "$output" == *"never ran in this session"* ]]
}

@test "the hook's own wording 'ready-to-paste /goal text' mid-sentence is not a block" {
    injected=$(assistant_line "Goal-cadence: your completion message MUST end with a Next goal block. Run /clavain:next-goal (2-4 candidates, a recommendation, and ready-to-paste /goal text), then append it.")
    run next_goal_block_emitted "$injected"
    [ "$status" -ne 0 ]
}

@test "a /goal placeholder quoted from the template is not a block" {
    # commands/next-goal.md shows the format with `/goal <ready-to-paste text ...>`.
    # A turn that quotes the template must not read as having emitted a block.
    quoted=$(assistant_line "The format is:\n\n## Next goal\n\n1. **<title>** — <rationale>\n\n    /goal <ready-to-paste text for the recommended candidate>")
    run next_goal_block_emitted "$quoted"
    [ "$status" -ne 0 ]
}

@test "a 'next goal' mention far from a quoted /goal line is not a block" {
    body="I will add a next goal block later."
    for i in $(seq 1 50); do body+="\nfiller line $i"; done
    body+="\nExample syntax:\n/goal Ship the thing."
    run next_goal_block_emitted "$(assistant_line "$body")"
    [ "$status" -ne 0 ]
}

@test "a block emitted before this turn's prompt is not this turn's block" {
    earlier="$(assistant_line_ts 2026-09-01T10:00:00.000Z "## Next goal\n\n1. Close mk-i43y\n\n/goal Ship it.")
$(user_line_ts 2026-09-01T11:00:00.000Z "what's next?")
$(assistant_line_ts 2026-09-01T11:00:05.000Z "Just an ordinary reply.")"
    run next_goal_block_emitted "$earlier"
    [ "$status" -ne 0 ]
    run next_goal_provenance_warning "sess-1" "$earlier"
    [ -z "$output" ]
}

@test "a skill expansion or hook injection does not start a new turn" {
    # Both are user lines with isMeta:true. If either reset the turn, a block
    # emitted before a mid-turn Skill call would vanish from the audit.
    body="$(user_line_ts 2026-09-01T10:00:00.000Z "what's next?")
$(assistant_line_ts 2026-09-01T10:05:00.000Z "## Next goal\n\n1. Close mk-i43y\n\n/goal Ship it.")
$(meta_user_line_ts 2026-09-01T10:06:00.000Z "Stop hook feedback: Goal-cadence: your reply MUST end with a Next goal block.")"
    run next_goal_turn_started_at "$body"
    [ "$output" = "2026-09-01T10:00:00.000Z" ]
    run next_goal_block_emitted "$body"
    [ "$status" -eq 0 ]
}

@test "the existing OUTCOME-carrying fixture is still a block" {
    run next_goal_block_emitted "$(block_claiming_provenance)"
    [ "$status" -eq 0 ]
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

@test "with CLAUDE_SESSION_ID unset the candidates receipt is keyed on CLAUDE_CODE_SESSION_ID" {
    # Claude Code 2.1.258's Bash tool exports CLAUDE_CODE_SESSION_ID. Clavain's
    # CLAUDE_SESSION_ID only exists when session-start.sh ran and wrote the env
    # file. Keyed on the second alone, every receipt landed as unknown.json and
    # every detected block was flagged as improvised.
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
        unset CLAUDE_SESSION_ID
        PATH="$stub_dir:$PATH" \
        CLAUDE_CODE_SESSION_ID="sess-code" \
        CLAVAIN_PROVENANCE_DIR="$CACHE_DIR" \
        CLAVAIN_NEXT_GOAL_ROOTS="$root" \
            "$BATS_TEST_DIRNAME/../../scripts/next-goal-candidates.sh" >/dev/null
    )
    [ -f "$CACHE_DIR/sess-code.json" ]
    [ ! -f "$CACHE_DIR/unknown.json" ]
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
        | PATH="$tmp:$PATH" CLAVAIN_PROVENANCE_DIR="$CLAVAIN_PROVENANCE_DIR" \
              CLAVAIN_VERIFY_DIR="${CLAVAIN_VERIFY_DIR:-$HOME/.cache/clavain/next-goal-verify}" \
              CLAVAIN_LOOP_BREAKER_DIR="$tmp/loop-breaker" \
              bash "$BATS_TEST_DIRNAME/../../hooks/auto-stop-actions.sh"
    )
    rm -rf "$tmp"
}

@test "hook blocks with the provenance warning on an unbacked block" {
    run run_stop_hook "$(block_claiming_provenance)" "sess-1"
    [ "$status" -eq 0 ]
    [[ "$output" == *'"decision"'* ]]
    [[ "$output" == *"Next-goal provenance"* ]]
}

@test "hook stays quiet when a receipt vouches for the block" {
    write_receipt true
    run run_stop_hook "$(block_claiming_provenance)" "sess-1"
    [ "$status" -eq 0 ]
    [[ "$output" != *"Next-goal provenance"* ]]
}

@test "provenance outranks goal-cadence rather than being overwritten by it" {
    # Both tiers are eligible: the turn says a goal was completed AND the block
    # it emitted cannot back its provenance. The specific complaint must win.
    transcript="$(assistant_line "The /goal is complete and shipped.")
$(block_claiming_provenance)"
    # Distinct session id on purpose: lib-loop-breaker.sh (mk-ax8) goes silent
    # when the same demand repeats for one session with no intervening
    # progress, and the unbacked-block case above already fired this exact
    # reason for sess-1. Reusing it would make this test pass or fail on test
    # ordering rather than on tier precedence.
    run run_stop_hook "$transcript" "sess-tier-order"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Next-goal provenance"* ]]
    [[ "$output" != *"Goal-cadence:"* ]]
}

@test "hook finds a receipt keyed on the writer's register when stdin's session id differs" {
    # The writer keys on CLAUDE_SESSION_ID / CLAUDE_CODE_SESSION_ID; the hook
    # gets .session_id on stdin. Nothing guaranteed the two strings agree, so
    # the reader tries every register the writer could have used.
    cat > "$CLAVAIN_PROVENANCE_DIR/sess-env.json" <<'EOF'
{"schema_version":"clavain.next-goal-provenance/v1","session_id":"sess-env",
 "tracker_reachable":true,"roots_ok":["mk"],"lookup_failures":[]}
EOF
    export CLAUDE_CODE_SESSION_ID="sess-env"
    run run_stop_hook "$(block_claiming_provenance)" "sess-stdin"
    [ "$status" -eq 0 ]
    [[ "$output" != *"Next-goal provenance"* ]]
}

@test "hook still flags when no register has a receipt" {
    export CLAUDE_CODE_SESSION_ID="sess-env-absent"
    run run_stop_hook "$(block_claiming_provenance)" "sess-stdin-2"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Next-goal provenance"* ]]
}

# ---------------------------------------------------- verification (2026-08-14)
#
# The second claim a block makes. Provenance asks whether a tracker answered;
# these ask whether the candidates it named are still live. A block cited a bead
# that had been closed for two weeks and every provenance signal read clean.

verify_receipt() {
    # $1 = session, $2 = the `ok` value, $3 = JSON array of disqualified,
    # $4 = JSON array of beads the verifier read back (optional),
    # $5 = verified_at (optional; absent means freshness is not judged)
    mkdir -p "$VERIFY_DIR"
    jq -cn --argjson ok "$2" --argjson disq "${3:-[]}" --argjson beads "${4:-[]}" --arg at "${5:-}" '
        {schema_version: "clavain.next-goal-verify/v1", ok: $ok, disqualified: $disq, beads: $beads}
        + (if $at == "" then {} else {verified_at: $at} end)' > "$VERIFY_DIR/$1.json"
}

setup_verify_dir() {
    VERIFY_DIR="$(mktemp -d)"
    CLAVAIN_VERIFY_DIR="$VERIFY_DIR"
}

@test "verification: silent when every cited candidate verified clean" {
    setup_verify_dir
    verify_receipt "v-ok" true '[]' '[{"id":"mk-i43y"}]'
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

# ------------------------------------------ freshness: a receipt is per turn (W3)
#
# Sessions live for months and a receipt had no expiry, so the receipt from a
# next-goal run weeks ago vouched for every block the session emitted since.
# A receipt now vouches only for the turn it was written in: it must postdate
# the last human prompt in the window. When the window holds no prompt (a
# long, tool-heavy turn), the block's own timestamp minus a budget bounds it
# instead — the fixed 80-line tail must not become a way to fail open.
# Both stamps come from the same host clock: Claude Code writes the transcript
# and runs the helper on the same machine.

fresh_turn() {
    # a human prompt at 10:00, the block at 10:05
    printf '%s\n%s\n' \
        "$(user_line_ts 2026-09-01T10:00:00.000Z "what's next?")" \
        "$(assistant_line_ts 2026-09-01T10:05:00.000Z "## Next goal\\n\\n1. Close mk-i43y\\n\\n/goal Ship it.")"
}

block_only_turn() {
    # no prompt in the window at all: only the block, at 10:05
    assistant_line_ts 2026-09-01T10:05:00.000Z "## Next goal\\n\\n1. Close mk-i43y\\n\\n/goal Ship it."
}

@test "freshness: a receipt older than this turn's prompt does not vouch (provenance)" {
    write_receipt true    # recorded 2026-08-07T12:00:00Z
    run next_goal_provenance_warning "sess-1" "$(fresh_turn)"
    [ "$status" -eq 0 ]
    [[ "$output" == *"STALE"* ]]
    [[ "$output" == *"2026-08-07T12:00:00Z"* ]]
    [[ "$output" == *"2026-09-01T10:00:00"* ]]
}

@test "freshness: a receipt older than this turn's prompt does not vouch (verification)" {
    setup_verify_dir
    verify_receipt "sess-1" true '[]' '[{"id":"mk-i43y"}]' "2026-08-07T12:00:00Z"
    run next_goal_verification_warning "sess-1" "$(fresh_turn)"
    [ "$status" -eq 0 ]
    [[ "$output" == *"STALE"* ]]
    [[ "$output" == *"2026-08-07T12:00:00Z"* ]]
    rm -rf "$VERIFY_DIR"
}

@test "freshness: a receipt written during this turn vouches" {
    write_receipt true 2026-09-01T10:03:00Z
    run next_goal_provenance_warning "sess-1" "$(fresh_turn)"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
    setup_verify_dir
    verify_receipt "sess-1" true '[]' '[{"id":"mk-i43y"}]' "2026-09-01T10:04:00Z"
    run next_goal_verification_warning "sess-1" "$(fresh_turn)"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
    rm -rf "$VERIFY_DIR"
}

@test "freshness: no timestamps anywhere means freshness is not judged" {
    write_receipt true
    run next_goal_provenance_warning "sess-1" "$(block_claiming_provenance)"
    [ -z "$output" ]
    run next_goal_receipt_freshness "2026-08-07T12:00:00Z" "$(block_claiming_provenance)"
    [ "$output" = "unknown" ]
    run next_goal_receipt_freshness "" "$(fresh_turn)"
    [ "$output" = "unknown" ]
}

@test "freshness: with no prompt in the window, the block's own timestamp bounds it" {
    write_receipt true    # 2026-08-07: weeks before a block at 2026-09-01T10:05
    run next_goal_provenance_warning "sess-1" "$(block_only_turn)"
    [[ "$output" == *"STALE"* ]]
    write_receipt true 2026-09-01T09:50:00Z    # 15 minutes before the block
    run next_goal_provenance_warning "sess-1" "$(block_only_turn)"
    [ -z "$output" ]
    CLAVAIN_NEXT_GOAL_RECEIPT_BUDGET_MIN=10 run next_goal_provenance_warning "sess-1" "$(block_only_turn)"
    [[ "$output" == *"STALE"* ]]
}

@test "freshness: the prompt, not the block, is the anchor when both are present" {
    # receipt 20 minutes before the block, but before the prompt: stale
    write_receipt true 2026-09-01T09:45:00Z
    run next_goal_provenance_warning "sess-1" "$(fresh_turn)"
    [[ "$output" == *"STALE"* ]]
}

# ------------------------------------------------- every warning is logged (f-003)
#
# The plan's own promotion gates ("warning now, error if measured") had no
# measurement. Each emitted warning appends one line to the audit log so the
# question "how often does this fire, and for what" has a data source.

@test "audit log: a flagged block leaves a line naming the warning kind" {
    run next_goal_provenance_warning "sess-1" "$(block_claiming_provenance)"
    [ -f "$CLAVAIN_PROVENANCE_DIR/audit-log.jsonl" ]
    grep -q '"kind":"provenance-missing"' "$CLAVAIN_PROVENANCE_DIR/audit-log.jsonl"
    write_receipt true
    run next_goal_provenance_warning "sess-1" "$(fresh_turn)"
    grep -q '"kind":"provenance-stale"' "$CLAVAIN_PROVENANCE_DIR/audit-log.jsonl"
    [ "$(jq -r 'select(.session=="sess-1") | .session' "$CLAVAIN_PROVENANCE_DIR/audit-log.jsonl" | wc -l | tr -d ' ')" = "2" ]
}

@test "audit log: a quiet audit writes nothing" {
    write_receipt true
    run next_goal_provenance_warning "sess-1" "$(block_claiming_provenance)"
    [ -z "$output" ]
    [ ! -f "$CLAVAIN_PROVENANCE_DIR/audit-log.jsonl" ]
}

# ------------------------------- cited must be a subset of verified (W5)
#
# A clean verify receipt says the IDs IT READ BACK are live. It says nothing
# about an ID the block cites that the verifier was never given, and on
# 2026-09-01 the #1 candidate ("Merge PR #26") carried no ID at all, so there
# was nothing to verify and nothing to re-find next session. Known prefixes
# come from the receipts themselves: roots_ok of the provenance receipt and
# the prefixes of every verified bead. A token with an unknown prefix is not
# accused of being a bead — but on a candidate line with no known ID it is
# named, because "solwend-w46q from a tracker the verifier never reached" is
# exactly the original 2026-08-14 failure.

cited_setup() {
    setup_verify_dir
    write_receipt true    # roots_ok: sylveste, mk
}

@test "cited: flags a cited ID the verifier never saw" {
    cited_setup
    verify_receipt "sess-1" true '[]' '[{"id":"mk-i43y"}]'
    body="$(assistant_line "## Next goal\\n\\n1. Close mk-i43y — nearly done\\n2. Land mk-zzzz — the other one\\n\\n**Recommendation:** 2\\n\\n/goal Land mk-zzzz.")"
    run next_goal_verification_warning "sess-1" "$body"
    [ "$status" -eq 0 ]
    [[ "$output" == *"mk-zzzz"* ]]
    [[ "$output" == *"never saw"* ]]
    rm -rf "$VERIFY_DIR"
}

@test "cited: silent when every cited ID is in the receipt" {
    cited_setup
    verify_receipt "sess-1" true '[]' '[{"id":"mk-i43y"},{"id":"sylveste-7t3n"}]'
    body="$(assistant_line "## Next goal\\n\\n1. Close mk-i43y — nearly done\\n2. Finish sylveste-7t3n — shape rules\\n\\n**Recommendation:** 1\\n\\n/goal Close mk-i43y.")"
    run next_goal_verification_warning "sess-1" "$body"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
    rm -rf "$VERIFY_DIR"
}

@test "cited: flags an ID-less candidate in a non-degraded block (the merge-PR-#26 case)" {
    cited_setup
    verify_receipt "sess-1" true '[]' '[{"id":"mk-i43y"}]'
    body="$(assistant_line "## Next goal\\n\\n1. **Merge PR #26** — lands the close protocol\\n2. Close mk-i43y — nearly done\\n\\n**Recommendation:** 1\\n\\n/goal Merge PR #26 so the protocol lands.")"
    run next_goal_verification_warning "sess-1" "$body"
    [ "$status" -eq 0 ]
    [[ "$output" == *"candidate 1"* ]]
    [[ "$output" == *"no tracker ID"* ]]
    [[ "$output" != *"candidate 2"* ]]
    rm -rf "$VERIFY_DIR"
}

@test "cited: an ID-less candidate is fine when the block discloses degradation" {
    cited_setup
    verify_receipt "sess-1" true '[]' '[]'
    body="$(assistant_line "## Next goal\\n\\nno tracker reachable — improvised from session context.\\n\\n1. **Merge PR #26** — lands the close protocol\\n\\n/goal Merge PR #26.")"
    run next_goal_verification_warning "sess-1" "$body"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
    rm -rf "$VERIFY_DIR"
}

@test "cited: IDs mentioned outside the block region are not cited" {
    cited_setup
    verify_receipt "sess-1" true '[]' '[{"id":"mk-i43y"}]'
    body="$(assistant_line "Earlier I looked at mk-qqqq and set it aside.\\n\\n## Next goal\\n\\n1. Close mk-i43y — nearly done\\n\\n/goal Close mk-i43y.")"
    run next_goal_verification_warning "sess-1" "$body"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
    rm -rf "$VERIFY_DIR"
}

@test "cited: an unknown-prefix token on an ID-less candidate is named as a hint, not accused" {
    cited_setup
    verify_receipt "sess-1" true '[]' '[{"id":"mk-i43y"}]'
    body="$(assistant_line "## Next goal\\n\\n1. Continue solwend-w46q — the scene slice\\n2. Close mk-i43y — nearly done\\n\\n/goal Continue solwend-w46q.")"
    run next_goal_verification_warning "sess-1" "$body"
    [ "$status" -eq 0 ]
    [[ "$output" == *"candidate 1"* ]]
    [[ "$output" == *"solwend-w46q"* ]]
    [[ "$output" == *"never reached"* ]]
    [[ "$output" != *"never saw"* ]]
    rm -rf "$VERIFY_DIR"
}

@test "cited: a branch name or hyphenated phrase is not an ID" {
    cited_setup
    verify_receipt "sess-1" true '[]' '[{"id":"mk-i43y"}]'
    body="$(assistant_line "## Next goal\\n\\n1. Close mk-i43y on fix/mk-hxgi-next-goal-audit — the next-goal audit, plan-clavain-hxgi.md\\n\\n/goal Close mk-i43y.")"
    run next_goal_verification_warning "sess-1" "$body"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
    rm -rf "$VERIFY_DIR"
}

@test "cited: the id-token helper keeps child suffixes and drops trailing punctuation" {
    # "next-goal" alone fits the grammar (which is why prefixes are filtered
    # against the receipts); "next-goal-audit" and "fix/mk-hxgi-next" do not.
    run next_goal_id_tokens "see mk-i43y, mk-i43y.2 and (sylveste-7t3n). Not fix/mk-hxgi-next or v0.2.86 or next-goal-audit, but next-goal."
    [ "$status" -eq 0 ]
    [ "$output" = "$(printf 'mk-i43y\nmk-i43y.2\nsylveste-7t3n\nnext-goal')" ]
}

# ------------------------------------------- end to end through the hook (f-002)

@test "hook surfaces a cited-but-unverified ID end to end" {
    cited_setup
    verify_receipt "sess-1" true '[]' '[{"id":"mk-i43y"}]'
    body="$(assistant_line "## Next goal\\n\\n1. Close mk-i43y — nearly done\\n2. Land mk-zzzz — the other one\\n\\n/goal Land mk-zzzz.")"
    run run_stop_hook "$body" "sess-1"
    [ "$status" -eq 0 ]
    [[ "$output" == *'"decision"'* ]]
    [[ "$output" == *"Next-goal verification"* ]]
    [[ "$output" == *"mk-zzzz"* ]]
    rm -rf "$VERIFY_DIR"
}

@test "hook surfaces a stale provenance receipt end to end" {
    write_receipt true    # 2026-08-07, weeks before the turn below
    run run_stop_hook "$(fresh_turn)" "sess-1"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Next-goal provenance: STALE"* ]]
}

# ---------------------------------------------------- the hook budget (f-018)

@test "timing: the full audit path stays inside the hook budget on an 80-line window" {
    cited_setup
    verify_receipt "sess-1" true '[]' '[{"id":"mk-i43y"}]'
    body=""
    for i in $(seq 1 78); do
        body+="$(assistant_line "Filler line $i mentioning mk-i43y and the next steps, with a /goal-looking token inline.")"$'\n'
    done
    body+="$(block_claiming_provenance)"
    start=$(date +%s)
    run run_stop_hook "$body" "sess-timing"
    end=$(date +%s)
    [ "$status" -eq 0 ]
    [ $((end - start)) -le 4 ]
    rm -rf "$VERIFY_DIR"
}
