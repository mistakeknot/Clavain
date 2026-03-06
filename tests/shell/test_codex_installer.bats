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

    mkdir -p "$SOURCE_DIR/scripts" "$SOURCE_DIR/skills/core" "$SOURCE_DIR/commands" "$SOURCE_DIR/bin" "$SOURCE_DIR/.claude-plugin"
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
    [ "$(readlink "$LOCAL_BIN_DIR/clavain-cli")" = "$SOURCE_DIR/bin/clavain-cli" ]

    run "$SCRIPT_UNDER_TEST" doctor \
        --source "$SOURCE_DIR" \
        --codex-home "$CODEX_HOME" \
        --json

    [ "$status" -eq 0 ]
    [ "$(echo "$output" | jq -r '.status')" = "ok" ]
    [ "$(echo "$output" | jq -r '.checks.clavain_cli_link_exists')" = "true" ]
    [ "$(echo "$output" | jq -r '.checks.clavain_cli_link_match')" = "true" ]
    [ "$(echo "$output" | jq -r '.checks.clavain_cli_target')" = "$SOURCE_DIR/bin/clavain-cli" ]
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
