#!/usr/bin/env bash
# lib-intercore.sh — Bash wrappers for intercore CLI
# shellcheck shell=bash
# shellcheck: sourced library — no set -euo pipefail (would alter caller's error policy)
# Version: 0.1.0 (source: infra/intercore/lib-intercore.sh)
# Re-copy to os/clavain/hooks/ on major intercore updates; version is pinned to plugin release.
# Source in hooks: source "$(dirname "$0")/lib-intercore.sh"

INTERCORE_WRAPPER_VERSION="1.1.0"

# Shared sentinel for Stop hook anti-cascade protocol.
# All Stop hooks MUST check this sentinel before doing work to prevent
# multiple Stop hooks from firing in the same stop cycle.
INTERCORE_STOP_DEDUP_SENTINEL="stop"

INTERCORE_BIN=""
INTERCORE_WARNED=false

# Host-local migration posture, outside the versioned plugin cache. Presence
# means local automatic consumers must not open shared state, even when a
# binary was cached earlier in the shell. Removing it is an explicit rebind.
intercore_remote_authority() {
    [[ -e "$HOME/.config/clavain/remote-shared-state" || -L "$HOME/.config/clavain/remote-shared-state" ]]
}

# Trace context: IC_TRACE_ID and IC_SPAN_ID are inherited from the environment.
# They are set by session-start.sh and flow through to all ic CLI calls
# via process environment inheritance. The ic binary reads them directly from env.

intercore_available() {
    if intercore_remote_authority; then
        if [[ "$INTERCORE_WARNED" != true ]]; then
            printf 'ic: shared-state authority is remote; local automatic actions are disabled\n' >&2
            INTERCORE_WARNED=true
        fi
        return 1
    fi
    # Returns 0 (available) or 1 (unavailable).
    # "binary not found" → return 1 (wrappers handle fail-safe individually)
    # "binary found but DB broken" → return 1, log error to stderr
    if [[ -n "$INTERCORE_BIN" ]]; then return 0; fi
    INTERCORE_BIN=$(command -v ic 2>/dev/null || command -v intercore 2>/dev/null)
    if [[ -z "$INTERCORE_BIN" ]]; then
        if [[ "$INTERCORE_WARNED" != true ]]; then
            printf 'ic: not found — run install.sh or /clavain:setup\n' >&2
            INTERCORE_WARNED=true
        fi
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
    if ! intercore_available; then return 1; fi
    printf '%s\n' "$json" | "$INTERCORE_BIN" state set "$key" "$scope_id" || return 1
}

intercore_state_get() {
    local key="$1" scope_id="$2"
    # Preserve ic's three states: 0=value, 1=absent, 2+=unavailable/error.
    if ! intercore_available; then return 2; fi
    "$INTERCORE_BIN" state get "$key" "$scope_id" 2>/dev/null
}

intercore_sentinel_check() {
    local name="$1" scope_id="$2" interval="$3"
    if ! intercore_available; then return 1; fi
    "$INTERCORE_BIN" sentinel check "$name" "$scope_id" --interval="$interval" >/dev/null
}

# intercore_sentinel_check_or_legacy — ic sentinel check (legacy temp file fallback removed).
# Args: $1=name, $2=scope_id, $3=interval_sec, $4=legacy_file (IGNORED, kept for caller compat)
# Returns: 0 if allowed (proceed), 1 if throttled (skip)
# A remote-authority marker always skips the action. Without a marker, legacy
# local unavailable behavior remains fail-open for advisory callers.
intercore_sentinel_check_or_legacy() {
    local name="$1" scope_id="$2" interval="$3"
    if intercore_remote_authority; then return 1; fi
    # $4 (legacy_file) is accepted but ignored — callers may still pass it during transition
    if ! intercore_available; then
        return 0  # fail-open: no ic = allow (hooks skip gracefully)
    fi
    local rc=0
    "$INTERCORE_BIN" sentinel check "$name" "$scope_id" --interval="$interval" >/dev/null || rc=$?
    if [[ $rc -eq 0 ]]; then
        return 0  # allowed
    elif [[ $rc -eq 1 ]]; then
        return 1  # throttled
    fi
    # Exit code 2+ = DB error — fail-open
    return 0
}

# intercore_check_or_die — Convenience wrapper: check sentinel, exit 0 if throttled.
# Args: $1=name, $2=scope_id, $3=interval, $4=legacy_path (IGNORED, kept for caller compat)
# Returns: 0 if allowed. Exits the calling script (exit 0) if throttled.
# NOTE: ic is now required. If unavailable, returns 0 (fail-open: allow the action).
intercore_check_or_die() {
    local name="$1" scope_id="$2" interval="$3"
    # $4 (legacy_path) is accepted but ignored — callers may still pass it during transition
    if type intercore_sentinel_check_or_legacy &>/dev/null; then
        intercore_sentinel_check_or_legacy "$name" "$scope_id" "$interval" || exit 0
        return 0
    fi
    # lib-intercore.sh failed to source — fail-open (no sentinel = allow)
    return 0
}

# intercore_sentinel_reset_or_legacy — ic sentinel reset (legacy temp file fallback removed).
# Args: $1=name, $2=scope_id, $3=legacy_glob (IGNORED, kept for caller compat)
intercore_sentinel_reset_or_legacy() {
    local name="$1" scope_id="$2"
    # $3 (legacy_glob) is accepted but ignored
    if ! intercore_available; then return 0; fi
    "$INTERCORE_BIN" sentinel reset "$name" "$scope_id" >/dev/null 2>&1 || true
}

# intercore_sentinel_reset_all — reset all scopes for a given sentinel name.
# Args: $1=name, $2=legacy_glob (IGNORED, kept for caller compat)
# NOTE: Has list-then-reset TOCTOU — acceptable for cache invalidation,
# NOT for mutual-exclusion sentinels. Use ic sentinel reset-all when added.
intercore_sentinel_reset_all() {
    local name="$1"
    # $2 (legacy_glob) is accepted but ignored
    if ! intercore_available; then return 0; fi
    local _name scope _fired
    while IFS=$'\t' read -r _name scope _fired; do
        [[ "$_name" == "$name" ]] || continue
        "$INTERCORE_BIN" sentinel reset "$name" "$scope" >/dev/null 2>&1 || true
    done < <("$INTERCORE_BIN" sentinel list 2>/dev/null || true)
}

# intercore_state_delete_all — delete all scopes for a given state key.
# Args: $1=key, $2=legacy_glob (IGNORED, kept for caller compat)
# Use for cache invalidation (not throttle sentinels).
intercore_state_delete_all() {
    local key="$1"
    # $2 (legacy_glob) is accepted but ignored
    if ! intercore_available; then return 0; fi
    local scope
    while read -r scope; do
        "$INTERCORE_BIN" state delete "$key" "$scope" 2>/dev/null || true
    done < <("$INTERCORE_BIN" state list "$key" 2>/dev/null || true)
}

# intercore_cleanup_stale — prune old sentinels.
# Called ONCE per stop cycle from session-handoff.sh only — not from every hook.
intercore_cleanup_stale() {
    if ! intercore_available; then return 0; fi
    "$INTERCORE_BIN" sentinel prune --older-than=1h >/dev/null 2>&1 || true
}

# --- Dispatch wrappers ---

# intercore_dispatch_spawn — Spawn an agent dispatch.
# Args: $1=type, $2=project_dir, $3=prompt_file, $4=output (optional), $5=name (optional)
# Prints: dispatch ID to stdout (for capture by caller)
# Returns: 0 on success, 1 on failure
intercore_dispatch_spawn() {
    local type="$1" project="$2" prompt_file="$3" output="${4:-}" name="${5:-codex}"
    if ! intercore_available; then return 1; fi
    local args=(dispatch spawn --type="$type" --project="$project" --prompt-file="$prompt_file" --name="$name")
    if [[ -n "$output" ]]; then
        args+=(--output="$output")
    fi
    "$INTERCORE_BIN" "${args[@]}"
}

# intercore_dispatch_status — Get dispatch status as JSON.
# Args: $1=dispatch_id
# Prints: JSON status to stdout
intercore_dispatch_status() {
    local id="$1"
    if ! intercore_available; then return 1; fi
    "$INTERCORE_BIN" dispatch status "$id" --json
}

# intercore_dispatch_wait — Wait for dispatch completion.
# Args: $1=dispatch_id, $2=timeout (optional, e.g. "5m")
# Returns: 0 if completed successfully, 1 if failed/timeout
intercore_dispatch_wait() {
    local id="$1" timeout="${2:-}"
    if ! intercore_available; then return 1; fi
    local args=(dispatch wait "$id")
    if [[ -n "$timeout" ]]; then
        args+=(--timeout="$timeout")
    fi
    "$INTERCORE_BIN" "${args[@]}" >/dev/null
}

# intercore_dispatch_list_active — List active dispatches.
# Prints: tab-separated list (id, status, type, name) to stdout
intercore_dispatch_list_active() {
    if intercore_remote_authority; then return 2; fi
    if ! intercore_available; then return 0; fi
    "$INTERCORE_BIN" dispatch list --active
}

# intercore_dispatch_kill — Kill a running dispatch.
# Args: $1=dispatch_id
intercore_dispatch_kill() {
    local id="$1"
    if ! intercore_available; then return 0; fi
    "$INTERCORE_BIN" dispatch kill "$id" >/dev/null 2>&1 || true
}

# --- Run wrappers ---

# intercore_run_current — Get the active run ID for a project.
# Args: $1=project_dir (optional, defaults to CWD)
# Prints: run ID to stdout
# Returns: 0 if found, 1 if no active run or ic unavailable
intercore_run_current() {
    local project="${1:-$(pwd)}"
    if ! intercore_available; then return 1; fi
    "$INTERCORE_BIN" run current --project="$project" 2>/dev/null
}

# intercore_run_phase — Get the current phase of a run.
# Args: $1=run_id
# Prints: phase name to stdout
# Returns: 0 on success, 1 on failure
intercore_run_phase() {
    local id="$1"
    if ! intercore_available; then return 1; fi
    "$INTERCORE_BIN" run phase "$id" 2>/dev/null
}

# intercore_run_agent_add — Add an agent to a run.
# Args: $1=run_id, $2=agent_type, $3=name (optional), $4=dispatch_id (optional)
# Prints: agent ID to stdout
# Returns: 0 on success, 1 on failure
intercore_run_agent_add() {
    local run_id="$1" agent_type="$2" name="${3:-}" dispatch_id="${4:-}"
    if ! intercore_available; then return 1; fi
    local args=(run agent add "$run_id" --type="$agent_type")
    if [[ -n "$name" ]]; then
        args+=(--name="$name")
    fi
    if [[ -n "$dispatch_id" ]]; then
        args+=(--dispatch-id="$dispatch_id")
    fi
    "$INTERCORE_BIN" "${args[@]}" 2>/dev/null
}

# intercore_run_artifact_add — Add an artifact to a run.
# Args: $1=run_id, $2=phase, $3=path, $4=type (optional, defaults to 'file')
# Prints: artifact ID to stdout
# Returns: 0 on success, 1 on failure
intercore_run_artifact_add() {
    local run_id="$1" artifact_phase="$2" artifact_path="$3" artifact_type="${4:-file}"
    if ! intercore_available; then return 1; fi
    "$INTERCORE_BIN" run artifact add "$run_id" --phase="$artifact_phase" --path="$artifact_path" --type="$artifact_type" 2>/dev/null
}

# intercore_run_create — Create a new run.
# Args: $1=project, $2=goal, $3=phases_json (optional), $4=scope_id (optional),
#       $5=complexity (optional, default 3), $6=token_budget (optional), $7=actions_json (optional)
# Prints: run ID to stdout
# Returns: 0 on success, 1 on failure
intercore_run_create() {
    local project="$1" goal="$2" phases_json="${3:-}" scope_id="${4:-}"
    local complexity="${5:-3}" token_budget="${6:-}" actions_json="${7:-}"
    if ! intercore_available; then return 1; fi
    local args=(run create --project="$project" --goal="$goal" --complexity="$complexity")
    [[ -n "$phases_json" ]] && args+=(--phases="$phases_json")
    [[ -n "$scope_id" ]] && args+=(--scope-id="$scope_id")
    [[ -n "$token_budget" ]] && args+=(--token-budget="$token_budget")
    [[ -n "$actions_json" ]] && args+=(--actions="$actions_json")
    "$INTERCORE_BIN" "${args[@]}" ${INTERCORE_DB:+--db="$INTERCORE_DB"} 2>/dev/null
}

# intercore_run_list — List runs. Passes all args through to ic run list.
# Always outputs JSON (for jq parsing by lib-sprint.sh).
# Args: variadic (e.g. "--active", "--scope=<s>")
# Prints: JSON array to stdout
# Returns: 0 on success, 1 on failure
intercore_run_list() {
    if ! intercore_available; then return 1; fi
    "$INTERCORE_BIN" --json run list "$@" ${INTERCORE_DB:+--db="$INTERCORE_DB"} 2>/dev/null
}

# intercore_run_status — Get full run details as JSON.
# Args: $1=run_id
# Prints: JSON object to stdout
# Returns: 0 on success, 1 on failure
intercore_run_status() {
    local run_id="$1"
    if ! intercore_available; then return 1; fi
    "$INTERCORE_BIN" --json run status "$run_id" ${INTERCORE_DB:+--db="$INTERCORE_DB"} 2>/dev/null
}

# intercore_run_agent_list — List agents for a run as JSON.
# Args: $1=run_id
# Prints: JSON array to stdout
# Returns: 0 on success, 1 on failure
intercore_run_agent_list() {
    local run_id="$1"
    if ! intercore_available; then return 1; fi
    "$INTERCORE_BIN" --json run agent list "$run_id" ${INTERCORE_DB:+--db="$INTERCORE_DB"} 2>/dev/null
}

# intercore_run_agent_update — Update an agent's status.
# Args: $1=agent_id, $2=status (active|completed|failed)
# Returns: 0 on success, 1 on failure
intercore_run_agent_update() {
    local agent_id="$1" status="$2"
    if ! intercore_available; then return 1; fi
    "$INTERCORE_BIN" run agent update "$agent_id" --status="$status" ${INTERCORE_DB:+--db="$INTERCORE_DB"} 2>/dev/null
}

# --- Gate wrappers ---

# intercore_gate_check — Dry-run gate evaluation for the next transition.
# Args: $1=run_id
# Returns: 0=pass, 1=fail, 2+=error/fallthrough
intercore_gate_check() {
    local run_id="$1"
    if intercore_remote_authority; then return 2; fi
    if intercore_available; then
        local rc=0
        "$INTERCORE_BIN" gate check "$run_id" ${INTERCORE_DB:+--db="$INTERCORE_DB"} >/dev/null || rc=$?
        return $rc
    fi
    return 0  # fail-open: no intercore = gates disabled
}

# intercore_gate_override — Force advance past a failing gate.
# Args: $1=run_id, $2=reason
# Returns: 0=success, 1=terminal, 2+=error
intercore_gate_override() {
    local run_id="$1" reason="$2"
    if intercore_remote_authority; then return 2; fi
    if intercore_available; then
        "$INTERCORE_BIN" gate override "$run_id" --reason="$reason" \
            ${INTERCORE_DB:+--db="$INTERCORE_DB"} || return $?
        return 0
    fi
    return 0  # fail-open
}

# --- Lock wrappers ---

# intercore_lock_available — Check if ic binary exists (no DB health check).
# Lock commands are filesystem-only — they work even when the DB is broken.
# This avoids the intercore_available() DB health check that would silently
# force all lock operations into the dumber bash fallback.
# INTERCORE_LOCK_FALLBACK_DIR overrides the base directory of the bash fallback
# only (tests use it to stay out of the shared production namespace); ic keeps
# its own default.
INTERCORE_LOCK_BIN=""

# --- Fallback lock helpers ---------------------------------------------------

# Tokens of the locks this shell holds, one "<lock_dir>=<token>" per line.
_INTERCORE_LOCK_TOKENS=""

_intercore_lock_token_get() {
    local line
    while IFS= read -r line; do
        if [[ "${line%%=*}" == "$1" ]]; then printf '%s' "${line#*=}"; return 0; fi
    done <<< "$_INTERCORE_LOCK_TOKENS"
    return 0
}

_intercore_lock_token_drop() {
    local line out=""
    while IFS= read -r line; do
        [[ -n "$line" && "${line%%=*}" != "$1" ]] && out+="${line}"$'\n'
    done <<< "$_INTERCORE_LOCK_TOKENS"
    _INTERCORE_LOCK_TOKENS="$out"
}

_intercore_lock_token_set() {
    _intercore_lock_token_drop "$1"
    _INTERCORE_LOCK_TOKENS+="$1=$2"$'\n'
}

# _intercore_lock_publish <dest> <content>: create <dest> holding <content>, all
# at once, and fail if <dest> exists. The content is written to a unique pending
# file in the same directory first, then linked into place with link(2) (plain
# ln, never -f), which is atomic and refuses to replace an existing name. A
# reader or cleaner therefore never sees a half-written record, and the claim
# does not depend on mkdir.
_intercore_lock_publish() {
    local dest="$1" content="$2" tmp
    tmp="${dest%/*}/.pending.$$.$(date +%s%N 2>/dev/null).${RANDOM}${RANDOM}"
    if ! ( set -C; printf '%s\n' "$content" > "$tmp" ) 2>/dev/null; then
        rm -f "$tmp" 2>/dev/null || true
        return 1
    fi
    if ln "$tmp" "$dest" 2>/dev/null; then
        rm -f "$tmp" 2>/dev/null || true
        return 0
    fi
    rm -f "$tmp" 2>/dev/null || true
    return 1
}

_intercore_pid_alive() {
    [[ "$1" =~ ^[0-9]+$ && "$1" -gt 0 ]] || return 1
    kill -0 "$1" 2>/dev/null || ps -p "$1" >/dev/null 2>&1
}

# A cleaner claim or pending file older than this many seconds belongs to
# nobody. The same bound as ic's (staleClaimAge in internal/lock/lock.go).
_INTERCORE_LOCK_STALE_CLAIM_SECS=30

# _intercore_lock_slurp <file>: set _ICL_BYTES to the exact bytes of <file>
# (trailing newlines included). Fails if the file cannot be read.
_intercore_lock_slurp() {
    local _v
    _v=$(cat -- "$1" 2>/dev/null && printf x) || return 1
    _ICL_BYTES="${_v%x}"
}

# _intercore_lock_mtime_age <file>: print the age of <file> in seconds.
_intercore_lock_mtime_age() {
    local m
    m=$(stat -c %Y -- "$1" 2>/dev/null || stat -f %m -- "$1" 2>/dev/null) || return 1
    printf '%d' $(( $(date +%s) - m ))
}

# _intercore_lock_json_field <record> <pid|host|created|token|owner>: print one
# field of a record held in a string.
_intercore_lock_json_field() {
    case "$2" in
        pid|created) printf '%s' "$1" | sed -n "s/.*\"$2\":[[:space:]]*\([0-9][0-9]*\).*/\1/p" | head -n1 ;;
        *) printf '%s' "$1" | sed -n "s/.*\"$2\":[[:space:]]*\"\([^\"]*\)\".*/\1/p" | head -n1 ;;
    esac
}

# _intercore_lock_remove_exactly <path> <bytes>: remove <path> only if it holds
# exactly <bytes>. The file is renamed to a unique name first (atomic: one
# caller wins), inspected, and linked back if it is not the file the caller
# meant to remove, so a successor's file is not destroyed by a delayed caller.
_intercore_lock_remove_exactly() {
    local path="$1" want="$2" tmp
    tmp="${path}.stale.$$.$(date +%s%N 2>/dev/null).${RANDOM}${RANDOM}"
    mv -- "$path" "$tmp" 2>/dev/null || return 1
    if _intercore_lock_slurp "$tmp" && [[ "$_ICL_BYTES" == "$want" ]]; then
        rm -f -- "$tmp" 2>/dev/null || true
        return 0
    fi
    ln -- "$tmp" "$path" 2>/dev/null || true   # EEXIST: a newer file already took its place
    rm -f -- "$tmp" 2>/dev/null || true
    return 1
}

# _intercore_lock_claim_abandoned <cleaner.json> <bytes>: true if the claim
# holding <bytes> belongs to a cleaner that is gone: older than the stale bound,
# or on this host with a dead pid. An unparsable claim is judged by file age.
# Hosts are compared as `uname -n` prints them, which is what ic records.
_intercore_lock_claim_abandoned() {
    local cf="$1" cur="$2" cpid chost created age
    cpid=$(_intercore_lock_json_field "$cur" pid)
    created=$(_intercore_lock_json_field "$cur" created)
    if [[ -z "$cpid" || -z "$created" ]]; then
        age=$(_intercore_lock_mtime_age "$cf") || return 1
        (( age > _INTERCORE_LOCK_STALE_CLAIM_SECS ))
        return
    fi
    if (( $(date +%s) - created > _INTERCORE_LOCK_STALE_CLAIM_SECS )); then return 0; fi
    chost=$(_intercore_lock_json_field "$cur" host)
    if [[ -z "$chost" || "$chost" == "$(uname -n 2>/dev/null)" ]]; then
        _intercore_pid_alive "$cpid" || return 0
    fi
    return 1
}

# _intercore_lock_take_claim <lock_dir>: publish this process's claim
# (cleaner.json: pid, host, created, token) so that only one cleaner or
# releaser works on the lock at a time. Sets _ICL_CLAIM to the claim's bytes.
# An existing claim blocks this unless it is abandoned; an abandoned claim is
# taken over (removed exactly, then published anew). Same protocol as ic.
_intercore_lock_take_claim() {
    local cf="$1/cleaner.json" content cur
    content=$(printf '{"pid":%d,"host":"%s","created":%d,"token":"%s"}' \
        "$$" "$(uname -n 2>/dev/null || echo unknown)" "$(date +%s)" \
        "$$.$(date +%s%N 2>/dev/null).${RANDOM}${RANDOM}")
    _ICL_CLAIM="$content"$'\n'
    if _intercore_lock_publish "$cf" "$content"; then return 0; fi
    _intercore_lock_slurp "$cf" || return 1       # it just went away: retry later
    cur="$_ICL_BYTES"
    _intercore_lock_claim_abandoned "$cf" "$cur" || return 1
    _intercore_lock_remove_exactly "$cf" "$cur" || return 1
    _intercore_lock_publish "$cf" "$content"
}

# _intercore_lock_take_claim_wait <lock_dir> <tries>: take_claim, retried
# (0.02s apart) up to <tries> times.
_intercore_lock_take_claim_wait() {
    local i
    for ((i = 0; i < $2; i++)); do
        _intercore_lock_take_claim "$1" && return 0
        sleep 0.02
    done
    return 1
}

# _intercore_lock_drop_claim <lock_dir>: remove cleaner.json only if it still
# holds the bytes this process published (_ICL_CLAIM). A claim taken over from
# us is not ours to remove.
_intercore_lock_drop_claim() {
    if _intercore_lock_slurp "$1/cleaner.json" && [[ "$_ICL_BYTES" == "$_ICL_CLAIM" ]]; then
        rm -f -- "$1/cleaner.json" 2>/dev/null || true
    fi
}

# _intercore_lock_break_dead <lock_dir>: remove the lock if its owner is dead,
# or the directory if it is an abandoned, ownerless one.
#
# A record is never moved or removed on the strength of an earlier look, because
# its pathname can be reused as soon as it is gone. Cleaners (and releasers) are
# serialized per lock by a claim file (cleaner.json, published like owner.json,
# so created complete and exclusively; ic takes the same claim). Under that
# claim the record is read again and removed only if it is byte-for-byte the
# record that was judged dead. Everything that removes an owner record takes the
# claim first (this cleaner, unlock, ic's Clean and Release), so the record
# cannot change between that re-read and the rm. The one gap left is the instant
# between the comparison and the rm itself, which the claim closes for every
# participant that follows the protocol.
#
# A cleaner that dies holding the claim must not wedge the lock: a claim older
# than 30s, or whose cleaner is a dead process on this host, is taken over (the
# stale file is renamed away, compared byte for byte, and only then deleted).
# Only the cleaner's own claim is ever removed afterwards.
#
# Ownerless directories are reclaimed as ic does: pending files of writers that
# are gone (dead pid, or older than 30s) are dropped; a directory with a live
# writer's pending file or a live cleaner's claim is left alone.
#
# Left alone, deliberately (a stranded lock is acceptable, two holders are not):
#   - a record with no readable pid (empty, or still being written by another
#     client): a half-written record is not a dead owner;
#   - a claim held by a live cleaner.
_intercore_lock_break_dead() {
    local d="$1" of="$1/owner.json" cf="$1/cleaner.json" rec pid f fpid age live=0
    for f in "$d"/.pending.*; do
        [[ -e "$f" ]] || continue
        fpid="${f##*/.pending.}"; fpid="${fpid%%.*}"
        age=$(_intercore_lock_mtime_age "$f") || age=0
        if ! _intercore_pid_alive "$fpid" || (( age > _INTERCORE_LOCK_STALE_CLAIM_SECS )); then
            rm -f -- "$f" 2>/dev/null || true
        else
            live=1
        fi
    done
    if [[ -e "$of" ]]; then
        _intercore_lock_slurp "$of" || return 0
        rec="$_ICL_BYTES"
        pid=$(_intercore_lock_json_field "$rec" pid)
        if [[ -z "$pid" ]]; then
            echo "intercore: lock record without a readable owner left in place: $of" >&2
            return 0
        fi
        _intercore_pid_alive "$pid" && return 0
        _intercore_lock_take_claim "$d" || return 0   # a live cleaner holds this lock's claim
        if _intercore_lock_slurp "$of" && [[ "$_ICL_BYTES" == "$rec" ]]; then
            rm -f -- "$of" 2>/dev/null || true
        fi
        _intercore_lock_drop_claim "$d"
    else
        (( live )) && return 0                          # a writer is mid-publish
        if [[ -e "$cf" ]]; then
            _intercore_lock_slurp "$cf" || return 0
            _intercore_lock_claim_abandoned "$cf" "$_ICL_BYTES" || return 0   # a live cleaner is mid-way
            _intercore_lock_remove_exactly "$cf" "$_ICL_BYTES" || return 0
        fi
    fi
    # Only an empty directory is removed: a successor that claimed it meanwhile
    # has an owner.json in it, so rmdir refuses.
    rmdir "$d" 2>/dev/null || true
}

intercore_lock_available() {
    if [[ -n "$INTERCORE_LOCK_BIN" ]]; then return 0; fi
    INTERCORE_LOCK_BIN=$(command -v ic 2>/dev/null || command -v intercore 2>/dev/null)
    [[ -n "$INTERCORE_LOCK_BIN" ]]
}

# intercore_lock — Acquire a named lock with spin-wait.
# Args: $1=name, $2=scope, $3=timeout (optional, default "1s")
# Returns: 0 if acquired, 1 if timeout/contention
# Uses 3-way exit code split: 0=acquired, 1=contention, 2+=fallthrough to fallback
intercore_lock() {
    local name="$1" scope="$2" timeout="${3:-1s}"
    local _owner="$$:$(hostname -s 2>/dev/null || echo unknown)"
    if intercore_lock_available; then
        local rc=0
        "$INTERCORE_LOCK_BIN" lock acquire "$name" "$scope" --timeout="$timeout" \
            --owner="$_owner" >/dev/null 2>&1 || rc=$?
        if [[ $rc -eq 0 ]]; then return 0; fi   # acquired
        if [[ $rc -eq 1 ]]; then return 1; fi   # contention
        # Exit 2+ = binary error — fall through to legacy
    fi
    # Fallback: directory + owner.json, the same layout ic uses, so `ic lock
    # clean` and `ic lock list` see these locks. Neither mkdir nor a plain
    # redirect is trusted for exclusion: uutils mkdir 0.8.0 can report success
    # for a directory that already exists (uutils/coreutils#13970). The lock is
    # held by whoever publishes owner.json: the complete record is written to a
    # pending file and linked into place with link(2), which fails if owner.json
    # exists and never exposes a partial record. The directory is only a
    # container, so an existing directory is not itself contention.
    local lock_dir="${INTERCORE_LOCK_FALLBACK_DIR:-/tmp/intercore/locks}/${name}/${scope}"
    mkdir -p "$(dirname "$lock_dir")" 2>/dev/null || true
    local retries=0 max_retries=10
    # The token makes this acquisition unique even for a process that acquires
    # the same lock twice, so a delayed unlock can tell its own record from a
    # successor's. ic ignores the extra field.
    local _token _meta
    _token="$$.$(date +%s%N 2>/dev/null).${RANDOM}${RANDOM}"
    _meta=$(printf '{"pid":%d,"host":"%s","owner":"%s","created":%d,"token":"%s"}' \
        "$$" "$(hostname -s 2>/dev/null || echo unknown)" "$_owner" "$(date +%s)" "$_token")
    while true; do
        mkdir "$lock_dir" 2>/dev/null || true
        if [[ -d "$lock_dir" ]] && _intercore_lock_publish "$lock_dir/owner.json" "$_meta"; then
            _intercore_lock_token_set "$lock_dir" "$_token"
            return 0
        fi
        retries=$((retries + 1))
        [[ $retries -gt $max_retries ]] && return 1
        sleep 0.1
    done
}

# intercore_unlock — Release a named lock.
# Args: $1=name, $2=scope
# Returns: 0 always (fail-safe: never block on unlock failure)
intercore_unlock() {
    local name="$1" scope="$2"
    local _owner="$$:$(hostname -s 2>/dev/null || echo unknown)"
    if intercore_lock_available; then
        "$INTERCORE_LOCK_BIN" lock release "$name" "$scope" --owner="$_owner" >/dev/null 2>&1 || true
        return 0
    fi
    # Fallback: remove the lock only if owner.json names this caller's pid AND
    # the token this shell recorded when it acquired. With no recorded token this
    # shell did not acquire the lock (or acquired it in a subshell), so nothing
    # is removed: a pid alone can match a predecessor's record after pid reuse.
    # A lock that was cleaned and re-acquired by someone else is theirs too.
    local lock_dir="${INTERCORE_LOCK_FALLBACK_DIR:-/tmp/intercore/locks}/${name}/${scope}"
    local _mytoken
    _mytoken=$(_intercore_lock_token_get "$lock_dir")
    _intercore_lock_token_drop "$lock_dir"
    if [[ -z "$_mytoken" ]]; then
        echo "intercore_unlock: no acquire token for ${name}/${scope} in this shell; not releasing" >&2
        return 0
    fi
    # The record is removed under the same per-lock claim cleaners take (ic's
    # Release does likewise), after reading it again, so a cleaner that judged it
    # dead cannot race the removal. If the claim stays held, the lock is left.
    local _rec
    _intercore_lock_slurp "$lock_dir/owner.json" || return 0
    _rec="$_ICL_BYTES"
    if [[ "$(_intercore_lock_json_field "$_rec" pid)" == "$$" \
        && "$(_intercore_lock_json_field "$_rec" token)" == "$_mytoken" ]]; then
        if ! _intercore_lock_take_claim_wait "$lock_dir" 100; then
            echo "intercore_unlock: ${name}/${scope} busy (cleaner claim held); not releasing" >&2
            return 0
        fi
        if _intercore_lock_slurp "$lock_dir/owner.json" && [[ "$_ICL_BYTES" == "$_rec" ]]; then
            rm -f -- "$lock_dir/owner.json" 2>/dev/null || true
        fi
        _intercore_lock_drop_claim "$lock_dir"
        rmdir "$lock_dir" 2>/dev/null || true
    fi
    return 0
}

# intercore_lock_clean — Remove stale locks.
# Args: $1=max_age (optional, default "5s")
# Returns: 0 always (fail-safe)
intercore_lock_clean() {
    local max_age="${1:-5s}"
    if intercore_lock_available; then
        "$INTERCORE_LOCK_BIN" lock clean --older-than="$max_age" >/dev/null 2>&1 || true
        return 0
    fi
    # Fallback: an aged lock is removed only when its owner process is gone, as
    # `ic lock clean` does. Age alone never justifies breaking a live holder.
    local _secs
    _secs=$(echo "$max_age" | sed -E 's/([0-9]+)s$/\1/; s/([0-9]+)m$/\1*60/; s/([0-9]+)h$/\1*3600/' | bc 2>/dev/null) || _secs=5
    [[ -z "$_secs" || "$_secs" -eq 0 ]] && _secs=5
    local _base="${INTERCORE_LOCK_FALLBACK_DIR:-/tmp/intercore/locks}" _d
    [[ -d "$_base" ]] || return 0
    while IFS= read -r -d '' _d; do
        _intercore_lock_break_dead "$_d"
    done < <(find "$_base" -mindepth 2 -maxdepth 2 -type d -not -newermt "${_secs} seconds ago" -print0 2>/dev/null)
    return 0
}

# --- Event bus wrappers (v0.6.0) ---

# intercore_events_tail <run_id> [--since-phase=N] [--since-dispatch=N]
# One-shot event dump. Returns JSON lines to stdout.
intercore_events_tail() {
    if intercore_remote_authority; then return 2; fi
    intercore_available || return 0
    local run_id="$1"; shift
    $INTERCORE_BIN events tail "$run_id" "$@" 2>/dev/null
}

# intercore_events_tail_all [--since-phase=N] [--since-dispatch=N]
# One-shot event dump across all runs.
intercore_events_tail_all() {
    if intercore_remote_authority; then return 2; fi
    intercore_available || return 0
    $INTERCORE_BIN events tail --all "$@" 2>/dev/null
}

# intercore_events_cursor_get <consumer>
# Returns cursor JSON payload or empty string.
# Uses `ic events cursor list` rather than reading state directly,
# so cursor format changes don't silently break the wrapper.
intercore_events_cursor_get() {
    if intercore_remote_authority; then return 2; fi
    intercore_available || { echo ""; return 0; }
    local consumer="$1"
    $INTERCORE_BIN events cursor list 2>/dev/null | grep -P "^${consumer}\t" | cut -f2 || echo ""
}

# intercore_events_cursor_set <consumer> <phase_id> <dispatch_id>
# Manually set cursor position.
intercore_events_cursor_set() {
    intercore_available || return 0
    local consumer="$1" phase_id="$2" dispatch_id="$3"
    echo "{\"phase\":${phase_id},\"dispatch\":${dispatch_id}}" | \
        $INTERCORE_BIN state set "cursor" "$consumer" --ttl=24h 2>/dev/null
}

# intercore_events_cursor_reset <consumer>
# Reset a consumer's cursor.
intercore_events_cursor_reset() {
    intercore_available || return 0
    $INTERCORE_BIN events cursor reset "$1" 2>/dev/null
}

# --- E1: Skip, Token, Budget wrappers ---

# intercore_run_skip — Skip a phase for a run.
# Args: $1=run_id, $2=phase, $3=reason, $4=actor (optional)
# Returns: 0 on success, 1 on failure
intercore_run_skip() {
    local run_id="$1" phase="$2" reason="$3" actor="${4:-}"
    if ! intercore_available; then return 1; fi
    local args=(run skip "$run_id" "$phase" --reason="$reason")
    [[ -n "$actor" ]] && args+=(--actor="$actor")
    "$INTERCORE_BIN" "${args[@]}" ${INTERCORE_DB:+--db="$INTERCORE_DB"} 2>/dev/null
}

# intercore_run_tokens — Get aggregated token usage for a run (JSON).
# Args: $1=run_id
# Prints: JSON with input_tokens, output_tokens, cache_hits, total_tokens
intercore_run_tokens() {
    local run_id="$1"
    if ! intercore_available; then return 1; fi
    "$INTERCORE_BIN" run tokens "$run_id" --json ${INTERCORE_DB:+--db="$INTERCORE_DB"} 2>/dev/null
}

# intercore_run_budget — Check budget status for a run (JSON).
# Args: $1=run_id
# Prints: JSON with budget, used, warning, exceeded
# Returns: 0=OK/warning, 1=exceeded
intercore_run_budget() {
    local run_id="$1"
    if ! intercore_available; then return 1; fi  # fail-safe: treat unavailability as exceeded
    "$INTERCORE_BIN" run budget "$run_id" --json ${INTERCORE_DB:+--db="$INTERCORE_DB"} 2>/dev/null
}

# intercore_dispatch_tokens — Report token counts for a dispatch.
# Args: $1=dispatch_id, $2=input_tokens, $3=output_tokens, $4=cache_hits (optional)
# Returns: 0 on success, 1 on failure
intercore_dispatch_tokens() {
    local dispatch_id="$1" tokens_in="$2" tokens_out="$3" cache_hits="${4:-}"
    if ! intercore_available; then return 1; fi
    local args=(dispatch tokens "$dispatch_id" --in="$tokens_in" --out="$tokens_out")
    [[ -n "$cache_hits" ]] && args+=(--cache="$cache_hits")
    "$INTERCORE_BIN" "${args[@]}" ${INTERCORE_DB:+--db="$INTERCORE_DB"} 2>/dev/null
}

# --- E6: Rollback wrappers ---

# intercore_run_rollback — Roll back a run to a prior phase.
# Args: $1=run_id, $2=target_phase, $3=reason (optional)
# Prints: JSON with from_phase, to_phase, rolled_back_phases, cancelled_dispatches, marked_artifacts
# Returns: 0=success, 1=failure (not found, invalid target, terminal)
intercore_run_rollback() {
    local run_id="$1" target_phase="$2" reason="${3:-}"
    if ! intercore_available; then return 1; fi
    local args=(run rollback "$run_id" --to-phase="$target_phase")
    [[ -n "$reason" ]] && args+=(--reason="$reason")
    "$INTERCORE_BIN" "${args[@]}" ${INTERCORE_DB:+--db="$INTERCORE_DB"} 2>/dev/null
}

# intercore_run_rollback_dry — Preview what a rollback would do.
# Args: $1=run_id, $2=target_phase
# Prints: JSON with dry_run=true, from_phase, to_phase, rolled_back_phases
# Returns: 0=success, 1=invalid
intercore_run_rollback_dry() {
    local run_id="$1" target_phase="$2"
    if ! intercore_available; then return 1; fi
    "$INTERCORE_BIN" run rollback "$run_id" --to-phase="$target_phase" --dry-run \
        ${INTERCORE_DB:+--db="$INTERCORE_DB"} 2>/dev/null
}

# intercore_run_code_rollback — Query dispatch metadata for code rollback.
# Args: $1=run_id, $2=phase (optional, filters to single phase)
# Prints: JSON array of {dispatch_id, dispatch_name, phase, path, content_hash, type}
# Returns: 0=success, 1=failure
intercore_run_code_rollback() {
    local run_id="$1" filter_phase="${2:-}"
    if ! intercore_available; then return 1; fi
    local args=(run rollback "$run_id" --layer=code)
    [[ -n "$filter_phase" ]] && args+=(--phase="$filter_phase")
    "$INTERCORE_BIN" "${args[@]}" ${INTERCORE_DB:+--db="$INTERCORE_DB"} 2>/dev/null
}

# --- Phase Action wrappers ---

# intercore_run_action_add — Register a phase action for a run.
# Args: $1=run_id, $2=phase, $3=command, $4=mode (optional), $5=args_json (optional)
# Prints: JSON with id
# Returns: 0 on success, 1 on duplicate, 2+ on error
intercore_run_action_add() {
    local run_id="$1" phase="$2" command="$3" mode="${4:-interactive}" args_json="${5:-}"
    if ! intercore_available; then return 1; fi
    local cmd_args=(--json run action add "$run_id" --phase="$phase" --command="$command" --mode="$mode")
    [[ -n "$args_json" ]] && cmd_args+=(--args="$args_json")
    "$INTERCORE_BIN" "${cmd_args[@]}" ${INTERCORE_DB:+--db="$INTERCORE_DB"} 2>/dev/null
}

# intercore_run_action_list — List actions for a run, optionally filtered by phase.
# Args: $1=run_id, $2=phase (optional)
# Prints: JSON array of actions
# Returns: 0 on success, 1 on failure
intercore_run_action_list() {
    local run_id="$1" phase="${2:-}"
    if ! intercore_available; then return 1; fi
    local cmd_args=(--json run action list "$run_id")
    [[ -n "$phase" ]] && cmd_args+=(--phase="$phase")
    "$INTERCORE_BIN" "${cmd_args[@]}" ${INTERCORE_DB:+--db="$INTERCORE_DB"} 2>/dev/null
}

# intercore_run_action_update — Update a phase action's args, mode, or priority.
# Args: $1=run_id, $2=phase, $3=command, $4=field=value pairs (--args=, --mode=, --priority=)
# Returns: 0 on success, 1 on not found
intercore_run_action_update() {
    local run_id="$1" phase="$2" command="$3"
    shift 3
    if ! intercore_available; then return 1; fi
    local cmd_args=(run action update "$run_id" --phase="$phase" --command="$command")
    cmd_args+=("$@")
    "$INTERCORE_BIN" "${cmd_args[@]}" ${INTERCORE_DB:+--db="$INTERCORE_DB"} 2>/dev/null
}

# intercore_run_action_delete — Delete a phase action.
# Args: $1=run_id, $2=phase, $3=command
# Returns: 0 on success, 1 on not found
intercore_run_action_delete() {
    local run_id="$1" phase="$2" command="$3"
    if ! intercore_available; then return 1; fi
    "$INTERCORE_BIN" run action delete "$run_id" --phase="$phase" --command="$command" \
        ${INTERCORE_DB:+--db="$INTERCORE_DB"} 2>/dev/null
}

# intercore_run_advance — Advance a run to the next phase.
# Args: $1=run_id, $2=priority (optional, default 0)
# Prints: JSON with from_phase, to_phase, advanced, actions, etc.
# Returns: 0 on success (advanced), 1 on blocked/not found
intercore_run_advance() {
    local run_id="$1" priority="${2:-0}"
    if ! intercore_available; then return 1; fi
    "$INTERCORE_BIN" --json run advance "$run_id" --priority="$priority" \
        ${INTERCORE_DB:+--db="$INTERCORE_DB"} 2>/dev/null
}

# intercore_agency_load — Load agency specs for a run.
# Args: $1=run_id, $2=spec_dir
# Returns: 0 on success, 1 on failure
intercore_agency_load() {
    local run_id="$1" spec_dir="${2:-}"
    if ! intercore_available; then return 1; fi
    local cmd_args=(agency load all --run="$run_id")
    [[ -n "$spec_dir" ]] && cmd_args+=(--spec-dir="$spec_dir")
    "$INTERCORE_BIN" "${cmd_args[@]}" ${INTERCORE_DB:+--db="$INTERCORE_DB"} 2>/dev/null
}

# intercore_agency_validate — Validate agency spec files.
# Args: $1=spec_dir (validates all specs in dir)
# Returns: 0 if all valid, 1 if any fail
intercore_agency_validate() {
    local spec_dir="$1"
    if ! intercore_available; then return 1; fi
    "$INTERCORE_BIN" agency validate --all --spec-dir="$spec_dir" \
        ${INTERCORE_DB:+--db="$INTERCORE_DB"} 2>/dev/null
}
