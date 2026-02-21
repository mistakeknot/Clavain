#!/usr/bin/env bats
# Tests for scripts/lib-routing.sh — model routing resolution library.

setup() {
    load test_helper

    SCRIPTS_DIR="$BATS_TEST_DIRNAME/../../scripts"

    # Create isolated temp directory for each test
    TEST_DIR="$(mktemp -d)"

    # Reset the source guard and all caches so each test starts clean
    unset _ROUTING_LOADED

    # Write a standard routing.yaml for most tests
    mkdir -p "$TEST_DIR/config"
    cat > "$TEST_DIR/config/routing.yaml" << 'YAML'
subagents:
  defaults:
    model: sonnet
    categories:
      research: haiku
      review: sonnet
      workflow: sonnet
      synthesis: haiku

  phases:
    brainstorm:
      model: opus
      categories:
        research: haiku
    brainstorm-reviewed:
      model: opus
    strategized:
      model: opus
    planned:
      model: sonnet
    executing:
      model: sonnet
      categories:
        review: opus
    shipping:
      model: sonnet
    reflect:
      model: sonnet
    done:
      model: sonnet

dispatch:
  tiers:
    fast:
      model: gpt-5.3-codex-spark
      description: Scoped read-only tasks
    fast-clavain:
      model: gpt-5.3-codex-spark-xhigh
      description: Clavain interserve-mode default
    deep:
      model: gpt-5.3-codex
      description: Generative tasks
    deep-clavain:
      model: gpt-5.3-codex-xhigh
      description: Clavain high-complexity dispatch

  fallback:
    fast: deep
    fast-clavain: deep-clavain
    deep-clavain: deep
YAML
}

teardown() {
    rm -rf "$TEST_DIR" 2>/dev/null || true
}

# Helper: source lib-routing.sh with a specific config, resetting caches
_source_routing() {
    unset _ROUTING_LOADED
    export CLAVAIN_ROUTING_CONFIG="${1:-$TEST_DIR/config/routing.yaml}"
    source "$SCRIPTS_DIR/lib-routing.sh"
}

# ═══════════════════════════════════════════════════════════════════
# Subagent resolution tests
# ═══════════════════════════════════════════════════════════════════

@test "resolve_model with no args returns default model" {
    _source_routing
    result="$(routing_resolve_model)"
    [[ "$result" == "sonnet" ]]
}

@test "resolve_model --category research returns haiku" {
    _source_routing
    result="$(routing_resolve_model --category research)"
    [[ "$result" == "haiku" ]]
}

@test "resolve_model --category review returns sonnet (default)" {
    _source_routing
    result="$(routing_resolve_model --category review)"
    [[ "$result" == "sonnet" ]]
}

@test "resolve_model --phase brainstorm returns opus (phase model)" {
    _source_routing
    result="$(routing_resolve_model --phase brainstorm)"
    [[ "$result" == "opus" ]]
}

@test "resolve_model --phase planned returns sonnet (phase model)" {
    _source_routing
    result="$(routing_resolve_model --phase planned)"
    [[ "$result" == "sonnet" ]]
}

@test "resolve_model --phase executing --category review returns opus (phase-category override)" {
    _source_routing
    result="$(routing_resolve_model --phase executing --category review)"
    [[ "$result" == "opus" ]]
}

@test "resolve_model --phase executing --category research returns phase model (not default category)" {
    # Resolution: phase-category (not set) → phase-model (sonnet) → returns sonnet
    # Phase model takes priority over default category
    _source_routing
    result="$(routing_resolve_model --phase executing --category research)"
    [[ "$result" == "sonnet" ]]
}

@test "resolve_model --phase brainstorm --category research returns haiku (phase-category)" {
    _source_routing
    result="$(routing_resolve_model --phase brainstorm --category research)"
    [[ "$result" == "haiku" ]]
}

@test "resolve_model --phase brainstorm (no category) returns opus, not haiku" {
    _source_routing
    result="$(routing_resolve_model --phase brainstorm)"
    [[ "$result" == "opus" ]]
}

# ═══════════════════════════════════════════════════════════════════
# Inherit sentinel tests
# ═══════════════════════════════════════════════════════════════════

@test "inherit in defaults.model falls through to sonnet fallback" {
    cat > "$TEST_DIR/config/inherit.yaml" << 'YAML'
subagents:
  defaults:
    model: inherit
YAML
    _source_routing "$TEST_DIR/config/inherit.yaml"
    result="$(routing_resolve_model)"
    [[ "$result" == "sonnet" ]]
}

@test "inherit at every level resolves to sonnet" {
    cat > "$TEST_DIR/config/all-inherit.yaml" << 'YAML'
subagents:
  defaults:
    model: inherit
    categories:
      research: inherit
  phases:
    brainstorm:
      model: inherit
      categories:
        research: inherit
YAML
    _source_routing "$TEST_DIR/config/all-inherit.yaml"
    result="$(routing_resolve_model --phase brainstorm --category research)"
    [[ "$result" == "sonnet" ]]
}

@test "inherit in phase-category falls through to phase model" {
    cat > "$TEST_DIR/config/phase-inherit.yaml" << 'YAML'
subagents:
  defaults:
    model: sonnet
  phases:
    executing:
      model: opus
      categories:
        review: inherit
YAML
    _source_routing "$TEST_DIR/config/phase-inherit.yaml"
    result="$(routing_resolve_model --phase executing --category review)"
    [[ "$result" == "opus" ]]
}

@test "resolve_model never returns the string inherit" {
    cat > "$TEST_DIR/config/inherit-chain.yaml" << 'YAML'
subagents:
  defaults:
    model: inherit
    categories:
      research: inherit
  phases:
    brainstorm:
      model: inherit
YAML
    _source_routing "$TEST_DIR/config/inherit-chain.yaml"
    for args in "" "--phase brainstorm" "--category research" "--phase brainstorm --category research"; do
        result="$(routing_resolve_model $args)"
        [[ "$result" != "inherit" ]]
    done
}

# ═══════════════════════════════════════════════════════════════════
# Dispatch tier tests
# ═══════════════════════════════════════════════════════════════════

@test "resolve_dispatch_tier fast returns correct model" {
    _source_routing
    result="$(routing_resolve_dispatch_tier fast)"
    [[ "$result" == "gpt-5.3-codex-spark" ]]
}

@test "resolve_dispatch_tier fast-clavain returns correct model" {
    _source_routing
    result="$(routing_resolve_dispatch_tier fast-clavain)"
    [[ "$result" == "gpt-5.3-codex-spark-xhigh" ]]
}

@test "resolve_dispatch_tier deep returns correct model" {
    _source_routing
    result="$(routing_resolve_dispatch_tier deep)"
    [[ "$result" == "gpt-5.3-codex" ]]
}

@test "resolve_dispatch_tier deep-clavain returns correct model" {
    _source_routing
    result="$(routing_resolve_dispatch_tier deep-clavain)"
    [[ "$result" == "gpt-5.3-codex-xhigh" ]]
}

@test "resolve_dispatch_tier follows fallback chain" {
    # Remove the 'fast' tier from config but keep its fallback
    cat > "$TEST_DIR/config/fallback.yaml" << 'YAML'
subagents:
  defaults:
    model: sonnet
dispatch:
  tiers:
    deep:
      model: gpt-5.3-codex
  fallback:
    fast: deep
YAML
    _source_routing "$TEST_DIR/config/fallback.yaml"
    result="$(routing_resolve_dispatch_tier fast)"
    [[ "$result" == "gpt-5.3-codex" ]]
}

@test "resolve_dispatch_tier returns error for unknown tier with no fallback" {
    _source_routing
    run routing_resolve_dispatch_tier nonexistent
    [[ "$status" -eq 1 ]]
    [[ -z "$output" ]]
}

# ═══════════════════════════════════════════════════════════════════
# Config discovery tests
# ═══════════════════════════════════════════════════════════════════

@test "CLAVAIN_ROUTING_CONFIG env var overrides default discovery" {
    cat > "$TEST_DIR/config/custom.yaml" << 'YAML'
subagents:
  defaults:
    model: opus
YAML
    _source_routing "$TEST_DIR/config/custom.yaml"
    result="$(routing_resolve_model)"
    [[ "$result" == "opus" ]]
}

@test "missing CLAVAIN_ROUTING_CONFIG falls through to script-relative discovery" {
    # When the env var points to a nonexistent file, _routing_find_config
    # falls through to script-relative, CLAVAIN_SOURCE_DIR, and cache paths.
    # Since we run from the project dir, script-relative finds the real config.
    _source_routing "/nonexistent/routing.yaml"
    result="$(routing_resolve_model)"
    # Result is non-empty because the script-relative path finds config/routing.yaml
    [[ -n "$result" ]]
}

# ═══════════════════════════════════════════════════════════════════
# Malformed config and comment stripping tests
# ═══════════════════════════════════════════════════════════════════

@test "malformed config produces stderr warning" {
    cat > "$TEST_DIR/config/garbage.yaml" << 'YAML'
garbage: true
nothing: useful
YAML
    _source_routing "$TEST_DIR/config/garbage.yaml"
    run bash -c "
        unset _ROUTING_LOADED
        export CLAVAIN_ROUTING_CONFIG='$TEST_DIR/config/garbage.yaml'
        source '$SCRIPTS_DIR/lib-routing.sh'
        routing_resolve_model
    "
    # stderr should contain the warning
    [[ "$output" == *"possible malformed config"* ]]
}

@test "inline comments are stripped from values" {
    cat > "$TEST_DIR/config/comments.yaml" << 'YAML'
subagents:
  defaults:
    model: opus  # this is a comment
    categories:
      research: haiku  # cheap model
YAML
    _source_routing "$TEST_DIR/config/comments.yaml"
    result="$(routing_resolve_model)"
    [[ "$result" == "opus" ]]
    result="$(routing_resolve_model --category research)"
    [[ "$result" == "haiku" ]]
}

# ═══════════════════════════════════════════════════════════════════
# routing_list_mappings tests
# ═══════════════════════════════════════════════════════════════════

@test "list_mappings prints source path and default model" {
    _source_routing
    result="$(routing_list_mappings)"
    [[ "$result" == *"Source:"* ]]
    [[ "$result" == *"Default model: sonnet"* ]]
    [[ "$result" == *"Dispatch Tiers:"* ]]
}
