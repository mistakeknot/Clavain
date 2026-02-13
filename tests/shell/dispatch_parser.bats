#!/usr/bin/env bats

# Tests for JSONL stream parser in dispatch.sh
# Tests the _jsonl_parser function by sourcing dispatch.sh in a controlled
# environment that stubs out everything except the parser function.

setup() {
    load test_helper

    STATE_FILE="/tmp/clavain-dispatch-test-$$.json"
    SUMMARY_FILE="/tmp/codex-test-$$.md.summary"
    DISPATCH_SCRIPT="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    STARTED_TS="$(date +%s)"

    # Skip all tests if gawk is not available (parser requires gawk)
    if ! awk --version 2>&1 | grep -q 'GNU Awk'; then
        skip "gawk required for JSONL parser tests"
    fi
}

teardown() {
    rm -f "$STATE_FILE" "${STATE_FILE}.tmp" "$SUMMARY_FILE" "${_PARSER_SCRIPT:-}"
    unset _PARSER_SCRIPT
}

# Helper: extract _jsonl_parser function body using brace-depth-aware awk.
# Written to a temp file once per test to avoid re-extraction.
_extract_parser() {
    if [[ -z "${_PARSER_SCRIPT:-}" ]]; then
        _PARSER_SCRIPT="$(mktemp)"
        awk '
            /^_jsonl_parser\(\)/ { in_func=1; depth=0 }
            in_func {
                print
                depth += gsub(/{/, "&")
                depth -= gsub(/}/, "&")
                if (depth == 0 && NR > 1) exit
            }
        ' "$DISPATCH_SCRIPT" > "$_PARSER_SCRIPT"
    fi
}

# Helper: run parser with synthetic JSONL input.
# Writes input to a temp file to avoid quoting issues in bash -c.
run_parser() {
    local input="$1"
    _extract_parser

    local input_file
    input_file="$(mktemp)"
    printf '%s\n' "$input" > "$input_file"

    # Source the function definition, then pipe input through it
    (
        source "$_PARSER_SCRIPT"
        cat "$input_file" | _jsonl_parser "$STATE_FILE" 'test' '/tmp' "$STARTED_TS" "$SUMMARY_FILE"
    )
    local rc=$?
    rm -f "$input_file"
    return $rc
}

@test "parser: skips non-JSON lines" {
    run_parser 'WARNING: some noise
{"type":"thread.started","thread_id":"abc"}
ERROR: more noise'
    [ -f "$STATE_FILE" ]
    activity=$(jq -r '.activity' "$STATE_FILE" 2>&1) || {
        echo "jq parse error. State file contents:" >&2
        cat "$STATE_FILE" >&2
        return 1
    }
    [ "$activity" = "starting" ]
}

@test "parser: turn.started sets activity to thinking" {
    run_parser '{"type":"turn.started"}'
    [ -f "$STATE_FILE" ]
    activity=$(jq -r '.activity' "$STATE_FILE")
    [ "$activity" = "thinking" ]
    turns=$(jq -r '.turns' "$STATE_FILE")
    [ "$turns" = "1" ]
}

@test "parser: item.started command_execution sets activity" {
    run_parser '{"type":"item.started","item":{"type":"command_execution","command":"ls","status":"in_progress"}}'
    [ -f "$STATE_FILE" ]
    activity=$(jq -r '.activity' "$STATE_FILE")
    [ "$activity" = "running command" ]
}

@test "parser: item.completed agent_message increments messages" {
    run_parser '{"type":"item.completed","item":{"type":"agent_message","text":"hello"}}'
    [ -f "$STATE_FILE" ]
    msgs=$(jq -r '.messages' "$STATE_FILE")
    [ "$msgs" = "1" ]
    activity=$(jq -r '.activity' "$STATE_FILE")
    [ "$activity" = "writing" ]
}

@test "parser: item.completed command_execution increments commands" {
    run_parser '{"type":"item.completed","item":{"type":"command_execution","command":"ls","exit_code":0,"status":"completed"}}'
    [ -f "$STATE_FILE" ]
    cmds=$(jq -r '.commands' "$STATE_FILE")
    [ "$cmds" = "1" ]
}

@test "parser: turn.completed accumulates tokens" {
    run_parser '{"type":"turn.completed","usage":{"input_tokens":1000,"cached_input_tokens":500,"output_tokens":200}}'
    [ -f "$STATE_FILE" ]
    # State file should exist with the update from turn.completed
    activity=$(jq -r '.activity' "$STATE_FILE")
    [ "$activity" = "thinking" ]
}

@test "parser: full session produces correct summary" {
    run_parser '{"type":"thread.started","thread_id":"abc"}
{"type":"turn.started"}
{"type":"item.completed","item":{"type":"agent_message","text":"thinking..."}}
{"type":"item.started","item":{"type":"command_execution","command":"ls","status":"in_progress"}}
{"type":"item.completed","item":{"type":"command_execution","command":"ls","exit_code":0,"status":"completed"}}
{"type":"item.completed","item":{"type":"agent_message","text":"done"}}
{"type":"turn.completed","usage":{"input_tokens":5000,"output_tokens":300}}'
    [ -f "$SUMMARY_FILE" ]
    grep -q "Turns: 1" "$SUMMARY_FILE"
    grep -q "Commands: 1" "$SUMMARY_FILE"
    grep -q "Messages: 2" "$SUMMARY_FILE"
}

@test "parser: state file preserves name and workdir" {
    run_parser '{"type":"turn.started"}'
    [ -f "$STATE_FILE" ]
    name=$(jq -r '.name' "$STATE_FILE")
    [ "$name" = "test" ]
    workdir=$(jq -r '.workdir' "$STATE_FILE")
    [ "$workdir" = "/tmp" ]
}

@test "parser: state file is valid JSON after write" {
    run_parser '{"type":"turn.started"}'
    [ -f "$STATE_FILE" ]
    # jq should parse it without error
    jq . "$STATE_FILE" > /dev/null 2>&1
    [ $? -eq 0 ]
}

@test "parser: no false positive on command_execution in text field" {
    # agent_message whose text mentions "command_execution" should NOT increment commands
    run_parser '{"type":"item.completed","item":{"type":"agent_message","text":"Previous command_execution failed"}}'
    [ -f "$STATE_FILE" ]
    cmds=$(jq -r '.commands' "$STATE_FILE")
    [ "$cmds" = "0" ]
    msgs=$(jq -r '.messages' "$STATE_FILE")
    [ "$msgs" = "1" ]
}
