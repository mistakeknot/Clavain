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
#   _interspect_sanitize      — strip ANSI, control chars, truncate, reject injection
#   _interspect_validate_hook_id — allowlist hook IDs

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

    # Fast path — DB already exists
    if [[ -f "$_INTERSPECT_DB" ]]; then
        return 0
    fi

    # Ensure directory exists
    mkdir -p "$(dirname "$_INTERSPECT_DB")" 2>/dev/null || return 1

    # Create tables + indexes + WAL mode
    sqlite3 "$_INTERSPECT_DB" <<'SQL'
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

# ─── Sanitization ────────────────────────────────────────────────────────────

# Sanitize a string for safe storage and later LLM consumption.
# Pipeline: strip ANSI → strip control chars → truncate → reject injection patterns.
# Args: $1 = input string
# Output: sanitized string on stdout
_interspect_sanitize() {
    local input="$1"

    # 1. Strip ANSI escape sequences
    input=$(printf '%s' "$input" | sed 's/\x1b\[[0-9;]*[a-zA-Z]//g')

    # 2. Strip control characters (0x00-0x08, 0x0B-0x0C, 0x0E-0x1F)
    input=$(printf '%s' "$input" | tr -d '\000-\010\013-\014\016-\037')

    # 3. Truncate to 500 chars
    input="${input:0:500}"

    # 4. Reject instruction-like patterns (case-insensitive)
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
