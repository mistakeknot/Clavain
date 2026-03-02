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

    mkdir -p "$SOURCE_DIR/scripts" "$SOURCE_DIR/skills" "$SOURCE_DIR/commands"
    mkdir -p "$CLONE_ROOT" "$SKILLS_DIR"

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
