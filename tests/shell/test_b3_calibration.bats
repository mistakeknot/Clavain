#!/usr/bin/env bats
# Tests for B3 Adaptive Routing — interspect calibration pipeline.
# Covers: _interspect_db_path, _interspect_record_verdict,
#         _interspect_compute_agent_scores, _interspect_write_routing_calibration,
#         _routing_read_calibration, routing_resolve_model with calibration.
# Requires: bats-core, jq, sqlite3

setup() {
    load test_helper

    SCRIPTS_DIR="$BATS_TEST_DIRNAME/../../scripts"

    # Create isolated temp project directory for each test
    export TEST_DIR=$(mktemp -d)
    export HOME="$TEST_DIR"
    export GIT_CONFIG_GLOBAL="$TEST_DIR/.gitconfig"
    export GIT_CONFIG_SYSTEM=/dev/null
    mkdir -p "$TEST_DIR/.clavain/interspect"

    # Create a test git repo
    cd "$TEST_DIR"
    git init -q
    git config user.email "test@test.com"
    git config user.name "Test"
    git commit --allow-empty -m "init" -q

    # Create minimal confidence.json
    cat > "$TEST_DIR/.clavain/interspect/confidence.json" << 'EOF'
{"min_sessions":3,"min_diversity":2,"min_events":5,"min_agent_wrong_pct":80,"canary_window_uses":20,"canary_window_days":14,"canary_min_baseline":15,"canary_alert_pct":20,"canary_noise_floor":0.1}
EOF

    # Create minimal protected-paths.json
    cat > "$TEST_DIR/.clavain/interspect/protected-paths.json" << 'EOF'
{"protected_paths":[],"modification_allow_list":[".claude/routing-overrides.json",".clavain/interspect/overlays/*/*"],"always_propose":[]}
EOF

    # Reset guard variables so lib can be re-sourced
    unset _LIB_INTERSPECT_LOADED _INTERSPECT_CONFIDENCE_LOADED _INTERSPECT_MANIFEST_LOADED

    # Source lib-interspect.sh from interspect companion plugin
    local interspect_lib=""
    if [[ -n "${INTERSPECT_ROOT:-}" ]]; then
        interspect_lib="$INTERSPECT_ROOT/hooks/lib-interspect.sh"
    elif [[ -f "$BATS_TEST_DIRNAME/../../../../interverse/interspect/hooks/lib-interspect.sh" ]]; then
        interspect_lib="$BATS_TEST_DIRNAME/../../../../interverse/interspect/hooks/lib-interspect.sh"
    else
        skip "lib-interspect.sh not found"
    fi
    source "$interspect_lib"
    _interspect_ensure_db
}

teardown() {
    rm -rf "$TEST_DIR" 2>/dev/null || true
}

# Helper: insert synthetic evidence rows directly into the DB
_insert_evidence() {
    local session="$1" source="$2" event="$3" context="${4:-\{\}}"
    local seq
    seq=$(sqlite3 "$_INTERSPECT_DB" "SELECT COALESCE(MAX(seq),0)+1 FROM evidence WHERE session_id='$session';")
    printf -v _sql "INSERT INTO evidence (ts, session_id, seq, source, source_version, event, override_reason, context, project, project_lang, project_type) VALUES (datetime('now'), '%s', %d, '%s', '', '%s', '', '%s', 'test', NULL, NULL);" "$session" "$seq" "$source" "$event" "$context"
    sqlite3 "$_INTERSPECT_DB" "$_sql"
}

# Helper: insert a verdict outcome with findings
_insert_verdict() {
    local session="$1" agent="$2" status="$3" findings="${4:-0}" model="${5:-sonnet}"
    local ctx="{\"status\":\"$status\",\"findings_count\":$findings,\"model_used\":\"$model\"}"
    _insert_evidence "$session" "$agent" "verdict_outcome" "$ctx"
}

# Helper: insert an agent_dispatch event
_insert_dispatch() {
    local session="$1" agent="$2"
    _insert_evidence "$session" "$agent" "agent_dispatch" "{}"
}

# ═══════════════════════════════════════════════════════════════════
# _interspect_db_path fallback resolution
# ═══════════════════════════════════════════════════════════════════

@test "db_path: CLAUDE_PROJECT_DIR takes priority over git root" {
    export CLAUDE_PROJECT_DIR="$TEST_DIR/custom-project"
    mkdir -p "$CLAUDE_PROJECT_DIR/.clavain/interspect"
    result=$(_interspect_db_path)
    [[ "$result" == "$CLAUDE_PROJECT_DIR/.clavain/interspect/interspect.db" ]]
}

@test "db_path: falls back to git root when no CLAUDE_PROJECT_DIR" {
    unset CLAUDE_PROJECT_DIR
    cd "$TEST_DIR"
    result=$(_interspect_db_path)
    git_root=$(git rev-parse --show-toplevel)
    [[ "$result" == "$git_root/.clavain/interspect/interspect.db" ]]
}

@test "db_path: CWD fallback only when .clavain/interspect exists" {
    unset CLAUDE_PROJECT_DIR
    # Go to a non-git dir that has .clavain/interspect
    local non_git_dir=$(mktemp -d)
    mkdir -p "$non_git_dir/.clavain/interspect"
    cd "$non_git_dir"
    # Disable git
    GIT_DIR=/nonexistent result=$(_interspect_db_path)
    [[ "$result" == "$non_git_dir/.clavain/interspect/interspect.db" ]]
    rm -rf "$non_git_dir"
}

@test "db_path: returns 1 when no valid root found" {
    unset CLAUDE_PROJECT_DIR
    local empty_dir=$(mktemp -d)
    cd "$empty_dir"
    GIT_DIR=/nonexistent run _interspect_db_path
    [[ "$status" -eq 1 ]]
    rm -rf "$empty_dir"
}

# ═══════════════════════════════════════════════════════════════════
# _interspect_record_verdict
# ═══════════════════════════════════════════════════════════════════

@test "record_verdict inserts verdict_outcome event" {
    _interspect_record_verdict "session-1" "fd-safety" "CLEAN" 0 "sonnet"
    local count
    count=$(sqlite3 "$_INTERSPECT_DB" "SELECT COUNT(*) FROM evidence WHERE event='verdict_outcome';")
    [[ "$count" -eq 1 ]]
}

@test "record_verdict normalizes agent name" {
    _interspect_record_verdict "session-1" "interflux:review:fd-safety" "CLEAN" 0 "sonnet"
    local source
    source=$(sqlite3 "$_INTERSPECT_DB" "SELECT source FROM evidence WHERE event='verdict_outcome' LIMIT 1;")
    # Should be normalized (no interflux:review: prefix)
    [[ "$source" == "fd-safety" ]]
}

@test "record_verdict stores context with correct fields" {
    _interspect_record_verdict "session-1" "fd-quality" "NEEDS_ATTENTION" 3 "haiku"
    local ctx
    ctx=$(sqlite3 "$_INTERSPECT_DB" "SELECT context FROM evidence WHERE event='verdict_outcome' LIMIT 1;")
    # Context may have trailing artifacts from sanitize — grep for field presence
    [[ "$ctx" == *'"status"'*'"NEEDS_ATTENTION"'* ]]
    [[ "$ctx" == *'"findings_count"'*'3'* ]]
    [[ "$ctx" == *'"model_used"'*'"haiku"'* ]]
}

@test "record_verdict stores event as verdict_outcome" {
    _interspect_record_verdict "session-1" "fd-safety" "CLEAN" 0 "sonnet"
    local event
    event=$(sqlite3 "$_INTERSPECT_DB" "SELECT event FROM evidence WHERE source='fd-safety' LIMIT 1;")
    [[ "$event" == "verdict_outcome" ]]
}

# ═══════════════════════════════════════════════════════════════════
# _interspect_compute_agent_scores
# ═══════════════════════════════════════════════════════════════════

@test "compute_scores returns empty with no evidence" {
    result=$(_interspect_compute_agent_scores)
    [[ "$result" == "[]" ]]
}

@test "compute_scores excludes agents with < 3 sessions" {
    # Only 2 sessions for fd-safety
    _insert_dispatch "s1" "fd-safety"
    _insert_dispatch "s2" "fd-safety"
    _insert_verdict "s1" "fd-safety" "CLEAN" 0 "sonnet"
    _insert_verdict "s2" "fd-safety" "NEEDS_ATTENTION" 3 "sonnet"
    result=$(_interspect_compute_agent_scores)
    [[ "$result" == "[]" ]]
}

@test "compute_scores excludes agents with zero total findings" {
    # 3 sessions, all CLEAN with 0 findings
    for i in 1 2 3; do
        _insert_dispatch "s$i" "fd-perception"
        _insert_verdict "s$i" "fd-perception" "CLEAN" 0 "haiku"
    done
    result=$(_interspect_compute_agent_scores)
    [[ "$result" == "[]" ]]
}

@test "compute_scores: division by zero does not crash" {
    # All findings_count = 0
    for i in 1 2 3 4; do
        _insert_dispatch "s$i" "fd-perception"
        _insert_verdict "s$i" "fd-perception" "CLEAN" 0 "haiku"
    done
    run _interspect_compute_agent_scores
    [[ "$status" -eq 0 ]]
    # Should return empty (zero findings → excluded)
    [[ "$output" == "[]" ]]
}

@test "compute_scores: high hit rate keeps sonnet recommendation" {
    # Agent with 80% NEEDS_ATTENTION rate (high hit rate = valuable)
    for i in 1 2 3 4 5; do
        _insert_dispatch "s$i" "fd-architecture"
        if [[ $i -le 4 ]]; then
            _insert_verdict "s$i" "fd-architecture" "NEEDS_ATTENTION" 3 "sonnet"
        else
            _insert_verdict "s$i" "fd-architecture" "CLEAN" 1 "sonnet"
        fi
    done
    result=$(_interspect_compute_agent_scores)
    rec=$(echo "$result" | jq -r '.[0].recommended_model')
    [[ "$rec" == "sonnet" ]]
}

@test "compute_scores: low hit rate recommends haiku for non-safety agent" {
    # Agent with 0% NEEDS_ATTENTION (low hit rate, not safety agent)
    for i in 1 2 3 4; do
        _insert_dispatch "s$i" "fd-game-design"
        _insert_verdict "s$i" "fd-game-design" "CLEAN" 1 "sonnet"
    done
    result=$(_interspect_compute_agent_scores)
    rec=$(echo "$result" | jq -r '.[0].recommended_model')
    [[ "$rec" == "haiku" ]]
}

@test "compute_scores: safety floor prevents below-sonnet for safety agents" {
    # fd-safety with 0% hit rate should still get sonnet (safety floor)
    for i in 1 2 3 4; do
        _insert_dispatch "s$i" "fd-safety"
        _insert_verdict "s$i" "fd-safety" "CLEAN" 1 "sonnet"
    done
    result=$(_interspect_compute_agent_scores)
    rec=$(echo "$result" | jq -r '.[0].recommended_model')
    [[ "$rec" == "sonnet" ]]
}

@test "compute_scores: safety floor applies to fd-correctness" {
    for i in 1 2 3 4; do
        _insert_dispatch "s$i" "fd-correctness"
        _insert_verdict "s$i" "fd-correctness" "CLEAN" 1 "sonnet"
    done
    result=$(_interspect_compute_agent_scores)
    rec=$(echo "$result" | jq -r '.[0].recommended_model')
    [[ "$rec" == "sonnet" ]]
}

# ═══════════════════════════════════════════════════════════════════
# _interspect_write_routing_calibration
# ═══════════════════════════════════════════════════════════════════

@test "write_calibration produces valid JSON" {
    # Seed enough evidence for scoring
    for i in 1 2 3 4; do
        _insert_dispatch "s$i" "fd-game-design"
        _insert_verdict "s$i" "fd-game-design" "CLEAN" 1 "sonnet"
    done
    _interspect_write_routing_calibration
    local cal_file="${TEST_DIR}/.clavain/interspect/routing-calibration.json"
    [[ -f "$cal_file" ]]
    jq -e '.' "$cal_file"
}

@test "write_calibration has schema_version 1" {
    for i in 1 2 3 4; do
        _insert_dispatch "s$i" "fd-game-design"
        _insert_verdict "s$i" "fd-game-design" "CLEAN" 1 "sonnet"
    done
    _interspect_write_routing_calibration
    local version
    version=$(jq -r '.schema_version' "${TEST_DIR}/.clavain/interspect/routing-calibration.json")
    [[ "$version" == "1" ]]
}

@test "write_calibration uses fd-prefixed agent keys" {
    for i in 1 2 3 4; do
        _insert_dispatch "s$i" "fd-game-design"
        _insert_verdict "s$i" "fd-game-design" "CLEAN" 1 "sonnet"
    done
    _interspect_write_routing_calibration
    local keys
    keys=$(jq -r '.agents | keys[]' "${TEST_DIR}/.clavain/interspect/routing-calibration.json")
    [[ "$keys" == *"fd-game-design"* ]]
}

# ═══════════════════════════════════════════════════════════════════
# _routing_read_calibration
# ═══════════════════════════════════════════════════════════════════

# Helper: source lib-routing with config and set calibration path
_setup_routing_cal() {
    unset _ROUTING_LOADED
    mkdir -p "$TEST_DIR/config"
    cat > "$TEST_DIR/config/routing.yaml" << 'YAML'
subagents:
  defaults:
    model: sonnet

calibration:
  mode: enforce
YAML
    export CLAVAIN_ROUTING_CONFIG="$TEST_DIR/config/routing.yaml"
    export CLAUDE_PROJECT_DIR="$TEST_DIR"
    source "$SCRIPTS_DIR/lib-routing.sh"
}

@test "read_calibration: no file returns empty" {
    _setup_routing_cal
    result=$(_routing_read_calibration "fd-safety")
    [[ -z "$result" ]]
}

@test "read_calibration: valid file returns recommendation" {
    _setup_routing_cal
    mkdir -p "$TEST_DIR/.clavain/interspect"
    cat > "$TEST_DIR/.clavain/interspect/routing-calibration.json" << 'JSON'
{
    "schema_version": 1,
    "agents": {
        "fd-game-design": {
            "recommended_model": "haiku",
            "confidence": 0.85,
            "evidence_sessions": 5
        }
    }
}
JSON
    result=$(_routing_read_calibration "fd-game-design")
    [[ "$result" == "haiku" ]]
}

@test "read_calibration: strips namespace prefix for lookup" {
    _setup_routing_cal
    mkdir -p "$TEST_DIR/.clavain/interspect"
    cat > "$TEST_DIR/.clavain/interspect/routing-calibration.json" << 'JSON'
{
    "schema_version": 1,
    "agents": {
        "fd-safety": {
            "recommended_model": "sonnet",
            "confidence": 0.85,
            "evidence_sessions": 5
        }
    }
}
JSON
    result=$(_routing_read_calibration "interflux:review:fd-safety")
    [[ "$result" == "sonnet" ]]
}

@test "read_calibration: malformed JSON returns empty" {
    _setup_routing_cal
    mkdir -p "$TEST_DIR/.clavain/interspect"
    echo "not json at all" > "$TEST_DIR/.clavain/interspect/routing-calibration.json"
    result=$(_routing_read_calibration "fd-safety" || true)
    [[ -z "$result" ]]
}

@test "read_calibration: wrong schema version returns empty" {
    _setup_routing_cal
    mkdir -p "$TEST_DIR/.clavain/interspect"
    cat > "$TEST_DIR/.clavain/interspect/routing-calibration.json" << 'JSON'
{
    "schema_version": 99,
    "agents": {
        "fd-safety": {
            "recommended_model": "haiku",
            "confidence": 0.85,
            "evidence_sessions": 5
        }
    }
}
JSON
    result=$(_routing_read_calibration "fd-safety" || true)
    [[ -z "$result" ]]
}

@test "read_calibration: invalid model name is rejected" {
    _setup_routing_cal
    mkdir -p "$TEST_DIR/.clavain/interspect"
    cat > "$TEST_DIR/.clavain/interspect/routing-calibration.json" << 'JSON'
{
    "schema_version": 1,
    "agents": {
        "fd-safety": {
            "recommended_model": "gpt-4-turbo",
            "confidence": 0.85,
            "evidence_sessions": 5
        }
    }
}
JSON
    result=$(_routing_read_calibration "fd-safety" || true)
    [[ -z "$result" ]]
}

@test "read_calibration: low confidence is rejected" {
    _setup_routing_cal
    mkdir -p "$TEST_DIR/.clavain/interspect"
    cat > "$TEST_DIR/.clavain/interspect/routing-calibration.json" << 'JSON'
{
    "schema_version": 1,
    "agents": {
        "fd-safety": {
            "recommended_model": "haiku",
            "confidence": 0.5,
            "evidence_sessions": 5
        }
    }
}
JSON
    result=$(_routing_read_calibration "fd-safety" || true)
    [[ -z "$result" ]]
}

@test "read_calibration: insufficient sessions is rejected" {
    _setup_routing_cal
    mkdir -p "$TEST_DIR/.clavain/interspect"
    cat > "$TEST_DIR/.clavain/interspect/routing-calibration.json" << 'JSON'
{
    "schema_version": 1,
    "agents": {
        "fd-safety": {
            "recommended_model": "haiku",
            "confidence": 0.85,
            "evidence_sessions": 2
        }
    }
}
JSON
    result=$(_routing_read_calibration "fd-safety" || true)
    [[ -z "$result" ]]
}

# ═══════════════════════════════════════════════════════════════════
# routing_resolve_model with B3 calibration
# ═══════════════════════════════════════════════════════════════════

@test "resolve_model: calibration enforce applies recommended model" {
    _setup_routing_cal
    mkdir -p "$TEST_DIR/.clavain/interspect"
    cat > "$TEST_DIR/.clavain/interspect/routing-calibration.json" << 'JSON'
{
    "schema_version": 1,
    "agents": {
        "fd-game-design": {
            "recommended_model": "haiku",
            "confidence": 0.85,
            "evidence_sessions": 5
        }
    }
}
JSON
    # Force bash path (skip ic fast path)
    export CLAVAIN_RUN_ID="test-run"
    result="$(routing_resolve_model --agent fd-game-design)"
    [[ "$result" == "haiku" ]]
}

@test "resolve_model: calibration enforce goes through safety floor" {
    _setup_routing_cal
    # Create agent-roles.yaml with safety floor for fd-safety
    cat > "$TEST_DIR/config/agent-roles.yaml" << 'YAML'
roles:
  reviewer:
    min_model: sonnet
    agents:
      - fd-safety
YAML
    mkdir -p "$TEST_DIR/.clavain/interspect"
    cat > "$TEST_DIR/.clavain/interspect/routing-calibration.json" << 'JSON'
{
    "schema_version": 1,
    "agents": {
        "fd-safety": {
            "recommended_model": "haiku",
            "confidence": 0.85,
            "evidence_sessions": 5
        }
    }
}
JSON
    export CLAVAIN_RUN_ID="test-run"
    result="$(routing_resolve_model --agent fd-safety 2>/dev/null)"
    # Safety floor should clamp haiku → sonnet
    [[ "$result" == "sonnet" ]]
}

@test "resolve_model: shadow mode logs but returns base model" {
    unset _ROUTING_LOADED
    mkdir -p "$TEST_DIR/config"
    cat > "$TEST_DIR/config/routing.yaml" << 'YAML'
subagents:
  defaults:
    model: sonnet

calibration:
  mode: shadow
YAML
    export CLAVAIN_ROUTING_CONFIG="$TEST_DIR/config/routing.yaml"
    export CLAUDE_PROJECT_DIR="$TEST_DIR"
    source "$SCRIPTS_DIR/lib-routing.sh"

    mkdir -p "$TEST_DIR/.clavain/interspect"
    cat > "$TEST_DIR/.clavain/interspect/routing-calibration.json" << 'JSON'
{
    "schema_version": 1,
    "agents": {
        "fd-game-design": {
            "recommended_model": "haiku",
            "confidence": 0.85,
            "evidence_sessions": 5
        }
    }
}
JSON
    export CLAVAIN_RUN_ID="test-run"
    run bash -c "
        unset _ROUTING_LOADED
        export CLAVAIN_ROUTING_CONFIG='$TEST_DIR/config/routing.yaml'
        export CLAUDE_PROJECT_DIR='$TEST_DIR'
        export CLAVAIN_RUN_ID='test-run'
        source '$SCRIPTS_DIR/lib-routing.sh'
        routing_resolve_model --agent fd-game-design
    "
    # stdout should contain base result (sonnet)
    [[ "$output" == *"sonnet"* ]]
    # stderr should contain shadow log
    [[ "$output" == *"interspect-shadow"* ]]
}

@test "resolve_model: INTERSPECT_ROUTING_MODE env overrides yaml" {
    unset _ROUTING_LOADED
    mkdir -p "$TEST_DIR/config"
    cat > "$TEST_DIR/config/routing.yaml" << 'YAML'
subagents:
  defaults:
    model: sonnet

calibration:
  mode: shadow
YAML
    export CLAVAIN_ROUTING_CONFIG="$TEST_DIR/config/routing.yaml"
    export CLAUDE_PROJECT_DIR="$TEST_DIR"
    export INTERSPECT_ROUTING_MODE="enforce"
    source "$SCRIPTS_DIR/lib-routing.sh"

    mkdir -p "$TEST_DIR/.clavain/interspect"
    cat > "$TEST_DIR/.clavain/interspect/routing-calibration.json" << 'JSON'
{
    "schema_version": 1,
    "agents": {
        "fd-game-design": {
            "recommended_model": "haiku",
            "confidence": 0.85,
            "evidence_sessions": 5
        }
    }
}
JSON
    export CLAVAIN_RUN_ID="test-run"
    result="$(routing_resolve_model --agent fd-game-design 2>/dev/null)"
    [[ "$result" == "haiku" ]]
    unset INTERSPECT_ROUTING_MODE
}
