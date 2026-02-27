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
{"protected_paths":[],"modification_allow_list":[".claude/routing-overrides.json",".clavain/interspect/overlays/*/*"],"always_propose":[]}
EOF

    # Reset guard variables so lib can be re-sourced
    unset _LIB_INTERSPECT_LOADED _INTERSPECT_CONFIDENCE_LOADED _INTERSPECT_MANIFEST_LOADED

    # Source lib-interspect.sh from interspect companion plugin
    # Searches: INTERSPECT_ROOT env, monorepo sibling, clavain hooks (legacy)
    local interspect_lib=""
    if [[ -n "${INTERSPECT_ROOT:-}" ]]; then
        interspect_lib="$INTERSPECT_ROOT/hooks/lib-interspect.sh"
    elif [[ -f "$BATS_TEST_DIRNAME/../../../../interverse/interspect/hooks/lib-interspect.sh" ]]; then
        interspect_lib="$BATS_TEST_DIRNAME/../../../../interverse/interspect/hooks/lib-interspect.sh"
    elif [[ -f "$HOOKS_DIR/lib-interspect.sh" ]]; then
        interspect_lib="$HOOKS_DIR/lib-interspect.sh"
    else
        skip "lib-interspect.sh not found (install interspect companion plugin)"
    fi
    source "$interspect_lib"
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

# ─── Pattern Detection Helpers ──────────────────────────────────────

@test "get_routing_eligible returns agents meeting all criteria" {
    DB=$(_interspect_db_path)
    # Insert 6 agent_wrong events across 3 sessions and 3 projects for fd-game-design
    for i in 1 2 3 4 5 6; do
        sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, ts, source, event, override_reason, context, project) VALUES ('s$i', $i, '2026-01-0${i}', 'fd-game-design', 'override', 'agent_wrong', '{}', 'proj$((i % 3 + 1))');"
    done

    result=$(_interspect_get_routing_eligible)
    echo "result: $result"
    [ -n "$result" ]
    echo "$result" | grep -q "fd-game-design"
}

@test "get_routing_eligible excludes agents below 80% wrong" {
    DB=$(_interspect_db_path)
    # 3 agent_wrong + 3 deprioritized = 50% wrong (below 80%)
    for i in 1 2 3; do
        sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, ts, source, event, override_reason, context, project) VALUES ('s$i', $i, '2026-01-0${i}', 'fd-test-agent', 'override', 'agent_wrong', '{}', 'proj$((i % 3 + 1))');"
    done
    for i in 4 5 6; do
        sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, ts, source, event, override_reason, context, project) VALUES ('s$i', $i, '2026-01-0${i}', 'fd-test-agent', 'override', 'deprioritized', '{}', 'proj$((i % 3 + 1))');"
    done

    result=$(_interspect_get_routing_eligible)
    echo "result: $result"
    # Should NOT contain fd-test-agent (50% < 80%)
    ! echo "$result" | grep -q "fd-test-agent"
}

@test "get_routing_eligible excludes already-overridden agents" {
    DB=$(_interspect_db_path)
    # Insert enough evidence to be eligible
    for i in 1 2 3 4 5 6; do
        sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, ts, source, event, override_reason, context, project) VALUES ('s$i', $i, '2026-01-0${i}', 'fd-game-design', 'override', 'agent_wrong', '{}', 'proj$((i % 3 + 1))');"
    done
    # Create an existing override
    mkdir -p "$TEST_DIR/.claude"
    cat > "$TEST_DIR/.claude/routing-overrides.json" << 'EOF'
{"version":1,"overrides":[{"agent":"fd-game-design","action":"exclude","reason":"test"}]}
EOF
    git add .claude/routing-overrides.json && git commit -q -m "add override"

    result=$(_interspect_get_routing_eligible)
    echo "result: $result"
    # Should be empty — agent already overridden
    [ -z "$result" ]
}

@test "get_routing_eligible returns empty on no evidence" {
    result=$(_interspect_get_routing_eligible)
    [ -z "$result" ]
}

# ─── Overlay Eligible ──────────────────────────────────────────────

@test "get_overlay_eligible returns agents in 40-79% wrong band" {
    DB=$(_interspect_db_path)
    # Need "ready" classification on at least one row: >=5 events, >=3 sessions, >=2 projects.
    # Insert 10 events: 6 agent_wrong + 4 deprioritized = 60% wrong (in 40-79% band)
    # agent_wrong: 6 events across s1-s6, projects proj1-proj3 → ready (6>=5, 6>=3, 3>=2)
    for i in 1 2 3 4 5 6; do
        sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, ts, source, event, override_reason, context, project) VALUES ('s$i', $i, '2026-01-0${i}', 'fd-overlay-test', 'override', 'agent_wrong', '{}', 'proj$((i % 3 + 1))');"
    done
    # deprioritized: 4 events across s7-s10 → growing (4<5 events)
    for i in 7 8 9; do
        sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, ts, source, event, override_reason, context, project) VALUES ('s$((i))', $i, '2026-01-0${i}', 'fd-overlay-test', 'override', 'deprioritized', '{}', 'proj$((i % 3 + 1))');"
    done
    sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, ts, source, event, override_reason, context, project) VALUES ('s10', 10, '2026-01-10', 'fd-overlay-test', 'override', 'deprioritized', '{}', 'proj1');"

    result=$(_interspect_get_overlay_eligible)
    echo "result: $result"
    [ -n "$result" ]
    echo "$result" | grep -q "fd-overlay-test"
}

@test "get_overlay_eligible excludes agents at 80%+ (routing territory)" {
    DB=$(_interspect_db_path)
    # Insert 6 agent_wrong events = 100% wrong (should be routing, not overlay)
    for i in 1 2 3 4 5 6; do
        sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, ts, source, event, override_reason, context, project) VALUES ('s$i', $i, '2026-01-0${i}', 'fd-too-wrong', 'override', 'agent_wrong', '{}', 'proj$((i % 3 + 1))');"
    done

    result=$(_interspect_get_overlay_eligible)
    echo "result: $result"
    ! echo "$result" | grep -q "fd-too-wrong"
}

@test "get_overlay_eligible excludes agents below 40%" {
    DB=$(_interspect_db_path)
    # Insert 6 events: 2 agent_wrong + 4 deprioritized = 33% wrong (below 40%)
    for i in 1 2; do
        sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, ts, source, event, override_reason, context, project) VALUES ('s$i', $i, '2026-01-0${i}', 'fd-low-wrong', 'override', 'agent_wrong', '{}', 'proj$((i % 3 + 1))');"
    done
    for i in 3 4 5 6; do
        sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, ts, source, event, override_reason, context, project) VALUES ('s$i', $i, '2026-01-0${i}', 'fd-low-wrong', 'override', 'deprioritized', '{}', 'proj$((i % 3 + 1))');"
    done

    result=$(_interspect_get_overlay_eligible)
    echo "result: $result"
    ! echo "$result" | grep -q "fd-low-wrong"
}

# ─── Cross-Cutting Detection ──────────────────────────────────────

@test "is_cross_cutting identifies architecture agent" {
    run _interspect_is_cross_cutting "fd-architecture"
    [ "$status" -eq 0 ]
}

@test "is_cross_cutting identifies safety agent" {
    run _interspect_is_cross_cutting "fd-safety"
    [ "$status" -eq 0 ]
}

@test "is_cross_cutting identifies quality agent" {
    run _interspect_is_cross_cutting "fd-quality"
    [ "$status" -eq 0 ]
}

@test "is_cross_cutting identifies correctness agent" {
    run _interspect_is_cross_cutting "fd-correctness"
    [ "$status" -eq 0 ]
}

@test "is_cross_cutting rejects non-cross-cutting agent" {
    run _interspect_is_cross_cutting "fd-game-design"
    [ "$status" -eq 1 ]
}

# ─── Propose Writer ─────────────────────────────────────────────────

@test "apply_propose writes propose action to routing-overrides.json" {
    _interspect_apply_propose "fd-game-design" "Agent produces irrelevant findings" '["ev1","ev2"]' "interspect"

    local root
    root=$(git rev-parse --show-toplevel)
    local overrides
    overrides=$(cat "$root/.claude/routing-overrides.json")

    # Verify action is "propose" not "exclude"
    local action
    action=$(echo "$overrides" | jq -r '.overrides[0].action')
    [ "$action" = "propose" ]

    # Verify agent name
    local agent
    agent=$(echo "$overrides" | jq -r '.overrides[0].agent')
    [ "$agent" = "fd-game-design" ]

    # Verify it was committed
    local log
    log=$(git log --oneline -1)
    echo "$log" | grep -q "Propose excluding fd-game-design"
}

@test "apply_propose skips if override already exists" {
    # Create an existing exclude override
    mkdir -p "$TEST_DIR/.claude"
    cat > "$TEST_DIR/.claude/routing-overrides.json" << 'EOF'
{"version":1,"overrides":[{"agent":"fd-game-design","action":"exclude","reason":"test"}]}
EOF
    git add .claude/routing-overrides.json && git commit -q -m "add override"

    run _interspect_apply_propose "fd-game-design" "test" '[]' "interspect"
    echo "output: $output"
    # Exit 0 (skip is not an error) and stdout says "already exists"
    [ "$status" -eq 0 ]
    echo "$output" | grep -qi "already exists"
}

@test "apply_propose skips if propose already exists" {
    # Create an existing propose override
    mkdir -p "$TEST_DIR/.claude"
    cat > "$TEST_DIR/.claude/routing-overrides.json" << 'EOF'
{"version":1,"overrides":[{"agent":"fd-game-design","action":"propose","reason":"test"}]}
EOF
    git add .claude/routing-overrides.json && git commit -q -m "add propose"

    run _interspect_apply_propose "fd-game-design" "test" '[]' "interspect"
    echo "output: $output"
    [ "$status" -eq 0 ]
    echo "$output" | grep -qi "already exists"
}

@test "apply_propose does not create canary record" {
    DB=$(_interspect_db_path)
    _interspect_apply_propose "fd-test-propose" "test reason" '[]' "interspect"

    local canary_count
    canary_count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM canary WHERE group_id = 'fd-test-propose';")
    [ "$canary_count" -eq 0 ]
}

# ─── Overlay Helpers ──────────────────────────────────────────────

# Helper: create a raw overlay file directly (bypasses write_overlay validation/git)
_create_test_overlay() {
    local agent="$1" overlay_id="$2" active="${3:-true}" body="${4:-Test overlay content}"
    local dir="${TEST_DIR}/.clavain/interspect/overlays/${agent}"
    mkdir -p "$dir"
    cat > "${dir}/${overlay_id}.md" << EOF
---
active: ${active}
created: 2026-01-01T00:00:00Z
created_by: test
evidence_ids: []
---
${body}
EOF
    cd "$TEST_DIR"
    git add ".clavain/interspect/overlays/${agent}/${overlay_id}.md"
    git commit -q -m "add test overlay ${overlay_id}"
}

@test "overlay_is_active returns 0 for active overlay" {
    _create_test_overlay "fd-quality" "tune-001" "true"
    local filepath="${TEST_DIR}/.clavain/interspect/overlays/fd-quality/tune-001.md"
    run _interspect_overlay_is_active "$filepath"
    [ "$status" -eq 0 ]
}

@test "overlay_is_active returns 1 for inactive overlay" {
    _create_test_overlay "fd-quality" "tune-002" "false"
    local filepath="${TEST_DIR}/.clavain/interspect/overlays/fd-quality/tune-002.md"
    run _interspect_overlay_is_active "$filepath"
    [ "$status" -eq 1 ]
}

@test "overlay_is_active returns 1 for missing file" {
    run _interspect_overlay_is_active "/nonexistent/path.md"
    [ "$status" -eq 1 ]
}

@test "overlay_is_active ignores active: true in body" {
    local dir="${TEST_DIR}/.clavain/interspect/overlays/fd-quality"
    mkdir -p "$dir"
    cat > "${dir}/tune-003.md" << 'EOF'
---
active: false
created: 2026-01-01T00:00:00Z
created_by: test
evidence_ids: []
---
This body contains active: true but it should be ignored.
EOF
    cd "$TEST_DIR"
    git add ".clavain/interspect/overlays/fd-quality/tune-003.md"
    git commit -q -m "add overlay with tricky body"

    run _interspect_overlay_is_active "${dir}/tune-003.md"
    [ "$status" -eq 1 ]
}

@test "overlay_body extracts content after frontmatter" {
    _create_test_overlay "fd-quality" "tune-004" "true" "Line one of body
Line two of body"
    local filepath="${TEST_DIR}/.clavain/interspect/overlays/fd-quality/tune-004.md"
    result=$(_interspect_overlay_body "$filepath")
    [[ "$result" == *"Line one of body"* ]]
    [[ "$result" == *"Line two of body"* ]]
}

@test "overlay_body returns empty for missing file" {
    result=$(_interspect_overlay_body "/nonexistent/path.md")
    [ -z "$result" ]
}

@test "overlay_body excludes frontmatter" {
    _create_test_overlay "fd-quality" "tune-005" "true" "Just body"
    local filepath="${TEST_DIR}/.clavain/interspect/overlays/fd-quality/tune-005.md"
    result=$(_interspect_overlay_body "$filepath")
    [[ "$result" != *"active:"* ]]
    [[ "$result" != *"created_by:"* ]]
    [[ "$result" == *"Just body"* ]]
}

@test "count_overlay_tokens returns 0 for empty content" {
    result=$(_interspect_count_overlay_tokens "")
    [ "$result" -eq 0 ]
}

@test "count_overlay_tokens estimates based on word count" {
    # "one two three four five" = 5 words * 1.3 = 6.5 → 6 (truncated)
    result=$(_interspect_count_overlay_tokens "one two three four five")
    [ "$result" -eq 6 ]
}

@test "count_overlay_tokens handles multiline content" {
    content="first line has four words
second line also four words
third"
    result=$(_interspect_count_overlay_tokens "$content")
    # 11 words * 1.3 = 14.3 → 14
    [ "$result" -eq 14 ]
}

@test "read_overlays returns empty for no overlays" {
    result=$(_interspect_read_overlays "fd-quality")
    [ -z "$result" ]
}

@test "read_overlays returns body of active overlay" {
    _create_test_overlay "fd-quality" "tune-006" "true" "Active overlay body"
    result=$(_interspect_read_overlays "fd-quality")
    [[ "$result" == *"Active overlay body"* ]]
}

@test "read_overlays skips inactive overlays" {
    _create_test_overlay "fd-quality" "tune-active" "true" "Should appear"
    _create_test_overlay "fd-quality" "tune-inactive" "false" "Should not appear"
    result=$(_interspect_read_overlays "fd-quality")
    [[ "$result" == *"Should appear"* ]]
    [[ "$result" != *"Should not appear"* ]]
}

@test "read_overlays concatenates multiple active overlays" {
    _create_test_overlay "fd-quality" "tune-aaa" "true" "First overlay"
    _create_test_overlay "fd-quality" "tune-bbb" "true" "Second overlay"
    result=$(_interspect_read_overlays "fd-quality")
    [[ "$result" == *"First overlay"* ]]
    [[ "$result" == *"Second overlay"* ]]
}

@test "read_overlays rejects invalid agent name" {
    run _interspect_read_overlays "malicious'; DROP TABLE--"
    [ "$status" -eq 1 ]
}

@test "validate_overlay_id accepts valid IDs" {
    run _interspect_validate_overlay_id "tune-001"
    [ "$status" -eq 0 ]
    run _interspect_validate_overlay_id "fix-false-positives"
    [ "$status" -eq 0 ]
    run _interspect_validate_overlay_id "a"
    [ "$status" -eq 0 ]
}

@test "validate_overlay_id rejects invalid IDs" {
    run _interspect_validate_overlay_id "UPPERCASE"
    [ "$status" -eq 1 ]
    run _interspect_validate_overlay_id "../escape"
    [ "$status" -eq 1 ]
    run _interspect_validate_overlay_id ""
    [ "$status" -eq 1 ]
}

# ─── Overlay Write + Disable (integration) ───────────────────────

@test "write_overlay creates file and commits" {
    run _interspect_write_overlay "fd-quality" "tune-int" "Test integration body" '[]' "test"
    [ "$status" -eq 0 ]
    [[ "$output" == *"SUCCESS"* ]]

    local filepath="${TEST_DIR}/.clavain/interspect/overlays/fd-quality/tune-int.md"
    [ -f "$filepath" ]
    run _interspect_overlay_is_active "$filepath"
    [ "$status" -eq 0 ]
}

@test "write_overlay rejects duplicate overlay ID" {
    _interspect_write_overlay "fd-quality" "tune-dup" "First" '[]' "test"

    run _interspect_write_overlay "fd-quality" "tune-dup" "Second" '[]' "test"
    [ "$status" -ne 0 ]
    [[ "$output" == *"already exists"* ]]
}

@test "write_overlay creates canary record" {
    DB=$(_interspect_db_path)
    _interspect_write_overlay "fd-quality" "tune-canary" "Canary test body" '[]' "test"

    canary_count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM canary WHERE group_id = 'fd-quality/tune-canary';")
    [ "$canary_count" -eq 1 ]

    canary_status=$(sqlite3 "$DB" "SELECT status FROM canary WHERE group_id = 'fd-quality/tune-canary';")
    [ "$canary_status" = "active" ]
}

@test "write_overlay enforces 500-token budget" {
    # Create a large overlay that uses most of the budget
    # 350 words * 1.3 = 455 tokens (fits under 500)
    local big_body
    big_body=$(printf 'word %.0s' {1..350})
    _interspect_write_overlay "fd-quality" "tune-big" "$big_body" '[]' "test"

    # Second overlay pushes over: 100 words * 1.3 = 130 tokens → 455+130=585 > 500
    local more_body
    more_body=$(printf 'extra %.0s' {1..100})
    run _interspect_write_overlay "fd-quality" "tune-over" "$more_body" '[]' "test"
    [ "$status" -ne 0 ]
    [[ "$output" == *"budget"* ]]
}

@test "disable_overlay sets active to false" {
    _create_test_overlay "fd-quality" "tune-dis" "true" "Will be disabled"
    local filepath="${TEST_DIR}/.clavain/interspect/overlays/fd-quality/tune-dis.md"

    # Verify active
    run _interspect_overlay_is_active "$filepath"
    [ "$status" -eq 0 ]

    # Disable
    run _interspect_disable_overlay "fd-quality" "tune-dis"
    [ "$status" -eq 0 ]
    [[ "$output" == *"SUCCESS"* ]]

    # Verify inactive
    run _interspect_overlay_is_active "$filepath"
    [ "$status" -eq 1 ]
}

@test "disable_overlay is idempotent" {
    _create_test_overlay "fd-quality" "tune-idem" "false" "Already inactive"

    run _interspect_disable_overlay "fd-quality" "tune-idem"
    [ "$status" -eq 0 ]
    [[ "$output" == *"already inactive"* ]]
}

@test "disable_overlay rejects missing overlay" {
    run _interspect_disable_overlay "fd-quality" "nonexistent"
    [ "$status" -eq 1 ]
    [[ "$output" == *"not found"* ]]
}

@test "disable_overlay preserves body content" {
    _create_test_overlay "fd-quality" "tune-body" "true" "Important instructions here"
    local filepath="${TEST_DIR}/.clavain/interspect/overlays/fd-quality/tune-body.md"

    _interspect_disable_overlay "fd-quality" "tune-body"

    body=$(_interspect_overlay_body "$filepath")
    [[ "$body" == *"Important instructions here"* ]]
}

@test "disable_overlay does not touch active: true in body" {
    local dir="${TEST_DIR}/.clavain/interspect/overlays/fd-quality"
    mkdir -p "$dir"
    cat > "${dir}/tune-tricky.md" << 'EOF'
---
active: true
created: 2026-01-01T00:00:00Z
created_by: test
evidence_ids: []
---
This body says active: true and should not be changed.
EOF
    cd "$TEST_DIR"
    git add ".clavain/interspect/overlays/fd-quality/tune-tricky.md"
    git commit -q -m "add tricky overlay"

    _interspect_disable_overlay "fd-quality" "tune-tricky"

    # Frontmatter should be false
    run _interspect_overlay_is_active "${dir}/tune-tricky.md"
    [ "$status" -eq 1 ]

    # Body should still contain the string
    body=$(_interspect_overlay_body "${dir}/tune-tricky.md")
    [[ "$body" == *"active: true"* ]]
}

@test "disable_overlay updates canary and modification status" {
    DB=$(_interspect_db_path)

    # Use write_overlay to get proper DB records
    _interspect_write_overlay "fd-quality" "tune-db" "DB tracking test" '[]' "test"

    # Verify canary is active
    canary_status=$(sqlite3 "$DB" "SELECT status FROM canary WHERE group_id = 'fd-quality/tune-db' LIMIT 1;")
    [ "$canary_status" = "active" ]

    # Disable
    _interspect_disable_overlay "fd-quality" "tune-db"

    # Canary should be reverted
    canary_status=$(sqlite3 "$DB" "SELECT status FROM canary WHERE group_id = 'fd-quality/tune-db' LIMIT 1;")
    [ "$canary_status" = "reverted" ]

    # Modification should be reverted
    mod_status=$(sqlite3 "$DB" "SELECT status FROM modifications WHERE group_id = 'fd-quality/tune-db' LIMIT 1;")
    [ "$mod_status" = "reverted" ]
}

@test "disable_overlay rejects invalid agent name" {
    run _interspect_disable_overlay "INVALID" "tune-001"
    [ "$status" -eq 1 ]
}

@test "disable_overlay rejects invalid overlay ID" {
    run _interspect_disable_overlay "fd-quality" "../ESCAPE"
    [ "$status" -eq 1 ]
}

# ─── Manual Override (F5) ────────────────────────────────────────

@test "apply_routing_override with created_by=human works" {
    run _interspect_apply_routing_override "fd-game-design" "Not relevant to this project" '[]' "human"
    [ "$status" -eq 0 ]
    [[ "$output" == *"SUCCESS"* ]]

    # Verify created_by is stored
    ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    FILEPATH="${ROOT}/.claude/routing-overrides.json"
    created_by=$(jq -r '.overrides[0].created_by' "$FILEPATH")
    [ "$created_by" = "human" ]
}

@test "apply_routing_override with scope persists scope in JSON" {
    local scope='{"file_patterns":["interverse/**"]}'
    run _interspect_apply_routing_override "fd-game-design" "Only for interverse" '[]' "human" "$scope"
    [ "$status" -eq 0 ]

    ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    FILEPATH="${ROOT}/.claude/routing-overrides.json"
    file_pattern=$(jq -r '.overrides[0].scope.file_patterns[0]' "$FILEPATH")
    [ "$file_pattern" = "interverse/**" ]
}

@test "apply_routing_override with domain scope persists" {
    local scope='{"domains":["claude-code-plugin"]}'
    run _interspect_apply_routing_override "fd-performance" "Not relevant for plugins" '[]' "human" "$scope"
    [ "$status" -eq 0 ]

    ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    FILEPATH="${ROOT}/.claude/routing-overrides.json"
    domain=$(jq -r '.overrides[0].scope.domains[0]' "$FILEPATH")
    [ "$domain" = "claude-code-plugin" ]
}

@test "apply_routing_override without scope omits scope field" {
    run _interspect_apply_routing_override "fd-game-design" "test" '[]' "interspect"
    [ "$status" -eq 0 ]

    ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    FILEPATH="${ROOT}/.claude/routing-overrides.json"
    has_scope=$(jq '.overrides[0] | has("scope")' "$FILEPATH")
    [ "$has_scope" = "false" ]
}

@test "apply_routing_override rejects invalid scope JSON" {
    run _interspect_apply_routing_override "fd-game-design" "test" '[]' "human" "not-json"
    [ "$status" -eq 1 ]
    [[ "$output" == *"scope must be a JSON object"* ]]
}

@test "apply_routing_override rejects scope that is not an object" {
    run _interspect_apply_routing_override "fd-game-design" "test" '[]' "human" '["array"]'
    [ "$status" -eq 1 ]
    [[ "$output" == *"scope must be a JSON object"* ]]
}

@test "manual override creates canary even with no evidence" {
    DB=$(_interspect_db_path)
    _interspect_apply_routing_override "fd-game-design" "Manual exclusion" '[]' "human"

    canary_count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM canary WHERE group_id = 'fd-game-design';")
    [ "$canary_count" -eq 1 ]

    canary_status=$(sqlite3 "$DB" "SELECT status FROM canary WHERE group_id = 'fd-game-design';")
    [ "$canary_status" = "active" ]
}

@test "manual override confidence is 1.0 when no evidence exists" {
    _interspect_apply_routing_override "fd-game-design" "Manual" '[]' "human"

    ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    FILEPATH="${ROOT}/.claude/routing-overrides.json"
    confidence=$(jq '.overrides[0].confidence' "$FILEPATH")
    # jq preserves "1.0" from printf "%.2f"
    [[ "$confidence" == "1" || "$confidence" == "1.0" ]]
}

# ─── Autonomy Mode (F6) ─────────────────────────────────────────

@test "is_autonomous returns 1 by default" {
    run _interspect_is_autonomous
    [ "$status" -eq 1 ]
}

@test "set_autonomy enables autonomous mode" {
    _interspect_set_autonomy "true"
    run _interspect_is_autonomous
    [ "$status" -eq 0 ]
}

@test "set_autonomy disables autonomous mode" {
    _interspect_set_autonomy "true"
    run _interspect_is_autonomous
    [ "$status" -eq 0 ]

    _interspect_set_autonomy "false"
    run _interspect_is_autonomous
    [ "$status" -eq 1 ]
}

@test "set_autonomy persists to confidence.json" {
    _interspect_set_autonomy "true"
    local root
    root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    local val
    val=$(jq -r '.autonomy' "${root}/.clavain/interspect/confidence.json")
    [ "$val" = "true" ]
}

@test "set_autonomy rejects invalid values" {
    run _interspect_set_autonomy "maybe"
    [ "$status" -eq 1 ]
    [[ "$output" == *"must be 'true' or 'false'"* ]]
}

@test "load_confidence reads autonomy flag" {
    # Write autonomy=true directly to config
    local root
    root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    local conf="${root}/.clavain/interspect/confidence.json"
    jq '.autonomy = true' "$conf" > "${conf}.tmp" && mv "${conf}.tmp" "$conf"

    # Reset and reload
    unset _INTERSPECT_CONFIDENCE_LOADED
    _interspect_load_confidence
    [ "$_INTERSPECT_AUTONOMY" = "true" ]
}

@test "circuit_breaker_tripped returns 1 when no reverts" {
    DB=$(_interspect_db_path)
    run _interspect_circuit_breaker_tripped "fd-game-design"
    [ "$status" -eq 1 ]
}

@test "circuit_breaker_tripped returns 0 after 3 reverts" {
    DB=$(_interspect_db_path)
    local ts
    ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    # Insert 3 revert records
    for i in 1 2 3; do
        sqlite3 "$DB" "INSERT INTO modifications (group_id, ts, tier, mod_type, target_file, commit_sha, confidence, evidence_summary, status)
            VALUES ('fd-game-design', '${ts}', 'persistent', 'routing', '.claude/routing-overrides.json', 'sha${i}', 1.0, 'test', 'reverted');"
    done

    run _interspect_circuit_breaker_tripped "fd-game-design"
    [ "$status" -eq 0 ]
}

@test "circuit_breaker ignores old reverts" {
    DB=$(_interspect_db_path)

    # Insert 3 revert records from 60 days ago (outside 30-day window)
    for i in 1 2 3; do
        sqlite3 "$DB" "INSERT INTO modifications (group_id, ts, tier, mod_type, target_file, commit_sha, confidence, evidence_summary, status)
            VALUES ('fd-game-design', datetime('now', '-60 days'), 'persistent', 'routing', '.claude/routing-overrides.json', 'old${i}', 1.0, 'test', 'reverted');"
    done

    run _interspect_circuit_breaker_tripped "fd-game-design"
    [ "$status" -eq 1 ]
}

@test "should_auto_apply returns 1 in propose mode" {
    run _interspect_should_auto_apply "fd-game-design" "routing"
    [ "$status" -eq 1 ]
}

@test "should_auto_apply returns 1 for prompt_tuning even in autonomous mode" {
    _interspect_set_autonomy "true"
    run _interspect_should_auto_apply "fd-game-design" "prompt_tuning"
    [ "$status" -eq 1 ]
}

@test "should_auto_apply returns 1 when circuit breaker tripped" {
    DB=$(_interspect_db_path)
    _interspect_set_autonomy "true"

    # Trip the circuit breaker
    local ts
    ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    for i in 1 2 3; do
        sqlite3 "$DB" "INSERT INTO modifications (group_id, ts, tier, mod_type, target_file, commit_sha, confidence, evidence_summary, status)
            VALUES ('fd-game-design', '${ts}', 'persistent', 'routing', '.claude/routing-overrides.json', 'cb${i}', 1.0, 'test', 'reverted');"
    done

    run _interspect_should_auto_apply "fd-game-design" "routing"
    [ "$status" -eq 1 ]
    [[ "$output" == *"Circuit breaker"* ]]
}

@test "should_auto_apply returns 1 when insufficient baseline" {
    _interspect_set_autonomy "true"
    # No evidence inserted → 0 sessions < 15 minimum
    run _interspect_should_auto_apply "fd-game-design" "routing"
    [ "$status" -eq 1 ]
    [[ "$output" == *"Insufficient baseline"* ]]
}

@test "should_auto_apply returns 0 when all checks pass" {
    DB=$(_interspect_db_path)
    _interspect_set_autonomy "true"

    # Insert enough evidence (15+ distinct sessions)
    for i in $(seq 1 16); do
        sqlite3 "$DB" "INSERT INTO sessions (session_id, start_ts, project) VALUES ('session-${i}', datetime('now', '-${i} days'), 'test-project');"
        sqlite3 "$DB" "INSERT INTO evidence (session_id, seq, source, event, override_reason, ts, context, project)
            VALUES ('session-${i}', 1, 'fd-game-design', 'override', 'agent_wrong', datetime('now', '-${i} days'), '{}', 'test-project');"
    done

    run _interspect_should_auto_apply "fd-game-design" "routing"
    [ "$status" -eq 0 ]
}

@test "load_confidence bounds-checks circuit breaker values" {
    local root
    root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    local conf="${root}/.clavain/interspect/confidence.json"
    # -5 is non-numeric (has sign) → falls through to default 3
    # 9999 is numeric but > 365 → clamped to 365
    jq '.circuit_breaker_max = -5 | .circuit_breaker_days = 9999' "$conf" > "${conf}.tmp" && mv "${conf}.tmp" "$conf"

    unset _INTERSPECT_CONFIDENCE_LOADED
    _interspect_load_confidence
    [ "$_INTERSPECT_CIRCUIT_BREAKER_MAX" -eq 3 ]    # -5 is non-numeric → default 3
    [ "$_INTERSPECT_CIRCUIT_BREAKER_DAYS" -eq 365 ]  # 9999 clamped to max 365
}
