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

# Write a tool payload: t_mk EVENT TOOL INPUT_JSON [SESSION] [AGENT_ID]
t_mk() {
    jq -nc --arg e "$1" --arg t "$2" --argjson i "$3" --arg s "${4:-s1}" --arg tp "$TRANSCRIPT" --arg a "${5:-}" \
        '{session_id:$s, hook_event_name:$e, tool_name:$t, tool_input:$i, transcript_path:$tp}
         + (if $a != "" then {agent_id:$a} else {} end)' > "$PAYLOAD"
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
# t_no_secret TEXT — fail if TEXT appears anywhere in the store (rows and
# state), in any letter case.
t_no_secret() {
    run grep -rqiF -- "$1" "$CLAVAIN_CONTEXT_RESET_DIR"
    [ "$status" -ne 0 ] || { echo "secret $1 leaked into the store"; return 1; }
}

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
        'git -C "my repo" push origin main'
        '/usr/bin/git push'
        'env GIT_TRACE=1 git push'
        'GIT_SSH_COMMAND=ssh git push origin'
        "bash -c 'git push origin main'"
        'timeout 30 git push'
        'sudo -u deploy git push'
        'cd repo && git push'
        $'git commit -m "$(cat <<\'EOF\'\nDon\'t stop\nEOF\n)" && git push'
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

@test "context-reset: ssh remote commands expose and an unresolved curl --url is a gap" {
    t_start startup
    t_bash_post 'ssh host.example cat /tmp/remote-output.txt'
    [ "$(t_count exposure)" -eq 1 ]
    [ "$(t_last exposure | jq -r .host)" = "host.example" ]
    [ "$(t_last exposure | jq -r .source_class)" = "remote-command" ]
    t_start startup
    t_bash_post 'curl --silent --url "$FETCH_URL"'
    [ "$(t_count coverage_gap)" -eq 1 ]
    [ "$(t_last coverage_gap | jq -r .kind)" = "unresolved-url" ]
    [ "$(t_last coverage_gap | jq -r .surface)" = "exposure" ]
    [ "$(t_count exposure)" -eq 1 ]
    t_bash_pre 'git push'
    [ "$(t_last would_be_reset | jq -r .exposure)" = "unknown" ]
}

@test "context-reset: credentials around an & in a URL are never logged" {
    t_start startup
    t_bash_post 'curl "https://review_secret_123:pw&suffix@api.example.com/data"'
    [ "$(t_count exposure)" -eq 1 ]
    [ "$(t_last exposure | jq -r .host)" = "<redacted-url>" ]
    t_start startup
    t_bash_post 'curl https://review_secret_456:pw&suffix@api.example.com/data'
    [ "$(t_count exposure)" -eq 2 ]
    [ "$(t_last exposure | jq -r .host)" = "<redacted-url>" ]
    t_start startup
    t_bash_post 'curl https://reviewsecret789:1234&suffix@api.example.com/data'
    [ "$(t_count exposure)" -eq 3 ]
    [ "$(t_last exposure | jq -r .host)" = "<redacted-url>" ]
    t_no_secret review_secret
    t_no_secret reviewsecret789
}

@test "context-reset: credentials cut by \$(...) in a URL are never logged" {
    t_start startup
    t_bash_post 'curl "https://TOKEN123:$(printf x)@api.example.com/"'
    [ "$(t_count exposure)" -eq 1 ]
    [ "$(t_last exposure | jq -r .host)" = "<redacted-url>" ]
    t_start startup
    t_bash_post 'curl "https://TOKEN124:1234$(printf x)@api.example.com/"'
    [ "$(t_last exposure | jq -r .host)" = "<redacted-url>" ]
    t_start startup
    t_bash_post "bash -c \"curl https://TOKEN125:1234\$(printf x)@api.example.com/\""
    t_no_secret TOKEN123
    t_no_secret TOKEN124
    t_no_secret TOKEN125
}

@test "context-reset: credentials cut by backticks in a URL are never logged" {
    t_start startup
    t_bash_post 'curl "https://TOKEN123:`printf x`@api.example.com/"'
    [ "$(t_count exposure)" -eq 1 ]
    [ "$(t_last exposure | jq -r .host)" = "<redacted-url>" ]
    t_start startup
    t_bash_post 'curl https://TOKEN124:1234`printf x`@api.example.com/'
    [ "$(t_last exposure | jq -r .host)" = "<redacted-url>" ]
    t_no_secret TOKEN123
    t_no_secret TOKEN124
}

@test "context-reset: credentials around \${VAR} in a URL are never logged" {
    t_start startup
    t_bash_post 'curl "https://TOKEN123:${SUFFIX}@api.example.com/"'
    [ "$(t_count exposure)" -eq 1 ]
    [ "$(t_last exposure | jq -r .host)" = "<redacted-url>" ]
    t_start startup
    t_bash_post 'curl https://TOKEN124:1234${SUFFIX}'
    t_no_secret TOKEN123
    t_no_secret TOKEN124
}

@test "context-reset: an @ after the authority redacts the URL" {
    t_start startup
    t_bash_post 'curl "https://TOKEN123:pa/ss@api.example.com/"'
    [ "$(t_count exposure)" -eq 1 ]
    [ "$(t_last exposure | jq -r .host)" = "<redacted-url>" ]
    t_start startup
    t_bash_post 'curl "https://TOKEN124:12?x@api.example.com/"'
    [ "$(t_last exposure | jq -r .host)" = "<redacted-url>" ]
    t_start startup
    t_post WebFetch '{"url":"https://TOKEN125:pa/ss@api.example.com/"}'
    [ "$(t_last exposure | jq -r .host)" = "<redacted-url>" ]
    t_no_secret TOKEN123
    t_no_secret TOKEN124
    t_no_secret TOKEN125
}

@test "context-reset: payload URLs that do not parse clean are redacted" {
    t_start startup
    t_post WebFetch '{"url":"https://TOKEN123:$(x)@api.example.com/"}'
    [ "$(t_last exposure | jq -r .host)" = "<redacted-url>" ]
    t_start startup
    t_post WebFetch '{"url":"https://TOKEN124:"}'
    [ "$(t_last exposure | jq -r .host)" = "<redacted-url>" ]
    t_start startup
    t_post mcp__playwright__browser_navigate '{"url":"https://TOKEN125:`x`@example.com/"}'
    [ "$(t_last exposure | jq -r .host)" = "<redacted-url>" ]
    t_start startup
    t_post WebFetch '{"url":"https://user:TOKEN126@api.example.com/"}'
    [ "$(t_last exposure | jq -r .host)" = "api.example.com" ]
    t_no_secret TOKEN123
    t_no_secret TOKEN124
    t_no_secret TOKEN125
    t_no_secret TOKEN126
}

@test "context-reset: curl --url credentials are never logged" {
    t_start startup
    t_bash_post 'curl --url "https://TOKEN123:$(printf x)@api.example.com/"'
    [ "$(t_count exposure)" -eq 1 ]
    [ "$(t_last exposure | jq -r .host)" = "<redacted-url>" ]
    t_start startup
    t_bash_post 'curl --url "https://TOKEN124:pw@api.example.com/"'
    [ "$(t_last exposure | jq -r .host)" = "api.example.com" ]
    t_start startup
    t_bash_post 'curl --url=https://TOKEN125:1234`printf x`@api.example.com/'
    [ "$(t_last exposure | jq -r .host)" = "<redacted-url>" ]
    t_no_secret TOKEN123
    t_no_secret TOKEN124
    t_no_secret TOKEN125
}

@test "context-reset: credentials in a push URL are never logged" {
    t_start startup
    t_bash_pre 'git push https://user:SECRET456@github.com/o/r.git main'
    [ "$(t_count approval_clean)" -eq 1 ]
    t_bash_pre 'git push "https://user:SECRET789$(printf x)@github.com/o/r.git" main'
    [ "$(t_count approval_clean)" -eq 2 ]
    t_bash_post 'git push "https://SECRET790:1234$(printf x)@github.com/o/r.git" main'
    t_no_secret SECRET456
    t_no_secret SECRET789
    t_no_secret SECRET790
}

@test "context-reset: ssh destinations never log the user part" {
    t_start startup
    t_bash_post 'ssh SSHSECRET88@host.example.com true'
    [ "$(t_count exposure)" -eq 1 ]
    [ "$(t_last exposure | jq -r .host)" = "host.example.com" ]
    t_start startup
    t_bash_post 'ssh "SSHSECRET77$(printf x)@host.example.com" true'
    [ "$(t_count exposure)" -eq 2 ]
    [ "$(t_last exposure | jq -r .host)" = "<redacted-url>" ]
    t_start startup
    t_bash_post 'ssh SSHSECRET99`printf x`@host.example.com true'
    [ "$(t_last exposure | jq -r .host)" = "<redacted-url>" ]
    t_no_secret SSHSECRET88
    t_no_secret SSHSECRET77
    t_no_secret SSHSECRET99
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

@test "context-reset: child agents keep their own state and Task results are uncertain in the parent" {
    t_start startup
    t_post WebFetch '{"url":"https://example.com/"}' s1 child1
    t_pre Bash "$(t_cmd 'git push origin main')" s1 child1
    [ "$(t_count would_be_reset)" -eq 1 ]
    local row
    row=$(t_last would_be_reset)
    [ "$(jq -r .agent <<<"$row")" = "child1" ]
    [ "$(jq -r .exposure <<<"$row")" = "exposed" ]
    [ "$(jq -r .simulated_reset <<<"$row")" = "true" ]
    t_bash_pre 'git push origin main'
    [ "$(t_count approval_clean)" -eq 1 ]
    [ "$(t_last approval_clean | jq -r .agent)" = "" ]
    t_post Task '{"description":"d","prompt":"p"}'
    [ "$(t_count exposure_unknown)" -eq 1 ]
    [ "$(t_last exposure_unknown | jq -r .source_class)" = "subagent-result" ]
    t_bash_pre 'git push origin main'
    [ "$(t_count would_be_reset)" -eq 2 ]
    row=$(t_last would_be_reset)
    [ "$(jq -r .agent <<<"$row")" = "" ]
    [ "$(jq -r .exposure <<<"$row")" = "unknown" ]
    [ "$(jq -r .exposure_reason <<<"$row")" = "subagent-result" ]
    [ "$(jq -r .simulated_reset <<<"$row")" = "true" ]
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

@test "context-reset: the first read after compaction logs its own first-in-epoch row" {
    t_start startup
    t_post WebFetch '{"url":"https://example.com/"}'
    t_start compact
    t_post WebFetch '{"url":"https://example.com/b"}'
    [ "$(t_count exposure)" -eq 2 ]
    local row
    row=$(t_last exposure)
    [ "$(jq -r .epoch <<<"$row")" -eq 2 ]
    [ "$(jq -r .first_in_epoch <<<"$row")" = "true" ]
    [ "$(jq -r .prior_exposure <<<"$row")" = "exposed" ]
    [ "$(jq -r .carried <<<"$row")" = "true" ]
    t_post WebSearch '{"query":"q"}'
    [ "$(t_count exposure)" -eq 2 ]
    run --separate-stderr bash "$REPORT" --json
    [ "$status" -eq 0 ]
    [ "$(jq -r .exposure_epochs <<<"$output")" -eq 2 ]
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

@test "context-reset: report prices research-triggered resets in the full-mode bound" {
    TRANSCRIPT="$BATS_TEST_TMPDIR/transcript.jsonl"
    printf '%s\n' '{"type":"assistant","message":{"usage":{"input_tokens":10000}}}' > "$TRANSCRIPT"
    t_start startup
    t_post WebFetch '{"url":"https://example.com/"}'
    run --separate-stderr bash "$REPORT" --json
    [ "$status" -eq 0 ]
    [ "$(jq -r .cost.research_batches.input_token_equivalents <<<"$output")" -eq 11500 ]
    [ "$(jq -r .cost.full_mode_upper_bound.input_token_equivalents <<<"$output")" -eq 11500 ]
    [ "$(jq -r .cost.full_mode_upper_bound.resets <<<"$output")" -eq 1 ]
    [ "$(jq -r .resets_per_session.full_mode_upper_bound <<<"$output")" = "1" ]
    run --separate-stderr bash "$REPORT"
    [ "$status" -eq 0 ]
    [[ "$output" == *"full mode (upper bound)"* ]]
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

@test "context-reset: audit reports a missed batch even after an earlier one was logged" {
    local tr="$BATS_TEST_TMPDIR/audit2.jsonl"
    jq -nc '{type:"assistant", sessionId:"aud2",
        message:{content:[range(21) | {type:"tool_use", name:"WebSearch", input:{query:"q"}}]}}' > "$tr"
    t_start startup aud2
    t_post WebSearch '{"query":"q"}' aud2
    run --separate-stderr bash "$AUDIT" --transcript "$tr" --json
    [ "$status" -eq 0 ]
    [ "$(jq -r .logged.exposure <<<"$output")" -eq 1 ]
    [ "$(jq -r .expected.exposure_batches <<<"$output")" -eq 2 ]
    [ "$(jq -r .missed.exposure <<<"$output")" -eq 1 ]
    local i
    for ((i = 2; i <= 21; i++)); do t_post WebSearch '{"query":"q"}' aud2; done
    run --separate-stderr bash "$AUDIT" --transcript "$tr" --json
    [ "$status" -eq 0 ]
    [ "$(jq -r .missed.exposure <<<"$output")" -eq 0 ]
}

@test "context-reset: audit compares batches per epoch, so a surplus cannot hide a missed epoch" {
    local tr="$BATS_TEST_TMPDIR/audit3.jsonl"
    {
        jq -nc '{type:"assistant", sessionId:"aud3", timestamp:"1970-01-01T00:16:40Z",
            message:{content:[{type:"tool_use", id:"r1", name:"WebFetch", input:{url:"https://example.com/a"}}]}}'
        jq -nc '{type:"user", sessionId:"aud3", timestamp:"1970-01-01T00:16:40Z",
            message:{content:[{type:"tool_result", tool_use_id:"r1", content:"x"}]}}'
        jq -nc '{type:"assistant", sessionId:"aud3", timestamp:"1970-01-01T00:26:30Z",
            message:{content:[{type:"tool_use", id:"r2", name:"WebFetch", input:{url:"https://example.com/b"}}]}}'
        jq -nc '{type:"user", sessionId:"aud3", timestamp:"1970-01-01T00:26:50Z",
            message:{content:[{type:"tool_result", tool_use_id:"r2", content:"x"}]}}'
        jq -nc '{type:"system", subtype:"compact_boundary", sessionId:"aud3"}'
        jq -nc '{type:"assistant", sessionId:"aud3", timestamp:"1970-01-01T00:33:20Z",
            message:{content:[{type:"tool_use", id:"r3", name:"WebFetch", input:{url:"https://example.com/c"}}]}}'
        jq -nc '{type:"user", sessionId:"aud3", timestamp:"1970-01-01T00:33:20Z",
            message:{content:[{type:"tool_result", tool_use_id:"r3", content:"x"}]}}'
    } > "$tr"
    # Reads start at 1000 and 1590 and complete at 1000 and 1610: the hooks log
    # two epoch-1 batches. The epoch-2 read after compaction is not logged.
    t_start startup aud3
    t_post WebFetch '{"url":"https://example.com/a"}' aud3
    export CLAVAIN_CONTEXT_RESET_NOW=1610
    t_post WebFetch '{"url":"https://example.com/b"}' aud3
    [ "$(t_count exposure)" -eq 2 ]
    t_start compact aud3
    run --separate-stderr bash "$AUDIT" --transcript "$tr" --json
    [ "$status" -eq 0 ]
    [ "$(jq -r .logged.exposure <<<"$output")" -eq 2 ]
    [ "$(jq -r .expected.exposure_batches <<<"$output")" -eq 3 ]
    [ "$(jq -r .epochs <<<"$output")" -eq 2 ]
    [ "$(jq -r .missed.exposure <<<"$output")" -eq 1 ]
    export CLAVAIN_CONTEXT_RESET_NOW=2000
    t_post WebFetch '{"url":"https://example.com/c"}' aud3
    run --separate-stderr bash "$AUDIT" --transcript "$tr" --json
    [ "$status" -eq 0 ]
    [ "$(jq -r .missed.exposure <<<"$output")" -eq 0 ]
}

@test "context-reset: audit flags a Task call whose exposure_unknown row is missing" {
    local tr="$BATS_TEST_TMPDIR/audit4.jsonl"
    printf '%s\n' '{"type":"assistant","sessionId":"aud4","message":{"content":[{"type":"tool_use","id":"k1","name":"Task","input":{"description":"d","prompt":"p"}}]}}' > "$tr"
    t_start startup aud4
    run --separate-stderr bash "$AUDIT" --transcript "$tr" --json
    [ "$status" -eq 0 ]
    [ "$(jq -r .expected.subagent_unknown <<<"$output")" -eq 1 ]
    [ "$(jq -r .missed.subagent_unknown <<<"$output")" -eq 1 ]
    [ "$(jq -r .missed.exposure <<<"$output")" -eq 0 ]
    run --separate-stderr bash "$AUDIT" --transcript "$tr" --record
    [ "$status" -eq 0 ]
    [ "$(t_last coverage_gap | jq -r .kind)" = "audit_missed_subagent_unknown" ]
    t_post Task '{"description":"d","prompt":"p"}' aud4
    run --separate-stderr bash "$AUDIT" --transcript "$tr" --json
    [ "$status" -eq 0 ]
    [ "$(jq -r .logged.subagent_unknown <<<"$output")" -eq 1 ]
    [ "$(jq -r .missed.subagent_unknown <<<"$output")" -eq 0 ]
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
             "PostToolUse|Task|{\"prompt\":\"p\"}" \
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
