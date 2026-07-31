#!/usr/bin/env bash
# shellcheck: sourced library — no set -euo pipefail (would alter caller's error policy)
# lib-shadow-tracker.sh — detect shadow work-tracking files
# Used by: auto-stop-actions.sh (Stop hook), doctor.md (manual)
#
# Shadow trackers are files that duplicate beads' work-tracking responsibility.
# They drift silently and cause duplicate effort. Three detection categories:
#   1. todos/*.md with status: frontmatter (pending|open|done|complete|ready|in_progress)
#   2. pending-beads*.md files anywhere
#   3. *.md files with type: task|todo|tracker frontmatter (tightened from doctor.md)
#
# Pruned directories: .git/, node_modules/, build-output trees (target/, dist/,
# build/, .next/), virtualenvs, vendor/, caches, and nested worktrees.
# Category 3 additionally skips docs/{brainstorms,plans,prds,research,solutions}/.
#
# PERFORMANCE (fixed 2026-07-30, doctor run):
#   This function was 2.87s of the Stop hook's 4.61s — 62% — and on a repo with
#   a large build tree it did not finish at all: detect_shadow_trackers against
#   ~/projects/shadow-work (13G Rust target/) exceeded 120s. The Stop hook is
#   capped at 5s, so every session in that repo lost its goal-cadence /
#   compound / drift instruction outright — the hook was timing out on 39 of
#   208 recorded runs.
#
#   Two causes, both fixed below:
#     1. `-not -path '*/node_modules/*'` FILTERS results but still DESCENDS into
#        the directory. Only `-prune` skips the subtree. The old scan walked
#        every ignored build artifact and then threw the paths away.
#     2. Categories 1 and 2 had no -maxdepth at all, so they walked the entire
#        tree to unlimited depth. Bounded to 6 now — deeper todos/ layouts are
#        vanishingly rare next to a 120s scan.
#
#   A wall-clock deadline is applied as defense in depth for trees nobody has
#   pruned yet; override with SHADOW_SCAN_DEADLINE (seconds, 0 disables).
#
#   The deadline is PER FIND, and detect_shadow_trackers runs three of them in
#   sequence — so the worst case is 3x the value, not 1x. It was 3s, which put
#   the ceiling at ~9s: nearly double the Stop hook's 5s cap, and a cold-FS-cache
#   run in ~/projects/Sylveste was measured at 11.4s for exactly that reason.
#   1s keeps the whole scan under ~3s, inside the cap with room for the rest of
#   the hook. A category that times out contributes no matches — silently, by
#   design: this is a nudge, not a gate.

[[ -n "${_LIB_SHADOW_TRACKER_LOADED:-}" ]] && return 0
_LIB_SHADOW_TRACKER_LOADED=1

# Directory NAMES pruned from every scan. See cause (1) above for why this is
# -prune and not -not -path.
_SHADOW_PRUNE_EXPR=(
    -name .git -o -name node_modules -o -name target -o -name dist
    -o -name build -o -name .next -o -name .venv -o -name venv
    -o -name vendor -o -name .cache -o -name __pycache__ -o -name worktrees
)

# Resolve a timeout(1) once. Hooks do not inherit an interactive PATH, so also
# probe the usual Homebrew/coreutils absolute paths. Empty => run undeadlined.
_shadow_timeout_bin() {
    local c
    for c in timeout gtimeout /opt/homebrew/bin/timeout /opt/homebrew/bin/gtimeout \
             /usr/local/bin/timeout /usr/local/bin/gtimeout /usr/bin/timeout; do
        if command -v "$c" >/dev/null 2>&1; then printf '%s' "$c"; return 0; fi
    done
    printf ''
}

# _shadow_find <dir> <maxdepth> [extra find predicates...]
# Emits matching file paths, pruning the noisy subtrees and honouring the
# wall-clock deadline. Never fails the caller.
_shadow_find() {
    local dir="$1" maxdepth="$2"; shift 2
    # Per-find, and three finds run in sequence — see the PERFORMANCE note above
    # before raising this. Effective ceiling for a full scan is 3x this value.
    local deadline="${SHADOW_SCAN_DEADLINE:-1}"
    local tbin; tbin="$(_shadow_timeout_bin)"

    if [[ -n "$tbin" && "$deadline" != "0" ]]; then
        "$tbin" "$deadline" find "$dir" -maxdepth "$maxdepth" \
            \( "${_SHADOW_PRUNE_EXPR[@]}" \) -prune -o \
            "$@" -type f -print 2>/dev/null
    else
        find "$dir" -maxdepth "$maxdepth" \
            \( "${_SHADOW_PRUNE_EXPR[@]}" \) -prune -o \
            "$@" -type f -print 2>/dev/null
    fi
}

# detect_shadow_trackers [dir]
# Outputs: one line per detected file. Returns count via exit code (0=none, N=count capped at 125).
# _shadow_grep_frontmatter <extended-regex> [files...]
# Prints the names of files whose FIRST 10 LINES match the regex, in one awk
# process for the whole batch. The old form spawned `head -10 | grep -q` per
# candidate — two processes per file, which dominated the scan once a repo had
# a few dozen matches. `nextfile` stops reading as soon as a file matches.
_shadow_grep_frontmatter() {
    local re="$1"; shift
    [[ $# -eq 0 ]] && return 0        # awk with no file args would read stdin and hang
    awk -v re="$re" 'FNR<=10 && $0 ~ re { print FILENAME; nextfile } FNR>10 { nextfile }' "$@" 2>/dev/null
}

detect_shadow_trackers() {
    local dir="${1:-.}"
    local count=0
    local files=()
    local cands=()

    # Category 1: todos/*.md with status frontmatter
    cands=()
    while IFS= read -r f; do [[ -n "$f" ]] && cands+=("$f"); done < <(_shadow_find "$dir" 6 -path '*/todos/*.md')
    while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        files+=("$f"); ((count++))
    done < <(_shadow_grep_frontmatter '^status:[[:space:]]*(pending|open|done|complete|ready|in_progress)' "${cands[@]}")

    # Category 2: pending-beads*.md files
    while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        files+=("$f")
        ((count++))
    done < <(_shadow_find "$dir" 6 -name 'pending-beads*.md')

    # Category 3: *.md files with type:task/todo/tracker frontmatter
    # Tightened from doctor.md: requires type:task|todo|tracker, not just any status: key
    cands=()
    while IFS= read -r f; do [[ -n "$f" ]] && cands+=("$f"); done < <(_shadow_find "$dir" 3 -name '*.md' \
        -not -path '*/docs/brainstorms/*' \
        -not -path '*/docs/plans/*' \
        -not -path '*/docs/prds/*' \
        -not -path '*/docs/research/*' \
        -not -path '*/docs/solutions/*' | head -50)
    while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        files+=("$f"); ((count++))
    done < <(_shadow_grep_frontmatter '^type:[[:space:]]*(task|todo|tracker)' "${cands[@]}")

    # Output detected files
    for f in "${files[@]}"; do
        echo "$f"
    done

    # Return count (capped at 125 for bash exit code safety)
    [[ $count -gt 125 ]] && count=125
    return "$count"
}
