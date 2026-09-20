#!/usr/bin/env bash
# lib-session-project.sh — the session's project directory, pinned once.
#
# The shell's cwd is not the project. A single `cd` in any tool call persists
# for the rest of the session, so $PWD can drift into a sibling repo and stay
# there. Any hook that scopes work by cwd will then act on a project the
# session was never about — observed 2026-09-19, when a Stop-hook goal audit
# reported a sibling repository's goal backlog and pulled the session into
# unrelated work.
#
# Nothing the shell can tell us is safe on its own: the Stop payload's `cwd`
# is "the working directory when the event fired" (already drifted), and a
# `git rev-parse --show-toplevel` from a drifted cwd resolves to the drifted
# repo. So the first hook to ask pins the answer for the whole session, and
# everyone after gets the pinned value regardless of where the shell wandered.
# In practice SessionStart asks first, before any tool call can move it.
#
# Callers must have sourced lib-intercore.sh first (fail-open if absent).

# clavain_resolve_project_dir
# Best-effort project root for the shell's CURRENT position. Only meaningful
# at pin time; everything afterwards should read the pinned value.
clavain_resolve_project_dir() {
    if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
        printf '%s' "$CLAUDE_PROJECT_DIR"
        return 0
    fi
    local top=""
    if top=$(git rev-parse --show-toplevel 2>/dev/null) && [[ -n "$top" ]]; then
        printf '%s' "$top"
        return 0
    fi
    printf '%s' "$PWD"
}

# clavain_session_project_dir <session_id>
# The project this session is about. Pins on first call, reads the pin after.
# Falls back to a live resolve when intercore state is unavailable, so hooks
# keep working without ic (lib-intercore.sh fail-open idiom).
clavain_session_project_dir() {
    local session_id="${1:-}"
    local pinned=""

    if [[ -n "$session_id" && "$session_id" != "unknown" ]] \
        && type intercore_state_get >/dev/null 2>&1; then
        pinned=$(intercore_state_get "session_project_dir" "$session_id" 2>/dev/null) || pinned=""
        # Stored as a JSON string; strip quotes and any trailing newline.
        pinned=${pinned//\"/}
        pinned=${pinned%$'\n'}
    fi

    # A pin to a directory that no longer exists is worse than re-resolving.
    if [[ -n "$pinned" && -d "$pinned" ]]; then
        printf '%s' "$pinned"
        return 0
    fi

    local resolved=""
    resolved=$(clavain_resolve_project_dir)

    if [[ -n "$session_id" && "$session_id" != "unknown" ]] \
        && type intercore_state_set >/dev/null 2>&1; then
        intercore_state_set "session_project_dir" "$session_id" "\"$resolved\"" >/dev/null 2>&1 || true
    fi

    printf '%s' "$resolved"
}
