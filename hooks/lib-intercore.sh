# lib-intercore.sh — Bash wrappers for intercore CLI
# Version: 0.1.0 (source: infra/intercore/lib-intercore.sh)
# Re-copy to hub/clavain/hooks/ on major intercore updates; version is pinned to plugin release.
# This file is SOURCED by hooks. Do NOT use set -e here — it would exit
# the parent shell on any failure.
# Source in hooks: source "$(dirname "$0")/lib-intercore.sh"
# shellcheck shell=bash

INTERCORE_WRAPPER_VERSION="0.1.0"

# Shared sentinel for Stop hook anti-cascade protocol.
# All Stop hooks MUST check this sentinel before doing work to prevent
# multiple Stop hooks from firing in the same stop cycle.
INTERCORE_STOP_DEDUP_SENTINEL="stop"

INTERCORE_BIN=""

intercore_available() {
    # Returns 0 (available) or 1 (unavailable).
    # "binary not found" → return 1 (wrappers handle fail-safe individually)
    # "binary found but DB broken" → return 1, log error to stderr
    if [[ -n "$INTERCORE_BIN" ]]; then return 0; fi
    INTERCORE_BIN=$(command -v ic 2>/dev/null || command -v intercore 2>/dev/null)
    if [[ -z "$INTERCORE_BIN" ]]; then
        return 1
    fi
    # Binary exists — check health
    if ! "$INTERCORE_BIN" health >/dev/null 2>&1; then
        printf 'ic: DB health check failed — run '\''ic init'\'' or '\''ic health'\''\n' >&2
        INTERCORE_BIN=""
        return 1
    fi
    return 0
}

intercore_state_set() {
    local key="$1" scope_id="$2" json="$3"
    if ! intercore_available; then return 0; fi
    printf '%s\n' "$json" | "$INTERCORE_BIN" state set "$key" "$scope_id" || return 0
}

intercore_state_get() {
    local key="$1" scope_id="$2"
    if ! intercore_available; then printf ''; return; fi
    "$INTERCORE_BIN" state get "$key" "$scope_id" 2>/dev/null || printf ''
}

intercore_sentinel_check() {
    local name="$1" scope_id="$2" interval="$3"
    if ! intercore_available; then return 0; fi
    "$INTERCORE_BIN" sentinel check "$name" "$scope_id" --interval="$interval" >/dev/null
}

# intercore_sentinel_check_or_legacy — try ic sentinel, fall back to temp file.
# Args: $1=name, $2=scope_id, $3=interval_sec, $4=legacy_file (temp file path)
# Returns: 0 if allowed (proceed), 1 if throttled (skip)
# Side effect: touches legacy file as fallback when ic unavailable or erroring
intercore_sentinel_check_or_legacy() {
    local name="$1" scope_id="$2" interval="$3" legacy_file="$4"
    if intercore_available; then
        # Suppress stdout (allowed/throttled message), preserve stderr (errors)
        # Exit 0 = allowed, 1 = throttled, 2+ = error → fall through to legacy
        local rc=0
        "$INTERCORE_BIN" sentinel check "$name" "$scope_id" --interval="$interval" >/dev/null || rc=$?
        if [[ $rc -eq 0 ]]; then
            return 0  # allowed
        elif [[ $rc -eq 1 ]]; then
            return 1  # throttled
        fi
        # Exit code 2+ = DB error — fall through to legacy path
        # (error message already written to stderr by ic)
    fi
    # Fallback: temp file check (known TOCTOU race — accepted for legacy compat)
    if [[ -f "$legacy_file" ]]; then
        if [[ "$interval" -eq 0 ]]; then
            return 1  # once-per-session: file exists = throttled
        fi
        local file_mtime now
        file_mtime=$(stat -c %Y "$legacy_file" 2>/dev/null || stat -f %m "$legacy_file" 2>/dev/null || echo 0)
        now=$(date +%s)
        if [[ $((now - file_mtime)) -lt "$interval" ]]; then
            return 1  # within throttle window
        fi
    fi
    touch "$legacy_file"
    return 0
}

# intercore_check_or_die — Convenience wrapper: check sentinel, exit 0 if throttled.
# Args: $1=name, $2=scope_id, $3=interval, $4=legacy_path
# Returns: 0 if allowed. Exits the calling script (exit 0) if throttled.
# This eliminates the per-hook boilerplate of type-check + inline fallback.
intercore_check_or_die() {
    local name="$1" scope_id="$2" interval="$3" legacy_path="$4"
    if type intercore_sentinel_check_or_legacy &>/dev/null; then
        intercore_sentinel_check_or_legacy "$name" "$scope_id" "$interval" "$legacy_path" || exit 0
        return 0
    fi
    # Inline fallback (wrapper unavailable — lib-intercore.sh failed to source)
    if [[ -f "$legacy_path" ]]; then
        if [[ "$interval" -eq 0 ]]; then
            exit 0
        fi
        local file_mtime now
        file_mtime=$(stat -c %Y "$legacy_path" 2>/dev/null || stat -f %m "$legacy_path" 2>/dev/null || echo 0)
        now=$(date +%s)
        if [[ $((now - file_mtime)) -lt "$interval" ]]; then
            exit 0
        fi
    fi
    touch "$legacy_path"
    return 0
}

# intercore_sentinel_reset_or_legacy — try ic sentinel reset, fall back to rm.
# Args: $1=name, $2=scope_id, $3=legacy_glob (temp file glob pattern)
intercore_sentinel_reset_or_legacy() {
    local name="$1" scope_id="$2" legacy_glob="$3"
    if intercore_available; then
        "$INTERCORE_BIN" sentinel reset "$name" "$scope_id" >/dev/null 2>&1 || true
        return 0
    fi
    # Fallback: rm legacy files
    # shellcheck disable=SC2086
    rm -f $legacy_glob 2>/dev/null || true
}

# intercore_sentinel_reset_all — reset all scopes for a given sentinel name.
# Args: $1=name, $2=legacy_glob (temp file glob pattern for fallback)
# NOTE: Has list-then-reset TOCTOU — acceptable for cache invalidation,
# NOT for mutual-exclusion sentinels. Use ic sentinel reset-all when added.
intercore_sentinel_reset_all() {
    local name="$1" legacy_glob="$2"
    if intercore_available; then
        local _name scope _fired
        while IFS=$'\t' read -r _name scope _fired; do
            [[ "$_name" == "$name" ]] || continue
            "$INTERCORE_BIN" sentinel reset "$name" "$scope" >/dev/null 2>&1 || true
        done < <("$INTERCORE_BIN" sentinel list 2>/dev/null || true)
        return 0
    fi
    # Fallback: rm legacy files
    # shellcheck disable=SC2086
    rm -f $legacy_glob 2>/dev/null || true
}

# intercore_state_delete_all — delete all scopes for a given state key.
# Args: $1=key, $2=legacy_glob (temp file glob pattern for fallback)
# Use for cache invalidation (not throttle sentinels).
intercore_state_delete_all() {
    local key="$1" legacy_glob="$2"
    if intercore_available; then
        local scope
        while read -r scope; do
            "$INTERCORE_BIN" state delete "$key" "$scope" 2>/dev/null || true
        done < <("$INTERCORE_BIN" state list "$key" 2>/dev/null || true)
        return 0
    fi
    # Fallback: rm legacy files
    # shellcheck disable=SC2086
    rm -f $legacy_glob 2>/dev/null || true
}

# intercore_cleanup_stale — prune old sentinels (replaces find -mmin -delete).
# Called ONCE per stop cycle from session-handoff.sh only — not from every hook.
intercore_cleanup_stale() {
    if intercore_available; then
        "$INTERCORE_BIN" sentinel prune --older-than=1h >/dev/null 2>&1 || true
        return 0
    fi
    # Fallback: clean legacy temp files
    find /tmp -maxdepth 1 \( -name 'clavain-stop-*' -o -name 'clavain-drift-last-*' -o -name 'clavain-compound-last-*' \) -mmin +60 -delete 2>/dev/null || true
}
