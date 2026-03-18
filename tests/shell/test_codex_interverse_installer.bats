#!/usr/bin/env bats
# Integration tests for scripts/install-codex-interverse.sh

bats_require_minimum_version 1.5.0

setup() {
    load test_helper

    command -v jq >/dev/null 2>&1 || skip "jq is required"

    SCRIPT_UNDER_TEST="$BATS_TEST_DIRNAME/../../scripts/install-codex-interverse.sh"
    TEST_DIR="$(mktemp -d)"

    SOURCE_DIR="$TEST_DIR/clavain"
    CLONE_ROOT="$TEST_DIR/clones"
    SKILLS_DIR="$TEST_DIR/skills"
    BIN_DIR="$TEST_DIR/bin"
    SYSTEM_GIT="$(command -v git)"

    mkdir -p "$SOURCE_DIR/scripts" "$SOURCE_DIR/skills" "$SOURCE_DIR/commands" "$BIN_DIR"
    mkdir -p "$CLONE_ROOT" "$SKILLS_DIR"
    CODEX_HOME="$TEST_DIR/codex-home"
    CODEX_PROMPTS_DIR="$CODEX_HOME/prompts"
    CLAVAIN_BACKUP_ROOT="$TEST_DIR/backups"
    export CODEX_HOME CODEX_PROMPTS_DIR CLAVAIN_BACKUP_ROOT
    mkdir -p "$CODEX_PROMPTS_DIR"

    _write_stub_git_binary
    export PATH="$BIN_DIR:$PATH"

    _write_stub_clavain_source
}

teardown() {
    [[ -d "$TEST_DIR" ]] && rm -rf "$TEST_DIR"
}

_write_stub_clavain_source() {
    cat > "$SOURCE_DIR/README.md" <<'EOF'
# Stub Clavain
EOF

    cat > "$SOURCE_DIR/scripts/install-codex.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

action="${1:-}"
if [[ "$action" == "doctor" ]]; then
  if [[ " $* " == *" --json "* ]]; then
    echo '{"status":"ok"}'
  else
    echo "Doctor checks passed."
  fi
  exit 0
fi

exit 0
EOF
    chmod +x "$SOURCE_DIR/scripts/install-codex.sh"
}

_write_agent_rig() {
    jq -n --args '$ARGS.positional | {
      plugins: {
        recommended: map({source: (. + "@interagency-marketplace")})
      }
    }' "$@" > "$SOURCE_DIR/agent-rig.json"
}

_write_stub_git_binary() {
    cat > "$BIN_DIR/git" <<EOF
#!/usr/bin/env bash
set -euo pipefail

if [[ "\${1:-}" == "-C" ]]; then
  shift 2
fi

case "\${1:-}" in
  pull)
    exit 0
    ;;
  clone)
    mkdir -p "\${3:?}/.git"
    exit 0
    ;;
  *)
    exec "$SYSTEM_GIT" "\$@"
    ;;
esac
EOF
    chmod +x "$BIN_DIR/git"
}

_make_plugin_skill_repo() {
    local plugin="$1"
    local skill_rel="$2"
    local skill_name="$3"
    local include_name="${4:-1}"
    local repo_dir="$CLONE_ROOT/$plugin"
    local skill_dir="$repo_dir/$skill_rel"

    mkdir -p "$repo_dir/.git" "$skill_dir"

    if [[ "$include_name" == "1" ]]; then
        cat > "$skill_dir/SKILL.md" <<EOF
---
name: $skill_name
description: test skill
---
# $skill_name
EOF
    else
        cat > "$skill_dir/SKILL.md" <<'EOF'
---
description: invalid skill missing name
---
# Invalid Skill
EOF
    fi
}

_make_plugin_command_repo() {
    local plugin="$1"
    local command_name="$2"
    local repo_dir="$CLONE_ROOT/$plugin"
    local command_dir="$repo_dir/commands"

    mkdir -p "$repo_dir/.git" "$command_dir"

    cat > "$command_dir/$command_name.md" <<EOF
---
name: $command_name
description: test command
---
# /$plugin:$command_name

Use AskUserQuestion if needed.
EOF
}

_write_prompt_wrapper() {
    local plugin="$1"
    local command_name="$2"
    local source_path="$3"
    local prompt_path="$CODEX_PROMPTS_DIR/$plugin-$command_name.md"
    local body="${4:-Converted content.}"

    cat > "$prompt_path" <<EOF
# Interverse Command: /$plugin:$command_name

Interverse prompt wrapper generated from companion command source.

- Source: \`$source_path\`
- Compatibility: interverse namespaces and .claude paths normalized for Codex.
- Elicitation adapter: if a prompt calls for AskUserQuestion, try future plan-mode escalation if host supports it, else use \`request_user_input\` when available, else ask in chat with numbered options and wait.

---

## Codex Elicitation Adapter

$body
EOF
}

@test "doctor auto-discovers companion skills for recommended plugins" {
    _write_agent_rig alpha beta
    _make_plugin_skill_repo alpha skills alpha-skill
    _make_plugin_skill_repo beta skills/custom beta-custom

    ln -s "$CLONE_ROOT/alpha/skills" "$SKILLS_DIR/alpha-skill"
    ln -s "$CLONE_ROOT/beta/skills/custom" "$SKILLS_DIR/beta-custom"

    run --separate-stderr "$SCRIPT_UNDER_TEST" doctor \
        --source "$SOURCE_DIR" \
        --clone-root "$CLONE_ROOT" \
        --skills-dir "$SKILLS_DIR" \
        --json

    [ "$status" -eq 0 ]
    [ "$(echo "$output" | jq -r '.status')" = "ok" ]
    [ "$(echo "$output" | jq -r '.interverse_companions.counts.recommended_plugin_count')" = "2" ]
    [ "$(echo "$output" | jq -r '.interverse_companions.counts.skill_link_count')" = "2" ]

    echo "$output" | jq -e '
      .interverse_companions.companions[]
      | select(
          .plugin == "alpha"
          and .link_name == "alpha-skill"
          and .repo_ok
          and .skill_ok
          and .link_ok
        )
    ' >/dev/null

    echo "$output" | jq -e '
      .interverse_companions.companions[]
      | select(
          .plugin == "beta"
          and .link_name == "beta-custom"
          and .repo_ok
          and .skill_ok
          and .link_ok
        )
    ' >/dev/null
}

@test "doctor skips invalid skills missing frontmatter name" {
    _write_agent_rig alpha gamma
    _make_plugin_skill_repo alpha skills alpha-skill
    _make_plugin_skill_repo gamma skills invalid 0

    ln -s "$CLONE_ROOT/alpha/skills" "$SKILLS_DIR/alpha-skill"

    run --separate-stderr "$SCRIPT_UNDER_TEST" doctor \
        --source "$SOURCE_DIR" \
        --clone-root "$CLONE_ROOT" \
        --skills-dir "$SKILLS_DIR" \
        --json

    [ "$status" -eq 0 ]
    [ "$(echo "$output" | jq -r '.status')" = "ok" ]
    [ "$(echo "$output" | jq -r '.interverse_companions.counts.recommended_plugin_count')" = "2" ]
    [ "$(echo "$output" | jq -r '.interverse_companions.counts.skill_link_count')" = "1" ]

    echo "$output" | jq -e '
      .interverse_companions.companions[]
      | select(.plugin == "alpha" and .link_name == "alpha-skill")
    ' >/dev/null

    ! echo "$output" | jq -e '
      .interverse_companions.companions[]
      | select(.plugin == "gamma")
    ' >/dev/null
}

@test "doctor prefers intercheck quality skill over legacy status path" {
    _write_agent_rig intercheck
    _make_plugin_skill_repo intercheck skills/quality quality

    ln -s "$CLONE_ROOT/intercheck/skills/quality" "$SKILLS_DIR/quality"

    run --separate-stderr "$SCRIPT_UNDER_TEST" doctor \
        --source "$SOURCE_DIR" \
        --clone-root "$CLONE_ROOT" \
        --skills-dir "$SKILLS_DIR" \
        --json

    [ "$status" -eq 0 ]
    [ "$(echo "$output" | jq -r '.status')" = "ok" ]

    echo "$output" | jq -e '
      .interverse_companions.companions[]
      | select(
          .plugin == "intercheck"
          and .link_name == "quality"
          and (.skill_path | endswith("/intercheck/skills/quality"))
          and .repo_ok
          and .skill_ok
          and .link_ok
        )
    ' >/dev/null

    ! echo "$output" | jq -e '
      .interverse_companions.companions[]
      | select(.plugin == "intercheck" and .link_name == "status")
    ' >/dev/null
}

@test "install replaces legacy intercheck status link with quality" {
    _write_agent_rig intercheck
    _make_plugin_skill_repo intercheck skills/quality quality

    ln -s "$CLONE_ROOT/intercheck/skills/status" "$SKILLS_DIR/status"

    run --separate-stderr "$SCRIPT_UNDER_TEST" install \
        --source "$SOURCE_DIR" \
        --clone-root "$CLONE_ROOT" \
        --skills-dir "$SKILLS_DIR" \
        --no-prompts

    [ "$status" -eq 0 ]
    [ -L "$SKILLS_DIR/quality" ]
    [ "$(readlink "$SKILLS_DIR/quality")" = "$CLONE_ROOT/intercheck/skills/quality" ]
    [ ! -e "$SKILLS_DIR/status" ]
}

@test "doctor validates generated prompt wrappers for command-based companions" {
    _write_agent_rig alpha
    _make_plugin_command_repo alpha sync
    _write_prompt_wrapper alpha sync "$CLONE_ROOT/alpha/commands/sync.md"

    run --separate-stderr env CODEX_HOME="$CODEX_HOME" CODEX_PROMPTS_DIR="$CODEX_PROMPTS_DIR" \
        "$SCRIPT_UNDER_TEST" doctor \
        --source "$SOURCE_DIR" \
        --clone-root "$CLONE_ROOT" \
        --skills-dir "$SKILLS_DIR" \
        --json

    [ "$status" -eq 0 ]
    [ "$(echo "$output" | jq -r '.interverse_companions.prompts.status')" = "ok" ]
    [ "$(echo "$output" | jq -r '.interverse_companions.prompts.counts.prompt_wrapper_count')" = "1" ]
    [ "$(echo "$output" | jq -r '.interverse_companions.prompts.prompt_wrappers[0].prompt_ok')" = "true" ]
    [ "$(echo "$output" | jq -r '.interverse_companions.prompts.prompt_wrappers[0].converted_ok')" = "true" ]
}

@test "doctor fails when a generated prompt wrapper still contains Claude-only tokens" {
    _write_agent_rig alpha
    _make_plugin_command_repo alpha sync
    _write_prompt_wrapper alpha sync "$CLONE_ROOT/alpha/commands/sync.md" "AskUserQuestion remains here."

    run --separate-stderr env CODEX_HOME="$CODEX_HOME" CODEX_PROMPTS_DIR="$CODEX_PROMPTS_DIR" \
        "$SCRIPT_UNDER_TEST" doctor \
        --source "$SOURCE_DIR" \
        --clone-root "$CLONE_ROOT" \
        --skills-dir "$SKILLS_DIR" \
        --json

    [ "$status" -eq 1 ]
    [ "$(echo "$output" | jq -r '.status')" = "fail" ]
    [ "$(echo "$output" | jq -r '.interverse_companions.prompts.status')" = "fail" ]
    [ "$(echo "$output" | jq -r '.interverse_companions.prompts.prompt_wrappers[0].converted_ok')" = "false" ]
}
