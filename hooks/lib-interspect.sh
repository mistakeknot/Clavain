#!/usr/bin/env bash
# Shared library for Interspect evidence collection and storage.
#
# Usage:
#   source hooks/lib-interspect.sh
#   _interspect_ensure_db
#   _interspect_insert_evidence "$session_id" "fd-safety" "override" "agent_wrong" "$context_json" "interspect-correction"
#
# Provides:
#   _interspect_db_path       — path to SQLite DB
#   _interspect_ensure_db     — create DB + tables if missing
#   _interspect_project_name  — basename of git root
#   _interspect_next_seq      — next seq number for session
#   _interspect_insert_evidence — sanitize + insert evidence row
#   _interspect_sanitize      — strip ANSI, control chars, truncate, redact secrets, reject injection
#   _interspect_redact_secrets — detect and redact credential patterns
#   _interspect_validate_hook_id — allowlist hook IDs
#   _interspect_classify_pattern — counting-rule confidence gate
#   _interspect_get_classified_patterns — query + classify all patterns
#   _interspect_get_routing_eligible — agents eligible for routing override proposals (ready + >=80% wrong)
#   _interspect_get_overlay_eligible — agents eligible for overlay proposals (ready + 40-79% wrong)
#   _interspect_is_cross_cutting — check if agent is structural/cross-cutting
#   _interspect_apply_propose — write "propose" entry to routing-overrides.json
#   _interspect_flock_git     — serialized git operations via flock

# Guard against re-parsing (same pattern as lib-signals.sh)
[[ -n "${_LIB_INTERSPECT_LOADED:-}" ]] && return 0
_LIB_INTERSPECT_LOADED=1

# ─── Path helpers ────────────────────────────────────────────────────────────

# Returns the path to the Interspect SQLite database.
# Uses git root if available, otherwise pwd.
_interspect_db_path() {
    local root
    root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    echo "${root}/.clavain/interspect/interspect.db"
}

# Returns the project name (basename of repo root).
_interspect_project_name() {
    basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
}

# ─── DB initialization ──────────────────────────────────────────────────────

# Ensure the database and all tables exist. Fast-path: skip if file exists.
# Sets global _INTERSPECT_DB to the resolved path for callers.
_interspect_ensure_db() {
    _INTERSPECT_DB=$(_interspect_db_path)

    # Fast path — DB already exists, but run migrations for new tables
    if [[ -f "$_INTERSPECT_DB" ]]; then
        sqlite3 "$_INTERSPECT_DB" <<'MIGRATE'
CREATE TABLE IF NOT EXISTS blacklist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_key TEXT NOT NULL UNIQUE,
    blacklisted_at TEXT NOT NULL,
    reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_blacklist_key ON blacklist(pattern_key);
CREATE TABLE IF NOT EXISTS canary_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canary_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    override_rate REAL,
    fp_rate REAL,
    finding_density REAL,
    UNIQUE(canary_id, session_id)
);
CREATE INDEX IF NOT EXISTS idx_canary_samples_canary ON canary_samples(canary_id);
MIGRATE
        # Add run_id column to sessions (E4.3: session-to-run correlation)
        sqlite3 "$_INTERSPECT_DB" "ALTER TABLE sessions ADD COLUMN run_id TEXT;" 2>/dev/null || true
        # Ensure overlays directory exists (Type 1 modifications)
        mkdir -p "$(dirname "$_INTERSPECT_DB")/overlays" 2>/dev/null || true
        # Ensure durable cursor for kernel event consumer (E4.2/E4.5)
        # Only register if cursor doesn't exist yet (register resets position to 0)
        if command -v ic &>/dev/null; then
            if ! ic events cursor list 2>/dev/null | grep -q 'interspect-consumer'; then
                ic events cursor register interspect-consumer --durable 2>/dev/null || true
            fi
        fi
        return 0
    fi

    # Ensure directory exists (including overlays subdirectory for Type 1 modifications)
    mkdir -p "$(dirname "$_INTERSPECT_DB")" 2>/dev/null || return 1
    mkdir -p "$(dirname "$_INTERSPECT_DB")/overlays" 2>/dev/null || true

    # Create tables + indexes + WAL mode
    sqlite3 "$_INTERSPECT_DB" <<'SQL' >/dev/null
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    source TEXT NOT NULL,
    source_version TEXT,
    event TEXT NOT NULL,
    override_reason TEXT,
    context TEXT NOT NULL,
    project TEXT NOT NULL,
    project_lang TEXT,
    project_type TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    start_ts TEXT NOT NULL,
    end_ts TEXT,
    project TEXT,
    run_id TEXT
);

CREATE TABLE IF NOT EXISTS canary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    group_id TEXT,
    applied_at TEXT NOT NULL,
    window_uses INTEGER NOT NULL DEFAULT 20,
    uses_so_far INTEGER NOT NULL DEFAULT 0,
    window_expires_at TEXT,
    baseline_override_rate REAL,
    baseline_fp_rate REAL,
    baseline_finding_density REAL,
    baseline_window TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    verdict_reason TEXT
);

CREATE TABLE IF NOT EXISTS modifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'persistent',
    mod_type TEXT NOT NULL,
    target_file TEXT NOT NULL,
    commit_sha TEXT,
    confidence REAL NOT NULL,
    evidence_summary TEXT,
    status TEXT NOT NULL DEFAULT 'applied'
);

CREATE INDEX IF NOT EXISTS idx_evidence_session ON evidence(session_id);
CREATE INDEX IF NOT EXISTS idx_evidence_source ON evidence(source);
CREATE INDEX IF NOT EXISTS idx_evidence_project ON evidence(project);
CREATE INDEX IF NOT EXISTS idx_evidence_event ON evidence(event);
CREATE INDEX IF NOT EXISTS idx_evidence_ts ON evidence(ts);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project);
CREATE INDEX IF NOT EXISTS idx_canary_status ON canary(status);
CREATE INDEX IF NOT EXISTS idx_canary_file ON canary(file);
CREATE INDEX IF NOT EXISTS idx_modifications_group ON modifications(group_id);
CREATE INDEX IF NOT EXISTS idx_modifications_status ON modifications(status);
CREATE INDEX IF NOT EXISTS idx_modifications_target ON modifications(target_file);

CREATE TABLE IF NOT EXISTS blacklist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_key TEXT NOT NULL UNIQUE,
    blacklisted_at TEXT NOT NULL,
    reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_blacklist_key ON blacklist(pattern_key);

CREATE TABLE IF NOT EXISTS canary_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canary_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    override_rate REAL,
    fp_rate REAL,
    finding_density REAL,
    UNIQUE(canary_id, session_id)
);
CREATE INDEX IF NOT EXISTS idx_canary_samples_canary ON canary_samples(canary_id);
SQL
    # Ensure durable cursor for kernel event consumer (E4.2/E4.5)
    # Only register if cursor doesn't exist yet (register resets position to 0)
    if command -v ic &>/dev/null; then
        if ! ic events cursor list 2>/dev/null | grep -q 'interspect-consumer'; then
            ic events cursor register interspect-consumer --durable 2>/dev/null || true
        fi
    fi
}

# ─── Protected paths enforcement ─────────────────────────────────────────────

# Path to the protected-paths manifest. Relative to repo root.
_INTERSPECT_MANIFEST=".clavain/interspect/protected-paths.json"

# Load the protected-paths manifest and cache the arrays.
# Sets: _INTERSPECT_PROTECTED_PATHS, _INTERSPECT_ALLOW_LIST, _INTERSPECT_ALWAYS_PROPOSE
_interspect_load_manifest() {
    # Cache: only parse once per process
    [[ -n "${_INTERSPECT_MANIFEST_LOADED:-}" ]] && return 0
    _INTERSPECT_MANIFEST_LOADED=1

    local root
    root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    local manifest="${root}/${_INTERSPECT_MANIFEST}"

    _INTERSPECT_PROTECTED_PATHS=()
    _INTERSPECT_ALLOW_LIST=()
    _INTERSPECT_ALWAYS_PROPOSE=()

    if [[ ! -f "$manifest" ]]; then
        echo "WARN: interspect manifest not found at ${manifest}" >&2
        return 1
    fi

    # Parse JSON arrays with jq — one pattern per line
    local line
    while IFS= read -r line; do
        [[ -n "$line" ]] && _INTERSPECT_PROTECTED_PATHS+=("$line")
    done < <(jq -r '.protected_paths[]? // empty' "$manifest" 2>/dev/null)

    while IFS= read -r line; do
        [[ -n "$line" ]] && _INTERSPECT_ALLOW_LIST+=("$line")
    done < <(jq -r '.modification_allow_list[]? // empty' "$manifest" 2>/dev/null)

    while IFS= read -r line; do
        [[ -n "$line" ]] && _INTERSPECT_ALWAYS_PROPOSE+=("$line")
    done < <(jq -r '.always_propose[]? // empty' "$manifest" 2>/dev/null)

    return 0
}

# Check if a file path matches any pattern in a glob array.
# Uses bash extended globbing for ** support.
# Args: $1 = file path (relative to repo root), $2... = glob patterns
# Returns: 0 if matches, 1 if not
_interspect_matches_any() {
    local filepath="$1"
    shift

    # Enable extended globbing for ** patterns
    local prev_extglob
    prev_extglob=$(shopt -p extglob 2>/dev/null || true)
    shopt -s extglob 2>/dev/null || true

    local pattern
    for pattern in "$@"; do
        # Convert glob pattern to a regex-like check using bash [[ == ]]
        # The [[ $str == $pattern ]] does glob matching natively
        # shellcheck disable=SC2053
        if [[ "$filepath" == $pattern ]]; then
            eval "$prev_extglob" 2>/dev/null || true
            return 0
        fi
    done

    eval "$prev_extglob" 2>/dev/null || true
    return 1
}

# Check if a path is protected (interspect CANNOT modify it).
# Args: $1 = file path relative to repo root
# Returns: 0 if protected, 1 if not
_interspect_is_protected() {
    _interspect_load_manifest || return 1
    _interspect_matches_any "$1" "${_INTERSPECT_PROTECTED_PATHS[@]}"
}

# Check if a path is in the modification allow-list (interspect CAN modify it).
# Args: $1 = file path relative to repo root
# Returns: 0 if allowed, 1 if not
_interspect_is_allowed() {
    _interspect_load_manifest || return 1
    _interspect_matches_any "$1" "${_INTERSPECT_ALLOW_LIST[@]}"
}

# Check if a path requires propose mode (even in autonomous mode).
# Args: $1 = file path relative to repo root
# Returns: 0 if always-propose, 1 if not
_interspect_is_always_propose() {
    _interspect_load_manifest || return 1
    _interspect_matches_any "$1" "${_INTERSPECT_ALWAYS_PROPOSE[@]}"
}

# Validate a target path for interspect modification.
# Must be allowed AND not protected. Prints reason on rejection.
# Args: $1 = file path relative to repo root
# Returns: 0 if valid target, 1 if rejected
_interspect_validate_target() {
    local filepath="$1"

    _interspect_load_manifest || {
        echo "REJECT: manifest not found" >&2
        return 1
    }

    # Check protected first (hard block)
    if _interspect_matches_any "$filepath" "${_INTERSPECT_PROTECTED_PATHS[@]}"; then
        echo "REJECT: ${filepath} is a protected path" >&2
        return 1
    fi

    # Check allow-list
    if ! _interspect_matches_any "$filepath" "${_INTERSPECT_ALLOW_LIST[@]}"; then
        echo "REJECT: ${filepath} is not in the modification allow-list" >&2
        return 1
    fi

    return 0
}

# ─── Evidence helpers ────────────────────────────────────────────────────────

# Next sequence number for a session.
# Args: $1 = session_id
_interspect_next_seq() {
    local session_id="$1"
    local db="${_INTERSPECT_DB:-$(_interspect_db_path)}"
    local escaped="${session_id//\'/\'\'}"
    sqlite3 "$db" "SELECT COALESCE(MAX(seq), 0) + 1 FROM evidence WHERE session_id = '${escaped}';"
}

# ─── Confidence Gate (Counting Rules) ───────────────────────────────────────

_INTERSPECT_CONFIDENCE_JSON=".clavain/interspect/confidence.json"

# Load confidence thresholds from config. Defaults if file missing.
_interspect_load_confidence() {
    [[ -n "${_INTERSPECT_CONFIDENCE_LOADED:-}" ]] && return 0
    _INTERSPECT_CONFIDENCE_LOADED=1

    local root
    root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    local conf="${root}/${_INTERSPECT_CONFIDENCE_JSON}"

    # Defaults from design §3.3
    _INTERSPECT_MIN_SESSIONS=3
    _INTERSPECT_MIN_DIVERSITY=2   # projects OR languages
    _INTERSPECT_MIN_EVENTS=5
    _INTERSPECT_MIN_AGENT_WRONG_PCT=80

    # Canary monitoring defaults
    _INTERSPECT_CANARY_WINDOW_USES=20
    _INTERSPECT_CANARY_WINDOW_DAYS=14
    _INTERSPECT_CANARY_MIN_BASELINE=15
    _INTERSPECT_CANARY_ALERT_PCT=20
    _INTERSPECT_CANARY_NOISE_FLOOR="0.1"

    # Autonomy mode (F6): default off — propose mode
    _INTERSPECT_AUTONOMY=false
    # Circuit breaker: max reverts before disabling autonomy for a target
    _INTERSPECT_CIRCUIT_BREAKER_MAX=3
    _INTERSPECT_CIRCUIT_BREAKER_DAYS=30

    if [[ -f "$conf" ]]; then
        _INTERSPECT_MIN_SESSIONS=$(jq -r '.min_sessions // 3' "$conf")
        _INTERSPECT_MIN_DIVERSITY=$(jq -r '.min_diversity // 2' "$conf")
        _INTERSPECT_MIN_EVENTS=$(jq -r '.min_events // 5' "$conf")
        _INTERSPECT_MIN_AGENT_WRONG_PCT=$(jq -r '.min_agent_wrong_pct // 80' "$conf")

        # Canary monitoring thresholds (§canary PRD F5)
        _INTERSPECT_CANARY_WINDOW_USES=$(jq -r '.canary_window_uses // 20' "$conf")
        _INTERSPECT_CANARY_WINDOW_DAYS=$(jq -r '.canary_window_days // 14' "$conf")
        _INTERSPECT_CANARY_MIN_BASELINE=$(jq -r '.canary_min_baseline // 15' "$conf")
        _INTERSPECT_CANARY_ALERT_PCT=$(jq -r '.canary_alert_pct // 20' "$conf")
        _INTERSPECT_CANARY_NOISE_FLOOR=$(jq -r '.canary_noise_floor // 0.1' "$conf")

        # Autonomy mode (F6)
        local autonomy_val
        autonomy_val=$(jq -r '.autonomy // false' "$conf")
        [[ "$autonomy_val" == "true" ]] && _INTERSPECT_AUTONOMY=true || _INTERSPECT_AUTONOMY=false

        # Circuit breaker thresholds (F6)
        _INTERSPECT_CIRCUIT_BREAKER_MAX=$(jq -r '.circuit_breaker_max // 3' "$conf")
        _INTERSPECT_CIRCUIT_BREAKER_DAYS=$(jq -r '.circuit_breaker_days // 30' "$conf")
    fi

    # Bounds-check canary config (review P0-3: prevent unbounded SQL LIMIT values)
    _interspect_clamp_int() {
        local val="$1" lo="$2" hi="$3" default="$4"
        # Non-numeric → default
        [[ "$val" =~ ^[0-9]+$ ]] || { printf '%s' "$default"; return; }
        (( val < lo )) && val=$lo
        (( val > hi )) && val=$hi
        printf '%s' "$val"
    }
    _INTERSPECT_CANARY_WINDOW_USES=$(_interspect_clamp_int "${_INTERSPECT_CANARY_WINDOW_USES:-20}" 1 1000 20)
    _INTERSPECT_CANARY_WINDOW_DAYS=$(_interspect_clamp_int "${_INTERSPECT_CANARY_WINDOW_DAYS:-14}" 1 365 14)
    _INTERSPECT_CANARY_MIN_BASELINE=$(_interspect_clamp_int "${_INTERSPECT_CANARY_MIN_BASELINE:-15}" 1 1000 15)
    _INTERSPECT_CANARY_ALERT_PCT=$(_interspect_clamp_int "${_INTERSPECT_CANARY_ALERT_PCT:-20}" 1 100 20)
    # Noise floor is a float — validate with awk
    if ! awk "BEGIN{v=${_INTERSPECT_CANARY_NOISE_FLOOR:-0.1}+0; exit (v>0 && v<10)?0:1}" 2>/dev/null; then
        _INTERSPECT_CANARY_NOISE_FLOOR="0.1"
    fi

    # Circuit breaker bounds (F6)
    _INTERSPECT_CIRCUIT_BREAKER_MAX=$(_interspect_clamp_int "${_INTERSPECT_CIRCUIT_BREAKER_MAX:-3}" 1 100 3)
    _INTERSPECT_CIRCUIT_BREAKER_DAYS=$(_interspect_clamp_int "${_INTERSPECT_CIRCUIT_BREAKER_DAYS:-30}" 1 365 30)
}

# Classify a pattern. Args: $1=event_count $2=session_count $3=project_count
# Output: "ready", "growing", or "emerging"
_interspect_classify_pattern() {
    _interspect_load_confidence
    local events="$1" sessions="$2" projects="$3"
    local met=0

    (( sessions >= _INTERSPECT_MIN_SESSIONS )) && (( met++ ))
    (( projects >= _INTERSPECT_MIN_DIVERSITY )) && (( met++ ))
    (( events >= _INTERSPECT_MIN_EVENTS )) && (( met++ ))

    if (( met == 3 )); then echo "ready"
    elif (( met >= 1 )); then echo "growing"
    else echo "emerging"
    fi
}

# Query all patterns and classify. Output: pipe-delimited rows.
# Format: source|event|override_reason|event_count|session_count|project_count|classification
_interspect_get_classified_patterns() {
    local db="${_INTERSPECT_DB:-$(_interspect_db_path)}"
    [[ -f "$db" ]] || return 1
    _interspect_load_confidence

    # Query with normalization: merge interflux:fd-X and interflux:review:fd-X
    # into fd-X for routing-eligible patterns. Non-fd-* sources pass through unchanged.
    sqlite3 -separator '|' "$db" "
        SELECT
            CASE
                WHEN source LIKE 'interflux:review:fd-%' THEN SUBSTR(source, 19)
                WHEN source LIKE 'interflux:fd-%' THEN SUBSTR(source, 11)
                ELSE source
            END as norm_source,
            event, COALESCE(override_reason,''),
            COUNT(*) as ec, COUNT(DISTINCT session_id) as sc,
            COUNT(DISTINCT project) as pc
        FROM evidence
        GROUP BY norm_source, event, override_reason
        HAVING COUNT(*) >= 2 ORDER BY ec DESC;
    " | while IFS='|' read -r src evt reason ec sc pc; do
        local cls
        cls=$(_interspect_classify_pattern "$ec" "$sc" "$pc")
        echo "${src}|${evt}|${reason}|${ec}|${sc}|${pc}|${cls}"
    done
}

# ─── Agent Name Normalization ────────────────────────────────────────────────

# Normalize agent source names to canonical fd-* format for routing.
# Strips interflux: and interflux:review: prefixes.
# Non-fd-* names pass through unchanged.
# Args: $1=source_name
# Output: normalized name on stdout
_interspect_normalize_agent_name() {
    local name="$1"
    # Strip interflux:review: prefix first (more specific)
    name="${name#interflux:review:}"
    # Strip interflux: prefix
    name="${name#interflux:}"
    printf '%s' "$name"
}

# ─── SQL Safety Helpers ──────────────────────────────────────────────────────

# Escape a string for safe use in sqlite3 single-quoted values.
# Handles single quotes, backslashes, and strips control characters.
# All SQL queries in routing override code MUST use this helper.
_interspect_sql_escape() {
    local val="$1"
    val="${val//\\/\\\\}"           # Escape backslashes first
    val="${val//\'/\'\'}"           # Then single quotes
    printf '%s' "$val" | tr -d '\000-\037\177'  # Strip control chars
}

# Validate agent name format. Rejects anything that isn't fd-<lowercase-name>.
# Args: $1=agent_name
# Returns: 0 if valid, 1 if not
_interspect_validate_agent_name() {
    local agent="$1"
    if [[ ! "$agent" =~ ^fd-[a-z][a-z0-9-]*$ ]]; then
        echo "ERROR: Invalid agent name '${agent}'. Must match fd-<name> (lowercase, hyphens only)." >&2
        return 1
    fi
    return 0
}

# ─── Routing Override Helpers ────────────────────────────────────────────────

# Check if a pattern is routing-eligible (for exclusion proposals).
# Args: $1=agent_name
# Returns: 0 if routing-eligible, 1 if not
# Output: "eligible" or "not_eligible:<reason>"
_interspect_is_routing_eligible() {
    _interspect_load_confidence
    local agent="$1"
    local db="${_INTERSPECT_DB:-$(_interspect_db_path)}"

    # Normalize agent name (accept interflux:fd-* format, convert to fd-*)
    agent=$(_interspect_normalize_agent_name "$agent")

    # Validate normalized agent name format
    if ! _interspect_validate_agent_name "$agent"; then
        echo "not_eligible:invalid_agent_name"
        return 1
    fi

    local escaped
    escaped=$(_interspect_sql_escape "$agent")

    # Validate config loaded
    if [[ -z "${_INTERSPECT_MIN_AGENT_WRONG_PCT:-}" ]]; then
        echo "not_eligible:config_load_failed"
        return 1
    fi

    # Check blacklist
    local blacklisted
    blacklisted=$(sqlite3 "$db" "SELECT COUNT(*) FROM blacklist WHERE pattern_key = '${escaped}';")
    if (( blacklisted > 0 )); then
        echo "not_eligible:blacklisted"
        return 1
    fi

    # Get agent_wrong percentage — query all name variants (fd-X, interflux:fd-X, interflux:review:fd-X)
    local total wrong pct
    total=$(sqlite3 "$db" "SELECT COUNT(*) FROM evidence WHERE (source = '${escaped}' OR source = 'interflux:${escaped}' OR source = 'interflux:review:${escaped}') AND event = 'override';")
    wrong=$(sqlite3 "$db" "SELECT COUNT(*) FROM evidence WHERE (source = '${escaped}' OR source = 'interflux:${escaped}' OR source = 'interflux:review:${escaped}') AND event = 'override' AND override_reason = 'agent_wrong';")

    if (( total == 0 )); then
        echo "not_eligible:no_override_events"
        return 1
    fi

    pct=$(( wrong * 100 / total ))
    if (( pct < _INTERSPECT_MIN_AGENT_WRONG_PCT )); then
        echo "not_eligible:agent_wrong_pct=${pct}%<${_INTERSPECT_MIN_AGENT_WRONG_PCT}%"
        return 1
    fi

    echo "eligible"
    return 0
}

# Get agents eligible for routing override proposals.
# Filters classified patterns for: ready + routing-eligible + not already overridden.
# Output: pipe-delimited rows: agent|event_count|session_count|project_count|agent_wrong_pct
# Note: _interspect_is_routing_eligible handles multi-variant source names
#       (fd-X, interflux:fd-X, interflux:review:fd-X) so pct is always correct.
_interspect_get_routing_eligible() {
    local db="${_INTERSPECT_DB:-$(_interspect_db_path)}"
    [[ -f "$db" ]] || return 0

    _interspect_load_confidence

    local -A seen_agents
    _interspect_get_classified_patterns | while IFS='|' read -r src evt reason ec sc pc cls; do
        # Only "ready" patterns with override/agent_wrong events
        [[ "$cls" == "ready" ]] || continue
        [[ "$evt" == "override" ]] || continue
        [[ "$reason" == "agent_wrong" ]] || continue

        # Dedup: only emit each agent once (first ready+agent_wrong row wins)
        [[ -z "${seen_agents[$src]+x}" ]] || continue
        seen_agents[$src]=1

        # Must be a valid fd-* agent
        _interspect_validate_agent_name "$src" 2>/dev/null || continue

        # Check routing eligibility (blacklist + >=80% wrong via multi-variant query)
        local eligible_result
        eligible_result=$(_interspect_is_routing_eligible "$src")
        [[ "$eligible_result" == "eligible" ]] || continue

        # Skip if already overridden (exclude or propose)
        if _interspect_override_exists "$src"; then
            continue
        fi

        # Get pct from multi-variant query (same as _interspect_is_routing_eligible uses)
        local escaped
        escaped=$(_interspect_sql_escape "$src")
        local total wrong pct
        total=$(sqlite3 "$db" "SELECT COUNT(*) FROM evidence WHERE (source = '${escaped}' OR source = 'interflux:${escaped}' OR source = 'interflux:review:${escaped}') AND event = 'override';")
        wrong=$(sqlite3 "$db" "SELECT COUNT(*) FROM evidence WHERE (source = '${escaped}' OR source = 'interflux:${escaped}' OR source = 'interflux:review:${escaped}') AND event = 'override' AND override_reason = 'agent_wrong';")
        pct=$(( total > 0 ? wrong * 100 / total : 0 ))

        echo "${src}|${ec}|${sc}|${pc}|${pct}"
    done
}

# Get agents eligible for prompt tuning overlay proposals.
# Filters for: has at least one "ready" row + 40-<routing_threshold>% agent_wrong + not overlaid.
# Accumulates ALL override rows (not just "ready") for correct pct denominator.
# Output: pipe-delimited rows: agent|event_count|session_count|project_count|agent_wrong_pct
_interspect_get_overlay_eligible() {
    local db="${_INTERSPECT_DB:-$(_interspect_db_path)}"
    [[ -f "$db" ]] || return 0

    _interspect_load_confidence

    # Accumulate ALL override events per agent (not just "ready"),
    # but track which agents have at least one "ready" row.
    local -A agent_total agent_wrong agent_sessions agent_projects agent_has_ready
    while IFS='|' read -r src evt reason ec sc pc cls; do
        [[ "$evt" == "override" ]] || continue
        _interspect_validate_agent_name "$src" 2>/dev/null || continue

        # Accumulate totals using +=
        agent_total[$src]=$(( ${agent_total[$src]:-0} + ec ))
        if [[ "$reason" == "agent_wrong" ]]; then
            agent_wrong[$src]=$(( ${agent_wrong[$src]:-0} + ec ))
        fi
        # Track max sessions/projects across rows
        if (( sc > ${agent_sessions[$src]:-0} )); then
            agent_sessions[$src]=$sc
        fi
        if (( pc > ${agent_projects[$src]:-0} )); then
            agent_projects[$src]=$pc
        fi
        # Track if any row for this agent is "ready"
        if [[ "$cls" == "ready" ]]; then
            agent_has_ready[$src]=1
        fi
    done < <(_interspect_get_classified_patterns)

    local src
    for src in "${!agent_total[@]}"; do
        # Must have at least one "ready"-classified row
        [[ "${agent_has_ready[$src]:-}" == "1" ]] || continue

        local total=${agent_total[$src]}
        local wrong=${agent_wrong[$src]:-0}
        (( total > 0 )) || continue

        local pct=$(( wrong * 100 / total ))

        # Overlay band: 40% to below routing threshold (config-driven)
        (( pct >= 40 && pct < _INTERSPECT_MIN_AGENT_WRONG_PCT )) || continue

        # Skip if already has routing override
        if _interspect_override_exists "$src"; then
            continue
        fi

        echo "${src}|${agent_total[$src]}|${agent_sessions[$src]}|${agent_projects[$src]}|${pct}"
    done
}

# Check if an agent is cross-cutting (structural coverage agents).
# Cross-cutting agents get extra safety gates in the propose flow —
# they provide foundational review coverage that should not be silently excluded.
# This list is intentionally static and NOT derived from the agent registry or DB.
# Source of truth: Demarch CLAUDE.md "7 core review agents" — these 4 are the
# structural subset (architecture, quality, safety, correctness) vs domain-specific
# (user-product, performance, game-design).
# When adding or reclassifying agents, update this list AND the /interspect:propose
# command spec (os/clavain/commands/interspect-propose.md).
# Args: $1=agent_name
# Returns: 0 if cross-cutting, 1 if not
_interspect_is_cross_cutting() {
    local agent="$1"
    case "$agent" in
        fd-architecture|fd-quality|fd-safety|fd-correctness) return 0 ;;
        *) return 1 ;;
    esac
}

# Validate FLUX_ROUTING_OVERRIDES_PATH is safe (relative, no traversal).
# Returns: 0 if safe, 1 if not
_interspect_validate_overrides_path() {
    local filepath="$1"
    if [[ "$filepath" == /* ]]; then
        echo "ERROR: FLUX_ROUTING_OVERRIDES_PATH must be relative (got: ${filepath})" >&2
        return 1
    fi
    if [[ "$filepath" == *../* ]] || [[ "$filepath" == */../* ]] || [[ "$filepath" == .. ]]; then
        echo "ERROR: FLUX_ROUTING_OVERRIDES_PATH must not contain '..' (got: ${filepath})" >&2
        return 1
    fi
    return 0
}

# Read routing-overrides.json. Returns JSON or empty structure.
# Uses optimistic locking: accepts TOCTOU race for reads (dedup at write time).
# Args: none (uses FLUX_ROUTING_OVERRIDES_PATH or default)
_interspect_read_routing_overrides() {
    local root
    root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    local filepath="${FLUX_ROUTING_OVERRIDES_PATH:-.claude/routing-overrides.json}"

    # Path traversal protection
    if ! _interspect_validate_overrides_path "$filepath"; then
        echo '{"version":1,"overrides":[]}'
        return 1
    fi

    local fullpath="${root}/${filepath}"

    if [[ ! -f "$fullpath" ]]; then
        echo '{"version":1,"overrides":[]}'
        return 0
    fi

    # Parse JSON
    local content
    if ! content=$(jq '.' "$fullpath" 2>/dev/null); then
        echo "WARN: ${filepath} is malformed JSON" >&2
        echo '{"version":1,"overrides":[]}'
        return 1
    fi

    # Validate version
    local version
    version=$(echo "$content" | jq -r '.version // empty')
    if [[ -z "$version" ]] || (( version > 1 )); then
        echo "WARN: ${filepath} has unsupported version (${version:-missing}), ignoring" >&2
        echo '{"version":1,"overrides":[]}'
        return 1
    fi

    # Validate overrides is array
    if ! echo "$content" | jq -e '.overrides | type == "array"' >/dev/null 2>&1; then
        echo "WARN: ${filepath} .overrides is not an array, ignoring" >&2
        echo '{"version":1,"overrides":[]}'
        return 1
    fi

    # Warn about entries missing required fields (non-blocking)
    local missing_count
    missing_count=$(echo "$content" | jq '[.overrides[] | select(.agent == null or .action == null)] | length')
    if (( missing_count > 0 )); then
        echo "WARN: ${filepath} has ${missing_count} override(s) missing agent or action field" >&2
    fi

    echo "$content"
}

# Read routing-overrides.json under shared flock (for status display).
# Prevents torn reads during concurrent apply operations.
_interspect_read_routing_overrides_locked() {
    local root
    root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    local lockdir="${root}/.clavain/interspect"
    local lockfile="${lockdir}/.git-lock"

    mkdir -p "$lockdir" 2>/dev/null || true

    (
        # Shared lock allows concurrent reads, blocks on exclusive write lock.
        # Timeout 1s: if lock unavailable, fall back to unlocked read.
        if ! flock -s -w 1 9; then
            echo "WARN: Override file locked (apply in progress). Showing latest available data." >&2
        fi
        _interspect_read_routing_overrides
    ) 9>"$lockfile"
}

# Write routing-overrides.json atomically (call inside _interspect_flock_git).
# Uses temp file + rename for crash safety.
# Args: $1=JSON content to write
_interspect_write_routing_overrides() {
    local content="$1"
    local root
    root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    local filepath="${FLUX_ROUTING_OVERRIDES_PATH:-.claude/routing-overrides.json}"

    if ! _interspect_validate_overrides_path "$filepath"; then
        return 1
    fi

    local fullpath="${root}/${filepath}"

    mkdir -p "$(dirname "$fullpath")" 2>/dev/null || true

    # Atomic write: temp file + rename
    local tmpfile="${fullpath}.tmp.$$"
    echo "$content" | jq '.' > "$tmpfile"

    # Validate before replacing
    if ! jq -e '.' "$tmpfile" >/dev/null 2>&1; then
        rm -f "$tmpfile"
        echo "ERROR: Write produced invalid JSON, aborted" >&2
        return 1
    fi

    mv "$tmpfile" "$fullpath"
}

# Check if an override exists for an agent.
# Args: $1=agent_name
# Returns: 0 if exists, 1 if not
_interspect_override_exists() {
    local agent="$1"
    local current
    current=$(_interspect_read_routing_overrides)
    echo "$current" | jq -e --arg agent "$agent" '.overrides[] | select(.agent == $agent)' >/dev/null 2>&1
}

# ─── Apply Routing Override ──────────────────────────────────────────────────

# Apply a routing override. Handles the full read-modify-write-commit-record flow.
# All operations (file write, git commit, DB inserts) run inside flock for atomicity.
# Args: $1=agent_name $2=reason $3=evidence_ids_json $4=created_by (default "interspect")
# Returns: 0 on success, 1 on failure
_interspect_apply_routing_override() {
    local agent="$1"
    local reason="$2"
    local evidence_ids="${3:-[]}"
    local created_by="${4:-interspect}"
    local scope_json="${5:-}"  # Optional JSON scope object (F5: manual override)

    # --- Pre-flock validation (fast-fail) ---

    # Validate agent name format (prevents injection + catches typos)
    if ! _interspect_validate_agent_name "$agent"; then
        return 1
    fi

    # Validate scope_json if provided
    if [[ -n "$scope_json" ]]; then
        if ! printf '%s\n' "$scope_json" | jq -e 'type == "object"' >/dev/null 2>&1; then
            echo "ERROR: scope must be a JSON object (got: ${scope_json})" >&2
            return 1
        fi
    fi

    # Validate evidence_ids is a JSON array
    if ! printf '%s\n' "$evidence_ids" | jq -e 'type == "array"' >/dev/null 2>&1; then
        echo "ERROR: evidence_ids must be a JSON array (got: ${evidence_ids})" >&2
        return 1
    fi

    local root
    root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    local filepath="${FLUX_ROUTING_OVERRIDES_PATH:-.claude/routing-overrides.json}"

    # Validate path (no traversal)
    if ! _interspect_validate_overrides_path "$filepath"; then
        return 1
    fi

    local fullpath="${root}/${filepath}"

    # Validate target path is in modification allow-list
    if ! _interspect_validate_target "$filepath"; then
        echo "ERROR: ${filepath} is not an allowed modification target" >&2
        return 1
    fi

    # --- Write commit message to temp file (avoids shell injection) ---

    local commit_msg_file
    commit_msg_file=$(mktemp)
    printf '[interspect] Exclude %s from flux-drive triage\n\nReason: %s\nEvidence: %s\nCreated-by: %s\n' \
        "$agent" "$reason" "$evidence_ids" "$created_by" > "$commit_msg_file"

    # --- DB path for use inside flock ---
    local db="${_INTERSPECT_DB:-$(_interspect_db_path)}"

    # --- Entire read-modify-write-commit-record inside flock ---
    local flock_output
    flock_output=$(_interspect_flock_git _interspect_apply_override_locked \
        "$root" "$filepath" "$fullpath" "$agent" "$reason" \
        "$evidence_ids" "$created_by" "$commit_msg_file" "$db" "$scope_json")

    local exit_code=$?
    rm -f "$commit_msg_file"

    if (( exit_code != 0 )); then
        echo "ERROR: Could not apply routing override. Check git status and retry." >&2
        echo "$flock_output" >&2
        return 1
    fi

    # Parse output from locked function
    local commit_sha
    commit_sha=$(echo "$flock_output" | tail -1)

    echo "SUCCESS: Excluded ${agent}. Commit: ${commit_sha}"
    echo "Canary monitoring active. Run /interspect:status after 5-10 sessions to check impact."
    echo "To undo: /interspect:revert ${agent}"
    return 0
}

# Inner function called under flock. Do NOT call directly.
# All arguments are positional to avoid quote-nesting hell.
_interspect_apply_override_locked() {
    set -e
    local root="$1" filepath="$2" fullpath="$3" agent="$4"
    local reason="$5" evidence_ids="$6" created_by="$7"
    local commit_msg_file="$8" db="$9" scope_json="${10:-}"

    local created
    created=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    # 1. Read current file
    local current
    if [[ -f "$fullpath" ]]; then
        current=$(jq '.' "$fullpath" 2>/dev/null || echo '{"version":1,"overrides":[]}')
    else
        current='{"version":1,"overrides":[]}'
    fi

    # 2. Dedup check (inside lock — TOCTOU-safe)
    local is_new=1
    if echo "$current" | jq -e --arg agent "$agent" '.overrides[] | select(.agent == $agent)' >/dev/null 2>&1; then
        echo "INFO: Override for ${agent} already exists, updating metadata." >&2
        is_new=0
    fi

    # 3. Compute confidence from evidence (inside lock — TOCTOU-safe)
    local escaped_agent
    escaped_agent=$(_interspect_sql_escape "$agent")
    _interspect_load_confidence
    local total wrong confidence
    total=$(sqlite3 "$db" "SELECT COUNT(*) FROM evidence WHERE source = '${escaped_agent}' AND event = 'override';")
    wrong=$(sqlite3 "$db" "SELECT COUNT(*) FROM evidence WHERE source = '${escaped_agent}' AND event = 'override' AND override_reason = 'agent_wrong';")
    if (( total > 0 )); then
        confidence=$(awk -v w="$wrong" -v t="$total" 'BEGIN {printf "%.2f", w/t}')
    else
        confidence="1.0"
    fi

    # 4. Build canary snapshot for JSON (DB remains authoritative for live state)
    local canary_window_uses="${_INTERSPECT_CANARY_WINDOW_USES:-20}"
    local canary_expires_at
    canary_expires_at=$(date -u -d "+${_INTERSPECT_CANARY_WINDOW_DAYS:-14} days" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
        || date -u -v+"${_INTERSPECT_CANARY_WINDOW_DAYS:-14}"d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)

    local canary_json="null"
    if [[ -n "$canary_expires_at" ]]; then
        canary_json=$(jq -n \
            --arg status "active" \
            --argjson window_uses "$canary_window_uses" \
            --arg expires_at "$canary_expires_at" \
            '{status:$status,window_uses:$window_uses,expires_at:$expires_at}')
    fi

    # 5. Build new override using jq --arg (no shell interpolation)
    local scope_arg="null"
    [[ -n "$scope_json" ]] && scope_arg="$scope_json"

    local new_override
    new_override=$(jq -n \
        --arg agent "$agent" \
        --arg action "exclude" \
        --arg reason "$reason" \
        --argjson evidence_ids "$evidence_ids" \
        --arg created "$created" \
        --arg created_by "$created_by" \
        --argjson confidence "$confidence" \
        --argjson canary "$canary_json" \
        --argjson scope "$scope_arg" \
        '{agent:$agent,action:$action,reason:$reason,evidence_ids:$evidence_ids,created:$created,created_by:$created_by,confidence:$confidence} + (if $canary != null then {canary:$canary} else {} end) + (if $scope != null then {scope:$scope} else {} end)')

    # 6. Merge (unique_by deduplicates, last write wins for metadata)
    local merged
    merged=$(echo "$current" | jq --argjson override "$new_override" \
        '.overrides = (.overrides + [$override] | unique_by(.agent))')

    # 7. Atomic write (temp + rename)
    mkdir -p "$(dirname "$fullpath")" 2>/dev/null || true
    local tmpfile="${fullpath}.tmp.$$"
    echo "$merged" | jq '.' > "$tmpfile"

    if ! jq -e '.' "$tmpfile" >/dev/null 2>&1; then
        rm -f "$tmpfile"
        echo "ERROR: Write produced invalid JSON, aborted" >&2
        return 1
    fi
    mv "$tmpfile" "$fullpath"

    # 8. Git add + commit (using -F for commit message — no injection)
    cd "$root"
    git add "$filepath"
    if ! git commit --no-verify -F "$commit_msg_file"; then
        # Rollback: unstage THEN restore working tree
        git reset HEAD -- "$filepath" 2>/dev/null || true
        git restore "$filepath" 2>/dev/null || git checkout -- "$filepath" 2>/dev/null || true
        echo "ERROR: Git commit failed. Override not applied." >&2
        return 1
    fi

    local commit_sha
    commit_sha=$(git rev-parse HEAD)

    # 9. DB inserts INSIDE flock (atomicity with git commit)
    escaped_reason=$(_interspect_sql_escape "$reason")

    # Only insert modification + canary for genuinely NEW overrides
    if (( is_new == 1 )); then
        local ts
        ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)

        # Modification record (confidence from evidence computation above)
        sqlite3 "$db" "INSERT INTO modifications (group_id, ts, tier, mod_type, target_file, commit_sha, confidence, evidence_summary, status)
            VALUES ('${escaped_agent}', '${ts}', 'persistent', 'routing', '${filepath}', '${commit_sha}', ${confidence}, '${escaped_reason}', 'applied');"

        # Canary record — compute baseline BEFORE insert
        # (_interspect_load_confidence already called in step 3 above)
        local baseline_json
        baseline_json=$(_interspect_compute_canary_baseline "$ts" "" 2>/dev/null || echo "null")

        local b_override_rate b_fp_rate b_finding_density b_window
        if [[ "$baseline_json" != "null" ]]; then
            b_override_rate=$(echo "$baseline_json" | jq -r '.override_rate')
            b_fp_rate=$(echo "$baseline_json" | jq -r '.fp_rate')
            b_finding_density=$(echo "$baseline_json" | jq -r '.finding_density')
            b_window=$(echo "$baseline_json" | jq -r '.window')
        else
            b_override_rate="NULL"
            b_fp_rate="NULL"
            b_finding_density="NULL"
            b_window="NULL"
        fi

        local expires_at
        expires_at=$(date -u -d "+${_INTERSPECT_CANARY_WINDOW_DAYS:-14} days" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
            || date -u -v+"${_INTERSPECT_CANARY_WINDOW_DAYS:-14}"d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)
        if [[ -z "$expires_at" ]]; then
            echo "ERROR: date command does not support relative dates" >&2
            return 1
        fi

        # Build INSERT with conditional NULLs for baseline
        local baseline_values
        if [[ "$b_override_rate" == "NULL" ]]; then
            baseline_values="NULL, NULL, NULL, NULL"
        else
            local escaped_bwindow
            escaped_bwindow=$(_interspect_sql_escape "$b_window")
            baseline_values="${b_override_rate}, ${b_fp_rate}, ${b_finding_density}, '${escaped_bwindow}'"
        fi

        if ! sqlite3 "$db" "INSERT INTO canary (file, commit_sha, group_id, applied_at, window_uses, window_expires_at, baseline_override_rate, baseline_fp_rate, baseline_finding_density, baseline_window, status)
            VALUES ('${filepath}', '${commit_sha}', '${escaped_agent}', '${ts}', ${_INTERSPECT_CANARY_WINDOW_USES:-20}, '${expires_at}', ${baseline_values}, 'active');"; then
            # Canary failure is non-fatal but flagged in DB
            sqlite3 "$db" "UPDATE modifications SET status = 'applied-unmonitored' WHERE commit_sha = '${commit_sha}';" 2>/dev/null || true
            echo "WARN: Canary monitoring failed — override active but unmonitored." >&2
        fi
    else
        echo "INFO: Metadata updated for existing override. No new canary." >&2
    fi

    # 10. Output commit SHA (last line, captured by caller)
    echo "$commit_sha"
}

# ─── Propose Routing Override ────────────────────────────────────────────────

# Write a "propose" entry to routing-overrides.json.
# Proposals are informational — flux-drive shows them in triage but does NOT exclude.
# No canary monitoring or modification record (lighter than apply_routing_override).
# Args: $1=agent_name $2=reason $3=evidence_ids_json $4=created_by
# Returns: 0 on success (including dedup skip), 1 on failure
_interspect_apply_propose() {
    local agent="$1"
    local reason="$2"
    local evidence_ids="${3:-[]}"
    local created_by="${4:-interspect}"

    # Pre-flock validation
    if ! _interspect_validate_agent_name "$agent"; then
        return 1
    fi
    if ! printf '%s\n' "$evidence_ids" | jq -e 'type == "array"' >/dev/null 2>&1; then
        echo "ERROR: evidence_ids must be a JSON array (got: ${evidence_ids})" >&2
        return 1
    fi

    local root
    root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    local filepath="${FLUX_ROUTING_OVERRIDES_PATH:-.claude/routing-overrides.json}"

    if ! _interspect_validate_overrides_path "$filepath"; then
        return 1
    fi

    local fullpath="${root}/${filepath}"

    if ! _interspect_validate_target "$filepath"; then
        echo "ERROR: ${filepath} is not an allowed modification target" >&2
        return 1
    fi

    # Sanitize reason to prevent credential leakage and control chars in commit message
    local sanitized_reason
    sanitized_reason=$(_interspect_sanitize "$reason" 500)

    local commit_msg_file
    commit_msg_file=$(mktemp)
    printf '[interspect] Propose excluding %s from flux-drive triage\n\nReason: %s\nEvidence: %s\nCreated-by: %s\n' \
        "$agent" "$sanitized_reason" "$evidence_ids" "$created_by" > "$commit_msg_file"

    local flock_output
    flock_output=$(_interspect_flock_git _interspect_apply_propose_locked \
        "$root" "$filepath" "$fullpath" "$agent" "$sanitized_reason" \
        "$evidence_ids" "$created_by" "$commit_msg_file")

    local exit_code=$?
    rm -f "$commit_msg_file"

    # Exit code 2 = dedup skip (already exists), not an error
    if (( exit_code == 2 )); then
        echo "INFO: Override for ${agent} already exists. Skipping."
        return 0
    fi

    if (( exit_code != 0 )); then
        echo "ERROR: Could not write proposal. Check git status and retry." >&2
        echo "$flock_output" >&2
        return 1
    fi

    local commit_sha
    commit_sha=$(echo "$flock_output" | tail -1)

    echo "SUCCESS: Proposed excluding ${agent}. Commit: ${commit_sha}"
    echo "Visible in /interspect:status and flux-drive triage notes."
    echo "To apply: /interspect:approve ${agent} (or re-run /interspect:propose)"
    return 0
}

# Inner function called under flock. Do NOT call directly.
_interspect_apply_propose_locked() {
    set -e
    local root="$1" filepath="$2" fullpath="$3" agent="$4"
    local reason="$5" evidence_ids="$6" created_by="$7"
    local commit_msg_file="$8"

    local created
    created=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    # 1. Read current file
    local current
    if [[ -f "$fullpath" ]]; then
        current=$(jq '.' "$fullpath" 2>/dev/null || echo '{"version":1,"overrides":[]}')
    else
        current='{"version":1,"overrides":[]}'
    fi

    # 2. Dedup check (inside lock — TOCTOU-safe)
    #    Exit code 2 = skip (already exists). Caller handles this distinctly from error (1).
    if echo "$current" | jq -e --arg agent "$agent" '.overrides[] | select(.agent == $agent)' >/dev/null 2>&1; then
        return 2
    fi

    # 3. Build new propose entry (no confidence or canary — proposals are informational)
    local new_override
    new_override=$(jq -n \
        --arg agent "$agent" \
        --arg action "propose" \
        --arg reason "$reason" \
        --argjson evidence_ids "$evidence_ids" \
        --arg created "$created" \
        --arg created_by "$created_by" \
        '{agent:$agent,action:$action,reason:$reason,evidence_ids:$evidence_ids,created:$created,created_by:$created_by}')

    # 4. Merge
    local merged
    merged=$(echo "$current" | jq --argjson override "$new_override" \
        '.overrides = (.overrides + [$override])')

    # 5. Atomic write
    mkdir -p "$(dirname "$fullpath")" 2>/dev/null || true
    local tmpfile="${fullpath}.tmp.$$"
    echo "$merged" | jq '.' > "$tmpfile"

    if ! jq -e '.' "$tmpfile" >/dev/null 2>&1; then
        rm -f "$tmpfile"
        echo "ERROR: Write produced invalid JSON, aborted" >&2
        return 1
    fi
    mv "$tmpfile" "$fullpath"

    # 6. Git add + commit (use git -C to avoid cd side-effect under set -e)
    git -C "$root" add "$filepath"
    if ! git -C "$root" commit --no-verify -F "$commit_msg_file"; then
        git -C "$root" reset HEAD -- "$filepath" 2>/dev/null || true
        git -C "$root" restore "$filepath" 2>/dev/null || git -C "$root" checkout -- "$filepath" 2>/dev/null || true
        echo "ERROR: Git commit failed. Proposal not applied." >&2
        return 1
    fi

    # No canary or modification records for proposals

    # 7. Output commit SHA
    git -C "$root" rev-parse HEAD
}

# ─── Approve (Promote propose → exclude) ────────────────────────────────────

# Promote a "propose" entry to "exclude" in routing-overrides.json.
# In-place promotion: preserves original created/created_by/evidence_ids,
# adds confidence, canary snapshot, approved timestamp.
# Handles full read-modify-write-commit-record flow under flock.
# Args: $1=agent_name
# Returns: 0 on success (including idempotent skip), 1 on failure
_interspect_approve_override() {
    local agent="$1"

    # --- Pre-flock validation (fast-fail) ---

    if ! _interspect_validate_agent_name "$agent"; then
        return 1
    fi

    local root
    root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    local filepath="${FLUX_ROUTING_OVERRIDES_PATH:-.claude/routing-overrides.json}"

    if ! _interspect_validate_overrides_path "$filepath"; then
        return 1
    fi

    local fullpath="${root}/${filepath}"

    if ! _interspect_validate_target "$filepath"; then
        echo "ERROR: ${filepath} is not an allowed modification target" >&2
        return 1
    fi

    # Pre-check: verify a propose entry exists (fast-fail before flock)
    if [[ -f "$fullpath" ]]; then
        if ! jq -e --arg agent "$agent" '.overrides[] | select(.agent == $agent and .action == "propose")' "$fullpath" >/dev/null 2>&1; then
            # Check if already excluded (idempotent)
            if jq -e --arg agent "$agent" '.overrides[] | select(.agent == $agent and .action == "exclude")' "$fullpath" >/dev/null 2>&1; then
                echo "INFO: ${agent} is already excluded. Nothing to approve."
                return 0
            fi
            echo "ERROR: No proposal found for ${agent}. Run /interspect:propose first." >&2
            return 1
        fi
    else
        echo "ERROR: ${fullpath} does not exist. No proposals to approve." >&2
        return 1
    fi

    # --- Write commit message to temp file (avoids shell injection) ---

    local commit_msg_file
    commit_msg_file=$(mktemp)
    printf '[interspect] Approve: exclude %s from flux-drive triage\n\nPromoted from proposal to active exclusion.\nAgent: %s\n' \
        "$agent" "$agent" > "$commit_msg_file"

    # --- DB path for use inside flock ---
    local db="${_INTERSPECT_DB:-$(_interspect_db_path)}"

    # --- Entire promote-write-commit-record inside flock ---
    local flock_output
    flock_output=$(_interspect_flock_git _interspect_approve_override_locked \
        "$root" "$filepath" "$fullpath" "$agent" "$commit_msg_file" "$db")

    local exit_code=$?
    rm -f "$commit_msg_file"

    # Exit code 2 = already excluded (idempotent)
    if (( exit_code == 2 )); then
        echo "INFO: ${agent} is already excluded. Nothing to approve."
        return 0
    fi

    if (( exit_code != 0 )); then
        echo "ERROR: Could not approve override. Check git status and retry." >&2
        echo "$flock_output" >&2
        return 1
    fi

    # Parse output from locked function
    local commit_sha
    commit_sha=$(echo "$flock_output" | tail -1)

    echo "SUCCESS: Approved exclusion for ${agent}. Commit: ${commit_sha}"
    echo "Canary monitoring active. Run /interspect:status after 5-10 sessions to check impact."
    echo "To undo: /interspect:revert ${agent}"
    return 0
}

# Inner function called under flock. Do NOT call directly.
# All arguments are positional to avoid quote-nesting hell.
_interspect_approve_override_locked() {
    set -e
    local root="$1" filepath="$2" fullpath="$3" agent="$4"
    local commit_msg_file="$5" db="$6"

    local approved_at
    approved_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    # 1. Read current file
    local current
    if [[ -f "$fullpath" ]]; then
        current=$(jq '.' "$fullpath" 2>/dev/null || echo '{"version":1,"overrides":[]}')
    else
        echo "ERROR: routing-overrides.json does not exist" >&2
        return 1
    fi

    # 2. Find propose entry (inside lock — TOCTOU-safe)
    if ! echo "$current" | jq -e --arg agent "$agent" '.overrides[] | select(.agent == $agent and .action == "propose")' >/dev/null 2>&1; then
        # Check if already excluded (race: another session approved between our pre-check and flock)
        if echo "$current" | jq -e --arg agent "$agent" '.overrides[] | select(.agent == $agent and .action == "exclude")' >/dev/null 2>&1; then
            return 2
        fi
        echo "ERROR: No proposal for ${agent} in routing-overrides.json" >&2
        return 1
    fi

    # 3. Compute confidence from evidence (inside lock — TOCTOU-safe)
    #    Query all name variants: fd-X, interflux:fd-X, interflux:review:fd-X
    #    Evidence is recorded under prefixed names; routing uses short fd-X format.
    local escaped_agent
    escaped_agent=$(_interspect_sql_escape "$agent")
    local escaped_prefixed escaped_review_prefixed
    escaped_prefixed=$(_interspect_sql_escape "interflux:${agent}")
    escaped_review_prefixed=$(_interspect_sql_escape "interflux:review:${agent}")
    _interspect_load_confidence
    local total wrong confidence
    total=$(sqlite3 "$db" "SELECT COUNT(*) FROM evidence WHERE source IN ('${escaped_agent}', '${escaped_prefixed}', '${escaped_review_prefixed}') AND event = 'override';")
    wrong=$(sqlite3 "$db" "SELECT COUNT(*) FROM evidence WHERE source IN ('${escaped_agent}', '${escaped_prefixed}', '${escaped_review_prefixed}') AND event = 'override' AND override_reason = 'agent_wrong';")
    if (( total > 0 )); then
        confidence=$(awk -v w="$wrong" -v t="$total" 'BEGIN {printf "%.2f", w/t}')
    else
        confidence="1.0"
    fi

    # 4. Build canary snapshot for JSON (DB remains authoritative for live state)
    local canary_window_uses="${_INTERSPECT_CANARY_WINDOW_USES:-20}"
    local canary_expires_at
    canary_expires_at=$(date -u -d "+${_INTERSPECT_CANARY_WINDOW_DAYS:-14} days" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
        || date -u -v+"${_INTERSPECT_CANARY_WINDOW_DAYS:-14}"d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)

    local canary_json="null"
    if [[ -n "$canary_expires_at" ]]; then
        canary_json=$(jq -n \
            --arg status "active" \
            --argjson window_uses "$canary_window_uses" \
            --arg expires_at "$canary_expires_at" \
            '{status:$status,window_uses:$window_uses,expires_at:$expires_at}')
    fi

    # 5. In-place promote: action→exclude, add confidence, canary, approved timestamp
    local merged
    merged=$(echo "$current" | jq \
        --arg agent "$agent" \
        --arg approved "$approved_at" \
        --argjson confidence "$confidence" \
        --argjson canary "$canary_json" \
        '(.overrides |= map(
            if .agent == $agent and .action == "propose" then
                .action = "exclude"
                | .approved = $approved
                | .confidence = $confidence
                | (if $canary != null then .canary = $canary else . end)
            else . end
        ))')

    # 6. Atomic write (temp + rename)
    mkdir -p "$(dirname "$fullpath")" 2>/dev/null || true
    local tmpfile="${fullpath}.tmp.$$"
    echo "$merged" | jq '.' > "$tmpfile"

    if ! jq -e '.' "$tmpfile" >/dev/null 2>&1; then
        rm -f "$tmpfile"
        echo "ERROR: Write produced invalid JSON, aborted" >&2
        return 1
    fi
    mv "$tmpfile" "$fullpath"

    # 7. Git add + commit (using git -C to avoid cd side-effect under set -e)
    git -C "$root" add "$filepath"
    if ! git -C "$root" commit --no-verify -F "$commit_msg_file"; then
        git -C "$root" reset HEAD -- "$filepath" 2>/dev/null || true
        git -C "$root" restore "$filepath" 2>/dev/null || git -C "$root" checkout -- "$filepath" 2>/dev/null || true
        echo "ERROR: Git commit failed. Approval not applied." >&2
        return 1
    fi

    local commit_sha
    commit_sha=$(git -C "$root" rev-parse HEAD)

    # 8. DB inserts INSIDE flock (atomicity with git commit)
    local ts
    ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    local escaped_reason
    escaped_reason=$(_interspect_sql_escape "Promoted from proposal to active exclusion")
    local escaped_filepath
    escaped_filepath=$(_interspect_sql_escape "$filepath")

    # Modification record (guarded — git commit already succeeded, DB failure is non-fatal)
    if ! sqlite3 "$db" "INSERT INTO modifications (group_id, ts, tier, mod_type, target_file, commit_sha, confidence, evidence_summary, status)
        VALUES ('${escaped_agent}', '${ts}', 'persistent', 'routing', '${escaped_filepath}', '${commit_sha}', ${confidence}, '${escaped_reason}', 'applied');"; then
        echo "WARN: Modification record insert failed — override is active but untracked." >&2
    fi

    # 9. Canary record — compute baseline BEFORE insert
    local baseline_json
    baseline_json=$(_interspect_compute_canary_baseline "$ts" "" 2>/dev/null || echo "null")

    local b_override_rate b_fp_rate b_finding_density b_window
    if [[ "$baseline_json" != "null" ]]; then
        b_override_rate=$(echo "$baseline_json" | jq -r '.override_rate')
        b_fp_rate=$(echo "$baseline_json" | jq -r '.fp_rate')
        b_finding_density=$(echo "$baseline_json" | jq -r '.finding_density')
        b_window=$(echo "$baseline_json" | jq -r '.window')
    else
        b_override_rate="NULL"
        b_fp_rate="NULL"
        b_finding_density="NULL"
        b_window="NULL"
    fi

    local expires_at
    expires_at=$(date -u -d "+${_INTERSPECT_CANARY_WINDOW_DAYS:-14} days" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
        || date -u -v+"${_INTERSPECT_CANARY_WINDOW_DAYS:-14}"d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)
    if [[ -z "$expires_at" ]]; then
        echo "ERROR: date command does not support relative dates" >&2
        return 1
    fi

    # Build INSERT with conditional NULLs for baseline
    local baseline_values
    if [[ "$b_override_rate" == "NULL" ]]; then
        baseline_values="NULL, NULL, NULL, NULL"
    else
        local escaped_bwindow
        escaped_bwindow=$(_interspect_sql_escape "$b_window")
        baseline_values="${b_override_rate}, ${b_fp_rate}, ${b_finding_density}, '${escaped_bwindow}'"
    fi

    if ! sqlite3 "$db" "INSERT INTO canary (file, commit_sha, group_id, applied_at, window_uses, window_expires_at, baseline_override_rate, baseline_fp_rate, baseline_finding_density, baseline_window, status)
        VALUES ('${escaped_filepath}', '${commit_sha}', '${escaped_agent}', '${ts}', ${_INTERSPECT_CANARY_WINDOW_USES:-20}, '${expires_at}', ${baseline_values}, 'active');"; then
        # Canary failure is non-fatal but flagged in DB
        sqlite3 "$db" "UPDATE modifications SET status = 'applied-unmonitored' WHERE commit_sha = '${commit_sha}';" 2>/dev/null || true
        echo "WARN: Canary monitoring failed — override active but unmonitored." >&2
    fi

    # 10. Output commit SHA (last line, captured by caller)
    echo "$commit_sha"
}

# ─── Revert Routing Override ─────────────────────────────────────────────────

# Revert a routing override. Handles the full read-modify-write-commit-record flow.
# All operations (file write, git commit, DB updates) run inside flock for atomicity.
# Args: $1=agent_name
# Returns: 0 on success, 1 on failure
_interspect_revert_routing_override() {
    local agent="$1"

    # --- Pre-flock validation (fast-fail) ---

    if ! _interspect_validate_agent_name "$agent"; then
        return 1
    fi

    local root
    root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    local filepath="${FLUX_ROUTING_OVERRIDES_PATH:-.claude/routing-overrides.json}"

    if ! _interspect_validate_overrides_path "$filepath"; then
        return 1
    fi

    local fullpath="${root}/${filepath}"

    # Idempotency check: verify override exists
    if ! _interspect_override_exists "$agent"; then
        echo "INFO: Override for ${agent} not found. Already removed or never existed." >&2
        return 0
    fi

    # --- Write commit message to temp file (avoids shell injection) ---

    local commit_msg_file
    commit_msg_file=$(mktemp)
    printf '[interspect] Revert routing override for %s\n\nReason: User requested revert via /interspect:revert\n' \
        "$agent" > "$commit_msg_file"

    # --- DB path for use inside flock ---
    local db="${_INTERSPECT_DB:-$(_interspect_db_path)}"

    # --- Entire read-modify-write-commit-record inside flock ---
    local flock_output
    flock_output=$(_interspect_flock_git _interspect_revert_override_locked \
        "$root" "$filepath" "$fullpath" "$agent" "$commit_msg_file" "$db")

    local exit_code=$?
    rm -f "$commit_msg_file"

    if (( exit_code != 0 )); then
        echo "ERROR: Could not revert routing override. Check git status and retry." >&2
        echo "$flock_output" >&2
        return 1
    fi

    echo "SUCCESS: Reverted routing override for ${agent}."
    return 0
}

# Inner function called under flock. Do NOT call directly.
_interspect_revert_override_locked() {
    set -e
    local root="$1" filepath="$2" fullpath="$3" agent="$4"
    local commit_msg_file="$5" db="$6"

    # Re-check inside flock (TOCTOU-safe)
    if [[ ! -f "$fullpath" ]]; then
        echo "INFO: Override file does not exist (concurrent removal)" >&2
        return 0
    fi

    local current
    current=$(jq '.' "$fullpath" 2>/dev/null || echo '{"version":1,"overrides":[]}')

    if ! echo "$current" | jq -e --arg agent "$agent" '.overrides[] | select(.agent == $agent)' >/dev/null 2>&1; then
        echo "INFO: Override for ${agent} already removed (concurrent revert)" >&2
        return 0
    fi

    # Remove the override entry
    local updated
    updated=$(echo "$current" | jq --arg agent "$agent" 'del(.overrides[] | select(.agent == $agent))')
    echo "$updated" | jq '.' > "$fullpath"

    # Git add + commit
    cd "$root"
    git add "$filepath"
    if ! git commit --no-verify -F "$commit_msg_file"; then
        # Rollback: unstage + restore
        git reset HEAD -- "$filepath" 2>/dev/null || true
        git restore "$filepath" 2>/dev/null || git checkout -- "$filepath" 2>/dev/null || true
        echo "ERROR: Git commit failed. Revert not applied." >&2
        return 1
    fi

    # Update DB records INSIDE flock
    local escaped_agent
    escaped_agent=$(_interspect_sql_escape "$agent")
    sqlite3 "$db" "UPDATE canary SET status = 'reverted' WHERE group_id = '${escaped_agent}' AND status = 'active';" 2>/dev/null || true
    sqlite3 "$db" "UPDATE modifications SET status = 'reverted' WHERE group_id = '${escaped_agent}' AND status = 'applied';" 2>/dev/null || true
}

# ─── Blacklist Management ────────────────────────────────────────────────────

# Add a pattern to the blacklist. Prevents interspect from re-proposing
# the same exclusion or overlay for this agent/pattern.
# Args: $1=pattern_key (agent name or agent/overlay_id), $2=reason
# Returns: 0 on success, 1 on failure
_interspect_blacklist_pattern() {
    local pattern_key="$1"
    local reason="${2:-User requested blacklist}"
    local db="${_INTERSPECT_DB:-$(_interspect_db_path)}"

    local escaped_key escaped_reason
    escaped_key=$(_interspect_sql_escape "$pattern_key")
    escaped_reason=$(_interspect_sql_escape "$reason")

    local ts
    ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    sqlite3 "$db" "INSERT OR REPLACE INTO blacklist (pattern_key, blacklisted_at, reason) VALUES ('${escaped_key}', '${ts}', '${escaped_reason}');"
}

# Remove a pattern from the blacklist.
# Args: $1=pattern_key
# Returns: 0 on success (even if not found)
_interspect_unblacklist_pattern() {
    local pattern_key="$1"
    local db="${_INTERSPECT_DB:-$(_interspect_db_path)}"

    local escaped_key
    escaped_key=$(_interspect_sql_escape "$pattern_key")

    sqlite3 "$db" "DELETE FROM blacklist WHERE pattern_key = '${escaped_key}';"
}

# ─── Autonomy Mode (F6) ────────────────────────────────────────────────────

# Check if autonomous mode is enabled.
# Returns: 0 if autonomous, 1 if propose mode (default)
_interspect_is_autonomous() {
    _interspect_load_confidence
    [[ "${_INTERSPECT_AUTONOMY:-false}" == "true" ]]
}

# Set autonomy mode. Writes to confidence.json (human-owned, protected).
# Args: $1=true|false
# Returns: 0 on success, 1 on failure
_interspect_set_autonomy() {
    local enabled="$1"
    if [[ "$enabled" != "true" && "$enabled" != "false" ]]; then
        echo "ERROR: autonomy must be 'true' or 'false' (got: ${enabled})" >&2
        return 1
    fi

    local root
    root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    local conf="${root}/${_INTERSPECT_CONFIDENCE_JSON}"

    if [[ ! -f "$conf" ]]; then
        echo "ERROR: confidence.json not found at ${conf}" >&2
        return 1
    fi

    # Update the JSON file
    local updated
    updated=$(jq --argjson val "$enabled" '.autonomy = $val' "$conf")
    echo "$updated" | jq '.' > "$conf"

    # Reset loaded flag so next load picks up the change
    unset _INTERSPECT_CONFIDENCE_LOADED
    _INTERSPECT_AUTONOMY="$enabled"

    return 0
}

# Check circuit breaker: has a target been reverted too many times recently?
# If a target is reverted >= circuit_breaker_max times within circuit_breaker_days,
# autonomous modifications are blocked for that target.
# Args: $1=group_id (agent name or agent/overlay_id)
# Returns: 0 if circuit breaker TRIPPED (should block), 1 if clear
_interspect_circuit_breaker_tripped() {
    _interspect_load_confidence
    local group_id="$1"
    local db="${_INTERSPECT_DB:-$(_interspect_db_path)}"

    local escaped_group
    escaped_group=$(_interspect_sql_escape "$group_id")
    local max_reverts="${_INTERSPECT_CIRCUIT_BREAKER_MAX:-3}"
    local days="${_INTERSPECT_CIRCUIT_BREAKER_DAYS:-30}"

    local revert_count
    revert_count=$(sqlite3 "$db" "SELECT COUNT(*) FROM modifications WHERE group_id = '${escaped_group}' AND status = 'reverted' AND ts > datetime('now', '-${days} days');" 2>/dev/null || echo "0")

    (( revert_count >= max_reverts ))
}

# Check if an override should auto-apply (autonomy mode + safety checks).
# This is the gateway function called by propose flow to decide propose vs apply.
# Args: $1=agent_name $2=mod_type ("routing" or "prompt_tuning")
# Returns: 0 if should auto-apply, 1 if should propose
_interspect_should_auto_apply() {
    local agent="$1"
    local mod_type="${2:-routing}"

    # Must be in autonomous mode
    if ! _interspect_is_autonomous; then
        return 1
    fi

    # Type 3 (prompt tuning overlays) always require propose mode
    # Type 1-2 (routing, overlays with routing effect) can auto-apply
    # Per design: overlays are "always_propose" in protected-paths.json
    if [[ "$mod_type" == "prompt_tuning" ]]; then
        return 1
    fi

    # Circuit breaker: too many reverts → force propose
    if _interspect_circuit_breaker_tripped "$agent"; then
        echo "INFO: Circuit breaker tripped for ${agent} — forcing propose mode." >&2
        return 1
    fi

    # Baseline check: need sufficient historical data for canary
    _interspect_load_confidence
    local min_baseline="${_INTERSPECT_CANARY_MIN_BASELINE:-15}"
    local db="${_INTERSPECT_DB:-$(_interspect_db_path)}"
    local escaped_agent
    escaped_agent=$(_interspect_sql_escape "$agent")

    local session_count
    session_count=$(sqlite3 "$db" "SELECT COUNT(DISTINCT session_id) FROM evidence WHERE source = '${escaped_agent}';" 2>/dev/null || echo "0")

    if (( session_count < min_baseline )); then
        echo "INFO: Insufficient baseline for ${agent} (${session_count}/${min_baseline} sessions) — forcing propose mode." >&2
        return 1
    fi

    return 0
}

# ─── Canary Monitoring ──────────────────────────────────────────────────────

# Compute canary baseline metrics from historical evidence.
# Uses the last N sessions (configurable) before a given timestamp.
# Args: $1=before_ts (ISO 8601), $2=project (optional, filters by project)
# Output: JSON object with baseline metrics or "null" if insufficient data
_interspect_compute_canary_baseline() {
    _interspect_load_confidence
    local before_ts="$1"
    local project="${2:-}"
    local db="${_INTERSPECT_DB:-$(_interspect_db_path)}"
    local min_baseline="${_INTERSPECT_CANARY_MIN_BASELINE:-15}"
    local window_size="${_INTERSPECT_CANARY_WINDOW_USES:-20}"

    # SQL-escape before_ts (review P0-1: prevent SQL injection)
    local escaped_ts
    escaped_ts=$(_interspect_sql_escape "$before_ts")

    # Build optional project filter
    local project_filter=""
    if [[ -n "$project" ]]; then
        local escaped_project
        escaped_project=$(_interspect_sql_escape "$project")
        project_filter="AND project = '${escaped_project}'"
    fi

    # Count available sessions
    local session_count
    session_count=$(sqlite3 "$db" "SELECT COUNT(*) FROM sessions WHERE start_ts < '${escaped_ts}' ${project_filter};")

    if (( session_count < min_baseline )); then
        echo "null"
        return 0
    fi

    # Session IDs in the window (reused subquery)
    local session_ids_sql="SELECT session_id FROM sessions WHERE start_ts < '${escaped_ts}' ${project_filter} ORDER BY start_ts DESC LIMIT ${window_size}"

    # Window boundaries
    local window_start window_end
    window_end="$before_ts"
    window_start=$(sqlite3 "$db" "SELECT start_ts FROM sessions WHERE start_ts < '${escaped_ts}' ${project_filter} ORDER BY start_ts DESC LIMIT 1 OFFSET $((window_size - 1));" 2>/dev/null)
    [[ -z "$window_start" ]] && window_start=$(sqlite3 "$db" "SELECT MIN(start_ts) FROM sessions WHERE start_ts < '${escaped_ts}' ${project_filter};")
    # Guard: if window_start is still empty (shouldn't happen given session_count >= min_baseline), bail
    [[ -z "$window_start" ]] && { echo "null"; return 0; }

    # Count sessions actually in window
    local total_sessions_in_window
    total_sessions_in_window=$(sqlite3 "$db" "SELECT COUNT(*) FROM (${session_ids_sql});")
    if (( total_sessions_in_window == 0 )); then
        echo "null"
        return 0
    fi

    # Override rate: overrides per session
    local total_overrides override_rate
    total_overrides=$(sqlite3 "$db" "SELECT COUNT(*) FROM evidence WHERE event = 'override' AND session_id IN (${session_ids_sql});")
    override_rate=$(awk "BEGIN {printf \"%.4f\", ${total_overrides} / ${total_sessions_in_window}}")

    # FP rate: agent_wrong / total overrides
    local agent_wrong_count fp_rate
    agent_wrong_count=$(sqlite3 "$db" "SELECT COUNT(*) FROM evidence WHERE event = 'override' AND override_reason = 'agent_wrong' AND session_id IN (${session_ids_sql});")
    if (( total_overrides == 0 )); then
        fp_rate="0.0000"
    else
        fp_rate=$(awk "BEGIN {printf \"%.4f\", ${agent_wrong_count} / ${total_overrides}}")
    fi

    # Finding density: total evidence events per session
    local total_evidence finding_density
    total_evidence=$(sqlite3 "$db" "SELECT COUNT(*) FROM evidence WHERE session_id IN (${session_ids_sql});")
    finding_density=$(awk "BEGIN {printf \"%.4f\", ${total_evidence} / ${total_sessions_in_window}}")

    # Output as JSON
    jq -n \
        --argjson override_rate "$override_rate" \
        --argjson fp_rate "$fp_rate" \
        --argjson finding_density "$finding_density" \
        --arg window "${window_start}..${window_end}" \
        --argjson session_count "$total_sessions_in_window" \
        '{override_rate:$override_rate,fp_rate:$fp_rate,finding_density:$finding_density,window:$window,session_count:$session_count}'
}

# Record a canary sample for the current session.
# Computes per-session metrics and stores them in canary_samples.
# Args: $1=session_id
# Returns: 0 on success (or no work to do), 1 on error
_interspect_record_canary_sample() {
    local session_id="$1"
    local db="${_INTERSPECT_DB:-$(_interspect_db_path)}"
    local escaped_sid
    escaped_sid=$(_interspect_sql_escape "$session_id")

    # Skip sessions with no evidence events (not a flux-drive "use")
    local event_count
    event_count=$(sqlite3 "$db" "SELECT COUNT(*) FROM evidence WHERE session_id = '${escaped_sid}';")
    if (( event_count == 0 )); then
        return 0
    fi

    # Get active canaries
    local canary_ids
    canary_ids=$(sqlite3 "$db" "SELECT id FROM canary WHERE status = 'active';")
    [[ -z "$canary_ids" ]] && return 0

    # Compute per-session metrics
    local override_count agent_wrong_count override_rate fp_rate finding_density
    override_count=$(sqlite3 "$db" "SELECT COUNT(*) FROM evidence WHERE session_id = '${escaped_sid}' AND event = 'override';")
    agent_wrong_count=$(sqlite3 "$db" "SELECT COUNT(*) FROM evidence WHERE session_id = '${escaped_sid}' AND event = 'override' AND override_reason = 'agent_wrong';")

    # Override rate: raw count for this session
    override_rate=$(awk "BEGIN {printf \"%.4f\", ${override_count} + 0}")

    # FP rate: agent_wrong / total overrides (for this session)
    if (( override_count == 0 )); then
        fp_rate="0.0000"
    else
        fp_rate=$(awk "BEGIN {printf \"%.4f\", ${agent_wrong_count} / ${override_count}}")
    fi

    # Finding density: total events in this session
    finding_density=$(awk "BEGIN {printf \"%.4f\", ${event_count} + 0}")

    local ts
    ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    # Insert sample for each active canary + increment uses_so_far
    local canary_id
    while IFS= read -r canary_id; do
        [[ -z "$canary_id" ]] && continue

        # Dedup: INSERT OR IGNORE + conditional increment in single transaction (review P1: TOCTOU fix)
        # changes() must be checked in same sqlite3 invocation as the INSERT
        sqlite3 "$db" "
            INSERT OR IGNORE INTO canary_samples (canary_id, session_id, ts, override_rate, fp_rate, finding_density)
                VALUES (${canary_id}, '${escaped_sid}', '${ts}', ${override_rate}, ${fp_rate}, ${finding_density});
            UPDATE canary SET uses_so_far = uses_so_far + 1 WHERE id = ${canary_id} AND changes() > 0;
        " 2>/dev/null || true
    done <<< "$canary_ids"

    return 0
}

# Evaluate a single canary — compare samples against baseline.
# Args: $1=canary_id
# Output: JSON object with verdict
_interspect_evaluate_canary() {
    _interspect_load_confidence
    local canary_id="$1"
    local db="${_INTERSPECT_DB:-$(_interspect_db_path)}"
    local alert_pct="${_INTERSPECT_CANARY_ALERT_PCT:-20}"
    local noise_floor="${_INTERSPECT_CANARY_NOISE_FLOOR:-0.1}"

    # Get canary record
    local canary_row
    canary_row=$(sqlite3 -separator '|' "$db" "SELECT group_id, baseline_override_rate, baseline_fp_rate, baseline_finding_density, uses_so_far, window_uses, status FROM canary WHERE id = ${canary_id};")
    [[ -z "$canary_row" ]] && { echo '{"error":"canary_not_found"}'; return 1; }

    local agent b_or b_fp b_fd uses_so_far window_uses current_status
    IFS='|' read -r agent b_or b_fp b_fd uses_so_far window_uses current_status <<< "$canary_row"

    # Already resolved
    if [[ "$current_status" != "active" ]]; then
        jq -n --argjson id "$canary_id" --arg agent "$agent" --arg status "$current_status" --arg reason "Already resolved" \
            '{canary_id:$id,agent:$agent,status:$status,reason:$reason}'
        return 0
    fi

    # Insufficient baseline (NULL columns come through as empty strings from sqlite3)
    if [[ -z "$b_or" ]]; then
        jq -n --argjson id "$canary_id" --arg agent "$agent" --argjson uses "$uses_so_far" --argjson window "$window_uses" \
            '{canary_id:$id,agent:$agent,status:"monitoring",reason:"Insufficient baseline — collecting data",uses_so_far:$uses,window_uses:$window}'
        return 0
    fi

    # Not enough samples yet — check time-based expiry
    if (( uses_so_far < window_uses )); then
        local expires_at now
        expires_at=$(sqlite3 "$db" "SELECT window_expires_at FROM canary WHERE id = ${canary_id};")
        now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
        if [[ "$now" < "$expires_at" ]]; then
            jq -n --argjson id "$canary_id" --arg agent "$agent" --argjson uses "$uses_so_far" --argjson window "$window_uses" \
                --arg reason "${uses_so_far}/${window_uses} uses" \
                '{canary_id:$id,agent:$agent,status:"monitoring",reason:$reason,uses_so_far:$uses,window_uses:$window}'
            return 0
        fi
        # Time expired — evaluate with what we have
    fi

    # No samples collected (expired unused)
    local sample_count
    sample_count=$(sqlite3 "$db" "SELECT COUNT(*) FROM canary_samples WHERE canary_id = ${canary_id};")
    if (( sample_count == 0 )); then
        sqlite3 "$db" "UPDATE canary SET status = 'expired_unused', verdict_reason = 'No sessions during monitoring window' WHERE id = ${canary_id};"
        jq -n --argjson id "$canary_id" --arg agent "$agent" \
            '{canary_id:$id,agent:$agent,status:"expired_unused",reason:"No sessions during monitoring window"}'
        return 0
    fi

    # Compute averages from samples
    local avg_or avg_fp avg_fd
    avg_or=$(sqlite3 "$db" "SELECT printf('%.4f', AVG(override_rate)) FROM canary_samples WHERE canary_id = ${canary_id};")
    avg_fp=$(sqlite3 "$db" "SELECT printf('%.4f', AVG(fp_rate)) FROM canary_samples WHERE canary_id = ${canary_id};")
    avg_fd=$(sqlite3 "$db" "SELECT printf('%.4f', AVG(finding_density)) FROM canary_samples WHERE canary_id = ${canary_id};")

    # Compare each metric against baseline
    local verdict="passed"
    local reasons=""

    # Helper: check if metric degraded beyond threshold
    # For override_rate and fp_rate: INCREASE = degradation
    # For finding_density: DECREASE = degradation
    _canary_check_metric() {
        local metric_name="$1" baseline="$2" current="$3" direction="$4"
        local abs_diff threshold

        abs_diff=$(awk "BEGIN {d = ${current} - ${baseline}; if (d < 0) d = -d; printf \"%.4f\", d}")

        # Below noise floor — ignore
        if awk "BEGIN {exit (${abs_diff} < ${noise_floor}) ? 0 : 1}" 2>/dev/null; then
            return 0  # no degradation
        fi

        # Compute threshold
        threshold=$(awk "BEGIN {printf \"%.4f\", ${baseline} * ${alert_pct} / 100}")

        if [[ "$direction" == "increase" ]]; then
            # Alert if current > baseline + threshold
            if awk "BEGIN {exit (${current} > ${baseline} + ${threshold}) ? 0 : 1}" 2>/dev/null; then
                local pct_change
                pct_change=$(awk "BEGIN {if (${baseline} > 0) printf \"%.0f\", (${current} - ${baseline}) / ${baseline} * 100; else print \"inf\"}")
                reasons="${reasons}${metric_name}: ${baseline} -> ${current} (+${pct_change}%); "
                return 1  # degradation detected
            fi
        else
            # Alert if current < baseline - threshold
            if awk "BEGIN {exit (${current} < ${baseline} - ${threshold}) ? 0 : 1}" 2>/dev/null; then
                local pct_change
                pct_change=$(awk "BEGIN {if (${baseline} > 0) printf \"%.0f\", (${current} - ${baseline}) / ${baseline} * 100; else print \"-inf\"}")
                reasons="${reasons}${metric_name}: ${baseline} -> ${current} (${pct_change}%); "
                return 1  # degradation detected
            fi
        fi

        return 0  # no degradation
    }

    if ! _canary_check_metric "override_rate" "$b_or" "$avg_or" "increase"; then
        verdict="alert"
    fi
    if ! _canary_check_metric "fp_rate" "$b_fp" "$avg_fp" "increase"; then
        verdict="alert"
    fi
    if ! _canary_check_metric "finding_density" "$b_fd" "$avg_fd" "decrease"; then
        verdict="alert"
    fi

    # Store verdict
    local verdict_reason
    if [[ "$verdict" == "passed" ]]; then
        verdict_reason="All metrics within threshold (${alert_pct}% tolerance, ${noise_floor} floor)"
    else
        verdict_reason="${reasons}"
    fi

    local escaped_verdict_reason
    escaped_verdict_reason=$(_interspect_sql_escape "$verdict_reason")
    sqlite3 "$db" "UPDATE canary SET status = '${verdict}', verdict_reason = '${escaped_verdict_reason}' WHERE id = ${canary_id};"

    # Check for multiple active canaries (confounding note)
    local active_count
    active_count=$(sqlite3 "$db" "SELECT COUNT(*) FROM canary WHERE status = 'active' AND id != ${canary_id};")
    if (( active_count > 0 )); then
        verdict_reason="${verdict_reason} Note: ${active_count} other override(s) active during monitoring — individual impact unclear."
    fi

    jq -n \
        --argjson canary_id "$canary_id" \
        --arg agent "$agent" \
        --arg status "$verdict" \
        --arg reason "$verdict_reason" \
        --argjson baseline_or "$b_or" \
        --argjson baseline_fp "$b_fp" \
        --argjson baseline_fd "$b_fd" \
        --argjson current_or "$avg_or" \
        --argjson current_fp "$avg_fp" \
        --argjson current_fd "$avg_fd" \
        --argjson sample_count "$sample_count" \
        '{canary_id:$canary_id,agent:$agent,status:$status,reason:$reason,metrics:{baseline:{override_rate:$baseline_or,fp_rate:$baseline_fp,finding_density:$baseline_fd},current:{override_rate:$current_or,fp_rate:$current_fp,finding_density:$current_fd}},sample_count:$sample_count}'
}

# Check all active canaries and evaluate those whose window has completed.
# Returns: JSON array of verdicts
_interspect_check_canaries() {
    local db="${_INTERSPECT_DB:-$(_interspect_db_path)}"
    local now
    now=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    # Find canaries ready for evaluation
    local ready_ids
    ready_ids=$(sqlite3 "$db" "SELECT id FROM canary WHERE status = 'active' AND (uses_so_far >= window_uses OR window_expires_at <= '${now}');")

    if [[ -z "$ready_ids" ]]; then
        echo "[]"
        return 0
    fi

    local results="["
    local first=1
    local canary_id
    while IFS= read -r canary_id; do
        [[ -z "$canary_id" ]] && continue
        local result
        result=$(_interspect_evaluate_canary "$canary_id")
        if (( first )); then
            first=0
        else
            results+=","
        fi
        results+="$result"
    done <<< "$ready_ids"
    results+="]"

    echo "$results"
}

# ─── Kernel Event Consumer ───────────────────────────────────────────────────

# Consume kernel events (phase/dispatch) from intercore event store (one-shot batch).
# Called at session start to catch up on events since last session.
# Uses ic events tail with --consumer for automatic cursor tracking.
# Args: $1=session_id
_interspect_consume_kernel_events() {
    local session_id="$1"
    command -v ic &>/dev/null || return 0

    local db="${_INTERSPECT_DB:-$(_interspect_db_path)}"
    [[ -f "$db" ]] || return 0

    # One-shot query: events since last consumer cursor position
    local events_json
    events_json=$(ic events tail --all --consumer=interspect-consumer --limit=100 2>/dev/null) || return 0
    [[ -z "$events_json" ]] && return 0

    while IFS= read -r line; do
        [[ -z "$line" ]] && continue

        local event_id run_id event_source event_type from_state to_state timestamp
        event_id=$(echo "$line" | jq -r '.id // 0' 2>/dev/null) || continue
        run_id=$(echo "$line" | jq -r '.run_id // empty' 2>/dev/null) || continue
        event_source=$(echo "$line" | jq -r '.source // empty' 2>/dev/null) || continue
        event_type=$(echo "$line" | jq -r '.type // empty' 2>/dev/null) || continue
        from_state=$(echo "$line" | jq -r '.from_state // ""' 2>/dev/null) || from_state=""
        to_state=$(echo "$line" | jq -r '.to_state // ""' 2>/dev/null) || to_state=""
        timestamp=$(echo "$line" | jq -r '.timestamp // ""' 2>/dev/null) || timestamp=""

        [[ -z "$event_source" || -z "$event_type" ]] && continue

        # Build enriched context
        local enriched_context
        enriched_context=$(jq -n \
            --argjson kernel_event_id "$event_id" \
            --arg run_id "$run_id" \
            --arg from_state "$from_state" \
            --arg to_state "$to_state" \
            --arg timestamp "$timestamp" \
            '{kernel_event_id:$kernel_event_id,run_id:$run_id,from_state:$from_state,to_state:$to_state,timestamp:$timestamp}' \
            2>/dev/null) || continue

        # Materialize into interspect.db evidence
        _interspect_insert_evidence \
            "$session_id" "kernel-${event_source}" "${event_type}" \
            "" "$enriched_context" "interspect-consumer" \
            2>/dev/null || true
    done <<< "$events_json"
}

# Get a summary of all canaries (for status display).
# Returns: JSON array of canary status objects
_interspect_get_canary_summary() {
    local db="${_INTERSPECT_DB:-$(_interspect_db_path)}"

    local result
    result=$(sqlite3 -json "$db" "
        SELECT c.id, c.group_id as agent, c.status, c.uses_so_far, c.window_uses,
               c.baseline_override_rate, c.baseline_fp_rate, c.baseline_finding_density,
               c.applied_at, c.window_expires_at, c.verdict_reason,
               (SELECT COUNT(*) FROM canary_samples cs WHERE cs.canary_id = c.id) as sample_count,
               (SELECT printf('%.4f', AVG(cs.override_rate)) FROM canary_samples cs WHERE cs.canary_id = c.id) as avg_override_rate,
               (SELECT printf('%.4f', AVG(cs.fp_rate)) FROM canary_samples cs WHERE cs.canary_id = c.id) as avg_fp_rate,
               (SELECT printf('%.4f', AVG(cs.finding_density)) FROM canary_samples cs WHERE cs.canary_id = c.id) as avg_finding_density
        FROM canary c ORDER BY c.applied_at DESC;
    " 2>/dev/null) || true
    # sqlite3 -json returns empty string for zero rows
    [[ -z "$result" ]] && result="[]"
    echo "$result"
}

# ─── Git Operation Serialization ────────────────────────────────────────────

_INTERSPECT_GIT_LOCK_TIMEOUT=30

# Execute a command or shell function under the interspect git lock.
# Accepts any command, including shell functions defined in this library
# (functions run in the same sourced context, NOT as a subprocess).
# Usage: _interspect_flock_git git add <file>
# Usage: _interspect_flock_git _interspect_write_overlay_locked arg1 arg2 ...
_interspect_flock_git() {
    local root
    root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    local lockdir="${root}/.clavain/interspect"
    local lockfile="${lockdir}/.git-lock"

    mkdir -p "$lockdir" 2>/dev/null || true

    (
        if ! flock -w "$_INTERSPECT_GIT_LOCK_TIMEOUT" 9; then
            echo "ERROR: interspect git lock timeout (${_INTERSPECT_GIT_LOCK_TIMEOUT}s). Another interspect session may be committing." >&2
            return 1
        fi
        "$@"
    ) 9>"$lockfile"
}

# ─── Secret Detection ──────────────────────────────────────────────────────

# Detect and redact secrets in a string.
# Returns redacted string on stdout.
_interspect_redact_secrets() {
    local input="$1"
    [[ -z "$input" ]] && return 0

    # Pattern list: API keys, tokens, passwords, connection strings
    # Each sed expression replaces matches with [REDACTED:<type>]
    local result="$input"

    # API keys (generic long hex/base64 strings after key-like prefixes)
    result=$(printf '%s' "$result" | sed -E 's/(api[_-]?key|apikey|api[_-]?secret)[[:space:]]*[:=][[:space:]]*['"'"'"][^'"'"'"]{8,}['"'"'"]/\1=[REDACTED:api_key]/gi') || true
    # Bearer/token auth
    result=$(printf '%s' "$result" | sed -E 's/(bearer|token|auth)[[:space:]]+[A-Za-z0-9_\.\-]{20,}/\1 [REDACTED:token]/gi') || true
    # AWS keys
    result=$(printf '%s' "$result" | sed -E 's/AKIA[0-9A-Z]{16}/[REDACTED:aws_key]/g') || true
    # GitHub tokens
    result=$(printf '%s' "$result" | sed -E 's/gh[ps]_[A-Za-z0-9]{36,}/[REDACTED:github_token]/g') || true
    result=$(printf '%s' "$result" | sed -E 's/github_pat_[A-Za-z0-9_]{22,}/[REDACTED:github_token]/g') || true
    # Anthropic keys
    result=$(printf '%s' "$result" | sed -E 's/sk-ant-[A-Za-z0-9\-]{20,}/[REDACTED:anthropic_key]/g') || true
    # OpenAI keys
    result=$(printf '%s' "$result" | sed -E 's/sk-[A-Za-z0-9]{20,}/[REDACTED:openai_key]/g') || true
    # Connection strings (proto://user:pass@host)
    result=$(printf '%s' "$result" | sed -E 's|[a-zA-Z]+://[^:]+:[^@]+@[^/[:space:]]+|[REDACTED:connection_string]|g') || true
    # Generic password patterns
    result=$(printf '%s' "$result" | sed -E 's/(password|passwd|pwd|secret)[[:space:]]*[:=][[:space:]]*['"'"'"][^'"'"'"]{4,}['"'"'"]/\1=[REDACTED:password]/gi') || true

    printf '%s' "$result"
}

# ─── Sanitization ────────────────────────────────────────────────────────────

# Sanitize a string for safe storage and later LLM consumption.
# Pipeline: strip ANSI → strip control chars → truncate → redact secrets → reject injection.
# Args: $1 = input string
# Output: sanitized string on stdout
_interspect_sanitize() {
    local input="$1"
    local max_chars="${2:-500}"  # Default 500 chars; overlays use 2000

    # 1. Strip ANSI escape sequences
    input=$(printf '%s' "$input" | sed 's/\x1b\[[0-9;]*[a-zA-Z]//g')

    # 2. Strip control characters (0x00-0x08, 0x0B-0x0C, 0x0E-0x1F)
    input=$(printf '%s' "$input" | tr -d '\000-\010\013-\014\016-\037')

    # 3. Truncate to max_chars (prevents DoS from massive strings)
    input="${input:0:$max_chars}"

    # 4. Redact secrets (after truncate to limit scan surface)
    input=$(_interspect_redact_secrets "$input")

    # 5. Reject instruction-like patterns (case-insensitive)
    # Returns empty string + exit 1 on injection match so callers can hard-fail.
    local lower="${input,,}"
    if [[ "$lower" == *"<system>"* ]] || \
       [[ "$lower" == *"<instructions>"* ]] || \
       [[ "$lower" == *"ignore previous"* ]] || \
       [[ "$lower" == *"you are now"* ]] || \
       [[ "$lower" == *"disregard"* ]] || \
       [[ "$lower" == *"system:"* ]]; then
        return 1
    fi

    printf '%s' "$input"
}

# Validate hook ID against allowlist.
# Args: $1 = hook_id
# Returns: 0 if valid, 1 if invalid
_interspect_validate_hook_id() {
    local hook_id="$1"
    case "$hook_id" in
        interspect-evidence|interspect-session-start|interspect-session-end|interspect-correction|interspect-consumer)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

# ─── Evidence insertion ──────────────────────────────────────────────────────

# Insert an evidence row with sanitization.
# Args: $1=session_id $2=source $3=event $4=override_reason $5=context_json $6=hook_id
_interspect_insert_evidence() {
    local session_id="$1"
    local source="$2"
    local event="$3"
    local override_reason="${4:-}"
    local context_json="${5:-{}}"
    local hook_id="${6:-}"

    # Validate hook_id
    if [[ -n "$hook_id" ]] && ! _interspect_validate_hook_id "$hook_id"; then
        return 1
    fi

    local db="${_INTERSPECT_DB:-$(_interspect_db_path)}"
    [[ -f "$db" ]] || return 1

    # Sanitize user-controlled fields
    source=$(_interspect_sanitize "$source")
    event=$(_interspect_sanitize "$event")
    override_reason=$(_interspect_sanitize "$override_reason")
    context_json=$(_interspect_sanitize "$context_json")

    # Extra secret pass on context_json — most likely to carry leaked credentials
    context_json=$(_interspect_redact_secrets "$context_json")

    # Get sequence number and project
    local seq
    seq=$(_interspect_next_seq "$session_id")
    local project
    project=$(_interspect_project_name)
    local ts
    ts=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
    local source_version
    source_version=$(git rev-parse --short HEAD 2>/dev/null || echo "")

    # SQL-escape all values (double single quotes)
    local e_session="${session_id//\'/\'\'}"
    local e_source="${source//\'/\'\'}"
    local e_event="${event//\'/\'\'}"
    local e_reason="${override_reason//\'/\'\'}"
    local e_context="${context_json//\'/\'\'}"
    local e_project="${project//\'/\'\'}"
    local e_version="${source_version//\'/\'\'}"

    sqlite3 "$db" "INSERT INTO evidence (ts, session_id, seq, source, source_version, event, override_reason, context, project, project_lang, project_type) VALUES ('${ts}', '${e_session}', ${seq}, '${e_source}', '${e_version}', '${e_event}', '${e_reason}', '${e_context}', '${e_project}', NULL, NULL);"
}

# ─── Overlay System (Type 1 Modifications) ──────────────────────────────────
#
# Overlays augment agent prompts with learned context. Unlike routing overrides
# (Type 2) which exclude agents entirely, overlays sharpen an agent's focus.
#
# File format: .clavain/interspect/overlays/<agent>/<overlay-id>.md
#   ---
#   active: true
#   created: <ISO 8601>
#   created_by: <source>
#   evidence_ids: [1, 2, 3]
#   ---
#   <overlay body — injected into agent prompt>

# ─── Shared YAML Frontmatter Parsers ────────────────────────────────────────
# Single source of truth for frontmatter parsing. All overlay code MUST use
# these helpers — never parse frontmatter inline (review finding F4).

# Check if an overlay file has active: true in its YAML frontmatter.
# Uses awk delimiter state machine — safe against body content containing
# "active: true" or "---" horizontal rules.
# Args: $1=overlay_file_path
# Returns: 0 if active, 1 if not
_interspect_overlay_is_active() {
    local filepath="$1"
    [[ -f "$filepath" ]] || return 1
    awk '/^---$/ { if (++delim == 2) exit } delim == 1 && /^active: true$/ { found=1 } END { exit !found }' "$filepath"
}

# Extract the body content from an overlay file (everything after second ---).
# Args: $1=overlay_file_path
# Returns: body on stdout, empty if no body or malformed frontmatter
_interspect_overlay_body() {
    local filepath="$1"
    [[ -f "$filepath" ]] || return 0
    awk '/^---$/ { if (++delim == 2) { body=1; next } } body { print }' "$filepath"
}

# ─── Overlay Read/Count ─────────────────────────────────────────────────────

# Read all active overlays for an agent. Returns concatenated body content.
# Args: $1=agent_name
# Output: overlay content on stdout, empty if none active
_interspect_read_overlays() {
    local agent="$1"
    if ! _interspect_validate_agent_name "$agent" 2>/dev/null; then
        return 1
    fi

    local root
    root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    local overlay_dir="${root}/.clavain/interspect/overlays/${agent}"

    [[ -d "$overlay_dir" ]] || return 0

    local content=""
    local overlay_file
    # Sort alphabetically for deterministic ordering
    while IFS= read -r overlay_file; do
        [[ -f "$overlay_file" ]] || continue
        if _interspect_overlay_is_active "$overlay_file"; then
            local body
            body=$(_interspect_overlay_body "$overlay_file")
            if [[ -n "$body" ]]; then
                [[ -n "$content" ]] && content+=$'\n\n'
                content+="$body"
            fi
        fi
    done < <(printf '%s\n' "${overlay_dir}"/*.md | sort)

    printf '%s' "$content"
}

# Estimate token count for overlay content.
# Canonical implementation: wc -w * 1.3 (must match everywhere — review finding F12).
# Args: $1=content_string
# Output: integer token estimate on stdout
_interspect_count_overlay_tokens() {
    local content="$1"
    [[ -z "$content" ]] && { echo "0"; return 0; }
    local word_count
    word_count=$(printf '%s' "$content" | wc -w | tr -d ' ')
    # Validate integer (defense against unexpected wc output)
    if ! [[ "$word_count" =~ ^[0-9]+$ ]]; then
        echo "0"
        return 0
    fi
    # Multiply by 1.3, truncate to integer (use -v to avoid injection)
    awk -v wc="$word_count" 'BEGIN { printf "%d", wc * 1.3 }'
}

# ─── Overlay Write ──────────────────────────────────────────────────────────

# Validate overlay ID format. Must be lowercase alphanumeric + hyphens only.
# Args: $1=overlay_id
# Returns: 0 if valid, 1 if not
_interspect_validate_overlay_id() {
    local overlay_id="$1"
    if [[ ! "$overlay_id" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
        echo "ERROR: Invalid overlay ID '${overlay_id}'. Must match [a-z0-9][a-z0-9-]*." >&2
        return 1
    fi
    return 0
}

# Write a new overlay file atomically inside flock.
# All budget checks, file writes, git commits, and DB inserts happen inside
# a single flock acquisition (review finding F1: TOCTOU safety).
# Args: $1=agent_name $2=overlay_id $3=content $4=evidence_ids_json $5=created_by
# Returns: 0 on success, 1 on failure
_interspect_write_overlay() {
    local agent="$1"
    local overlay_id="$2"
    local content="$3"
    local evidence_ids="${4:-[]}"
    local created_by="${5:-interspect}"

    # --- Pre-flock validation (fast-fail) ---

    if ! _interspect_validate_agent_name "$agent"; then
        return 1
    fi
    if ! _interspect_validate_overlay_id "$overlay_id"; then
        return 1
    fi
    if ! printf '%s\n' "$evidence_ids" | jq -e 'type == "array"' >/dev/null 2>&1; then
        echo "ERROR: evidence_ids must be a JSON array (got: ${evidence_ids})" >&2
        return 1
    fi

    # Sanitize content (F3: prevent prompt injection in overlay body)
    # Use 2000-char limit (matches 500-token budget at ~4 chars/token)
    # _interspect_sanitize already calls _interspect_redact_secrets internally
    if ! content=$(_interspect_sanitize "$content" 2000); then
        echo "ERROR: Overlay content rejected — contains instruction-like patterns (prompt injection)" >&2
        return 1
    fi
    if [[ -z "$content" ]]; then
        echo "ERROR: Overlay content is empty after sanitization" >&2
        return 1
    fi

    local root
    root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)

    # Assemble path from validated components (F9)
    local rel_path=".clavain/interspect/overlays/${agent}/${overlay_id}.md"
    local fullpath="${root}/${rel_path}"

    # Containment assertion (F9): resolved path must stay within overlays dir
    local overlays_root="${root}/.clavain/interspect/overlays/"
    case "$fullpath" in
        "${overlays_root}"*) ;; # OK
        *)
            echo "ERROR: Path escapes overlay directory: ${fullpath}" >&2
            return 1
            ;;
    esac

    if ! _interspect_validate_target "$rel_path"; then
        echo "ERROR: ${rel_path} is not an allowed modification target" >&2
        return 1
    fi

    # Write commit message to temp file (avoids shell injection)
    local commit_msg_file
    commit_msg_file=$(mktemp)
    printf '[interspect] Add overlay %s for %s\n\nOverlay-ID: %s\nEvidence: %s\nCreated-by: %s\n' \
        "$overlay_id" "$agent" "$overlay_id" "$evidence_ids" "$created_by" > "$commit_msg_file"

    local db="${_INTERSPECT_DB:-$(_interspect_db_path)}"

    # --- Everything inside flock (F1: budget + write + DB atomically) ---
    local flock_output
    flock_output=$(_interspect_flock_git _interspect_write_overlay_locked \
        "$root" "$rel_path" "$fullpath" "$agent" "$overlay_id" \
        "$content" "$evidence_ids" "$created_by" "$commit_msg_file" "$db")

    local exit_code=$?
    rm -f "$commit_msg_file"

    if (( exit_code != 0 )); then
        echo "ERROR: Could not write overlay. Check git status and retry." >&2
        echo "$flock_output" >&2
        return 1
    fi

    local commit_sha
    commit_sha=$(echo "$flock_output" | tail -1)
    echo "SUCCESS: Overlay ${overlay_id} written for ${agent}. Commit: ${commit_sha}"
    echo "Canary monitoring active. Run /interspect:status to check impact."
    echo "To undo: /interspect:revert ${agent}"
    return 0
}

# Inner function called under flock. Do NOT call directly.
_interspect_write_overlay_locked() {
    set -e
    local root="$1" rel_path="$2" fullpath="$3" agent="$4"
    local overlay_id="$5" content="$6" evidence_ids="$7"
    local created_by="$8" commit_msg_file="$9" db="${10}"

    # Dedup check (F6): reject if file already exists
    if [[ -f "$fullpath" ]]; then
        echo "ERROR: Overlay ${overlay_id} already exists for ${agent}. Use a different ID." >&2
        return 1
    fi

    # Token budget check (F1: inside flock, TOCTOU-safe)
    local existing_content
    existing_content=$(_interspect_read_overlays "$agent")
    local combined="${existing_content}"
    [[ -n "$combined" ]] && combined+=$'\n\n'
    combined+="$content"

    local total_tokens
    total_tokens=$(_interspect_count_overlay_tokens "$combined")
    if (( total_tokens > 500 )); then
        local existing_tokens
        existing_tokens=$(_interspect_count_overlay_tokens "$existing_content")
        echo "ERROR: Token budget exceeded. Existing: ${existing_tokens}, new: $(_interspect_count_overlay_tokens "$content"), total: ${total_tokens} > 500." >&2
        return 1
    fi

    local created
    created=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    # Create agent overlay directory if needed
    mkdir -p "$(dirname "$fullpath")" 2>/dev/null || true

    # Atomic write: temp file → mv (quoted printf, not heredoc — no shell expansion)
    local tmpfile="${fullpath}.tmp.$$"
    trap 'rm -f "$tmpfile"' RETURN
    {
        printf '%s\n' '---'
        printf 'active: true\n'
        printf 'created: %s\n' "$created"
        printf 'created_by: %s\n' "$created_by"
        printf 'evidence_ids: %s\n' "$evidence_ids"
        printf '%s\n' '---'
        printf '%s\n' "$content"
    } > "$tmpfile"

    mv "$tmpfile" "$fullpath"

    # Git add + commit
    cd "$root"
    git add "$rel_path"
    if ! git commit --no-verify -F "$commit_msg_file"; then
        # Rollback: remove file + unstage (F11)
        rm -f "$fullpath"
        git reset HEAD -- "$rel_path" 2>/dev/null || true
        echo "ERROR: Git commit failed. Overlay not applied." >&2
        return 1
    fi

    local commit_sha
    commit_sha=$(git rev-parse HEAD)

    # DB inserts INSIDE flock (atomicity with git commit)
    local escaped_agent escaped_overlay_id
    escaped_agent=$(_interspect_sql_escape "$agent")
    escaped_overlay_id=$(_interspect_sql_escape "$overlay_id")
    local group_id="${escaped_agent}/${escaped_overlay_id}"

    local ts
    ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    local escaped_created_by
    escaped_created_by=$(_interspect_sql_escape "$created_by")

    # Modification record (F5: compound group_id)
    sqlite3 "$db" "INSERT INTO modifications (group_id, ts, tier, mod_type, target_file, commit_sha, confidence, evidence_summary, status)
        VALUES ('${group_id}', '${ts}', 'persistent', 'prompt_tuning', '$(_interspect_sql_escape "$rel_path")', '${commit_sha}', 1.0, '${escaped_created_by}', 'applied');"

    # Canary record (F5: compound group_id)
    # Disable set -e for canary setup — git commit already succeeded, so overlay
    # is active. Canary failure should warn, not abort (C-02 fix).
    set +e
    _interspect_load_confidence 2>/dev/null
    local baseline_json
    baseline_json=$(_interspect_compute_canary_baseline "$ts" "" 2>/dev/null || echo "null")

    local b_override_rate b_fp_rate b_finding_density b_window
    if [[ "$baseline_json" != "null" ]]; then
        b_override_rate=$(echo "$baseline_json" | jq -r '.override_rate')
        b_fp_rate=$(echo "$baseline_json" | jq -r '.fp_rate')
        b_finding_density=$(echo "$baseline_json" | jq -r '.finding_density')
        b_window=$(echo "$baseline_json" | jq -r '.window')
    else
        b_override_rate="NULL"
        b_fp_rate="NULL"
        b_finding_density="NULL"
        b_window="NULL"
    fi

    local expires_at
    expires_at=$(date -u -d "+${_INTERSPECT_CANARY_WINDOW_DAYS:-14} days" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
        || date -u -v+"${_INTERSPECT_CANARY_WINDOW_DAYS:-14}"d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)
    if [[ -z "$expires_at" ]]; then
        echo "ERROR: date command does not support relative dates" >&2
        return 1
    fi

    local baseline_values
    if [[ "$b_override_rate" == "NULL" ]]; then
        baseline_values="NULL, NULL, NULL, NULL"
    else
        local escaped_bwindow
        escaped_bwindow=$(_interspect_sql_escape "$b_window")
        baseline_values="${b_override_rate}, ${b_fp_rate}, ${b_finding_density}, '${escaped_bwindow}'"
    fi

    if ! sqlite3 "$db" "INSERT INTO canary (file, commit_sha, group_id, applied_at, window_uses, window_expires_at, baseline_override_rate, baseline_fp_rate, baseline_finding_density, baseline_window, status)
        VALUES ('$(_interspect_sql_escape "$rel_path")', '${commit_sha}', '${group_id}', '${ts}', ${_INTERSPECT_CANARY_WINDOW_USES:-20}, '${expires_at}', ${baseline_values}, 'active');"; then
        sqlite3 "$db" "UPDATE modifications SET status = 'applied-unmonitored' WHERE commit_sha = '${commit_sha}';" 2>/dev/null || true
        echo "WARN: Canary monitoring failed — overlay active but unmonitored." >&2
    fi

    echo "$commit_sha"
}

# ─── Overlay Disable ────────────────────────────────────────────────────────

# Disable an overlay by setting active: false in frontmatter.
# Uses awk state machine to only modify within frontmatter (F2: safe against
# body content containing "active: true").
# Args: $1=agent_name $2=overlay_id
# Returns: 0 on success, 1 on failure
_interspect_disable_overlay() {
    local agent="$1"
    local overlay_id="$2"

    if ! _interspect_validate_agent_name "$agent"; then
        return 1
    fi
    if ! _interspect_validate_overlay_id "$overlay_id"; then
        return 1
    fi

    local root
    root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    local rel_path=".clavain/interspect/overlays/${agent}/${overlay_id}.md"
    local fullpath="${root}/${rel_path}"

    if [[ ! -f "$fullpath" ]]; then
        echo "ERROR: Overlay ${overlay_id} not found for ${agent}" >&2
        return 1
    fi

    if ! _interspect_overlay_is_active "$fullpath"; then
        echo "INFO: Overlay ${overlay_id} is already inactive" >&2
        return 0
    fi

    local commit_msg_file
    commit_msg_file=$(mktemp)
    printf '[interspect] Disable overlay %s for %s\n\nReason: User requested disable via /interspect:revert\n' \
        "$overlay_id" "$agent" > "$commit_msg_file"

    local db="${_INTERSPECT_DB:-$(_interspect_db_path)}"

    local flock_output
    flock_output=$(_interspect_flock_git _interspect_disable_overlay_locked \
        "$root" "$rel_path" "$fullpath" "$agent" "$overlay_id" "$commit_msg_file" "$db")

    local exit_code=$?
    rm -f "$commit_msg_file"

    if (( exit_code != 0 )); then
        echo "ERROR: Could not disable overlay." >&2
        echo "$flock_output" >&2
        return 1
    fi

    echo "SUCCESS: Overlay ${overlay_id} disabled for ${agent}."
    return 0
}

# Inner function called under flock. Do NOT call directly.
_interspect_disable_overlay_locked() {
    set -e
    local root="$1" rel_path="$2" fullpath="$3" agent="$4"
    local overlay_id="$5" commit_msg_file="$6" db="$7"

    # Re-check active status inside flock (prevents TOCTOU re-enable — C-03)
    if ! _interspect_overlay_is_active "$fullpath"; then
        echo "INFO: Overlay ${overlay_id} already inactive (concurrent disable)" >&2
        return 0
    fi

    # Toggle active: true → active: false using awk state machine (F2)
    # Only modifies within frontmatter (between first and second ---)
    local tmpfile="${fullpath}.tmp.$$"
    trap 'rm -f "$tmpfile"' RETURN
    awk '
        /^---$/ { delim++ }
        delim == 1 && /^active: true$/ { $0 = "active: false" }
        { print }
    ' "$fullpath" > "$tmpfile"

    mv "$tmpfile" "$fullpath"

    cd "$root"
    git add "$rel_path"
    if ! git commit --no-verify -F "$commit_msg_file"; then
        # Rollback: restore file from git (F11)
        git reset HEAD -- "$rel_path" 2>/dev/null || true
        git restore "$rel_path" 2>/dev/null || git checkout -- "$rel_path" 2>/dev/null || true
        echo "ERROR: Git commit failed. Overlay not disabled." >&2
        return 1
    fi

    # Update DB records (F5: compound group_id)
    local escaped_agent escaped_overlay_id
    escaped_agent=$(_interspect_sql_escape "$agent")
    escaped_overlay_id=$(_interspect_sql_escape "$overlay_id")
    local group_id="${escaped_agent}/${escaped_overlay_id}"

    sqlite3 "$db" "UPDATE modifications SET status = 'reverted' WHERE group_id = '${group_id}' AND status = 'applied';" 2>/dev/null || true
    sqlite3 "$db" "UPDATE canary SET status = 'reverted' WHERE group_id = '${group_id}' AND status = 'active';" 2>/dev/null || true
}
