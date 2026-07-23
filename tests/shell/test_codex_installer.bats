#!/usr/bin/env bats
# Integration tests for scripts/install-codex.sh

bats_require_minimum_version 1.5.0

setup() {
    load test_helper

    command -v jq >/dev/null 2>&1 || skip "jq is required"

    SCRIPT_UNDER_TEST="$BATS_TEST_DIRNAME/../../scripts/install-codex.sh"
    TEST_DIR="$(mktemp -d)"
    export HOME="$TEST_DIR/home"

    SOURCE_DIR="$TEST_DIR/clavain"
    AGENTS_SKILLS_DIR="$HOME/.agents/skills"
    CODEX_HOME="$HOME/.codex"
    LOCAL_BIN_DIR="$HOME/.local/bin"

    mkdir -p "$SOURCE_DIR/scripts" "$SOURCE_DIR/hooks" "$SOURCE_DIR/skills/core" "$SOURCE_DIR/commands" "$SOURCE_DIR/bin" "$SOURCE_DIR/.claude-plugin"
    mkdir -p "$AGENTS_SKILLS_DIR" "$CODEX_HOME" "$LOCAL_BIN_DIR"

    _write_stub_clavain_source
}

teardown() {
    [[ -d "$TEST_DIR" ]] && rm -rf "$TEST_DIR"
}

_write_stub_clavain_source() {
    cat > "$SOURCE_DIR/README.md" <<'EOF'
# Stub Clavain
EOF

    cat > "$SOURCE_DIR/skills/core/SKILL.md" <<'EOF'
---
name: stub-skill
description: test skill
---
# Stub skill
EOF

    cat > "$SOURCE_DIR/commands/help.md" <<'EOF'
---
name: help
description: test command
---
# Help
EOF

    cat > "$SOURCE_DIR/scripts/dispatch.sh" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
    chmod +x "$SOURCE_DIR/scripts/dispatch.sh"

    cat > "$SOURCE_DIR/scripts/debate.sh" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
    chmod +x "$SOURCE_DIR/scripts/debate.sh"

    cat > "$SOURCE_DIR/scripts/remontoire-attention.sh" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
    chmod +x "$SOURCE_DIR/scripts/remontoire-attention.sh"

    cat > "$SOURCE_DIR/scripts/context-gateway.py" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "doctor" ]]; then
  printf '%s\n' '{"ok":true,"checks":{"tldrs_executable":{"ok":true},"packet_schema":{"ok":true},"receipt_directory":{"ok":true}}}'
fi
exit 0
EOF
    chmod +x "$SOURCE_DIR/scripts/context-gateway.py"

    cat > "$SOURCE_DIR/hooks/context-gateway.sh" <<'EOF'
#!/usr/bin/env bash
exec "$(dirname "$0")/../scripts/context-gateway.py" hook --harness "${1:-claude}"
EOF
    chmod +x "$SOURCE_DIR/hooks/context-gateway.sh"

    cat > "$SOURCE_DIR/bin/clavain-cli" <<'EOF'
#!/usr/bin/env bash
echo "stub clavain-cli"
EOF
    chmod +x "$SOURCE_DIR/bin/clavain-cli"

    cat > "$SOURCE_DIR/.claude-plugin/plugin.json" <<'EOF'
{
  "mcpServers": {
    "stub": {
      "command": "stub-server",
      "args": []
    }
  }
}
EOF
}

@test "install creates managed ~/.local/bin/clavain-cli link and doctor validates it" {
    run "$SCRIPT_UNDER_TEST" install \
        --source "$SOURCE_DIR" \
        --codex-home "$CODEX_HOME"

    [ "$status" -eq 0 ]
    [ -L "$LOCAL_BIN_DIR/clavain-cli" ]
    [ "$(readlink "$LOCAL_BIN_DIR/clavain-cli")" = "$(cd "$SOURCE_DIR" && pwd -P)/bin/clavain-cli" ]

    run "$SCRIPT_UNDER_TEST" doctor \
        --source "$SOURCE_DIR" \
        --codex-home "$CODEX_HOME" \
        --json

    [ "$status" -eq 0 ]
    [ "$(echo "$output" | jq -r '.status')" = "ok" ]
    [ "$(echo "$output" | jq -r '.checks.clavain_cli_link_exists')" = "true" ]
    [ "$(echo "$output" | jq -r '.checks.clavain_cli_link_match')" = "true" ]
    [ "$(echo "$output" | jq -r '.checks.clavain_cli_target')" = "$(cd "$SOURCE_DIR" && pwd -P)/bin/clavain-cli" ]
}

@test "uninstall removes managed ~/.local/bin/clavain-cli link" {
    run "$SCRIPT_UNDER_TEST" install \
        --source "$SOURCE_DIR" \
        --codex-home "$CODEX_HOME"

    [ "$status" -eq 0 ]
    [ -L "$LOCAL_BIN_DIR/clavain-cli" ]

    run "$SCRIPT_UNDER_TEST" uninstall \
        --source "$SOURCE_DIR" \
        --codex-home "$CODEX_HOME"

    [ "$status" -eq 0 ]
    [ ! -e "$LOCAL_BIN_DIR/clavain-cli" ]
}

@test "install merges bounded SessionStart and UserPromptSubmit hooks and doctor validates them" {
    run "$SCRIPT_UNDER_TEST" install \
        --source "$SOURCE_DIR" \
        --codex-home "$CODEX_HOME"

    [ "$status" -eq 0 ]
    [ -f "$CODEX_HOME/hooks.json" ]
    jq -e --arg source "$SOURCE_DIR/scripts/remontoire-attention.sh" '
      [.hooks.SessionStart[]?.hooks[]?
       | select((.command // "") | contains("remontoire-attention.sh"))] as $managed
      | ($managed | length) == 1
        and ($managed[0].type == "command")
        and ($managed[0].timeout > 0 and $managed[0].timeout <= 15)
        and ($managed[0].command | contains("CLAVAIN_AGENT_SURFACE=codex"))
        and ($managed[0].command | contains($source))
    ' "$CODEX_HOME/hooks.json" >/dev/null
    jq -e --arg source "$SOURCE_DIR/hooks/context-gateway.sh" '
      [.hooks.UserPromptSubmit[]?.hooks[]?
       | select((.command // "") | contains("context-gateway.sh"))] as $managed
      | ($managed | length) == 1
        and ($managed[0].type == "command")
        and ($managed[0].timeout > 0 and $managed[0].timeout <= 30)
        and ($managed[0].command | contains($source))
        and ($managed[0].command | endswith(" codex"))
    ' "$CODEX_HOME/hooks.json" >/dev/null

    run "$SCRIPT_UNDER_TEST" doctor \
        --source "$SOURCE_DIR" \
        --codex-home "$CODEX_HOME" \
        --json

    [ "$status" -eq 0 ]
    echo "$output" | jq -e --arg hooks "$CODEX_HOME/hooks.json" '
      .status == "ok"
      and .checks.codex_hooks_file_present == true
      and .checks.remontoire_session_start_hook_present == true
      and .checks.remontoire_session_start_hook_match == true
      and .checks.context_gateway_user_prompt_hook_present == true
      and .checks.context_gateway_user_prompt_hook_match == true
      and .checks.context_gateway_tldrs_executable == true
      and .checks.context_gateway_packet_schema == true
      and .checks.context_gateway_receipt_directory == true
      and .paths.hooks_file == $hooks
    ' >/dev/null
}

@test "install and source-explicit update preserve unrelated Codex hooks" {
    cat > "$CODEX_HOME/hooks.json" <<'EOF'
{
  "description": "operator hooks",
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "echo keep-session", "timeout": 2}]}],
    "Notification": [{"hooks": [{"type": "command", "command": "echo keep-notification", "timeout": 2}]}]
  }
}
EOF

    run "$SCRIPT_UNDER_TEST" install \
        --source "$SOURCE_DIR" \
        --codex-home "$CODEX_HOME"
    [ "$status" -eq 0 ]

    mkdir -p "$TEST_DIR/must-not-use"
    run "$SCRIPT_UNDER_TEST" update \
        --source "$SOURCE_DIR" \
        --clone-dir "$TEST_DIR/must-not-use" \
        --codex-home "$CODEX_HOME"
    [ "$status" -eq 0 ]

    jq -e '
      .description == "operator hooks"
      and ([.hooks.SessionStart[]?.hooks[]? | select(.command == "echo keep-session")] | length) == 1
      and ([.hooks.Notification[]?.hooks[]? | select(.command == "echo keep-notification")] | length) == 1
      and ([.hooks.SessionStart[]?.hooks[]? | select((.command // "") | contains("remontoire-attention.sh"))] | length) == 1
      and ([.hooks.UserPromptSubmit[]?.hooks[]? | select((.command // "") | contains("context-gateway.sh"))] | length) == 1
    ' "$CODEX_HOME/hooks.json" >/dev/null
}

@test "uninstall removes only the managed Codex hook" {
    cat > "$CODEX_HOME/hooks.json" <<'EOF'
{"hooks":{"SessionStart":[{"hooks":[{"type":"command","command":"echo keep","timeout":2}]}]}}
EOF

    run "$SCRIPT_UNDER_TEST" install \
        --source "$SOURCE_DIR" \
        --codex-home "$CODEX_HOME"
    [ "$status" -eq 0 ]

    run "$SCRIPT_UNDER_TEST" uninstall \
        --source "$SOURCE_DIR" \
        --codex-home "$CODEX_HOME"
    [ "$status" -eq 0 ]

    jq -e '
      ([.hooks.SessionStart[]?.hooks[]? | select(.command == "echo keep")] | length) == 1
      and ([.hooks.SessionStart[]?.hooks[]? | select((.command // "") | contains("remontoire-attention.sh"))] | length) == 0
      and ([.hooks.UserPromptSubmit[]?.hooks[]? | select((.command // "") | contains("context-gateway.sh"))] | length) == 0
    ' "$CODEX_HOME/hooks.json" >/dev/null
}
