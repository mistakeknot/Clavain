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
MIGRATE
        return 0
    fi

    # Ensure directory exists
    mkdir -p "$(dirname "$_INTERSPECT_DB")" 2>/dev/null || return 1

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
    project TEXT
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
SQL
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

    if [[ -f "$conf" ]]; then
        _INTERSPECT_MIN_SESSIONS=$(jq -r '.min_sessions // 3' "$conf")
        _INTERSPECT_MIN_DIVERSITY=$(jq -r '.min_diversity // 2' "$conf")
        _INTERSPECT_MIN_EVENTS=$(jq -r '.min_events // 5' "$conf")
        _INTERSPECT_MIN_AGENT_WRONG_PCT=$(jq -r '.min_agent_wrong_pct // 80' "$conf")
    fi
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

    sqlite3 -separator '|' "$db" "
        SELECT source, event, COALESCE(override_reason,''),
               COUNT(*) as ec, COUNT(DISTINCT session_id) as sc,
               COUNT(DISTINCT project) as pc
        FROM evidence GROUP BY source, event, override_reason
        HAVING COUNT(*) >= 2 ORDER BY ec DESC;
    " | while IFS='|' read -r src evt reason ec sc pc; do
        local cls
        cls=$(_interspect_classify_pattern "$ec" "$sc" "$pc")
        echo "${src}|${evt}|${reason}|${ec}|${sc}|${pc}|${cls}"
    done
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

    # Validate agent name format
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

    # Get agent_wrong percentage
    local total wrong pct
    total=$(sqlite3 "$db" "SELECT COUNT(*) FROM evidence WHERE source = '${escaped}' AND event = 'override';")
    wrong=$(sqlite3 "$db" "SELECT COUNT(*) FROM evidence WHERE source = '${escaped}' AND event = 'override' AND override_reason = 'agent_wrong';")

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

    if ! jq -e '.' "$fullpath" >/dev/null 2>&1; then
        echo "WARN: ${filepath} is malformed JSON" >&2
        echo '{"version":1,"overrides":[]}'
        return 1
    fi

    jq '.' "$fullpath"
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

    # --- Pre-flock validation (fast-fail) ---

    # Validate agent name format (prevents injection + catches typos)
    if ! _interspect_validate_agent_name "$agent"; then
        return 1
    fi

    # Validate evidence_ids is a JSON array
    if ! echo "$evidence_ids" | jq -e 'type == "array"' >/dev/null 2>&1; then
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
        "$evidence_ids" "$created_by" "$commit_msg_file" "$db")

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
    local commit_msg_file="$8" db="$9"

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

    # 3. Build new override using jq --arg (no shell interpolation)
    local new_override
    new_override=$(jq -n \
        --arg agent "$agent" \
        --arg action "exclude" \
        --arg reason "$reason" \
        --argjson evidence_ids "$evidence_ids" \
        --arg created "$created" \
        --arg created_by "$created_by" \
        '{agent:$agent,action:$action,reason:$reason,evidence_ids:$evidence_ids,created:$created,created_by:$created_by}')

    # 4. Merge (unique_by deduplicates, last write wins for metadata)
    local merged
    merged=$(echo "$current" | jq --argjson override "$new_override" \
        '.overrides = (.overrides + [$override] | unique_by(.agent))')

    # 5. Atomic write (temp + rename)
    mkdir -p "$(dirname "$fullpath")" 2>/dev/null || true
    local tmpfile="${fullpath}.tmp.$$"
    echo "$merged" | jq '.' > "$tmpfile"

    if ! jq -e '.' "$tmpfile" >/dev/null 2>&1; then
        rm -f "$tmpfile"
        echo "ERROR: Write produced invalid JSON, aborted" >&2
        return 1
    fi
    mv "$tmpfile" "$fullpath"

    # 6. Git add + commit (using -F for commit message — no injection)
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

    # 7. DB inserts INSIDE flock (atomicity with git commit)
    local escaped_agent escaped_reason
    escaped_agent=$(_interspect_sql_escape "$agent")
    escaped_reason=$(_interspect_sql_escape "$reason")

    # Only insert modification + canary for genuinely NEW overrides
    if (( is_new == 1 )); then
        local ts
        ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)

        # Modification record
        sqlite3 "$db" "INSERT INTO modifications (group_id, ts, tier, mod_type, target_file, commit_sha, confidence, evidence_summary, status)
            VALUES ('${escaped_agent}', '${ts}', 'persistent', 'routing', '${filepath}', '${commit_sha}', 1.0, '${escaped_reason}', 'applied');"

        # Canary record
        local expires_at
        expires_at=$(date -u -d "+14 days" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
            || date -u -v+14d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)
        if [[ -z "$expires_at" ]]; then
            echo "ERROR: date command does not support relative dates" >&2
            return 1
        fi

        if ! sqlite3 "$db" "INSERT INTO canary (file, commit_sha, group_id, applied_at, window_uses, window_expires_at, status)
            VALUES ('${filepath}', '${commit_sha}', '${escaped_agent}', '${ts}', 20, '${expires_at}', 'active');"; then
            # Canary failure is non-fatal but flagged in DB
            sqlite3 "$db" "UPDATE modifications SET status = 'applied-unmonitored' WHERE commit_sha = '${commit_sha}';" 2>/dev/null || true
            echo "WARN: Canary monitoring failed — override active but unmonitored." >&2
        fi
    else
        echo "INFO: Metadata updated for existing override. No new canary." >&2
    fi

    # 8. Output commit SHA (last line, captured by caller)
    echo "$commit_sha"
}

# ─── Git Operation Serialization ────────────────────────────────────────────

_INTERSPECT_GIT_LOCK_TIMEOUT=30

# Execute a command under the interspect git lock.
# Usage: _interspect_flock_git git add <file>
# Usage: _interspect_flock_git git commit -m "[interspect] ..."
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

    # 1. Strip ANSI escape sequences
    input=$(printf '%s' "$input" | sed 's/\x1b\[[0-9;]*[a-zA-Z]//g')

    # 2. Strip control characters (0x00-0x08, 0x0B-0x0C, 0x0E-0x1F)
    input=$(printf '%s' "$input" | tr -d '\000-\010\013-\014\016-\037')

    # 3. Truncate to 500 chars (prevents DoS from massive strings)
    input="${input:0:500}"

    # 4. Redact secrets (after truncate to limit scan surface)
    input=$(_interspect_redact_secrets "$input")

    # 5. Reject instruction-like patterns (case-insensitive)
    local lower="${input,,}"
    if [[ "$lower" == *"<system>"* ]] || \
       [[ "$lower" == *"<instructions>"* ]] || \
       [[ "$lower" == *"ignore previous"* ]] || \
       [[ "$lower" == *"you are now"* ]] || \
       [[ "$lower" == *"disregard"* ]] || \
       [[ "$lower" == *"system:"* ]]; then
        printf '%s' "[REDACTED]"
        return 0
    fi

    printf '%s' "$input"
}

# Validate hook ID against allowlist.
# Args: $1 = hook_id
# Returns: 0 if valid, 1 if invalid
_interspect_validate_hook_id() {
    local hook_id="$1"
    case "$hook_id" in
        interspect-evidence|interspect-session-start|interspect-session-end|interspect-correction)
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
