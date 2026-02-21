# lib-intercore.sh — Bash wrappers for intercore CLI
# Version: 0.1.0 (source: infra/intercore/lib-intercore.sh)
# Re-copy to hub/clavain/hooks/ on major intercore updates; version is pinned to plugin release.
# This file is SOURCED by hooks. Do NOT use set -e here — it would exit
# the parent shell on any failure.
# Source in hooks: source "$(dirname "$0")/lib-intercore.sh"
# shellcheck shell=bash

INTERCORE_WRAPPER_VERSION="1.1.0"

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

# intercore_run_create — Create a new ic run.
# Args: $1=project_dir, $2=goal, $3=phases_json, $4=scope_id (optional),
#       $5=complexity (optional, default 3), $6=token_budget (optional),
#       $7=actions_json (optional, e.g. '{"planned":{"command":"/clavain:work","mode":"interactive"}}')
# Prints: run ID to stdout
# Returns: 0 on success, 1 on failure
intercore_run_create() {
    local project="$1" goal="$2" phases_json="$3" scope_id="${4:-}" complexity="${5:-3}" token_budget="${6:-}" actions_json="${7:-}"
    if ! intercore_available; then return 1; fi
    local args=(run create --project="$project" --goal="$goal" --complexity="$complexity")
    [[ -n "$phases_json" ]] && args+=(--phases="$phases_json")
    [[ -n "$scope_id" ]] && args+=(--scope-id="$scope_id")
    [[ -n "$token_budget" ]] && args+=(--token-budget="$token_budget")
    [[ -n "$actions_json" ]] && args+=(--actions="$actions_json")
    "$INTERCORE_BIN" "${args[@]}" ${INTERCORE_DB:+--db="$INTERCORE_DB"} 2>/dev/null
}

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

# --- Gate wrappers ---

# intercore_gate_check — Dry-run gate evaluation for the next transition.
# Args: $1=run_id
# Returns: 0=pass, 1=fail, 2+=error/fallthrough
intercore_gate_check() {
    local run_id="$1"
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
INTERCORE_LOCK_BIN=""

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
    # Fallback: direct mkdir with minimal owner.json for ic lock clean visibility
    local lock_dir="/tmp/intercore/locks/${name}/${scope}"
    mkdir -p "$(dirname "$lock_dir")" 2>/dev/null || true
    local retries=0 max_retries=10
    while ! mkdir "$lock_dir" 2>/dev/null; do
        retries=$((retries + 1))
        [[ $retries -gt $max_retries ]] && return 1
        sleep 0.1
    done
    # Write owner.json so ic lock clean can detect and remove stale fallback locks
    printf '{"pid":%d,"host":"%s","owner":"%s","created":%d}\n' \
        "$$" "$(hostname -s 2>/dev/null || echo unknown)" "$_owner" "$(date +%s)" \
        > "$lock_dir/owner.json" 2>/dev/null || true
    return 0
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
    # Fallback: rm owner.json + rmdir (no owner check in fallback)
    rm -f "/tmp/intercore/locks/${name}/${scope}/owner.json" 2>/dev/null || true
    rmdir "/tmp/intercore/locks/${name}/${scope}" 2>/dev/null || true
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
    # Fallback: find + rm stale lock dirs. Parse max_age to seconds for date offset.
    local _secs
    _secs=$(echo "$max_age" | sed -E 's/([0-9]+)s$/\1/; s/([0-9]+)m$/\1*60/; s/([0-9]+)h$/\1*3600/' | bc 2>/dev/null) || _secs=5
    [[ -z "$_secs" || "$_secs" -eq 0 ]] && _secs=5
    find /tmp/intercore/locks -mindepth 2 -maxdepth 2 -type d -not -newermt "${_secs} seconds ago" \
        -exec sh -c 'rm -f "$1/owner.json" && rmdir "$1"' _ {} \; 2>/dev/null || true
    return 0
}

# --- Event bus wrappers (v0.6.0) ---

# intercore_events_tail <run_id> [--since-phase=N] [--since-dispatch=N]
# One-shot event dump. Returns JSON lines to stdout.
intercore_events_tail() {
    intercore_available || return 0
    local run_id="$1"; shift
    $INTERCORE_BIN events tail "$run_id" "$@" 2>/dev/null
}

# intercore_events_tail_all [--since-phase=N] [--since-dispatch=N]
# One-shot event dump across all runs.
intercore_events_tail_all() {
    intercore_available || return 0
    $INTERCORE_BIN events tail --all "$@" 2>/dev/null
}

# intercore_events_cursor_get <consumer>
# Returns cursor JSON payload or empty string.
# Uses `ic events cursor list` rather than reading state directly,
# so cursor format changes don't silently break the wrapper.
intercore_events_cursor_get() {
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
