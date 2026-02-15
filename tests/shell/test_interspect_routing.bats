#!/usr/bin/env bats
# Tests for interspect routing override helpers in lib-interspect.sh
# Requires: bats-core, jq, sqlite3

setup() {
    load test_helper

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
{"min_sessions":3,"min_diversity":2,"min_events":5,"min_agent_wrong_pct":80}
EOF

    # Create minimal protected-paths.json
    cat > "$TEST_DIR/.clavain/interspect/protected-paths.json" << 'EOF'
{"protected_paths":[],"modification_allow_list":[".claude/routing-overrides.json"],"always_propose":[]}
EOF

    # Reset guard variables so lib can be re-sourced
    unset _LIB_INTERSPECT_LOADED _INTERSPECT_CONFIDENCE_LOADED _INTERSPECT_MANIFEST_LOADED

    # Source lib-interspect.sh from hooks dir
    source "$HOOKS_DIR/lib-interspect.sh"
    _interspect_ensure_db
}

teardown() {
    rm -rf "$TEST_DIR" 2>/dev/null || true
}

# ─── Blacklist table ────────────────────────────────────────────────

@test "blacklist table exists after ensure_db" {
    DB=$(_interspect_db_path)
    result=$(sqlite3 "$DB" ".tables" | grep -c "blacklist")
    [ "$result" -ge 1 ]
}

# ─── SQL escape ─────────────────────────────────────────────────────

@test "sql_escape handles single quotes" {
    result=$(_interspect_sql_escape "it's a test")
    [ "$result" = "it''s a test" ]
}

@test "sql_escape handles backslashes" {
    result=$(_interspect_sql_escape 'back\\slash')
    [ "$result" = 'back\\\\slash' ]
}

@test "sql_escape strips control characters" {
    input=$'fd-game\tdesign'
    result=$(_interspect_sql_escape "$input")
    [ "$result" = "fd-gamedesign" ]
}

# ─── Agent name validation ──────────────────────────────────────────

@test "validate_agent_name accepts valid names" {
    run _interspect_validate_agent_name "fd-game-design"
    [ "$status" -eq 0 ]
}

@test "validate_agent_name accepts fd-quality" {
    run _interspect_validate_agent_name "fd-quality"
    [ "$status" -eq 0 ]
}

@test "validate_agent_name rejects SQL injection" {
    run _interspect_validate_agent_name "fd-game'; DROP TABLE evidence; --"
    [ "$status" -eq 1 ]
}

@test "validate_agent_name rejects non-fd prefix" {
    run _interspect_validate_agent_name "malicious-agent"
    [ "$status" -eq 1 ]
}

@test "validate_agent_name rejects uppercase" {
    run _interspect_validate_agent_name "fd-Game-Design"
    [ "$status" -eq 1 ]
}

@test "validate_agent_name rejects empty string" {
    run _interspect_validate_agent_name ""
    [ "$status" -eq 1 ]
}

# ─── Path validation ───────────────────────────────────────────────

@test "validate_overrides_path accepts default path" {
    run _interspect_validate_overrides_path ".claude/routing-overrides.json"
    [ "$status" -eq 0 ]
}

@test "validate_overrides_path rejects absolute path" {
    run _interspect_validate_overrides_path "/etc/passwd"
    [ "$status" -eq 1 ]
}

@test "validate_overrides_path rejects traversal" {
    run _interspect_validate_overrides_path "../../../etc/passwd"
    [ "$status" -eq 1 ]
}

# ─── Read routing overrides ────────────────────────────────────────

@test "read routing overrides returns empty for missing file" {
    result=$(_interspect_read_routing_overrides)
    version=$(echo "$result" | jq -r '.version')
    count=$(echo "$result" | jq '.overrides | length')
    [ "$version" = "1" ]
    [ "$count" = "0" ]
}

@test "read routing overrides returns data for valid file" {
    mkdir -p "$TEST_DIR/.claude"
    echo '{"version":1,"overrides":[{"agent":"fd-game-design","action":"exclude"}]}' > "$TEST_DIR/.claude/routing-overrides.json"

    result=$(_interspect_read_routing_overrides)
    agent=$(echo "$result" | jq -r '.overrides[0].agent')
    [ "$agent" = "fd-game-design" ]
}

@test "read routing overrides handles malformed JSON" {
    mkdir -p "$TEST_DIR/.claude"
    echo 'NOT-JSON{{{' > "$TEST_DIR/.claude/routing-overrides.json"

    result=$(_interspect_read_routing_overrides 2>/dev/null) || true
    version=$(echo "$result" | jq -r '.version')
    [ "$version" = "1" ]
}

# ─── Write routing overrides ───────────────────────────────────────

@test "write and read routing overrides round-trip" {
    local content='{"version":1,"overrides":[{"agent":"fd-game-design","action":"exclude","reason":"test","evidence_ids":[],"created":"2026-01-01","created_by":"test"}]}'
    _interspect_write_routing_overrides "$content"

    result=$(_interspect_read_routing_overrides)
    agent=$(echo "$result" | jq -r '.overrides[0].agent')
    [ "$agent" = "fd-game-design" ]
}

@test "write routing overrides rejects invalid JSON" {
    run _interspect_write_routing_overrides "NOT VALID JSON"
    [ "$status" -eq 1 ]
}

# ─── Override exists check ──────────────────────────────────────────

@test "override_exists returns 1 for missing file" {
    run _interspect_override_exists "fd-game-design"
    [ "$status" -ne 0 ]
}

@test "override_exists returns 0 after write" {
    mkdir -p "$TEST_DIR/.claude"
    echo '{"version":1,"overrides":[{"agent":"fd-game-design","action":"exclude"}]}' > "$TEST_DIR/.claude/routing-overrides.json"

    run _interspect_override_exists "fd-game-design"
    [ "$status" -eq 0 ]
}

# ─── Routing eligibility ───────────────────────────────────────────

@test "is_routing_eligible returns not_eligible for no events" {
    result=$(_interspect_is_routing_eligible "fd-game-design" 2>/dev/null) || true
    [[ "$result" == *"no_override_events"* ]]
}

@test "is_routing_eligible returns not_eligible for blacklisted agent" {
    DB=$(_interspect_db_path)
    sqlite3 "$DB" "INSERT INTO blacklist (pattern_key, blacklisted_at) VALUES ('fd-game-design', '2026-01-01');"
    result=$(_interspect_is_routing_eligible "fd-game-design" 2>/dev/null) || true
    [[ "$result" == *"blacklisted"* ]]
}

@test "is_routing_eligible returns eligible at 80% threshold" {
    DB=$(_interspect_db_path)
    # Insert 5 events: 4 agent_wrong, 1 deprioritized (80%)
    for i in 1 2 3 4; do
        sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, ts, source, event, override_reason, context, project) VALUES ('s$i', $i, '2026-01-0${i}', 'fd-game-design', 'override', 'agent_wrong', '{}', 'proj$((i % 3 + 1))');"
    done
    sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, ts, source, event, override_reason, context, project) VALUES ('s5', 5, '2026-01-05', 'fd-game-design', 'override', 'deprioritized', '{}', 'proj1');"

    result=$(_interspect_is_routing_eligible "fd-game-design")
    [ "$result" = "eligible" ]
}

@test "is_routing_eligible returns not_eligible below threshold" {
    DB=$(_interspect_db_path)
    # Insert 5 events: 3 agent_wrong, 2 deprioritized (60%)
    for i in 1 2 3; do
        sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, ts, source, event, override_reason, context, project) VALUES ('s$i', $i, '2026-01-0${i}', 'fd-game-design', 'override', 'agent_wrong', '{}', 'proj$i');"
    done
    for i in 4 5; do
        sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, ts, source, event, override_reason, context, project) VALUES ('s$i', $i, '2026-01-0${i}', 'fd-game-design', 'override', 'deprioritized', '{}', 'proj1');"
    done

    result=$(_interspect_is_routing_eligible "fd-game-design" 2>/dev/null) || true
    [[ "$result" == *"not_eligible"* ]]
}

@test "is_routing_eligible rejects invalid agent name" {
    run _interspect_is_routing_eligible "malicious'; DROP TABLE evidence; --"
    [ "$status" -eq 1 ]
    [[ "$output" == *"not_eligible:invalid_agent_name"* ]]
}

@test "is_routing_eligible truncates percentage (7/9 = 77% < 80%)" {
    DB=$(_interspect_db_path)
    for i in 1 2 3 4 5 6 7; do
        sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, ts, source, event, override_reason, context, project) VALUES ('s$i', $i, '2026-01-0${i}', 'fd-game-design', 'override', 'agent_wrong', '{}', 'proj$((i % 3 + 1))');"
    done
    for i in 8 9; do
        sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, ts, source, event, override_reason, context, project) VALUES ('s$i', $i, '2026-01-0${i}', 'fd-game-design', 'override', 'deprioritized', '{}', 'proj1');"
    done

    result=$(_interspect_is_routing_eligible "fd-game-design" 2>/dev/null) || true
    [[ "$result" == *"not_eligible"* ]]
}

# ─── Blacklist migration on existing DB ─────────────────────────────

@test "ensure_db adds blacklist table to existing DB" {
    DB=$(_interspect_db_path)

    # Verify table was created (even though DB already existed from setup)
    result=$(sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='table' AND name='blacklist';")
    [ "$result" = "blacklist" ]
}
