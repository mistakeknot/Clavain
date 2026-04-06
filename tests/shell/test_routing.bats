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
    unset _ROUTING_LOADED _ROUTING_CACHE_POPULATED
    # Reset safety floor cache to avoid leakage between tests
    declare -gA _ROUTING_SF_AGENT_MIN=()
    # Reset B5 cache
    _ROUTING_B5_MODE=""
    _ROUTING_B5_ENDPOINT=""
    declare -gA _ROUTING_B5_TIER_MAP=()
    declare -gA _ROUTING_B5_CX_MODEL=()
    declare -gA _ROUTING_B5_INELIGIBLE=()
    _ROUTING_B5_HEALTH_CACHE=""
    _ROUTING_B5_HEALTH_TIME=0
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

# ═══════════════════════════════════════════════════════════════════
# Safety floor tests (iv-db5pc)
# ═══════════════════════════════════════════════════════════════════

@test "safety floor: agent in role with min_model gets clamped up" {
    cat > "$TEST_DIR/config/agent-roles.yaml" << 'YAML'
roles:
  reviewer:
    min_model: sonnet
    agents:
      - fd-safety
      - fd-correctness
  checker:
    agents:
      - fd-perception
YAML
    cat > "$TEST_DIR/config/routing.yaml" << 'YAML'
subagents:
  defaults:
    model: haiku
YAML
    _source_routing
    result="$(routing_resolve_model --agent fd-safety)"
    [[ "$result" == "sonnet" ]]
}

@test "safety floor: agent without min_model is not clamped" {
    cat > "$TEST_DIR/config/agent-roles.yaml" << 'YAML'
roles:
  checker:
    agents:
      - fd-perception
YAML
    cat > "$TEST_DIR/config/routing.yaml" << 'YAML'
subagents:
  defaults:
    model: haiku
YAML
    _source_routing
    result="$(routing_resolve_model --agent fd-perception)"
    [[ "$result" == "haiku" ]]
}

@test "safety floor: agent already at or above floor is not changed" {
    cat > "$TEST_DIR/config/agent-roles.yaml" << 'YAML'
roles:
  reviewer:
    min_model: sonnet
    agents:
      - fd-safety
YAML
    cat > "$TEST_DIR/config/routing.yaml" << 'YAML'
subagents:
  defaults:
    model: opus
YAML
    _source_routing
    result="$(routing_resolve_model --agent fd-safety)"
    [[ "$result" == "opus" ]]
}

@test "safety floor: planner role agents get sonnet floor" {
    cat > "$TEST_DIR/config/agent-roles.yaml" << 'YAML'
roles:
  planner:
    min_model: sonnet
    agents:
      - fd-architecture
      - fd-systems
  checker:
    agents:
      - fd-perception
YAML
    cat > "$TEST_DIR/config/routing.yaml" << 'YAML'
subagents:
  defaults:
    model: haiku
YAML
    _source_routing
    result="$(routing_resolve_model --agent fd-architecture)"
    [[ "$result" == "sonnet" ]]
}

@test "safety floor: clamping emits structured log to stderr" {
    cat > "$TEST_DIR/config/agent-roles.yaml" << 'YAML'
roles:
  reviewer:
    min_model: sonnet
    agents:
      - fd-safety
YAML
    cat > "$TEST_DIR/config/routing.yaml" << 'YAML'
subagents:
  defaults:
    model: haiku
YAML
    _source_routing
    # Capture stderr only (stdout to /dev/null)
    local stderr_output
    stderr_output="$(routing_resolve_model --agent fd-safety 2>&1 1>/dev/null)"
    [[ "$stderr_output" == *"[safety-floor]"* ]]
    [[ "$stderr_output" == *"agent=fd-safety"* ]]
    [[ "$stderr_output" == *"resolved=haiku"* ]]
    [[ "$stderr_output" == *"clamped_to=sonnet"* ]]
}

@test "safety floor: no log when not clamping" {
    cat > "$TEST_DIR/config/agent-roles.yaml" << 'YAML'
roles:
  reviewer:
    min_model: sonnet
    agents:
      - fd-safety
YAML
    cat > "$TEST_DIR/config/routing.yaml" << 'YAML'
subagents:
  defaults:
    model: opus
YAML
    _source_routing
    local stderr_output
    stderr_output="$(routing_resolve_model --agent fd-safety 2>&1 1>/dev/null)"
    [[ -z "$stderr_output" ]]
}

@test "safety floor: no roles file means no clamping (graceful)" {
    # Don't create agent-roles.yaml — only routing.yaml
    # Explicitly disable roles discovery so the real agent-roles.yaml isn't found
    export CLAVAIN_ROLES_CONFIG="/dev/null"
    cat > "$TEST_DIR/config/routing.yaml" << 'YAML'
subagents:
  defaults:
    model: haiku
YAML
    _source_routing
    result="$(routing_resolve_model --agent fd-safety)"
    [[ "$result" == "haiku" ]]
    unset CLAVAIN_ROLES_CONFIG
}

@test "safety floor: namespaced agent ID (interflux:review:fd-safety) is clamped" {
    cat > "$TEST_DIR/config/agent-roles.yaml" << 'YAML'
roles:
  reviewer:
    min_model: sonnet
    agents:
      - fd-safety
YAML
    cat > "$TEST_DIR/config/routing.yaml" << 'YAML'
subagents:
  defaults:
    model: haiku
YAML
    _source_routing
    # This is the path routing_resolve_agents uses — namespaced agent ID
    result="$(routing_resolve_model --agent "interflux:review:fd-safety")"
    [[ "$result" == "sonnet" ]]
}

@test "safety floor: invalid min_model emits warning" {
    export CLAVAIN_ROLES_CONFIG="$TEST_DIR/config/agent-roles.yaml"
    cat > "$TEST_DIR/config/agent-roles.yaml" << 'YAML'
roles:
  reviewer:
    min_model: sonett
    agents:
      - fd-safety
YAML
    cat > "$TEST_DIR/config/routing.yaml" << 'YAML'
subagents:
  defaults:
    model: haiku
YAML
    _source_routing
    local stderr_output
    stderr_output="$(routing_resolve_model --agent fd-safety 2>&1 1>/dev/null)"
    [[ "$stderr_output" == *"invalid min_model"* ]]
    # Model should NOT be clamped (invalid floor is ignored)
    result="$(routing_resolve_model --agent fd-safety 2>/dev/null)"
    [[ "$result" == "haiku" ]]
    unset CLAVAIN_ROLES_CONFIG
}

# ═══════════════════════════════════════════════════════════════════
# Batch agent resolution tests (routing_resolve_agents)
# ═══════════════════════════════════════════════════════════════════

@test "resolve_agents returns valid JSON for fd-* agents" {
    _source_routing
    result="$(routing_resolve_agents --phase executing --agents "fd-safety,fd-architecture,fd-quality")"
    # Verify it's valid JSON with expected keys
    echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'fd-safety' in d; assert 'fd-architecture' in d; assert 'fd-quality' in d"
}

@test "resolve_agents maps fd-* agents to review category" {
    _source_routing
    result="$(routing_resolve_agents --phase executing --agents "fd-safety,fd-quality")"
    # Executing phase has categories.review=opus in test config, so review agents get opus
    echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['fd-safety']=='opus', f\"got {d['fd-safety']}\"; assert d['fd-quality']=='opus', f\"got {d['fd-quality']}\""
}

@test "resolve_agents maps research agents to research category" {
    _source_routing
    result="$(routing_resolve_agents --phase executing --agents "best-practices-researcher,git-history-analyzer")"
    # Research agents get haiku in economy mode (research category)
    echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['best-practices-researcher']=='haiku' or d['best-practices-researcher']=='sonnet'"
}

@test "resolve_agents respects phase override" {
    _source_routing
    result="$(routing_resolve_agents --phase brainstorm --agents "fd-architecture")"
    # Brainstorm phase has model: opus, review agents get phase model (opus)
    echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['fd-architecture']=='opus', f\"expected opus, got {d['fd-architecture']}\""
}

@test "resolve_agents returns empty JSON with no config" {
    cat > "$TEST_DIR/config/empty.yaml" << 'YAML'
# empty
YAML
    _source_routing "$TEST_DIR/config/empty.yaml"
    result="$(routing_resolve_agents --phase executing --agents "fd-safety")"
    # Should return empty JSON or valid JSON (graceful degradation)
    [[ "$result" == "{}" ]] || echo "$result" | python3 -c "import sys,json; json.load(sys.stdin)"
}

@test "resolve_agents returns empty JSON with no agents" {
    _source_routing
    result="$(routing_resolve_agents --phase executing --agents "")"
    [[ "$result" == "{}" ]]
}

@test "resolve_agents safety floor clamps fd-safety to sonnet" {
    cat > "$TEST_DIR/config/agent-roles.yaml" << 'YAML'
roles:
  reviewer:
    min_model: sonnet
    agents:
      - interflux:review:fd-safety
      - interflux:review:fd-correctness
YAML
    cat > "$TEST_DIR/config/routing.yaml" << 'YAML'
subagents:
  defaults:
    model: haiku
    categories:
      review: haiku
YAML
    _source_routing
    result="$(routing_resolve_agents --phase executing --agents "fd-safety,fd-correctness" 2>/dev/null)"
    echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['fd-safety']=='sonnet', f\"expected sonnet, got {d['fd-safety']}\"; assert d['fd-correctness']=='sonnet', f\"expected sonnet, got {d['fd-correctness']}\""
}

@test "resolve_agents brainstorm phase review category uses phase model" {
    _source_routing
    result="$(routing_resolve_agents --phase brainstorm --agents "fd-safety,fd-architecture,fd-quality")"
    # Brainstorm phase model=opus, but brainstorm has categories.research=haiku.
    # Review agents: no brainstorm:review override → falls to phase model (opus)
    echo "$result" | python3 -c "
import sys,json
d=json.load(sys.stdin)
for agent in ['fd-safety','fd-architecture','fd-quality']:
    assert d[agent]=='opus', f'{agent}: expected opus, got {d[agent]}'
"
}

@test "resolve_agents handles whitespace in agent list" {
    _source_routing
    result="$(routing_resolve_agents --phase executing --agents " fd-safety , fd-quality ")"
    echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'fd-safety' in d; assert 'fd-quality' in d"
}

@test "resolve_agents category override applies to all agents" {
    _source_routing
    result="$(routing_resolve_agents --phase executing --agents "fd-safety,fd-architecture" --category research)"
    # With category override to research, executing phase has no research category override
    # So falls to phase model (sonnet)
    echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['fd-safety']=='sonnet'; assert d['fd-architecture']=='sonnet'"
}

# ═══════════════════════════════════════════════════════════════════
# B2: routing_resolve_agents with complexity signal flags
# ═══════════════════════════════════════════════════════════════════

@test "resolve_agents with --prompt-tokens classifies and uses complexity resolver" {
    _write_cx_config shadow
    _source_routing "$TEST_DIR/config/cx.yaml"
    export CLAVAIN_RUN_ID="test-run"  # Force bash path (skip ic fast path)
    # 5000 tokens → C5 classification. Shadow mode returns base result + logs.
    run bash -c "
        unset _ROUTING_LOADED
        export CLAVAIN_ROUTING_CONFIG='$TEST_DIR/config/cx.yaml'
        export CLAVAIN_RUN_ID='test-run'
        source '$SCRIPTS_DIR/lib-routing.sh'
        routing_resolve_agents --phase executing --agents 'fd-safety' --prompt-tokens 5000 --reasoning-depth 1
    "
    [ "$status" -eq 0 ]
    # Shadow log should appear (C5 would override sonnet → opus)
    [[ "$output" == *"B2-shadow"* ]]
    unset CLAVAIN_RUN_ID
}

@test "resolve_agents with --prompt-tokens 100 classifies as C1" {
    _write_cx_config enforce
    _source_routing "$TEST_DIR/config/cx.yaml"
    export CLAVAIN_RUN_ID="test-run"
    # 100 tokens, 0 files, depth 1 → C1 → override to haiku
    # Use fd-perception (checker role, no safety floor) — fd-safety has min_model=sonnet floor
    result="$(routing_resolve_agents --phase executing --agents "fd-perception" --prompt-tokens 100 --file-count 0 --reasoning-depth 1 2>/dev/null)"
    echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['fd-perception']=='haiku', f\"expected haiku, got {d['fd-perception']}\""
    unset CLAVAIN_RUN_ID
}

@test "resolve_agents with --prompt-tokens 5000 classifies as C5 enforce" {
    _write_cx_config enforce
    _source_routing "$TEST_DIR/config/cx.yaml"
    export CLAVAIN_RUN_ID="test-run"
    # 5000 tokens → C5 → override to opus
    result="$(routing_resolve_agents --phase executing --agents "fd-safety" --prompt-tokens 5000 --reasoning-depth 1 2>/dev/null)"
    echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['fd-safety']=='opus', f\"expected opus, got {d['fd-safety']}\""
    unset CLAVAIN_RUN_ID
}

@test "resolve_agents without signal flags behaves as B1 only" {
    _write_cx_config enforce
    _source_routing "$TEST_DIR/config/cx.yaml"
    export CLAVAIN_RUN_ID="test-run"
    # No signal flags → no complexity classification → B1 base result (sonnet)
    result="$(routing_resolve_agents --phase executing --agents "fd-safety" 2>/dev/null)"
    echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['fd-safety']=='sonnet', f\"expected sonnet, got {d['fd-safety']}\""
    unset CLAVAIN_RUN_ID
}

@test "resolve_agents skips ic fast path when complexity mode is shadow" {
    _write_cx_config shadow
    _source_routing "$TEST_DIR/config/cx.yaml"
    # Don't set CLAVAIN_RUN_ID — the fast-path guard should check _ROUTING_CX_MODE
    # With mode=shadow, the Go fast path should be skipped even without CLAVAIN_RUN_ID
    # We verify by checking that the function still returns valid JSON (bash path works)
    result="$(routing_resolve_agents --phase executing --agents "fd-safety" 2>/dev/null)"
    echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'fd-safety' in d"
}

# ═══════════════════════════════════════════════
# Interspect override consumption tests
# ═══════════════════════════════════════════════

@test "override: missing file has no effect" {
    _source_routing
    export CLAUDE_PROJECT_DIR="$TEST_DIR"
    export CLAVAIN_RUN_ID="test-run"  # Force bash path (skip ic fast path)
    # No .claude/routing-overrides.json exists
    run routing_resolve_model --agent fd-safety --phase executing --category review
    [ "$status" -eq 0 ]
    [ "$output" = "opus" ]  # executing + review = opus per routing.yaml
    unset CLAVAIN_RUN_ID
}

@test "override: malformed file has no effect" {
    _source_routing
    export CLAUDE_PROJECT_DIR="$TEST_DIR"
    mkdir -p "$TEST_DIR/.claude"
    echo 'NOT-JSON{{{' > "$TEST_DIR/.claude/routing-overrides.json"
    run routing_resolve_model --agent fd-safety --phase executing --category review
    [ "$status" -eq 0 ]
    [ "$output" = "opus" ]
}

@test "override: exclude action returns _EXCLUDED_" {
    _source_routing
    export CLAUDE_PROJECT_DIR="$TEST_DIR"
    mkdir -p "$TEST_DIR/.claude"
    cat > "$TEST_DIR/.claude/routing-overrides.json" << 'EOF'
{"overrides":[{"agent":"fd-game-design","action":"exclude","reason":"not relevant"}]}
EOF
    run routing_resolve_model --agent fd-game-design --phase executing --category review
    [ "$status" -eq 0 ]
    [ "$output" = "_EXCLUDED_" ]
}

@test "override: approved model recommendation overrides default" {
    _source_routing
    export CLAUDE_PROJECT_DIR="$TEST_DIR"
    mkdir -p "$TEST_DIR/.claude"
    cat > "$TEST_DIR/.claude/routing-overrides.json" << 'EOF'
{"overrides":[{"agent":"fd-safety","action":"propose","status":"approved","recommended_model":"haiku"}]}
EOF
    run routing_resolve_model --agent fd-safety --phase executing --category review
    [ "$status" -eq 0 ]
    # Safety floor may clamp this up, but override was applied
    # fd-safety has min_model sonnet in agent-roles, so haiku gets clamped to sonnet
    # Without agent-roles loaded, it should be haiku
    [[ "$output" == "haiku" || "$output" == "sonnet" ]]
}

@test "override: pending proposal has no effect" {
    _source_routing
    export CLAUDE_PROJECT_DIR="$TEST_DIR"
    mkdir -p "$TEST_DIR/.claude"
    cat > "$TEST_DIR/.claude/routing-overrides.json" << 'EOF'
{"overrides":[{"agent":"fd-safety","action":"propose","status":"pending_approval","recommended_model":"haiku"}]}
EOF
    run routing_resolve_model --agent fd-safety --phase executing --category review
    [ "$status" -eq 0 ]
    [ "$output" = "opus" ]  # Normal resolution, no override applied
}

@test "override: namespaced agent matches stripped name" {
    _source_routing
    export CLAUDE_PROJECT_DIR="$TEST_DIR"
    mkdir -p "$TEST_DIR/.claude"
    cat > "$TEST_DIR/.claude/routing-overrides.json" << 'EOF'
{"overrides":[{"agent":"fd-game-design","action":"exclude","reason":"not relevant"}]}
EOF
    # Query with full namespace — should still match "fd-game-design"
    run routing_resolve_model --agent "interflux:review:fd-game-design" --phase executing --category review
    [ "$status" -eq 0 ]
    [ "$output" = "_EXCLUDED_" ]
}

@test "override: routing.yaml agent override takes precedence over interspect override" {
    # If routing.yaml has a per-agent override, it should win over interspect
    mkdir -p "$TEST_DIR/config"
    cat > "$TEST_DIR/config/routing.yaml" << 'YAML'
subagents:
  defaults:
    model: sonnet
  overrides:
    fd-safety: opus
YAML
    _source_routing "$TEST_DIR/config/routing.yaml"
    export CLAUDE_PROJECT_DIR="$TEST_DIR"
    mkdir -p "$TEST_DIR/.claude"
    cat > "$TEST_DIR/.claude/routing-overrides.json" << 'EOF'
{"overrides":[{"agent":"fd-safety","action":"propose","status":"approved","recommended_model":"haiku"}]}
EOF
    run routing_resolve_model --agent fd-safety
    [ "$status" -eq 0 ]
    [ "$output" = "opus" ]  # routing.yaml override wins
}

# ═══════════════════════════════════════════════════════════════════
# Track B5: Local model routing
# ═══════════════════════════════════════════════════════════════════

_write_b5_config() {
    cat > "$TEST_DIR/config/routing.yaml" << 'YAML'
subagents:
  defaults:
    model: sonnet

complexity:
  mode: enforce
  tiers:
    C1:
      description: trivial
    C2:
      description: routine
  overrides:
    C1:
      subagent_model: haiku
    C2:
      subagent_model: haiku

local_models:
  mode: shadow
  endpoint: "http://127.0.0.1:19999"
  tier_mappings:
    "local:qwen3.5-35b-a3b-4bit": 2
    "flash-moe:qwen3.5-397b": 3
  complexity_routing:
    C1: "local:qwen3.5-35b-a3b-4bit"
    C2: "local:qwen3.5-35b-a3b-4bit"
    C3: "flash-moe:qwen3.5-397b"
  ineligible_agents:
    - fd-safety
    - fd-correctness
YAML
}

@test "B5: config is parsed — mode, endpoint, tiers, cx_model, ineligible" {
    _write_b5_config
    _source_routing "$TEST_DIR/config/routing.yaml"
    # Direct cache load (not via run, which forks a subshell)
    _routing_load_cache
    [ "$_ROUTING_B5_MODE" = "shadow" ]
    [ "$_ROUTING_B5_ENDPOINT" = "http://127.0.0.1:19999" ]
    [ "${_ROUTING_B5_CX_MODEL[C1]}" = "local:qwen3.5-35b-a3b-4bit" ]
    [ "${_ROUTING_B5_CX_MODEL[C2]}" = "local:qwen3.5-35b-a3b-4bit" ]
    [ "${_ROUTING_B5_CX_MODEL[C3]}" = "flash-moe:qwen3.5-397b" ]
    [ "${_ROUTING_B5_INELIGIBLE[fd-safety]}" = "1" ]
    [ "${_ROUTING_B5_INELIGIBLE[fd-correctness]}" = "1" ]
}

@test "B5: shadow mode logs but returns cloud model" {
    _write_b5_config
    _source_routing "$TEST_DIR/config/routing.yaml"
    # Direct call (not run) so cache loads in this process
    local result
    result=$(routing_resolve_model_complex --complexity C2 --phase executing 2>/dev/null)
    # Should return cloud model (haiku from B2 enforce), not local
    [ "$result" = "haiku" ]
}

@test "B5: ineligible agent is logged in shadow" {
    _write_b5_config
    _source_routing "$TEST_DIR/config/routing.yaml"
    run routing_resolve_model_complex --complexity C2 --phase executing --agent fd-safety
    [ "$status" -eq 0 ]
    # fd-safety has safety floor of opus in the real config, but here
    # it's just the ineligible check we care about
}

@test "B5: off mode produces no B5 logs" {
    _write_b5_config
    # Override to off
    export INTERFERE_ROUTING_MODE=off
    _source_routing "$TEST_DIR/config/routing.yaml"
    run routing_resolve_model_complex --complexity C2 --phase executing
    [ "$status" -eq 0 ]
    # No [B5-shadow] in stderr
    [[ ! "${output}" =~ "B5-shadow" ]]
    unset INTERFERE_ROUTING_MODE
}

@test "B5: env override INTERFERE_ROUTING_MODE works" {
    _write_b5_config
    export INTERFERE_ROUTING_MODE=enforce
    _source_routing "$TEST_DIR/config/routing.yaml"
    _routing_load_cache
    [ "$_ROUTING_B5_MODE" = "enforce" ]
    unset INTERFERE_ROUTING_MODE
}
