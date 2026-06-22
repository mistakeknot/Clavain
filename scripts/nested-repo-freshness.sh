#!/usr/bin/env bash
set -uo pipefail

# nested-repo-freshness.sh — Report freshness of nested plugin/subproject git repos.
#
# Background (sylveste-x1rf): the Sylveste monorepo root checkout can be clean
# while a nested plugin repo (e.g. interverse/interlock) is one commit behind
# origin/main, leaving Claude Code loading obsolete code from the plugin cache.
# Each subproject under os/ interverse/ core/ sdk/ apps/ is its OWN git repo,
# so a clean root `git status` says nothing about them.
#
# This script enumerates those nested repos and reports, per repo:
#   - current branch (and whether it differs from the expected default)
#   - ahead / behind counts vs the tracked upstream
#   - dirty tracked changes (modified/staged)
#   - untracked files (cache/generated paths are filtered out)
#   - missing remote / missing upstream tracking
# Stale critical plugins (those Claude Code loads constantly) are highlighted,
# and safe `git -C <dir> pull --ff-only` update commands are emitted.
#
# Usage:
#   ./scripts/nested-repo-freshness.sh             # report (uses cached refs, no network)
#   ./scripts/nested-repo-freshness.sh --fetch     # git fetch first (network) for accurate behind counts
#   ./scripts/nested-repo-freshness.sh --quiet     # only print repos with issues + summary
#   ./scripts/nested-repo-freshness.sh --root DIR  # override monorepo root autodetection
#
# Exit code: 0 if all clean; 1 if any repo is behind/dirty/diverged/misremoted.

FETCH=0
QUIET=0
ROOT_OVERRIDE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fetch) FETCH=1; shift ;;
    --quiet) QUIET=1; shift ;;
    --root) ROOT_OVERRIDE="${2:-}"; shift 2 ;;
    -h|--help) sed -n '3,30p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
if [[ ! -t 1 ]]; then RED=''; GREEN=''; YELLOW=''; CYAN=''; BOLD=''; NC=''; fi

# --- Locate the monorepo root ----------------------------------------------
# Markers that identify the Sylveste monorepo root (any one is sufficient).
_is_monorepo_root() {
  [[ -d "$1/os/Clavain" ]] || { [[ -d "$1/interverse" ]] && [[ -d "$1/core" ]]; }
}

find_root() {
  if [[ -n "$ROOT_OVERRIDE" ]]; then echo "$ROOT_OVERRIDE"; return; fi
  # Walk up from cwd.
  local d; d="$(pwd)"
  while [[ "$d" != "/" ]]; do
    if _is_monorepo_root "$d"; then echo "$d"; return; fi
    d="$(dirname "$d")"
  done
  # Fall back to walking up from this script's location (handles being run
  # from the plugin cache symlink as well as the source tree).
  local s; s="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  while [[ "$s" != "/" ]]; do
    if _is_monorepo_root "$s"; then echo "$s"; return; fi
    s="$(dirname "$s")"
  done
  echo ""
}

ROOT="$(find_root)"
if [[ -z "$ROOT" ]]; then
  echo "nested-repo freshness: SKIP (not inside the Sylveste monorepo — no os/Clavain or interverse+core markers found)"
  exit 0
fi

# --- Configuration ----------------------------------------------------------
# Top-level directories that contain nested subproject repos.
SUBPROJECT_DIRS=(os interverse core sdk apps)

# Critical plugins: those Claude Code loads on every session. A stale checkout
# here means obsolete behavior is live, so flag them louder.
CRITICAL_REPOS=(
  "os/Clavain"
  "interverse/interflux"
  "interverse/interphase"
  "interverse/interspect"
  "interverse/interline"
  "interverse/interlock"
  "interverse/interpath"
  "interverse/interwatch"
  "interverse/interknow"
  "core/intercore"
)

_is_critical() {
  local rel="$1" c
  for c in "${CRITICAL_REPOS[@]}"; do [[ "$rel" == "$c" ]] && return 0; done
  return 1
}

# Untracked paths that are cache/generated/agent-runtime artifacts, not real
# uncommitted work. Matched against the porcelain path (prefix match). These
# are produced by Claude Code, companion plugins, and research tooling and are
# expected to be untracked in every subrepo.
IGNORE_UNTRACKED_PREFIXES=(
  ".claude/"
  ".claude-plugin/hooks/"
  ".clavain/scratch/"
  ".interwatch/"
  ".interfluence/"
  ".serena/"
  ".beads/"
  "docs/research/flux-drive/"
  "docs/research/flux-review/"
  "docs/research/flux-research/"
  "docs/research/flux-explore/"
  "config/flux-drive/knowledge/"
  "__pycache__/"
  ".DS_Store"
)

_untracked_is_ignored() {
  local path="$1" p
  for p in "${IGNORE_UNTRACKED_PREFIXES[@]}"; do
    case "$path" in
      "$p"*) return 0 ;;
      *"/$p"*) return 0 ;;
    esac
  done
  case "$path" in
    */__pycache__/*|*.pyc|*.DS_Store) return 0 ;;
  esac
  return 1
}

# --- Per-repo inspection ----------------------------------------------------
total=0; behind_n=0; dirty_n=0; diverged_n=0; noremote_n=0; offbranch_n=0; clean_n=0
declare -a UPDATE_CMDS=()
declare -a CRITICAL_STALE=()

inspect_repo() {
  local dir="$1" rel="$2"
  total=$((total + 1))

  local branch upstream ahead=0 behind=0
  local -a issues=()
  branch="$(git -C "$dir" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"

  # Remote?
  if ! git -C "$dir" remote 2>/dev/null | grep -q .; then
    issues+=("no-remote")
    noremote_n=$((noremote_n + 1))
  fi

  # Optional fetch for accurate counts.
  if [[ "$FETCH" -eq 1 ]]; then
    git -C "$dir" fetch --quiet --all 2>/dev/null || true
  fi

  # Upstream tracking + ahead/behind.
  upstream="$(git -C "$dir" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || echo '')"
  if [[ -n "$upstream" ]]; then
    local lr
    lr="$(git -C "$dir" rev-list --left-right --count "HEAD...$upstream" 2>/dev/null || echo '0	0')"
    ahead="$(echo "$lr" | awk '{print $1}')"
    behind="$(echo "$lr" | awk '{print $2}')"
    [[ -z "$ahead" ]] && ahead=0
    [[ -z "$behind" ]] && behind=0
    if [[ "$behind" -gt 0 && "$ahead" -gt 0 ]]; then
      issues+=("diverged(+$ahead/-$behind)"); diverged_n=$((diverged_n + 1))
    elif [[ "$behind" -gt 0 ]]; then
      issues+=("behind:$behind"); behind_n=$((behind_n + 1))
      UPDATE_CMDS+=("git -C $rel pull --ff-only")
    elif [[ "$ahead" -gt 0 ]]; then
      issues+=("ahead:$ahead")
    fi
  elif [[ "$branch" != "?" ]]; then
    issues+=("no-upstream")
  fi

  # Off expected default branch (only flag when we have a remote default).
  local def
  def="$(git -C "$dir" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##' || echo '')"
  if [[ -n "$def" && "$branch" != "?" && "$branch" != "$def" ]]; then
    issues+=("branch:$branch!=$def"); offbranch_n=$((offbranch_n + 1))
  fi

  # Dirty tracked changes (modified/added/deleted — porcelain non-?? lines).
  local tracked_changes untracked_real=0
  tracked_changes="$(git -C "$dir" status --porcelain 2>/dev/null | grep -vE '^\?\?' | wc -l | tr -d ' ')"
  if [[ "$tracked_changes" -gt 0 ]]; then
    issues+=("dirty:$tracked_changes"); dirty_n=$((dirty_n + 1))
  fi

  # Untracked files, minus known cache/generated paths.
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    local path="${line#?? }"
    _untracked_is_ignored "$path" || untracked_real=$((untracked_real + 1))
  done < <(git -C "$dir" status --porcelain 2>/dev/null | grep -E '^\?\?')
  if [[ "$untracked_real" -gt 0 ]]; then
    issues+=("untracked:$untracked_real")
  fi

  # Classify + render.
  local critical=0
  _is_critical "$rel" && critical=1
  if [[ "$behind" -gt 0 && "$critical" -eq 1 ]]; then
    CRITICAL_STALE+=("$rel ($behind behind)")
  fi

  if [[ ${#issues[@]} -eq 0 ]]; then
    clean_n=$((clean_n + 1))
    if [[ "$QUIET" -eq 0 ]]; then
      printf "  ${GREEN}%-28s %-8s clean${NC}\n" "$rel" "$branch"
    fi
    return
  fi

  local color="$YELLOW"
  # Behind / no-remote on a critical repo is the loud case.
  if [[ "$behind" -gt 0 ]] && [[ "$critical" -eq 1 ]]; then color="$RED"; fi
  local tag=""
  [[ "$critical" -eq 1 ]] && tag=" ${BOLD}[critical]${NC}"
  printf "  ${color}%-28s %-8s %s${NC}%b\n" "$rel" "$branch" "$(IFS=', '; echo "${issues[*]}")" "$tag"
}

# --- Main loop --------------------------------------------------------------
echo "=== Nested repo freshness (root: $ROOT) ==="
if [[ "$FETCH" -eq 0 ]]; then
  echo "  (using cached refs — pass --fetch for live behind counts)"
fi
echo ""

for top in "${SUBPROJECT_DIRS[@]}"; do
  [[ -d "$ROOT/$top" ]] || continue
  for dir in "$ROOT/$top"/*/; do
    [[ -e "${dir}.git" ]] || continue
    rel="$top/$(basename "$dir")"
    inspect_repo "${dir%/}" "$rel"
  done
done

# --- Summary ----------------------------------------------------------------
echo ""
issue_total=$((behind_n + dirty_n + diverged_n + noremote_n + offbranch_n))
printf "Total: %d repos | clean: %d | behind: %d | dirty: %d | diverged: %d | no-remote: %d | off-branch: %d\n" \
  "$total" "$clean_n" "$behind_n" "$dirty_n" "$diverged_n" "$noremote_n" "$offbranch_n"

if [[ ${#CRITICAL_STALE[@]} -gt 0 ]]; then
  echo ""
  printf "${RED}${BOLD}STALE CRITICAL PLUGINS:${NC}\n"
  for c in "${CRITICAL_STALE[@]}"; do echo "  - $c"; done
  echo "  These load on every session; stale code is live until you fast-forward."
fi

if [[ ${#UPDATE_CMDS[@]} -gt 0 ]]; then
  echo ""
  echo "Safe update commands (fast-forward only):"
  # De-dup while preserving order.
  printf '%s\n' "${UPDATE_CMDS[@]}" | awk '!seen[$0]++ {print "  " $0}'
fi

if [[ "$issue_total" -eq 0 ]]; then
  echo ""
  echo "nested-repo freshness: PASS"
  exit 0
else
  echo ""
  echo "nested-repo freshness: WARN ($issue_total repos need attention)"
  exit 1
fi
