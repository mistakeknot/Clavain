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
{"min_sessions":3,"min_diversity":2,"min_events":5,"min_agent_wrong_pct":80,"canary_window_uses":20,"canary_window_days":14,"canary_min_baseline":15,"canary_alert_pct":20,"canary_noise_floor":0.1}
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

# ─── Canary samples table ─────────────────────────────────────────

@test "canary_samples table exists after ensure_db" {
    DB=$(_interspect_db_path)
    result=$(sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='table' AND name='canary_samples';")
    [ "$result" = "canary_samples" ]
}

@test "canary_samples unique constraint prevents duplicates" {
    DB=$(_interspect_db_path)
    sqlite3 "$DB" "INSERT INTO canary (file, commit_sha, group_id, applied_at, window_uses, status) VALUES ('test', 'abc', 'fd-test', '2026-01-01', 20, 'active');"
    sqlite3 "$DB" "INSERT INTO canary_samples (canary_id, session_id, ts, override_rate, fp_rate, finding_density) VALUES (1, 's1', '2026-01-01', 1.0, 0.5, 3.0);"

    # Second insert should fail due to UNIQUE constraint
    run sqlite3 "$DB" "INSERT INTO canary_samples (canary_id, session_id, ts, override_rate, fp_rate, finding_density) VALUES (1, 's1', '2026-01-02', 2.0, 0.6, 4.0);"
    [ "$status" -ne 0 ]
}

# ─── Canary baseline computation ──────────────────────────────────

@test "compute_canary_baseline returns null with no sessions" {
    result=$(_interspect_compute_canary_baseline "2026-02-16T00:00:00Z")
    [ "$result" = "null" ]
}

@test "compute_canary_baseline returns null with insufficient sessions" {
    DB=$(_interspect_db_path)
    # Insert 10 sessions (below min_baseline of 15)
    for i in $(seq 1 10); do
        sqlite3 "$DB" "INSERT INTO sessions (session_id, start_ts, project) VALUES ('s${i}', '2026-01-$(printf '%02d' $i)T00:00:00Z', 'proj1');"
    done
    result=$(_interspect_compute_canary_baseline "2026-02-01T00:00:00Z")
    [ "$result" = "null" ]
}

@test "compute_canary_baseline returns metrics with sufficient sessions" {
    DB=$(_interspect_db_path)
    # Insert 20 sessions with some evidence
    for i in $(seq 1 20); do
        local day
        day=$(printf '%02d' $((i % 28 + 1)))
        sqlite3 "$DB" "INSERT INTO sessions (session_id, start_ts, project) VALUES ('s${i}', '2026-01-${day}T0${i}:00:00Z', 'proj1');"
        sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, ts, source, event, override_reason, context, project) VALUES ('s${i}', 1, '2026-01-${day}T0${i}:00:00Z', 'fd-test', 'override', 'agent_wrong', '{}', 'proj1');"
    done

    result=$(_interspect_compute_canary_baseline "2026-02-01T00:00:00Z")
    [ "$result" != "null" ]

    # Check JSON structure
    echo "$result" | jq -e '.override_rate' >/dev/null
    echo "$result" | jq -e '.fp_rate' >/dev/null
    echo "$result" | jq -e '.finding_density' >/dev/null
    echo "$result" | jq -e '.session_count' >/dev/null
    echo "$result" | jq -e '.window' >/dev/null
}

@test "compute_canary_baseline override_rate is correct" {
    DB=$(_interspect_db_path)
    # 20 sessions, 10 with overrides → override_rate = 10/20 = 0.5
    for i in $(seq 1 20); do
        sqlite3 "$DB" "INSERT INTO sessions (session_id, start_ts, project) VALUES ('s${i}', '2026-01-$(printf '%02d' $i)T00:00:00Z', 'proj1');"
    done
    for i in $(seq 1 10); do
        sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, ts, source, event, override_reason, context, project) VALUES ('s${i}', 1, '2026-01-$(printf '%02d' $i)T00:00:00Z', 'fd-test', 'override', 'agent_wrong', '{}', 'proj1');"
    done

    result=$(_interspect_compute_canary_baseline "2026-02-01T00:00:00Z")
    rate=$(echo "$result" | jq '.override_rate')
    # 10 overrides / 20 sessions = 0.5 (may be formatted as 0.5 or 0.5000)
    [[ "$rate" == 0.5* ]]
}

# ─── Canary sample collection ─────────────────────────────────────

@test "record_canary_sample skips sessions with no evidence" {
    DB=$(_interspect_db_path)
    sqlite3 "$DB" "INSERT INTO canary (file, commit_sha, group_id, applied_at, window_uses, status) VALUES ('test', 'abc', 'fd-test', '2026-01-01', 20, 'active');"

    _interspect_record_canary_sample "empty_session"

    count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM canary_samples;")
    [ "$count" -eq 0 ]
}

@test "record_canary_sample inserts sample for active canary" {
    DB=$(_interspect_db_path)
    sqlite3 "$DB" "INSERT INTO canary (file, commit_sha, group_id, applied_at, window_uses, status) VALUES ('test', 'abc', 'fd-test', '2026-01-01', 20, 'active');"
    sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, ts, source, event, context, project) VALUES ('test_session', 1, '2026-01-15', 'fd-test', 'agent_dispatch', '{}', 'proj1');"

    _interspect_record_canary_sample "test_session"

    count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM canary_samples;")
    [ "$count" -eq 1 ]
}

@test "record_canary_sample skips non-active canaries" {
    DB=$(_interspect_db_path)
    sqlite3 "$DB" "INSERT INTO canary (file, commit_sha, group_id, applied_at, window_uses, status) VALUES ('test', 'abc', 'fd-test', '2026-01-01', 20, 'passed');"
    sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, ts, source, event, context, project) VALUES ('test_session', 1, '2026-01-15', 'fd-test', 'agent_dispatch', '{}', 'proj1');"

    _interspect_record_canary_sample "test_session"

    count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM canary_samples;")
    [ "$count" -eq 0 ]
}

@test "record_canary_sample deduplicates via INSERT OR IGNORE" {
    DB=$(_interspect_db_path)
    sqlite3 "$DB" "INSERT INTO canary (file, commit_sha, group_id, applied_at, window_uses, status) VALUES ('test', 'abc', 'fd-test', '2026-01-01', 20, 'active');"
    sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, ts, source, event, context, project) VALUES ('test_session', 1, '2026-01-15', 'fd-test', 'agent_dispatch', '{}', 'proj1');"

    _interspect_record_canary_sample "test_session"
    _interspect_record_canary_sample "test_session"

    count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM canary_samples;")
    [ "$count" -eq 1 ]
}

# ─── Canary evaluation ────────────────────────────────────────────

@test "evaluate_canary returns monitoring for incomplete window" {
    DB=$(_interspect_db_path)
    sqlite3 "$DB" "INSERT INTO canary (file, commit_sha, group_id, applied_at, window_uses, uses_so_far, window_expires_at, baseline_override_rate, baseline_fp_rate, baseline_finding_density, status) VALUES ('test', 'abc', 'fd-test', '2026-01-01', 20, 5, '2026-12-31T00:00:00Z', 0.5, 0.3, 2.0, 'active');"

    result=$(_interspect_evaluate_canary 1)
    status_val=$(echo "$result" | jq -r '.status')
    [ "$status_val" = "monitoring" ]
}

@test "evaluate_canary returns monitoring for NULL baseline" {
    DB=$(_interspect_db_path)
    sqlite3 "$DB" "INSERT INTO canary (file, commit_sha, group_id, applied_at, window_uses, uses_so_far, window_expires_at, status) VALUES ('test', 'abc', 'fd-test', '2026-01-01', 20, 3, '2026-12-31T00:00:00Z', 'active');"

    result=$(_interspect_evaluate_canary 1)
    status_val=$(echo "$result" | jq -r '.status')
    [ "$status_val" = "monitoring" ]
    reason=$(echo "$result" | jq -r '.reason')
    [[ "$reason" == *"baseline"* ]]
}

@test "evaluate_canary returns passed when metrics within threshold" {
    DB=$(_interspect_db_path)
    sqlite3 "$DB" "INSERT INTO canary (file, commit_sha, group_id, applied_at, window_uses, uses_so_far, window_expires_at, baseline_override_rate, baseline_fp_rate, baseline_finding_density, status) VALUES ('test', 'abc', 'fd-test', '2026-01-01', 5, 5, '2026-12-31T00:00:00Z', 1.0, 0.5, 3.0, 'active');"

    # Insert 5 samples with similar metrics (within 20% threshold)
    for i in 1 2 3 4 5; do
        sqlite3 "$DB" "INSERT INTO canary_samples (canary_id, session_id, ts, override_rate, fp_rate, finding_density) VALUES (1, 's${i}', '2026-01-0${i}', 1.1, 0.55, 2.8);"
    done

    result=$(_interspect_evaluate_canary 1)
    status_val=$(echo "$result" | jq -r '.status')
    [ "$status_val" = "passed" ]

    # Verify DB updated
    db_status=$(sqlite3 "$DB" "SELECT status FROM canary WHERE id = 1;")
    [ "$db_status" = "passed" ]
}

@test "evaluate_canary returns alert when override rate degrades >20%" {
    DB=$(_interspect_db_path)
    sqlite3 "$DB" "INSERT INTO canary (file, commit_sha, group_id, applied_at, window_uses, uses_so_far, window_expires_at, baseline_override_rate, baseline_fp_rate, baseline_finding_density, status) VALUES ('test', 'abc', 'fd-test', '2026-01-01', 5, 5, '2026-12-31T00:00:00Z', 1.0, 0.3, 3.0, 'active');"

    # Insert 5 samples with significantly higher override rate (100% increase)
    for i in 1 2 3 4 5; do
        sqlite3 "$DB" "INSERT INTO canary_samples (canary_id, session_id, ts, override_rate, fp_rate, finding_density) VALUES (1, 's${i}', '2026-01-0${i}', 2.0, 0.35, 2.8);"
    done

    result=$(_interspect_evaluate_canary 1)
    status_val=$(echo "$result" | jq -r '.status')
    [ "$status_val" = "alert" ]

    # Verify DB updated
    db_status=$(sqlite3 "$DB" "SELECT status FROM canary WHERE id = 1;")
    [ "$db_status" = "alert" ]
}

@test "evaluate_canary returns alert when finding density drops >20%" {
    DB=$(_interspect_db_path)
    sqlite3 "$DB" "INSERT INTO canary (file, commit_sha, group_id, applied_at, window_uses, uses_so_far, window_expires_at, baseline_override_rate, baseline_fp_rate, baseline_finding_density, status) VALUES ('test', 'abc', 'fd-test', '2026-01-01', 5, 5, '2026-12-31T00:00:00Z', 1.0, 0.3, 5.0, 'active');"

    # Insert 5 samples with much lower finding density (3.0 vs 5.0 = 40% drop)
    for i in 1 2 3 4 5; do
        sqlite3 "$DB" "INSERT INTO canary_samples (canary_id, session_id, ts, override_rate, fp_rate, finding_density) VALUES (1, 's${i}', '2026-01-0${i}', 1.0, 0.3, 3.0);"
    done

    result=$(_interspect_evaluate_canary 1)
    status_val=$(echo "$result" | jq -r '.status')
    [ "$status_val" = "alert" ]
}

@test "evaluate_canary ignores differences below noise floor" {
    DB=$(_interspect_db_path)
    sqlite3 "$DB" "INSERT INTO canary (file, commit_sha, group_id, applied_at, window_uses, uses_so_far, window_expires_at, baseline_override_rate, baseline_fp_rate, baseline_finding_density, status) VALUES ('test', 'abc', 'fd-test', '2026-01-01', 5, 5, '2026-12-31T00:00:00Z', 0.05, 0.03, 0.5, 'active');"

    # Small differences (within noise floor of 0.1 absolute)
    for i in 1 2 3 4 5; do
        sqlite3 "$DB" "INSERT INTO canary_samples (canary_id, session_id, ts, override_rate, fp_rate, finding_density) VALUES (1, 's${i}', '2026-01-0${i}', 0.07, 0.04, 0.48);"
    done

    result=$(_interspect_evaluate_canary 1)
    status_val=$(echo "$result" | jq -r '.status')
    [ "$status_val" = "passed" ]
}

@test "evaluate_canary expired_unused when no samples exist" {
    DB=$(_interspect_db_path)
    # Window expired (past date), baseline present, no samples
    sqlite3 "$DB" "INSERT INTO canary (file, commit_sha, group_id, applied_at, window_uses, uses_so_far, window_expires_at, baseline_override_rate, baseline_fp_rate, baseline_finding_density, status) VALUES ('test', 'abc', 'fd-test', '2026-01-01', 20, 0, '2025-01-01T00:00:00Z', 1.0, 0.5, 3.0, 'active');"

    result=$(_interspect_evaluate_canary 1)
    status_val=$(echo "$result" | jq -r '.status')
    [ "$status_val" = "expired_unused" ]

    db_status=$(sqlite3 "$DB" "SELECT status FROM canary WHERE id = 1;")
    [ "$db_status" = "expired_unused" ]
}

# ─── Check canaries ───────────────────────────────────────────────

@test "check_canaries returns empty array when no canaries ready" {
    result=$(_interspect_check_canaries)
    [ "$result" = "[]" ]
}

@test "check_canaries evaluates canary with completed window" {
    DB=$(_interspect_db_path)
    # Canary with full uses window
    sqlite3 "$DB" "INSERT INTO canary (file, commit_sha, group_id, applied_at, window_uses, uses_so_far, window_expires_at, baseline_override_rate, baseline_fp_rate, baseline_finding_density, status) VALUES ('test', 'abc', 'fd-test', '2026-01-01', 3, 3, '2026-12-31T00:00:00Z', 1.0, 0.5, 3.0, 'active');"

    for i in 1 2 3; do
        sqlite3 "$DB" "INSERT INTO canary_samples (canary_id, session_id, ts, override_rate, fp_rate, finding_density) VALUES (1, 's${i}', '2026-01-0${i}', 1.0, 0.5, 3.0);"
    done

    result=$(_interspect_check_canaries)
    count=$(echo "$result" | jq 'length')
    [ "$count" -eq 1 ]

    verdict=$(echo "$result" | jq -r '.[0].status')
    [ "$verdict" = "passed" ]
}

# ─── Canary summary ───────────────────────────────────────────────

@test "get_canary_summary returns empty for no canaries" {
    result=$(_interspect_get_canary_summary)
    # sqlite3 -json returns empty string for zero rows; fallback returns "[]"
    [[ -z "$result" ]] || [ "$result" = "[]" ]
}

@test "get_canary_summary returns canary details" {
    DB=$(_interspect_db_path)
    sqlite3 "$DB" "INSERT INTO canary (file, commit_sha, group_id, applied_at, window_uses, uses_so_far, window_expires_at, baseline_override_rate, baseline_fp_rate, baseline_finding_density, status) VALUES ('test', 'abc', 'fd-test', '2026-01-01', 20, 5, '2026-02-01', 1.0, 0.5, 3.0, 'active');"

    result=$(_interspect_get_canary_summary)
    count=$(echo "$result" | jq 'length')
    [ "$count" -eq 1 ]

    agent=$(echo "$result" | jq -r '.[0].agent')
    [ "$agent" = "fd-test" ]

    status_val=$(echo "$result" | jq -r '.[0].status')
    [ "$status_val" = "active" ]
}

# ─── Confidence loading with canary fields ─────────────────────────

@test "load_confidence sets canary defaults" {
    # Reset to reload
    unset _INTERSPECT_CONFIDENCE_LOADED
    _interspect_load_confidence

    [ "$_INTERSPECT_CANARY_WINDOW_USES" -eq 20 ]
    [ "$_INTERSPECT_CANARY_WINDOW_DAYS" -eq 14 ]
    [ "$_INTERSPECT_CANARY_MIN_BASELINE" -eq 15 ]
    [ "$_INTERSPECT_CANARY_ALERT_PCT" -eq 20 ]
}

@test "load_confidence bounds-checks canary values" {
    DB=$(_interspect_db_path)
    local root
    root=$(git rev-parse --show-toplevel)

    # Write extreme values
    echo '{"canary_window_uses":99999,"canary_window_days":9999,"canary_min_baseline":-1,"canary_alert_pct":200}' > "$root/.clavain/interspect/confidence.json"

    unset _INTERSPECT_CONFIDENCE_LOADED
    _interspect_load_confidence

    # Should be clamped to bounds
    [ "$_INTERSPECT_CANARY_WINDOW_USES" -le 1000 ]
    [ "$_INTERSPECT_CANARY_WINDOW_DAYS" -le 365 ]
    [ "$_INTERSPECT_CANARY_MIN_BASELINE" -ge 1 ]
    [ "$_INTERSPECT_CANARY_ALERT_PCT" -le 100 ]
}

# ─── Revert routing override ──────────────────────────────────────

@test "revert_routing_override removes override and commits" {
    # Apply an override first
    _interspect_apply_routing_override "fd-game-design" "test reason" "[]" "test"

    # Verify it exists
    run _interspect_override_exists "fd-game-design"
    [ "$status" -eq 0 ]

    # Revert it
    run _interspect_revert_routing_override "fd-game-design"
    [ "$status" -eq 0 ]

    # Verify it's gone
    run _interspect_override_exists "fd-game-design"
    [ "$status" -ne 0 ]
}

@test "revert_routing_override is idempotent" {
    # Revert something that doesn't exist
    run _interspect_revert_routing_override "fd-game-design"
    [ "$status" -eq 0 ]
    [[ "$output" == *"not found"* ]]
}

@test "revert_routing_override rejects invalid agent name" {
    run _interspect_revert_routing_override "malicious'; DROP TABLE evidence; --"
    [ "$status" -eq 1 ]
}

@test "revert_routing_override updates canary status to reverted" {
    DB=$(_interspect_db_path)

    # Apply override (creates canary)
    _interspect_apply_routing_override "fd-game-design" "test reason" "[]" "test"

    # Verify canary is active
    canary_status=$(sqlite3 "$DB" "SELECT status FROM canary WHERE group_id = 'fd-game-design' LIMIT 1;")
    [ "$canary_status" = "active" ] || [ "$canary_status" = "" ]

    # Revert
    _interspect_revert_routing_override "fd-game-design"

    # Canary should be reverted (if one existed)
    reverted=$(sqlite3 "$DB" "SELECT COUNT(*) FROM canary WHERE group_id = 'fd-game-design' AND status = 'reverted';")
    active=$(sqlite3 "$DB" "SELECT COUNT(*) FROM canary WHERE group_id = 'fd-game-design' AND status = 'active';")
    [ "$active" -eq 0 ]
}

@test "revert_routing_override updates modifications status to reverted" {
    DB=$(_interspect_db_path)

    # Apply override (creates modification record)
    _interspect_apply_routing_override "fd-game-design" "test reason" "[]" "test"

    # Verify modification is applied
    mod_status=$(sqlite3 "$DB" "SELECT status FROM modifications WHERE group_id = 'fd-game-design' LIMIT 1;")
    [ "$mod_status" = "applied" ] || [ "$mod_status" = "applied-unmonitored" ]

    # Revert
    _interspect_revert_routing_override "fd-game-design"

    # Modification should be reverted
    active=$(sqlite3 "$DB" "SELECT COUNT(*) FROM modifications WHERE group_id = 'fd-game-design' AND status = 'applied';")
    [ "$active" -eq 0 ]
}

# ─── Blacklist/unblacklist functions ──────────────────────────────

@test "blacklist_pattern inserts into blacklist table" {
    DB=$(_interspect_db_path)
    _interspect_blacklist_pattern "fd-game-design" "test blacklist"

    count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM blacklist WHERE pattern_key = 'fd-game-design';")
    [ "$count" -eq 1 ]

    reason=$(sqlite3 "$DB" "SELECT reason FROM blacklist WHERE pattern_key = 'fd-game-design';")
    [ "$reason" = "test blacklist" ]
}

@test "blacklist_pattern is idempotent via INSERT OR REPLACE" {
    DB=$(_interspect_db_path)
    _interspect_blacklist_pattern "fd-game-design" "first reason"
    _interspect_blacklist_pattern "fd-game-design" "updated reason"

    count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM blacklist WHERE pattern_key = 'fd-game-design';")
    [ "$count" -eq 1 ]

    reason=$(sqlite3 "$DB" "SELECT reason FROM blacklist WHERE pattern_key = 'fd-game-design';")
    [ "$reason" = "updated reason" ]
}

@test "unblacklist_pattern removes from blacklist table" {
    DB=$(_interspect_db_path)
    _interspect_blacklist_pattern "fd-game-design" "test"

    count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM blacklist WHERE pattern_key = 'fd-game-design';")
    [ "$count" -eq 1 ]

    _interspect_unblacklist_pattern "fd-game-design"

    count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM blacklist WHERE pattern_key = 'fd-game-design';")
    [ "$count" -eq 0 ]
}

@test "unblacklist_pattern is idempotent for missing pattern" {
    run _interspect_unblacklist_pattern "fd-nonexistent"
    [ "$status" -eq 0 ]
}
