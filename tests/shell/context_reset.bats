#!/usr/bin/env bats
# Tests for the observe-mode context-reset telemetry (mk-42j9.40):
# hooks/context-reset-pre.sh, hooks/context-reset-post.sh,
# hooks/lib-context-reset.sh and the scripts/context-reset-*.sh tools.
# This is observe-mode hygiene telemetry, NOT a security boundary. These tests
# cover the plan's acceptance table: every hook prints nothing, exits 0, and
# writes only "allow" rows. Each test builds a hook payload with jq and pipes it
# to the hook on stdin. All state lives under $BATS_TEST_TMPDIR.

bats_require_minimum_version 1.5.0

setup() {
    load test_helper
    PRE="$HOOKS_DIR/context-reset-pre.sh"
    POST="$HOOKS_DIR/context-reset-post.sh"
    VERDICT="$CLAUDE_PLUGIN_ROOT/scripts/context-reset-verdict.sh"
    REPORT="$CLAUDE_PLUGIN_ROOT/scripts/context-reset-report.sh"
    AUDIT="$CLAUDE_PLUGIN_ROOT/scripts/context-reset-audit.sh"
    export CLAVAIN_CONTEXT_RESET_DIR="$BATS_TEST_TMPDIR/store"
    export CLAVAIN_CONTEXT_RESET_CONFIG="$BATS_TEST_TMPDIR/context-reset.yaml"
    cp "$CLAUDE_PLUGIN_ROOT/config/context-reset.yaml" "$CLAVAIN_CONTEXT_RESET_CONFIG"
    export CLAVAIN_CONTEXT_RESET_NOW=1000
    unset CLAVAIN_CONTEXT_RESET_MODE CLAVAIN_DISPATCH_ROLE BB_THREAD_ID
    EVENTS="$CLAVAIN_CONTEXT_RESET_DIR/events.jsonl"
    PAYLOAD="$BATS_TEST_TMPDIR/payload.json"
    TRANSCRIPT=""
}

# Write a tool payload: t_mk EVENT TOOL INPUT_JSON [SESSION]
t_mk() {
    jq -nc --arg e "$1" --arg t "$2" --argjson i "$3" --arg s "${4:-s1}" --arg tp "$TRANSCRIPT" \
        '{session_id:$s, hook_event_name:$e, tool_name:$t, tool_input:$i, transcript_path:$tp}' > "$PAYLOAD"
}
# Write a SessionStart payload: t_mk_start SOURCE [SESSION]
t_mk_start() {
    jq -nc --arg src "$1" --arg s "${2:-s1}" --arg tp "$TRANSCRIPT" \
        '{session_id:$s, hook_event_name:"SessionStart", source:$src, transcript_path:$tp}' > "$PAYLOAD"
}
t_start() { t_mk_start "$@"; bash "$POST" < "$PAYLOAD"; }
t_post() { t_mk PostToolUse "$@"; bash "$POST" < "$PAYLOAD"; }
t_pre() { t_mk PreToolUse "$@"; bash "$PRE" < "$PAYLOAD"; }
t_cmd() { jq -nc --arg c "$1" '{command:$c}'; }
t_bash_pre() { t_pre Bash "$(t_cmd "$1")" "${2:-s1}"; }
t_bash_post() { t_post Bash "$(t_cmd "$1")" "${2:-s1}"; }
t_count() {
    if [[ ! -f "$EVENTS" ]]; then echo 0; return 0; fi
    jq -s --arg e "$1" 'map(select(.event == $e)) | length' "$EVENTS"
}
t_rows() {
    if [[ ! -f "$EVENTS" ]]; then echo 0; return 0; fi
    jq -s 'length' "$EVENTS"
}
t_last() { jq -sc --arg e "$1" 'map(select(.event == $e)) | last' "$EVENTS"; }

@test "context-reset: trusted reads write no record" {
    t_start startup
    local before
    before=$(t_rows)
    t_post Read '{"file_path":"README.md"}'
    t_bash_post 'git status'
    t_bash_post 'bd show mk-1'
    t_bash_post 'git log --oneline -5'
    t_bash_post 'grep -rn foo .'
    [ "$(t_count exposure)" -eq 0 ]
    [ "$(t_rows)" -eq "$before" ]
}

@test "context-reset: an external read marks the epoch exposed without logging the URL" {
    t_start startup
    t_post WebFetch '{"url":"https://Example.com/page?token=SECRET123","prompt":"x"}'
    [ "$(t_count exposure)" -eq 1 ]
    local row
    row=$(t_last exposure)
    [ "$(jq -r .host <<<"$row")" = "example.com" ]
    [ "$(jq -r .source_class <<<"$row")" = "web" ]
    [ "$(jq -r .first_in_epoch <<<"$row")" = "true" ]
    [ "$(jq -r .verdict <<<"$row")" = "allow" ]
    [ "$(jq -r .security_boundary <<<"$row")" = "false" ]
    run grep -rq SECRET123 "$CLAVAIN_CONTEXT_RESET_DIR"
    [ "$status" -ne 0 ]
}

@test "context-reset: reads coalesce into one batch until the time window closes" {
    t_start startup
    local i
    for i in 1 2 3; do t_post WebSearch '{"query":"q"}'; done
    [ "$(t_count exposure)" -eq 1 ]
    export CLAVAIN_CONTEXT_RESET_NOW=1601
    t_post WebFetch '{"url":"https://a.example.org/"}'
    [ "$(t_count exposure)" -eq 2 ]
    [ "$(t_last exposure | jq -r .batch)" -eq 2 ]
    [ "$(t_last exposure | jq -r .first_in_epoch)" = "false" ]
}

@test "context-reset: the 21st read opens a second batch" {
    t_start startup
    local i
    for ((i = 1; i <= 21; i++)); do t_post WebSearch '{"query":"q"}'; done
    [ "$(t_count exposure)" -eq 2 ]
    [ "$(t_last exposure | jq -r .prev_batch_reads)" -eq 20 ]
}

@test "context-reset: approval action while exposed logs a would-be reset and proceeds" {
    t_start startup
    t_post WebFetch '{"url":"https://example.com/"}'
    t_mk PreToolUse Bash "$(t_cmd 'git push origin main')"
    run --separate-stderr bash "$PRE" < "$PAYLOAD"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
    [ "$(t_count would_be_reset)" -eq 1 ]
    local row
    row=$(t_last would_be_reset)
    [ "$(jq -r .exposure <<<"$row")" = "exposed" ]
    [ "$(jq -r .family <<<"$row")" = "remote-source-change" ]
    [ "$(jq -r .verdict <<<"$row")" = "allow" ]
    [ "$(jq -r .enforced <<<"$row")" = "false" ]
    [ "$(jq -r .would_be_reset <<<"$row")" = "true" ]
    [ "$(jq -r .simulated_reset <<<"$row")" = "true" ]
}

@test "context-reset: approval action with no session record counts as unknown" {
    t_mk PreToolUse Bash "$(t_cmd 'gh pr create --title t --body b')"
    run --separate-stderr bash "$PRE" < "$PAYLOAD"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
    local row
    row=$(t_last would_be_reset)
    [ "$(jq -r .exposure <<<"$row")" = "unknown" ]
    [ "$(jq -r .family <<<"$row")" = "pr-publication" ]
    [ "$(jq -r .exposure_reason <<<"$row")" = "no-session-start-record" ]
}

@test "context-reset: approval action while clean is logged separately" {
    t_start startup
    t_bash_pre 'git push origin main'
    [ "$(t_count approval_clean)" -eq 1 ]
    [ "$(t_count would_be_reset)" -eq 0 ]
    [ "$(t_last approval_clean | jq -r .would_be_reset)" = "false" ]
    [ "$(t_last approval_clean | jq -r .exposure)" = "clean" ]
}

@test "context-reset: approval command forms are recognized" {
    local c
    local -a forms=(
        'git -C repo push origin main'
        '/usr/bin/git push'
        'env GIT_TRACE=1 git push'
        'GIT_SSH_COMMAND=ssh git push origin'
        "bash -c 'git push origin main'"
        'timeout 30 git push'
        'sudo -u deploy git push'
        'cd repo && git push'
        'ic publish --auto'
        'gh release create v1.2.3'
        './scripts/bump-version.sh 1.2.3'
        'npm publish --access public'
        'gh api -X POST repos/o/r/issues -f title=x'
        'git reset --hard HEAD~1'
        'git clean -fdx'
        'curl -X POST https://api.example.com/hook -d x=1'
    )
    t_start startup
    for c in "${forms[@]}"; do
        rm -f "$EVENTS"
        t_bash_pre "$c"
        [ "$(t_count approval_clean)" -eq 1 ] || { echo "not recognized: $c"; return 1; }
    done
}

@test "context-reset: look-alike commands are not approval actions" {
    t_start startup
    t_post WebFetch '{"url":"https://example.com/"}'
    local c
    for c in 'git commit -m "push later"' 'git push --dry-run' 'gh pr view 12' 'git status' \
             'echo release notes' 'gh api repos/o/r/pulls' 'git clean -n'; do
        t_bash_pre "$c"
    done
    [ "$(t_count would_be_reset)" -eq 0 ]
    [ "$(t_count approval_clean)" -eq 0 ]
    [ "$(t_count coverage_gap)" -eq 0 ]
}

@test "context-reset: unrecognized approval forms increment the gap counter, never clean" {
    local c
    t_start startup
    for c in '$GIT push origin' 'git ls-files | xargs git push' 'make release' './deploy.sh prod'; do
        rm -f "$EVENTS"
        t_bash_pre "$c"
        [ "$(t_count coverage_gap)" -eq 1 ] || { echo "no gap for: $c"; return 1; }
        [ "$(t_last coverage_gap | jq -r .surface)" = "approval" ] || { echo "wrong surface: $c"; return 1; }
        [ "$(t_count approval_clean)" -eq 0 ] || { echo "false clean: $c"; return 1; }
        [ "$(t_count would_be_reset)" -eq 0 ] || { echo "misclassified: $c"; return 1; }
    done
}

@test "context-reset: an unclassified remote URL is a gap and leaves exposure unknown" {
    t_start startup
    t_bash_post 'python3 fetch.py https://example.com/data'
    [ "$(t_count coverage_gap)" -eq 1 ]
    [ "$(t_last coverage_gap | jq -r .kind)" = "unclassified-url" ]
    [ "$(t_last coverage_gap | jq -r .surface)" = "exposure" ]
    [ "$(t_count exposure)" -eq 0 ]
    t_bash_pre 'git push'
    [ "$(t_last would_be_reset | jq -r .exposure)" = "unknown" ]
}

@test "context-reset: malformed stdin fails open and records a hook_error" {
    printf 'not json\n' > "$PAYLOAD"
    run --separate-stderr bash "$PRE" < "$PAYLOAD"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
    run --separate-stderr bash "$POST" < "$PAYLOAD"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
    [ "$(t_count hook_error)" -eq 2 ]
}

@test "context-reset: a hung recorder times out, the hook exits 0 and says NOT recorded" {
    command -v timeout >/dev/null 2>&1 || skip "timeout(1) not available"
    local fake="$BATS_TEST_TMPDIR/fakeroot"
    mkdir -p "$fake/scripts"
    printf '#!/usr/bin/env bash\nexec sleep 30\n' > "$fake/scripts/context-reset-verdict.sh"
    export CLAUDE_PLUGIN_ROOT="$fake"
    t_mk PostToolUse WebFetch '{"url":"https://example.com/"}'
    local t0=$SECONDS
    run --separate-stderr bash "$POST" < "$PAYLOAD"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
    [ $((SECONDS - t0)) -lt 8 ]
    [[ "$stderr" == *"NOT recorded"* ]]
}

@test "context-reset: an unwritable store fails open and says NOT recorded" {
    printf 'x' > "$BATS_TEST_TMPDIR/afile"
    export CLAVAIN_CONTEXT_RESET_DIR="$BATS_TEST_TMPDIR/afile/store"
    t_mk PostToolUse WebFetch '{"url":"https://example.com/"}'
    run --separate-stderr bash "$POST" < "$PAYLOAD"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
    [[ "$stderr" == *"NOT recorded"* ]]
}

@test "context-reset: the verdict script always allows" {
    run --separate-stderr bash "$VERDICT" --store "$BATS_TEST_TMPDIR/v" <<<'{"event":"x"}'
    [ "$status" -eq 0 ]
    [ "$(jq -r .decision <<<"$output")" = "allow" ]
    [ "$(jq -r .recorded <<<"$output")" = "true" ]
    run --separate-stderr bash "$VERDICT" --store "$BATS_TEST_TMPDIR/v" <<<'garbage'
    [ "$status" -eq 0 ]
    [ "$(jq -r .decision <<<"$output")" = "allow" ]
    printf 'x' > "$BATS_TEST_TMPDIR/afile"
    run --separate-stderr bash "$VERDICT" --store "$BATS_TEST_TMPDIR/afile/v" <<<'{"event":"x"}'
    [ "$status" -eq 0 ]
    [ "$(jq -r .decision <<<"$output")" = "allow" ]
    [ "$(jq -r .recorded <<<"$output")" = "false" ]
    [[ "$stderr" == *"NOT recorded"* ]]
}

@test "context-reset: approval and full modes log an error and record nothing" {
    local m
    for m in approval full; do
        rm -rf "$CLAVAIN_CONTEXT_RESET_DIR"
        export CLAVAIN_CONTEXT_RESET_MODE="$m"
        t_mk_start startup
        run --separate-stderr bash "$POST" < "$PAYLOAD"
        [ "$status" -eq 0 ]
        [ -z "$output" ]
        [[ "$stderr" == *"not implemented"* ]]
        [[ "$stderr" == *"NOT a security boundary"* ]]
        t_mk PreToolUse Bash "$(t_cmd 'git push')"
        run --separate-stderr bash "$PRE" < "$PAYLOAD"
        [ "$status" -eq 0 ]
        [ -z "$output" ]
        [ ! -e "$EVENTS" ]
    done
    unset CLAVAIN_CONTEXT_RESET_MODE
    printf 'mode: full\n' > "$CLAVAIN_CONTEXT_RESET_CONFIG"
    t_mk_start startup
    run --separate-stderr bash "$POST" < "$PAYLOAD"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
    [[ "$stderr" == *"not implemented"* ]]
    [ ! -e "$EVENTS" ]
}

@test "context-reset: off mode records nothing, even for malformed input" {
    export CLAVAIN_CONTEXT_RESET_MODE=off
    printf 'not json\n' > "$PAYLOAD"
    run --separate-stderr bash "$POST" < "$PAYLOAD"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
    t_start startup
    t_post WebFetch '{"url":"https://example.com/"}'
    t_bash_pre 'git push'
    [ ! -e "$EVENTS" ]
}

@test "context-reset: curl to local hosts is trusted, remote reads expose, remote POST is publication" {
    t_start startup
    t_bash_post 'curl -s http://localhost:8080/health'
    t_bash_post 'curl -s http://127.0.0.1:3311/x'
    [ "$(t_count exposure)" -eq 0 ]
    t_bash_post 'curl -s https://api.example.com/v1/items'
    [ "$(t_count exposure)" -eq 1 ]
    [ "$(t_last exposure | jq -r .host)" = "api.example.com" ]
    [ "$(t_last exposure | jq -r .source_class)" = "remote-command" ]
    t_bash_pre 'curl -X POST https://api.example.com/v1/items -d x=1'
    [ "$(t_last would_be_reset | jq -r .family)" = "external-publication" ]
    t_bash_pre 'curl -X POST http://localhost:8080/x'
    [ "$(t_count would_be_reset)" -eq 1 ]
}

@test "context-reset: MCP reads expose unless exempt; MCP writes are approval actions" {
    sed 's/^exempt_mcp_servers:.*/exempt_mcp_servers: [qmd]/' \
        "$CLAUDE_PLUGIN_ROOT/config/context-reset.yaml" > "$CLAVAIN_CONTEXT_RESET_CONFIG"
    t_start startup
    t_post mcp__qmd__search '{"query":"x"}'
    [ "$(t_count exposure)" -eq 0 ]
    t_post mcp__context7__get-library-docs '{"libraryID":"x"}'
    [ "$(t_count exposure)" -eq 1 ]
    [ "$(t_last exposure | jq -r .source_class)" = "mcp" ]
    t_start startup
    t_post mcp__playwright__browser_navigate '{"url":"https://example.com"}'
    [ "$(t_last exposure | jq -r .source_class)" = "browser" ]
    t_pre mcp__github__create_pull_request '{}'
    [ "$(t_last would_be_reset | jq -r .family)" = "pr-publication" ]
    t_pre mcp__github__list_releases '{}'
    [ "$(t_count would_be_reset)" -eq 1 ]
    [ "$(t_count approval_clean)" -eq 0 ]
}

@test "context-reset: uncovered child agents make exposure unknown" {
    t_start startup
    t_bash_post 'scripts/dispatch.sh --role review --prompt-file p.md'
    [ "$(t_count exposure_unknown)" -eq 1 ]
    t_bash_post 'codex exec summarise'
    [ "$(t_count exposure_unknown)" -eq 1 ]
    t_bash_pre 'git push'
    [ "$(t_last would_be_reset | jq -r .exposure)" = "unknown" ]
    [ "$(t_last would_be_reset | jq -r .exposure_reason)" = "child-uncovered" ]
    t_start startup
    t_bash_post 'codex exec summarise'
    [ "$(t_count exposure_unknown)" -eq 2 ]
}

@test "context-reset: session sources open, carry, or keep epochs" {
    t_start startup
    t_post WebFetch '{"url":"https://example.com/"}'
    t_start compact
    local row
    row=$(t_last session_start)
    [ "$(jq -r .epoch <<<"$row")" -eq 2 ]
    [ "$(jq -r .exposure <<<"$row")" = "exposed" ]
    [ "$(jq -r .reason <<<"$row")" = "compact-carried" ]
    t_start resume
    row=$(t_last session_start)
    [ "$(jq -r .epoch <<<"$row")" -eq 2 ]
    [ "$(jq -r .exposure <<<"$row")" = "exposed" ]
    t_start startup
    row=$(t_last session_start)
    [ "$(jq -r .epoch <<<"$row")" -eq 3 ]
    [ "$(jq -r .exposure <<<"$row")" = "clean" ]
    t_start resume s2
    row=$(t_last session_start)
    [ "$(jq -r .exposure <<<"$row")" = "unknown" ]
    [ "$(jq -r .reason <<<"$row")" = "resume-without-record" ]
}

@test "context-reset: report counts resets and prices them at H x (write - read)" {
    TRANSCRIPT="$BATS_TEST_TMPDIR/transcript.jsonl"
    printf '%s\n' '{"type":"assistant","message":{"usage":{"input_tokens":1000,"cache_read_input_tokens":90000,"cache_creation_input_tokens":9000}}}' > "$TRANSCRIPT"
    t_start startup
    t_post WebFetch '{"url":"https://example.com/"}'
    t_bash_pre 'git push origin main'
    t_bash_pre 'gh pr create -t x'
    run --separate-stderr bash "$REPORT" --json
    [ "$status" -eq 0 ]
    [ "$(jq -r .sessions <<<"$output")" -eq 1 ]
    [ "$(jq -r .research_batches <<<"$output")" -eq 1 ]
    [ "$(jq -r .would_be_resets.exposed <<<"$output")" -eq 2 ]
    [ "$(jq -r .simulated_approval_resets <<<"$output")" -eq 1 ]
    [ "$(jq -r .cost.approval_mode.input_token_equivalents <<<"$output")" -eq 115000 ]
    [ "$(jq -r .cost.all_would_be_resets.input_token_equivalents <<<"$output")" -eq 230000 ]
    [ "$(jq -r .security_boundary <<<"$output")" = "false" ]
    run --separate-stderr bash "$REPORT"
    [ "$status" -eq 0 ]
    [[ "$output" == *"NOT a security boundary"* ]]
}

@test "context-reset: audit finds unlogged calls and --record is idempotent" {
    local tr="$BATS_TEST_TMPDIR/audit.jsonl"
    printf '%s\n' '{"type":"assistant","sessionId":"aud1","message":{"content":[{"type":"tool_use","name":"WebFetch","input":{"url":"https://example.com/"}},{"type":"tool_use","name":"Bash","input":{"command":"git push origin main"}}]}}' > "$tr"
    run --separate-stderr bash "$AUDIT" --transcript "$tr" --json
    [ "$status" -eq 0 ]
    [ "$(jq -r .session <<<"$output")" = "aud1" ]
    [ "$(jq -r .missed.exposure <<<"$output")" -eq 1 ]
    [ "$(jq -r .missed.approval <<<"$output")" -eq 1 ]
    run --separate-stderr bash "$AUDIT" --transcript "$tr" --record
    [ "$status" -eq 0 ]
    run --separate-stderr bash "$AUDIT" --transcript "$tr" --record
    [ "$status" -eq 0 ]
    [ "$(t_count coverage_gap)" -eq 2 ]
    run --separate-stderr bash "$REPORT" --json
    [ "$(jq -r .coverage_gaps.total <<<"$output")" -eq 2 ]
}

@test "context-reset: credentials in a push URL are never logged" {
    t_start startup
    t_bash_pre 'git push https://user:SECRET456@github.com/o/r.git main'
    [ "$(t_count approval_clean)" -eq 1 ]
    run grep -rq SECRET456 "$CLAVAIN_CONTEXT_RESET_DIR"
    [ "$status" -ne 0 ]
}

@test "context-reset: rows carry the dispatch role and the report splits by role and mode" {
    export CLAVAIN_DISPATCH_ROLE=review
    t_start startup
    t_bash_pre 'git push'
    run --separate-stderr bash "$REPORT" --json
    [ "$status" -eq 0 ]
    [ "$(jq -r '.by_role.review.approval_actions_clean' <<<"$output")" -eq 1 ]
    [ "$(jq -r '.by_mode.observe.session_starts' <<<"$output")" -eq 1 ]
}

@test "context-reset: no case prints to stdout and every row is allow" {
    t_start startup
    local p
    for p in "PostToolUse|WebFetch|{\"url\":\"https://example.com/\"}" \
             "PreToolUse|Bash|{\"command\":\"git push\"}" \
             "PreToolUse|Bash|{\"command\":\"make release\"}" \
             "PostToolUse|Bash|{\"command\":\"codex exec x\"}" \
             "PreToolUse|Skill|{\"skill\":\"interpub:release\"}" \
             "PreToolUse|mcp__github__merge_pull_request|{}"; do
        IFS='|' read -r ev tool input <<<"$p"
        t_mk "$ev" "$tool" "$input"
        if [[ "$ev" == PreToolUse ]]; then
            run --separate-stderr bash "$PRE" < "$PAYLOAD"
        else
            run --separate-stderr bash "$POST" < "$PAYLOAD"
        fi
        [ "$status" -eq 0 ] || { echo "nonzero for $p"; return 1; }
        [ -z "$output" ] || { echo "stdout for $p: $output"; return 1; }
    done
    [ "$(jq -s 'all(.verdict == "allow")' "$EVENTS")" = "true" ]
    [ "$(jq -s 'all(.security_boundary == false)' "$EVENTS")" = "true" ]
}
