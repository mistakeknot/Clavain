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
#   - never pushes main, master or the default branch of the remote, asked of
#     the remote itself for every push URL (ls-remote --symref); if that cannot
#     be told, nothing is pushed
#   - skips branches matching a skip pattern: CLAVAIN_AUTO_PUSH_SKIP (space or
#     comma separated globs), else git config clavain.autoPushSkip (repeatable),
#     else the default "wk/*". A configured list replaces the default.
# A skip pattern or protected branch still lets beads push run (it pushes the
# Dolt database, not a git branch); the explicit opt-outs above skip that too.
#
# Log: every push (and every failed push, and every skip of work that would
# have been pushed) appends one key=value line (values percent-encoded, so one
# event is one line) to
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

# Percent-encode a log value so one event is one line and one field is one word.
enc() {
    local LC_ALL=C s="${1:0:600}" out="" c i
    for ((i = 0; i < ${#s}; i++)); do
        c="${s:i:1}"
        case "$c" in
            [A-Za-z0-9._/:@+,=~*-]) out+="$c" ;;
            *) out+=$(printf '%%%02X' "'$c") ;;
        esac
    done
    printf '%s' "$out"
}

# One log line: EVENT, then key=value words (values are encoded here). Never fails the hook.
log_event() {
    local event="$1" extra="" kv parent
    shift
    for kv in "$@"; do extra+=" ${kv%%=*}=$(enc "${kv#*=}")"; done
    parent=$(ps -o comm= -p "$PPID" 2>/dev/null | tr -d ' ') || parent=""
    {
        mkdir -p "$(dirname "$LOG_FILE")" &&
            printf '%s event=%s repo=%s branch=%s%s pid=%s ppid=%s parent=%s session=%s hook_event=%s\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$event" "$(enc "$GIT_ROOT")" "$(enc "$BRANCH")" "$extra" \
                "$$" "$PPID" "$(enc "${parent:-unknown}")" "$(enc "$(json_field session_id)")" \
                "$(enc "$(json_field hook_event_name)")" \
                >>"$LOG_FILE"
    } 2>/dev/null || true
}

# --- opt-outs (the whole hook) ------------------------------------------------
global_off_reason() {
    case "${CLAVAIN_AUTO_PUSH:-}" in
        0 | false | no | off) echo "env:CLAVAIN_AUTO_PUSH=${CLAVAIN_AUTO_PUSH}"; return ;;
    esac
    local marker cfg rc
    marker=$(git rev-parse --git-path info/no-auto-push 2>/dev/null) || marker=""
    if [[ -n "$marker" && -e "$marker" ]]; then
        echo "marker:$marker"
        return
    fi
    if [[ -e ".no-auto-push" ]]; then
        echo "marker:$GIT_ROOT/.no-auto-push"
        return
    fi
    cfg=$(git config --type=bool --get clavain.autoPush 2>/dev/null)
    rc=$?
    if [[ $rc -eq 0 && "$cfg" == "false" ]]; then
        echo "git-config:clavain.autoPush=false"
    elif [[ $rc -ne 0 && $rc -ne 1 ]]; then
        # 1 means the key is unset; anything else is a bad value or an unreadable file: fail closed.
        echo "git-config:clavain.autoPush-unreadable(rc=$rc)"
    fi
}

GLOBAL_OFF=$(global_off_reason)

# --- branch rules ---------------------------------------------------------------
skip_patterns() {
    if [[ -n "${CLAVAIN_AUTO_PUSH_SKIP:-}" ]]; then
        printf '%s\n' "${CLAVAIN_AUTO_PUSH_SKIP//,/ }" | tr -s ' ' '\n'
        return
    fi
    local configured rc
    configured=$(git config --get-all clavain.autoPushSkip 2>/dev/null)
    rc=$?
    if [[ $rc -gt 1 ]]; then
        echo '*' # an unreadable list blocks every branch: fail closed
    elif [[ -n "$configured" ]]; then
        printf '%s\n' "$configured"
    else
        echo 'wk/*'
    fi
}

# The default branch of the repository at URL, asked of that repository itself (ls-remote --symref,
# no prompts, bounded). Prints nothing when it cannot be told. Local remote-tracking metadata is never
# trusted for this: it goes stale when the remote's default changes.
remote_default_branch() {
    GIT_TERMINAL_PROMPT=0 timeout 20 git ls-remote --symref "$1" HEAD 2>/dev/null </dev/null |
        sed -n 's|^ref: refs/heads/\(.*\)[[:space:]]HEAD$|\1|p' | head -n1
}

# Prints why the guard cannot prove that the repository it queries is the one the push reaches, or
# nothing when it can. The query is ls-remote against each push URL; the push goes through git's own
# transport, so anything that can make the two differ fails closed:
#   - a custom receive-pack/upload-pack/helper on any remote, or a custom ssh/proxy command (the push
#     may run another command than the query does);
#   - an ext:: URL (it runs a command);
#   - a control character (newline, SOH, ...) anywhere in a remote URL or URL rewrite rule: the URL
#     list is read line by line, so such a URL would be truncated;
#   - config that cannot be read.
destination_unverifiable() {
    local LC_ALL=C remote="$1" key rc rec value
    # Overrides on ANY remote count: ls-remote treats a URL that equals a remote's name as that remote.
    if git config --get-regexp '^remote\..*\.(receivepack|uploadpack|vcs)$' >/dev/null 2>&1; then
        echo "remote-command-override"
        return
    fi
    for key in core.sshCommand core.gitProxy; do
        git config --get "$key" >/dev/null 2>&1
        rc=$?
        if [[ $rc -ne 1 ]]; then
            echo "$key"
            return
        fi
    done
    for key in GIT_SSH GIT_SSH_COMMAND GIT_PROXY_COMMAND; do
        if [[ -n "${!key:-}" ]]; then
            echo "env:$key"
            return
        fi
    done
    git config --get-regexp '^(remote\..*\.(url|pushurl)|url\..*\.(insteadof|pushinsteadof))$' >/dev/null 2>&1
    rc=$?
    if [[ $rc -ne 0 && $rc -ne 1 ]]; then
        echo "config-unreadable"
        return
    fi
    # -z gives "key\nvalue\0" records, read here with NUL as the delimiter (no byte is substituted,
    # so no legal URL byte can collide with the separator). The key never holds a newline.
    while IFS= read -r -d '' rec; do
        value="${rec#*$'\n'}"
        if [[ "$value" == *[[:cntrl:]]* ]]; then
            echo "control-character-in-url-config"
            return
        fi
        case "$value" in
            ext::*) echo "ext-transport"; return ;;
        esac
    done < <(LC_ALL=C git config -z --get-regexp '^(remote\..*\.(url|pushurl)|url\..*\.(insteadof|pushinsteadof))$' 2>/dev/null)
}

# Prints why BRANCH must not be pushed to REMOTE, or nothing when it may be. A push goes to every
# push URL of the remote, so each one's default branch is checked; one unknown or matching blocks all.
branch_block_reason() {
    local remote="$1" cached default pat url found=0 unverifiable
    case "$BRANCH" in
        main | master) echo "protected-branch:$BRANCH"; return ;;
    esac
    while IFS= read -r pat; do
        [[ -n "$pat" ]] || continue
        # shellcheck disable=SC2053 # the pattern is meant to glob
        if [[ "$BRANCH" == $pat ]]; then
            echo "skip-pattern:$pat"
            return
        fi
    done < <(skip_patterns)
    # The cached default can only add a refusal, never remove one.
    cached=$(git symbolic-ref -q --short "refs/remotes/$remote/HEAD" 2>/dev/null) || cached=""
    if [[ -n "$cached" && "$BRANCH" == "${cached#"$remote"/}" ]]; then
        echo "default-branch:$remote/$BRANCH"
        return
    fi
    unverifiable=$(destination_unverifiable "$remote")
    if [[ -n "$unverifiable" ]]; then
        echo "destination-unverifiable:$unverifiable"
        return
    fi
    while IFS= read -r url; do
        [[ -n "$url" ]] || continue
        found=1
        # ls-remote reads an argument that names a configured remote as that remote (and uses its url,
        # not this pushurl), so such a URL would query a different repository than the push reaches.
        if git remote | grep -Fxq -- "$url"; then
            echo "default-branch-of-$remote-unknown"
            return
        fi
        # ls-remote rewrites its URL argument (insteadOf) once more. If that changes it, the query
        # would reach a different repository than the push does, so treat the default as unknown.
        if [[ "$(git ls-remote --get-url "$url" 2>/dev/null)" != "$url" ]]; then
            echo "default-branch-of-$remote-unknown"
            return
        fi
        default=$(remote_default_branch "$url")
        if [[ -z "$default" ]]; then
            echo "default-branch-of-$remote-unknown" # fail closed: cannot show this is not the default
            return
        fi
        if [[ "$BRANCH" == "$default" ]]; then
            echo "default-branch:$remote/$default"
            return
        fi
    done < <(git remote get-url --push --all "$remote" 2>/dev/null)
    if [[ $found -eq 0 ]]; then
        echo "default-branch-of-$remote-unknown"
    fi
}

# push_to REMOTE KIND [-u]: the one place a push happens. Logs the outcome.
push_to() {
    local remote="$1" kind="$2" setup="${3:-}" reason before after rc urls
    if [[ -n "$GLOBAL_OFF" ]]; then
        log_event skipped "remote=$remote" "kind=$kind" "reason=$GLOBAL_OFF"
        return 0
    fi
    reason=$(branch_block_reason "$remote")
    if [[ -n "$reason" ]]; then
        log_event skipped "remote=$remote" "kind=$kind" "reason=$reason"
        return 0
    fi
    before=$(git rev-parse --verify -q "refs/remotes/$remote/$BRANCH" 2>/dev/null) || before="none"
    # git push goes to EVERY push URL of the remote, so log them all.
    urls=$(git remote get-url --push --all "$remote" 2>/dev/null | paste -sd, -) || urls=""
    [[ -n "$urls" ]] || urls="unknown"
    # An explicit refspec: never rely on push.default (matching would push other branches).
    # shellcheck disable=SC2086 # $setup is empty or a single -u
    git push $setup "$remote" "refs/heads/$BRANCH:refs/heads/$BRANCH" >/dev/null 2>&1
    rc=$?
    after=$(git rev-parse HEAD 2>/dev/null) || after="unknown"
    if [[ $rc -eq 0 ]]; then
        log_event pushed "remote=$remote" "urls=$urls" "kind=$kind" "from=${before:0:12}" "sha=${after:0:12}"
    else
        # With several push URLs a failure may still have updated some of them.
        if [[ "$urls" == *,* ]]; then
            log_event push-failed "remote=$remote" "urls=$urls" "kind=$kind" "rc=$rc" "sha=${after:0:12}" "note=may-be-partial"
        else
            log_event push-failed "remote=$remote" "urls=$urls" "kind=$kind" "rc=$rc" "sha=${after:0:12}"
        fi
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
