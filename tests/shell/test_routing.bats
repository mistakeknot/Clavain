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

# ═══════════════════════════════════════════════════════════════════
# B2: Complexity-aware routing tests
# ═══════════════════════════════════════════════════════════════════

# Helper: write a complexity-enabled config for B2 tests
_write_cx_config() {
    local mode="${1:-enforce}"
    cat > "$TEST_DIR/config/cx.yaml" << YAML
subagents:
  defaults:
    model: sonnet
    categories:
      research: haiku
  phases:
    brainstorm:
      model: opus

dispatch:
  tiers:
    fast:
      model: gpt-5.3-codex-spark
    deep:
      model: gpt-5.3-codex

complexity:
  mode: ${mode}
  tiers:
    C5:
      description: Architectural
      prompt_tokens: 4000
      file_count: 15
      reasoning_depth: 5
    C4:
      description: Complex
      prompt_tokens: 2000
      file_count: 8
      reasoning_depth: 4
    C3:
      description: Moderate
      prompt_tokens: 800
      file_count: 4
      reasoning_depth: 3
    C2:
      description: Simple
      prompt_tokens: 300
      file_count: 2
      reasoning_depth: 2
    C1:
      description: Trivial
      prompt_tokens: 0
      file_count: 0
      reasoning_depth: 1
  overrides:
    C5:
      subagent_model: opus
      dispatch_tier: deep
    C4:
      subagent_model: opus
      dispatch_tier: deep
    C3:
      subagent_model: inherit
      dispatch_tier: inherit
    C2:
      subagent_model: haiku
      dispatch_tier: fast
    C1:
      subagent_model: haiku
      dispatch_tier: fast
YAML
}

# --- Classification tests ---

@test "classify_complexity returns empty when mode=off" {
    _source_routing  # default config has no complexity section → mode=off
    result="$(routing_classify_complexity --prompt-tokens 5000 --file-count 20)"
    [[ -z "$result" ]]
}

@test "classify_complexity returns C5 for high token count" {
    _write_cx_config enforce
    _source_routing "$TEST_DIR/config/cx.yaml"
    result="$(routing_classify_complexity --prompt-tokens 5000)"
    [[ "$result" == "C5" ]]
}

@test "classify_complexity returns C5 for high file count" {
    _write_cx_config enforce
    _source_routing "$TEST_DIR/config/cx.yaml"
    result="$(routing_classify_complexity --file-count 20)"
    [[ "$result" == "C5" ]]
}

@test "classify_complexity returns C5 for reasoning_depth=5" {
    _write_cx_config enforce
    _source_routing "$TEST_DIR/config/cx.yaml"
    result="$(routing_classify_complexity --reasoning-depth 5)"
    [[ "$result" == "C5" ]]
}

@test "classify_complexity returns C3 for moderate tokens" {
    _write_cx_config enforce
    _source_routing "$TEST_DIR/config/cx.yaml"
    result="$(routing_classify_complexity --prompt-tokens 900)"
    [[ "$result" == "C3" ]]
}

@test "classify_complexity returns C2 for low tokens" {
    _write_cx_config enforce
    _source_routing "$TEST_DIR/config/cx.yaml"
    result="$(routing_classify_complexity --prompt-tokens 350)"
    [[ "$result" == "C2" ]]
}

@test "classify_complexity returns C1 for minimal signals" {
    _write_cx_config enforce
    _source_routing "$TEST_DIR/config/cx.yaml"
    result="$(routing_classify_complexity --prompt-tokens 100 --file-count 0 --reasoning-depth 1)"
    [[ "$result" == "C1" ]]
}

@test "classify_complexity ANY threshold triggers tier" {
    # High file_count but low tokens should still classify as C4
    _write_cx_config enforce
    _source_routing "$TEST_DIR/config/cx.yaml"
    result="$(routing_classify_complexity --prompt-tokens 100 --file-count 10)"
    [[ "$result" == "C4" ]]
}

# --- Zero-cost bypass tests ---

@test "resolve_model_complex with no complexity is identical to resolve_model" {
    _source_routing
    base="$(routing_resolve_model --phase brainstorm)"
    complex="$(routing_resolve_model_complex --phase brainstorm)"
    [[ "$base" == "$complex" ]]
}

@test "resolve_model_complex with mode=off delegates to base" {
    _source_routing  # no complexity section → mode=off
    result="$(routing_resolve_model_complex --complexity C5 --phase brainstorm)"
    [[ "$result" == "opus" ]]  # base B1 result, not overridden
}

@test "resolve_dispatch_tier_complex with mode=off delegates to base" {
    _source_routing
    result="$(routing_resolve_dispatch_tier_complex fast)"
    [[ "$result" == "gpt-5.3-codex-spark" ]]
}

# --- Enforce mode tests ---

@test "resolve_model_complex C5 enforce overrides to opus" {
    _write_cx_config enforce
    _source_routing "$TEST_DIR/config/cx.yaml"
    # Base would return sonnet (default), but C5 overrides to opus
    result="$(routing_resolve_model_complex --complexity C5)"
    [[ "$result" == "opus" ]]
}

@test "resolve_model_complex C2 enforce overrides to haiku" {
    _write_cx_config enforce
    _source_routing "$TEST_DIR/config/cx.yaml"
    # Base would return opus (brainstorm phase), but C2 overrides to haiku
    result="$(routing_resolve_model_complex --complexity C2 --phase brainstorm)"
    [[ "$result" == "haiku" ]]
}

@test "resolve_model_complex C3 enforce inherits from base (inherit passthrough)" {
    _write_cx_config enforce
    _source_routing "$TEST_DIR/config/cx.yaml"
    # C3 has subagent_model: inherit → should return base result
    result="$(routing_resolve_model_complex --complexity C3 --phase brainstorm)"
    [[ "$result" == "opus" ]]  # base B1 result
}

@test "resolve_dispatch_tier_complex C5 enforce promotes to deep" {
    _write_cx_config enforce
    _source_routing "$TEST_DIR/config/cx.yaml"
    # Requesting fast, but C5 overrides to deep
    result="$(routing_resolve_dispatch_tier_complex --complexity C5 fast)"
    [[ "$result" == "gpt-5.3-codex" ]]
}

@test "resolve_dispatch_tier_complex C2 enforce demotes to fast" {
    _write_cx_config enforce
    _source_routing "$TEST_DIR/config/cx.yaml"
    # Requesting deep, but C2 overrides to fast
    result="$(routing_resolve_dispatch_tier_complex --complexity C2 deep)"
    [[ "$result" == "gpt-5.3-codex-spark" ]]
}

@test "resolve_dispatch_tier_complex C3 enforce inherits original tier" {
    _write_cx_config enforce
    _source_routing "$TEST_DIR/config/cx.yaml"
    result="$(routing_resolve_dispatch_tier_complex --complexity C3 deep)"
    [[ "$result" == "gpt-5.3-codex" ]]
}

# --- Shadow mode tests ---

@test "resolve_model_complex shadow logs but returns base result" {
    _write_cx_config shadow
    _source_routing "$TEST_DIR/config/cx.yaml"
    # C2 would override sonnet → haiku, but shadow returns base
    run bash -c "
        unset _ROUTING_LOADED
        export CLAVAIN_ROUTING_CONFIG='$TEST_DIR/config/cx.yaml'
        source '$SCRIPTS_DIR/lib-routing.sh'
        routing_resolve_model_complex --complexity C2
    "
    # stdout should be base result (sonnet)
    [[ "$output" == *"sonnet"* ]]
    # stderr should contain shadow log (captured in combined output by bats)
    [[ "$output" == *"B2-shadow"* ]]
}

@test "resolve_dispatch_tier_complex shadow logs but returns base" {
    _write_cx_config shadow
    _source_routing "$TEST_DIR/config/cx.yaml"
    run bash -c "
        unset _ROUTING_LOADED
        export CLAVAIN_ROUTING_CONFIG='$TEST_DIR/config/cx.yaml'
        source '$SCRIPTS_DIR/lib-routing.sh'
        routing_resolve_dispatch_tier_complex --complexity C5 fast
    "
    # stdout should be base result (fast tier model)
    [[ "$output" == *"gpt-5.3-codex-spark"* ]]
    # stderr should contain shadow log
    [[ "$output" == *"B2-shadow"* ]]
}

@test "resolve_model_complex shadow does not log when no change" {
    _write_cx_config shadow
    _source_routing "$TEST_DIR/config/cx.yaml"
    # C3 has inherit → no change → no shadow log
    run bash -c "
        unset _ROUTING_LOADED
        export CLAVAIN_ROUTING_CONFIG='$TEST_DIR/config/cx.yaml'
        source '$SCRIPTS_DIR/lib-routing.sh'
        routing_resolve_model_complex --complexity C3
    "
    [[ "$output" == *"sonnet"* ]]
    [[ "$output" != *"B2-shadow"* ]]
}

# --- list_mappings with complexity ---

@test "list_mappings shows complexity mode when enabled" {
    _write_cx_config enforce
    _source_routing "$TEST_DIR/config/cx.yaml"
    result="$(routing_list_mappings)"
    [[ "$result" == *"Complexity Routing (B2):"* ]]
    [[ "$result" == *"Mode: enforce"* ]]
    [[ "$result" == *"C5:"* ]]
    [[ "$result" == *"C1:"* ]]
}

@test "list_mappings shows mode=off without tier details" {
    _source_routing  # default config, no complexity → mode=off
    result="$(routing_list_mappings)"
    [[ "$result" == *"Mode: off"* ]]
    # Should NOT show tier details when off
    [[ "$result" != *"C5:"* ]]
}
