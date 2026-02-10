#!/usr/bin/env bats
# Tests for hooks/hooks.json structure

setup() {
    load test_helper
}

@test "hooks.json: valid JSON" {
    run jq . "$HOOKS_DIR/hooks.json"
    assert_success
}

@test "hooks.json: all hook types are valid event types" {
    # Extract all hook type keys and check each one
    local valid="PreToolUse PostToolUse Notification SessionStart SessionEnd Stop"
    local keys
    keys=$(jq -r '.hooks | keys[]' "$HOOKS_DIR/hooks.json")
    for key in $keys; do
        local found=0
        for v in $valid; do
            if [[ "$key" == "$v" ]]; then
                found=1
                break
            fi
        done
        if [[ "$found" -eq 0 ]]; then
            echo "Invalid hook type: $key"
            return 1
        fi
    done
}

@test "hooks.json: matchers are valid regex" {
    local matchers
    matchers=$(jq -r '.. | .matcher? // empty' "$HOOKS_DIR/hooks.json")
    while IFS= read -r matcher; do
        [[ -z "$matcher" ]] && continue
        # grep -E returns 2 for invalid regex, 1 for no match (which is fine)
        echo "" | grep -E "$matcher" >/dev/null 2>&1 || {
            local rc=$?
            if [[ "$rc" -eq 2 ]]; then
                echo "Invalid regex: $matcher"
                return 1
            fi
        }
    done <<< "$matchers"
}

@test "hooks.json: command paths use CLAUDE_PLUGIN_ROOT variable" {
    local commands
    commands=$(jq -r '.. | .command? // empty' "$HOOKS_DIR/hooks.json")
    while IFS= read -r cmd; do
        [[ -z "$cmd" ]] && continue
        if ! echo "$cmd" | grep -q 'CLAUDE_PLUGIN_ROOT'; then
            echo "Command does not use CLAUDE_PLUGIN_ROOT: $cmd"
            return 1
        fi
    done <<< "$commands"
}
