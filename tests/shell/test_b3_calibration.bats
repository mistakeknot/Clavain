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

@test "reader: modern calibration requires explicit propagation eligibility" {
    source "$SCRIPTS_DIR/lib-routing.sh"
    for eligibility in false null '"true"'; do
        printf '{"schema_version":2,"agents":{"fd-quality":{"recommended_model":"haiku","confidence":0.9,"evidence_sessions":30,"propagation_eligible":%s}}}' "$eligibility" > "$TEST_DIR/.clavain/interspect/routing-calibration.json"
        result=$(_routing_read_calibration fd-quality) || true
        [[ -z "$result" ]]
    done
}

@test "reader: schema v3 skill section does not discard eligible agents" {
    source "$SCRIPTS_DIR/lib-routing.sh"
    printf '%s' '{"schema_version":3,"skills":{},"agents":{"fd-quality":{"recommended_model":"haiku","confidence":0.9,"evidence_sessions":30,"propagation_eligible":true}}}' > "$TEST_DIR/.clavain/interspect/routing-calibration.json"
    result=$(_routing_read_calibration fd-quality) || true
    [[ "$result" == haiku ]]
}

@test "reader: invalid numeric types cannot authorize calibration" {
    source "$SCRIPTS_DIR/lib-routing.sh"
    printf '%s' '{"schema_version":2,"agents":{"fd-quality":{"recommended_model":"haiku","confidence":"high","evidence_sessions":"many","propagation_eligible":true}}}' > "$TEST_DIR/.clavain/interspect/routing-calibration.json"
    result=$(_routing_read_calibration fd-quality) || true
    [[ -z "$result" ]]
}

@test "reader: modern phase eligibility is independent and falls back globally" {
    source "$SCRIPTS_DIR/lib-routing.sh"
    printf '%s' '{"schema_version":2,"agents":{"fd-quality":{"recommended_model":"opus","confidence":0.9,"evidence_sessions":30,"propagation_eligible":true,"phases":{"plan":{"recommended_model":"haiku","confidence":0.9,"evidence_sessions":30,"propagation_eligible":false}}}}}' > "$TEST_DIR/.clavain/interspect/routing-calibration.json"
    result=$(_routing_read_calibration fd-quality plan) || true
    [[ "$result" == opus ]]
}

@test "reader: phase aliases are symmetric and exact entries win" {
    source "$SCRIPTS_DIR/lib-routing.sh"
    printf '%s' '{"schema_version":2,"agents":{"fd-quality":{"recommended_model":"sonnet","confidence":0.9,"evidence_sessions":30,"propagation_eligible":true,"phases":{"ship":{"recommended_model":"haiku","confidence":0.9,"evidence_sessions":30,"propagation_eligible":true},"quality-gates":{"recommended_model":"opus","confidence":0.9,"evidence_sessions":30,"propagation_eligible":true},"plan":{"recommended_model":"haiku","confidence":0.9,"evidence_sessions":30,"propagation_eligible":true},"build":{"recommended_model":"opus","confidence":0.9,"evidence_sessions":30,"propagation_eligible":true}}}}}' > "$TEST_DIR/.clavain/interspect/routing-calibration.json"
    [[ "$(_routing_read_calibration fd-quality quality-gates)" == opus ]]
    [[ "$(_routing_read_calibration fd-quality quality_gates)" == haiku ]]
    [[ "$(_routing_read_calibration fd-quality shipping)" == haiku ]]
    [[ "$(_routing_read_calibration fd-quality planning)" == haiku ]]
    [[ "$(_routing_read_calibration fd-quality implementation)" == opus ]]
    [[ "$(_routing_read_calibration fd-quality implement)" == opus ]]
}

@test "reader: shared strict calibration golden cases match shell selection" {
    local cases="$BATS_TEST_DIRNAME/../fixtures/routing-calibration-consumer-cases.json"
    mkdir -p "$TEST_DIR/config"
    while IFS= read -r row; do
        local name mode phase body expected result
        name=$(jq -r '.name' <<< "$row")
        mode=$(jq -r '.mode' <<< "$row")
        phase=$(jq -r '.phase // ""' <<< "$row")
        body=$(jq -r '.body' <<< "$row")
        expected=$(jq -r '.expected_model' <<< "$row")
        printf '%s' "$body" > "$TEST_DIR/.clavain/interspect/routing-calibration.json"
        printf 'subagents:\n  defaults:\n    model: sonnet\ncalibration:\n  mode: %s\n' "$mode" > "$TEST_DIR/config/routing.yaml"
        result=$(env CLAVAIN_ROUTING_CONFIG="$TEST_DIR/config/routing.yaml" \
            CLAUDE_PROJECT_DIR="$TEST_DIR" CLAVAIN_RUN_ID=test-run \
            INTERSPECT_ROUTING_MODE="$mode" SCRIPTS_DIR="$SCRIPTS_DIR" \
            bash -c 'source "$SCRIPTS_DIR/lib-routing.sh"; routing_resolve_model --agent fd-quality --phase "$1"' _ "$phase" 2>/dev/null)
        [[ "$result" == "$expected" ]] || {
            echo "$name: got $result, want $expected" >&2
            return 1
        }
    done < <(jq -c '.[]' "$cases")
}

@test "reader: shared calibration golden cases match the Intercore candidate" {
    # Explicit opt-in only (Sylveste-we1q). This used to default to a dated path
    # under world-writable /tmp and execute whatever was there -- under a daily
    # timer that is a predictable target. Unset means the case is visibly omitted;
    # an explicit path that is not a regular executable file is an error, never a
    # silent fallback to something else.
    local candidate="${INTERCORE_CALIBRATION_CANDIDATE:-}"
    [[ -n "$candidate" ]] || skip "Intercore calibration candidate not available"
    [[ -f "$candidate" && -x "$candidate" ]] || {
        echo "INTERCORE_CALIBRATION_CANDIDATE=$candidate is not an executable regular file" >&2
        return 1
    }
    local cases="$BATS_TEST_DIRNAME/../fixtures/routing-calibration-consumer-cases.json"
    while IFS= read -r row; do
        local name mode phase body expected artifact result got
        name=$(jq -r '.name' <<< "$row")
        mode=$(jq -r '.mode' <<< "$row")
        phase=$(jq -r '.phase // ""' <<< "$row")
        body=$(jq -r '.body' <<< "$row")
        expected=$(jq -r '.expected_model' <<< "$row")
        artifact="$TEST_DIR/${name}.json"
        printf '%s' "$body" > "$artifact"
        local args=(--json route model --agent=fd-quality --calibration="$artifact")
        [[ -n "$phase" ]] && args+=(--phase="$phase")
        run env INTERSPECT_ROUTING_MODE="$mode" CLAVAIN_ROUTING_CONFIG="$SCRIPTS_DIR/../config/routing.yaml" \
            "$candidate" "${args[@]}"
        [[ "$status" -eq 0 ]] || {
            echo "$name: candidate exited $status: $output" >&2
            return 1
        }
        got=$(jq -r '.model' <<< "$output")
        [[ "$got" == "$expected" ]] || {
            echo "$name: candidate got $got, want $expected" >&2
            return 1
        }
    done < <(jq -c '.[]' "$cases")
}

@test "resolve_model: production fast path cannot bypass an enforce calibration artifact" {
    unset CLAVAIN_ROUTING_CONFIG CLAVAIN_RUN_ID _ROUTING_LOADED
    export CLAUDE_PROJECT_DIR="$TEST_DIR"
    export INTERSPECT_ROUTING_MODE=enforce
    printf '%s' '{"schema_version":2,"agents":{"fd-quality":{"recommended_model":"haiku","confidence":0.9,"evidence_sessions":30,"propagation_eligible":true}}}' > "$TEST_DIR/.clavain/interspect/routing-calibration.json"
    source "$SCRIPTS_DIR/lib-routing.sh"
    ic() {
        printf '%s\n' "$*" >> "$TEST_DIR/ic-calls"
        echo opus
    }

    result=$(routing_resolve_model --agent fd-quality)

    [[ "$result" == haiku ]]
    [[ ! -e "$TEST_DIR/ic-calls" ]]
}

@test "resolve_model: invalid calibration mode is visibly static" {
    _setup_routing_cal
    export INTERSPECT_ROUTING_MODE=invalid
    printf '%s' '{"schema_version":2,"agents":{"fd-quality":{"recommended_model":"haiku","confidence":0.9,"evidence_sessions":30,"propagation_eligible":true}}}' > "$TEST_DIR/.clavain/interspect/routing-calibration.json"
    export CLAVAIN_RUN_ID=test-run

    run routing_resolve_model --agent fd-quality

    [[ "$status" -eq 0 ]]
    [[ "$output" == *"invalid calibration mode"* ]]
    [[ "$output" == *"sonnet"* ]]
}

@test "resolve_model: off mode ignores an otherwise eligible artifact" {
    _setup_routing_cal
    export INTERSPECT_ROUTING_MODE=off
    printf '%s' '{"schema_version":2,"agents":{"fd-quality":{"recommended_model":"haiku","confidence":0.9,"evidence_sessions":30,"propagation_eligible":true}}}' > "$TEST_DIR/.clavain/interspect/routing-calibration.json"
    export CLAVAIN_RUN_ID=test-run

    result=$(routing_resolve_model --agent fd-quality)

    [[ "$result" == sonnet ]]
}

@test "resolve_model: missing strict helper is visibly static" {
    _setup_routing_cal
    printf '%s' '{"schema_version":2,"agents":{"fd-quality":{"recommended_model":"haiku","confidence":0.9,"evidence_sessions":30,"propagation_eligible":true}}}' > "$TEST_DIR/.clavain/interspect/routing-calibration.json"
    export CLAVAIN_RUN_ID=test-run
    _ROUTING_CALIBRATION_HELPER="$TEST_DIR/missing-helper.py"

    run routing_resolve_model --agent fd-quality

    [[ "$status" -eq 0 ]]
    [[ "$output" == *"UNVERIFIABLE"* ]]
    [[ "$output" == *"sonnet"* ]]
}

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

@test "write_calibration has schema_version 2" {
    for i in 1 2 3 4; do
        _insert_dispatch "s$i" "fd-game-design"
        _insert_verdict "s$i" "fd-game-design" "CLEAN" 1 "sonnet"
    done
    _interspect_write_routing_calibration
    local version
    version=$(jq -r '.schema_version' "${TEST_DIR}/.clavain/interspect/routing-calibration.json")
    [[ "$version" == "2" ]]
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

@test "read_calibration: schema v1 file is diagnostic only" {
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
    [[ -z "$result" ]]
    evidence=$(_routing_read_calibration "fd-game-design" "" evidence)
    [[ "$(jq -r '.model' <<< "$evidence")" == haiku ]]
    [[ "$(jq -r '.authoritative' <<< "$evidence")" == false ]]
}

@test "read_calibration: schema v2 file returns recommendation" {
    _setup_routing_cal
    mkdir -p "$TEST_DIR/.clavain/interspect"
    cat > "$TEST_DIR/.clavain/interspect/routing-calibration.json" << 'JSON'
{
    "schema_version": 2,
    "agents": {
        "fd-game-design": {
            "recommended_model": "haiku",
            "confidence": 0.85,
            "evidence_sessions": 5,
            "propagation_eligible": true,
            "weighted_hit_rate": 0.1
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
    "schema_version": 2,
    "agents": {
        "fd-safety": {
            "recommended_model": "sonnet",
            "confidence": 0.85,
            "evidence_sessions": 5,
            "propagation_eligible": true
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
    "schema_version": 2,
    "agents": {
        "fd-safety": {
            "recommended_model": "gpt-4-turbo",
            "confidence": 0.85,
            "evidence_sessions": 5,
            "propagation_eligible": true
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
    "schema_version": 2,
    "agents": {
        "fd-safety": {
            "recommended_model": "haiku",
            "confidence": 0.5,
            "evidence_sessions": 5,
            "propagation_eligible": true
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
    "schema_version": 2,
    "agents": {
        "fd-safety": {
            "recommended_model": "haiku",
            "confidence": 0.85,
            "evidence_sessions": 2,
            "propagation_eligible": true
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
    "schema_version": 2,
    "agents": {
        "fd-game-design": {
            "recommended_model": "haiku",
            "confidence": 0.85,
            "evidence_sessions": 5,
            "propagation_eligible": true
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
    "schema_version": 2,
    "agents": {
        "fd-safety": {
            "recommended_model": "haiku",
            "confidence": 0.85,
            "evidence_sessions": 5,
            "propagation_eligible": true
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
    "schema_version": 2,
    "agents": {
        "fd-game-design": {
            "recommended_model": "haiku",
            "confidence": 0.85,
            "evidence_sessions": 5,
            "propagation_eligible": true
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
    "schema_version": 2,
    "agents": {
        "fd-game-design": {
            "recommended_model": "haiku",
            "confidence": 0.85,
            "evidence_sessions": 5,
            "propagation_eligible": true
        }
    }
}
JSON
    export CLAVAIN_RUN_ID="test-run"
    result="$(routing_resolve_model --agent fd-game-design 2>/dev/null)"
    [[ "$result" == "haiku" ]]
    unset INTERSPECT_ROUTING_MODE
}

# ═══════════════════════════════════════════════════════════════════
# Audit-trail emission (Sylveste-a5u — closes audit-trail unconformity)
#
# When B3 calibration runs in shadow mode, every decision branch — including
# the no-op short-circuit where calibrated == base — must emit a
# VerificationStep to .clavain/interspect/microrouter-shadow.jsonl. Without
# this, operators cannot tell "calibration agreed with base" from
# "calibration was never read".
# ═══════════════════════════════════════════════════════════════════

# Helper: write a routing.yaml + calibration.json that makes shadow mode emit.
# After this, sourcing lib-routing.sh and calling routing_resolve_model
# --agent <agent> for the configured agent will produce a JSONL line.
_setup_shadow_audit() {
    local recommended="$1" base="${2:-sonnet}"
    unset _ROUTING_LOADED
    mkdir -p "$TEST_DIR/config" "$TEST_DIR/.clavain/interspect"
    cat > "$TEST_DIR/config/routing.yaml" << YAML
subagents:
  defaults:
    model: $base

calibration:
  mode: shadow
YAML
    cat > "$TEST_DIR/.clavain/interspect/routing-calibration.json" << JSON
{
    "schema_version": 2,
    "agents": {
        "fd-game-design": {
            "recommended_model": "$recommended",
            "confidence": 0.85,
            "evidence_sessions": 5,
            "propagation_eligible": true
        }
    }
}
JSON
    export CLAVAIN_ROUTING_CONFIG="$TEST_DIR/config/routing.yaml"
    export CLAUDE_PROJECT_DIR="$TEST_DIR"
    export CLAVAIN_RUN_ID="test-run"
}

@test "audit: shadow no-op (calibrated == base) emits passthrough VerificationStep" {
    _setup_shadow_audit "sonnet" "sonnet"  # calibrated matches base → no-op
    source "$SCRIPTS_DIR/lib-routing.sh"

    routing_resolve_model --agent fd-game-design >/dev/null 2>&1

    local log="$TEST_DIR/.clavain/interspect/microrouter-shadow.jsonl"
    [[ -f "$log" ]]

    local line
    line=$(tail -n 1 "$log")
    [[ -n "$line" ]]
    [[ $(jq -r '.name' <<< "$line") == "calibration-passthrough" ]]
    [[ $(jq -r '.state' <<< "$line") == "VERIFIED" ]]
    [[ $(jq -r '.decision_type' <<< "$line") == "passthrough" ]]
    [[ $(jq -r '.evidence' <<< "$line") == *"matched B3 calibration:sonnet"* ]]
    [[ $(jq -r '.evidence' <<< "$line") == *"fd-game-design"* ]]
}

@test "audit: shadow record uses the supported durable CLI contract" {
    _setup_shadow_audit "haiku" "sonnet"
    source "$SCRIPTS_DIR/lib-routing.sh"
    ic() {
        [[ "$1 $2" == 'route record' ]] || return 1
        shift 2
        printf '%s\n' "$@" > "$TEST_DIR/record-args"
    }
    routing_resolve_model --agent fd-game-design >/dev/null 2>&1
    [[ -f "$TEST_DIR/record-args" ]]
    ! grep -E '^--[^=]+$' "$TEST_DIR/record-args"
    grep -E '^--model=' "$TEST_DIR/record-args"
    grep -E '^--agent=' "$TEST_DIR/record-args"
    grep -E '^--rule=' "$TEST_DIR/record-args"
    ! grep -E '^--selected-model(=|$)' "$TEST_DIR/record-args"
    ! grep -E '^--meta(=|$)' "$TEST_DIR/record-args"
    grep -E '^--context=' "$TEST_DIR/record-args"
    grep -Fx -- '--run=test-run' "$TEST_DIR/record-args"
    grep -Fx -- "--project=$TEST_DIR" "$TEST_DIR/record-args"
}

@test "audit: recorder stdout cannot contaminate the resolved model" {
    _setup_shadow_audit "haiku" "sonnet"
    source "$SCRIPTS_DIR/lib-routing.sh"
    ic() { printf '%s\n' 'Routing decision recorded: id=1 agent=fd-game-design model=sonnet rule=B3'; }
    result=$(routing_resolve_model --agent fd-game-design 2>/dev/null)
    [[ "$result" == sonnet ]]
}

@test "audit: failed durable shadow recording is explicitly unverifiable" {
    _setup_shadow_audit "haiku" "sonnet"
    source "$SCRIPTS_DIR/lib-routing.sh"
    ic() { return 2; }
    run routing_resolve_model --agent fd-game-design
    [[ "$status" -eq 0 ]]
    [[ "$output" == *"UNVERIFIABLE"* ]]
    [[ "$output" == *"sonnet"* ]]
    [[ "$(jq -s '[.[] | select(.name == "calibration-record" and .state == "UNVERIFIABLE")] | length' "$TEST_DIR/.clavain/interspect/microrouter-shadow.jsonl")" -eq 1 ]]
}

@test "audit: real ic writes one durable isolated routing decision" {
    _setup_shadow_audit "haiku" "sonnet"
    source "$SCRIPTS_DIR/lib-routing.sh"
    unset CLAVAIN_INTERCORE_DB INTERCORE_DB
    export REAL_IC_BIN="${INTERCORE_IC_BIN:-$(command -v ic)}"
    [[ -x "$REAL_IC_BIN" ]]
    ic() { "$REAL_IC_BIN" --db=.clavain/intercore.db "$@"; }
    "$REAL_IC_BIN" --db=.clavain/intercore.db init >/dev/null

    result=$(routing_resolve_model --phase quality-gates --agent fd-game-design 2>"$TEST_DIR/stderr")
    [[ "$result" == sonnet ]]
    [[ ! -s "$TEST_DIR/stderr" || "$(<"$TEST_DIR/stderr")" == *"interspect-shadow"* ]]

    local row
    row=$(sqlite3 -json "$TEST_DIR/.clavain/intercore.db" "SELECT agent, selected_model, rule_matched, phase, project_dir, policy_hash, context_json FROM routing_decisions;")
    [[ "$(jq 'length' <<< "$row")" -eq 1 ]]
    [[ "$(jq -r '.[0].agent' <<< "$row")" == fd-game-design ]]
    [[ "$(jq -r '.[0].selected_model' <<< "$row")" == sonnet ]]
    [[ "$(jq -r '.[0].rule_matched' <<< "$row")" == B3 ]]
    [[ "$(jq -r '.[0].phase' <<< "$row")" == quality-gates ]]
    [[ "$(jq -r '.[0].project_dir' <<< "$row")" == "$TEST_DIR" ]]
    [[ "$(jq -r '.[0].context_json | fromjson | .calibrated_model' <<< "$row")" == haiku ]]
    local calibration_hash routing_hash
    calibration_hash=$(shasum -a 256 "$TEST_DIR/.clavain/interspect/routing-calibration.json" | awk '{print $1}')
    routing_hash=$(shasum -a 256 "$TEST_DIR/config/routing.yaml" | awk '{print $1}')
    [[ "$(jq -r '.[0].context_json | fromjson | .calibration_sha256' <<< "$row")" == "$calibration_hash" ]]
    [[ "$(jq -r '.[0].context_json | fromjson | .routing_sha256' <<< "$row")" == "$routing_hash" ]]
    [[ "$(jq -r '.[0].policy_hash' <<< "$row")" == "$routing_hash" ]]
}

@test "audit: shadow override (calibrated != base) emits override VerificationStep" {
    _setup_shadow_audit "haiku" "sonnet"  # calibrated differs from base → override
    source "$SCRIPTS_DIR/lib-routing.sh"

    routing_resolve_model --agent fd-game-design >/dev/null 2>&1

    local log="$TEST_DIR/.clavain/interspect/microrouter-shadow.jsonl"
    [[ -f "$log" ]]

    local line
    line=$(tail -n 1 "$log")
    [[ $(jq -r '.name' <<< "$line") == "calibration-override" ]]
    [[ $(jq -r '.state' <<< "$line") == "VERIFIED" ]]
    [[ $(jq -r '.decision_type' <<< "$line") == "override" ]]
    [[ $(jq -r '.evidence' <<< "$line") == *"base=sonnet"* ]]
    [[ $(jq -r '.evidence' <<< "$line") == *"calibrated=haiku"* ]]
}

@test "reader: unsupported phase model falls back to a valid global recommendation" {
    source "$SCRIPTS_DIR/lib-routing.sh"
    printf '%s' '{"schema_version":2,"agents":{"fd-quality":{"recommended_model":"opus","confidence":0.9,"evidence_sessions":30,"propagation_eligible":true,"phases":{"ship":{"recommended_model":"unsupported","confidence":0.9,"evidence_sessions":30,"propagation_eligible":true}}}}}' > "$TEST_DIR/.clavain/interspect/routing-calibration.json"
    result=$(_routing_read_calibration fd-quality ship) || true
    [[ "$result" == opus ]]
}

@test "audit: replacement between selection and recording cannot change evidence hashes" {
    _setup_shadow_audit "haiku" "sonnet"
    source "$SCRIPTS_DIR/lib-routing.sh"
    local old_cal old_policy
    old_cal=$(shasum -a 256 "$TEST_DIR/.clavain/interspect/routing-calibration.json" | awk '{print $1}')
    old_policy=$(shasum -a 256 "$TEST_DIR/config/routing.yaml" | awk '{print $1}')
    eval "$(declare -f _routing_record_calibration_shadow | sed '1s/_routing_record_calibration_shadow/_record_before_mutation/')"
    _routing_record_calibration_shadow() {
        printf '%s\n' '{"schema_version":3,"agents":{}}' > "$TEST_DIR/.clavain/interspect/replacement.json"
        mv -f "$TEST_DIR/.clavain/interspect/replacement.json" "$TEST_DIR/.clavain/interspect/routing-calibration.json"
        printf '%s\n' 'subagents:' '  defaults:' '    model: opus' > "$TEST_DIR/config/replacement.yaml"
        mv -f "$TEST_DIR/config/replacement.yaml" "$TEST_DIR/config/routing.yaml"
        _record_before_mutation "$@"
    }
    ic() { printf '%s\n' "$@" > "$TEST_DIR/record-args"; }
    result=$(routing_resolve_model --agent fd-game-design 2>/dev/null)
    [[ "$result" == sonnet ]]
    local context
    context=$(sed -n 's/^--context=//p' "$TEST_DIR/record-args")
    [[ "$(jq -r .calibration_sha256 <<< "$context")" == "$old_cal" ]]
    [[ "$(jq -r .routing_sha256 <<< "$context")" == "$old_policy" ]]
    grep -Fx -- "--policy-hash=$old_policy" "$TEST_DIR/record-args"
}

@test "audit: FLUX_RUN_UUID flows into emitted records" {
    _setup_shadow_audit "sonnet" "sonnet"
    source "$SCRIPTS_DIR/lib-routing.sh"

    FLUX_RUN_UUID="audit-run-xyz" routing_resolve_model --agent fd-game-design >/dev/null 2>&1

    local log="$TEST_DIR/.clavain/interspect/microrouter-shadow.jsonl"
    local line; line=$(tail -n 1 "$log")
    [[ $(jq -r '.run_uuid' <<< "$line") == "audit-run-xyz" ]]
}

@test "audit: enforce mode does NOT emit (no shadow short-circuit to record)" {
    _setup_shadow_audit "haiku" "sonnet"
    # Override mode to enforce — calibration applies directly, no shadow branch
    sed -i.bak 's/mode: shadow/mode: enforce/' "$TEST_DIR/config/routing.yaml" && rm -f "$TEST_DIR/config/routing.yaml.bak"
    source "$SCRIPTS_DIR/lib-routing.sh"

    routing_resolve_model --agent fd-game-design >/dev/null 2>&1

    local log="$TEST_DIR/.clavain/interspect/microrouter-shadow.jsonl"
    [[ ! -f "$log" ]]
}

@test "audit: emit failure (missing primitive) writes diagnostic to stderr" {
    _setup_shadow_audit "sonnet" "sonnet"
    source "$SCRIPTS_DIR/lib-routing.sh"

    # Hide the primitive so emission fails. Helper must surface the gap on
    # stderr — silent-fail would recreate the audit-erasure bug.
    _ROUTING_LIB_DIR="/nonexistent/scripts"

    run routing_resolve_model --agent fd-game-design
    [[ "$status" -eq 0 ]]  # routing must NOT fail just because audit failed
    [[ "$output" == *"verification-emit-fail"* ]]
}

@test "audit: schema 1 shadow is diagnostic without claiming an override" {
    _setup_shadow_audit "haiku" "sonnet"
    local cal="$TEST_DIR/.clavain/interspect/routing-calibration.json"
    jq '.schema_version = 1' "$cal" > "$cal.next"
    mv -f "$cal.next" "$cal"
    source "$SCRIPTS_DIR/lib-routing.sh"
    run routing_resolve_model --agent fd-game-design
    [ "$status" -eq 0 ]
    [[ "$output" == *"diagnostic only"* ]]
    [[ "$output" != *"would override"* ]]
    [[ ! -s "$TEST_DIR/.clavain/interspect/microrouter-shadow.jsonl" ]]
}
