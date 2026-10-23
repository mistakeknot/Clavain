#!/usr/bin/env bash
# SessionEnd hook: auto-push unpushed commits
#
# Pushes commits the session left unpushed. Handles three branch shapes
# (mk-667 — the old version exited silently when @{upstream} was missing,
# stranding every worktree branch's commits):
#   1. Branch with a same-name upstream: push it under that name.
#   2. Branch tracking a DIFFERENT ref (e.g. a worktree branch tracking
#      origin/main): publish under the branch's own name and adopt that as
#      upstream.
#   3. No upstream at all: push -u origin <branch>, but only when the
#      branch carries commits that exist on no remote ref (avoids minting
#      pointless remote branches for unmodified checkouts).
# Also runs beads push if .beads/ exists. Runs async so it doesn't block.
#
# Opt-outs (mk-ge29k) — any one of these makes the hook push nothing:
#   - CLAVAIN_AUTO_PUSH=0 (also false, no, off) in the environment
#   - a marker file: <git-dir>/info/no-auto-push (this clone only; shared by
#     its worktrees), or a tracked/untracked .no-auto-push at the work tree root
#   - git config clavain.autoPush=false (local, global or system)
# Branch rules:
#   - never pushes main, master or the remote's default branch
#     (refs/remotes/<remote>/HEAD)
#   - skips branches matching a skip pattern: CLAVAIN_AUTO_PUSH_SKIP (space or
#     comma separated globs), else git config clavain.autoPushSkip (repeatable),
#     else the default "wk/*". A configured list replaces the default.
# A skip pattern or protected branch still lets beads push run (it pushes the
# Dolt database, not a git branch); the explicit opt-outs above skip that too.
#
# Log: every push (and every failed push, and every skip of work that would
# have been pushed) appends one key=value line to
#   $CLAVAIN_AUTO_PUSH_LOG, else ${XDG_STATE_HOME:-$HOME/.local/state}/clavain/auto-push.log
# so "who pushed this branch?" is `grep branch=NAME` on that file.
#
# Input: Hook JSON on stdin
# Output: none (async, fire-and-forget)
# Exit: 0 always

set -uo pipefail
trap 'exit 0' ERR

INPUT=""
[[ -t 0 ]] || INPUT=$(cat 2>/dev/null || true)

# Find git root
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$GIT_ROOT"

BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) || exit 0
[[ "$BRANCH" == "HEAD" ]] && exit 0 # detached — nothing safe to push

LOG_FILE="${CLAVAIN_AUTO_PUSH_LOG:-${XDG_STATE_HOME:-$HOME/.local/state}/clavain/auto-push.log}"

# Value of a "key":"value" string field in the hook JSON (no jq dependency).
json_field() {
    printf '%s' "$INPUT" | sed -n 's/.*"'"$1"'"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1
}

# One log line: the caller's key=value words. Never fails the hook.
log_event() {
    local parent
    parent=$(ps -o comm= -p "$PPID" 2>/dev/null | tr -d ' ') || parent=""
    {
        mkdir -p "$(dirname "$LOG_FILE")" &&
            printf '%s event=%s repo=%s branch=%s %s pid=%s ppid=%s parent=%s session=%s hook_event=%s\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$GIT_ROOT" "$BRANCH" "$2" \
                "$$" "$PPID" "${parent:-unknown}" "$(json_field session_id)" "$(json_field hook_event_name)" \
                >>"$LOG_FILE"
    } 2>/dev/null || true
}

# --- opt-outs (the whole hook) ------------------------------------------------
global_off_reason() {
    case "${CLAVAIN_AUTO_PUSH:-}" in
        0 | false | no | off) echo "env CLAVAIN_AUTO_PUSH=${CLAVAIN_AUTO_PUSH}"; return ;;
    esac
    local marker
    marker=$(git rev-parse --git-path info/no-auto-push 2>/dev/null) || marker=""
    if [[ -n "$marker" && -e "$marker" ]]; then
        echo "marker $marker"
        return
    fi
    if [[ -e ".no-auto-push" ]]; then
        echo "marker $GIT_ROOT/.no-auto-push"
        return
    fi
    local cfg
    cfg=$(git config --type=bool --get clavain.autoPush 2>/dev/null) || cfg=""
    if [[ "$cfg" == "false" ]]; then
        echo "git-config clavain.autoPush=false"
        return
    fi
}

GLOBAL_OFF=$(global_off_reason)

# --- branch rules ---------------------------------------------------------------
skip_patterns() {
    if [[ -n "${CLAVAIN_AUTO_PUSH_SKIP:-}" ]]; then
        printf '%s\n' "${CLAVAIN_AUTO_PUSH_SKIP//,/ }" | tr -s ' ' '\n'
        return
    fi
    local configured
    configured=$(git config --get-all clavain.autoPushSkip 2>/dev/null) || configured=""
    if [[ -n "$configured" ]]; then
        printf '%s\n' "$configured"
    else
        echo 'wk/*'
    fi
}

# Prints why BRANCH must not be pushed to REMOTE, or nothing when it may be.
branch_block_reason() {
    local remote="$1" default pat
    case "$BRANCH" in
        main | master) echo "protected branch $BRANCH"; return ;;
    esac
    default=$(git symbolic-ref -q --short "refs/remotes/$remote/HEAD" 2>/dev/null) || default=""
    default="${default#"$remote"/}"
    if [[ -n "$default" && "$BRANCH" == "$default" ]]; then
        echo "default branch of $remote ($default)"
        return
    fi
    while IFS= read -r pat; do
        [[ -n "$pat" ]] || continue
        # shellcheck disable=SC2053 # the pattern is meant to glob
        if [[ "$BRANCH" == $pat ]]; then
            echo "skip pattern $pat"
            return
        fi
    done < <(skip_patterns)
}

# push_to REMOTE KIND [-u]: the one place a push happens. Logs the outcome.
push_to() {
    local remote="$1" kind="$2" setup="${3:-}" reason before after rc url
    if [[ -n "$GLOBAL_OFF" ]]; then
        log_event skipped "remote=$remote kind=$kind reason=\"$GLOBAL_OFF\""
        return 0
    fi
    reason=$(branch_block_reason "$remote")
    if [[ -n "$reason" ]]; then
        log_event skipped "remote=$remote kind=$kind reason=\"$reason\""
        return 0
    fi
    before=$(git rev-parse --verify -q "refs/remotes/$remote/$BRANCH" 2>/dev/null) || before="none"
    url=$(git remote get-url --push "$remote" 2>/dev/null) || url="unknown"
    # An explicit refspec: never rely on push.default (matching would push other branches).
    # shellcheck disable=SC2086 # $setup is empty or a single -u
    git push $setup "$remote" "refs/heads/$BRANCH:refs/heads/$BRANCH" >/dev/null 2>&1
    rc=$?
    after=$(git rev-parse HEAD 2>/dev/null) || after="unknown"
    if [[ $rc -eq 0 ]]; then
        log_event pushed "remote=$remote url=$url kind=$kind from=${before:0:12} sha=${after:0:12}"
    else
        log_event push-failed "remote=$remote url=$url kind=$kind rc=$rc sha=${after:0:12}"
    fi
    return 0
}

push_current() {
    local upstream ahead remote unpushed
    upstream=$(git rev-parse --abbrev-ref "@{upstream}" 2>/dev/null) || upstream=""

    if [[ -z "$upstream" ]]; then
        git remote get-url origin >/dev/null 2>&1 || return 0
        unpushed=$(git rev-list --count HEAD --not --remotes 2>/dev/null) || return 0
        if [[ "${unpushed:-0}" -gt 0 ]]; then
            push_to origin new-branch -u
        fi
        return 0
    fi

    ahead=$(git rev-list --count "${upstream}..HEAD" 2>/dev/null) || return 0
    [[ "${ahead:-0}" -gt 0 ]] || return 0
    remote="${upstream%%/*}"
    if [[ "${upstream#*/}" == "$BRANCH" ]]; then
        push_to "$remote" tracked
    else
        # Tracking a foreign ref (origin/main): publish the branch under
        # its own name; -u moves the upstream so future counts are sane.
        push_to "$remote" foreign-upstream -u
    fi
}

push_current

# Push beads if present (may create a sync commit — push again). The explicit
# opt-outs skip this too; a branch rule does not, since it pushes the Dolt DB.
if [[ -f ".beads/push.sh" && -z "$GLOBAL_OFF" ]]; then
    bash .beads/push.sh 2>/dev/null || true
    push_current
fi

exit 0
