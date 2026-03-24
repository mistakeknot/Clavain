#!/usr/bin/env bash
# check-install-updates.sh — conservative, read-only update notifier for Demarch/Clavain installs
#
# Light mode (default):
# - current Demarch checkout, if detectable from cwd or script source
# - ~/.codex/clavain clone drift vs origin
# - installed Claude plugin cache version vs local ~/.codex/clavain version
#
# Full mode (--full):
# - adds recommended ~/.codex companion repo drift checks
#
# Hook mode (--hook):
# - uses cached results by default
# - prints only when updates or warnings exist

set -euo pipefail

MODE="light"
HOOK_MODE=0
FORCE_REFRESH=0
JSON_MODE=0
TTL_SECONDS="${CLAVAIN_UPDATE_CHECK_TTL_SECONDS:-21600}"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
PLUGIN_CACHE_ROOT="${CLAUDE_PLUGIN_CACHE_ROOT:-$HOME/.claude/plugins/cache}"
CACHE_DIR="${CLAVAIN_UPDATE_CHECK_CACHE_DIR:-$HOME/.cache/clavain}"

usage() {
  cat <<'EOF'
Usage:
  check-install-updates.sh [--hook] [--full] [--refresh] [--json] [--ttl <seconds>]

Options:
  --hook            Print only actionable startup notices; prefer cached results.
  --full            Also check recommended ~/.codex companion repos against origin.
  --refresh         Ignore cache and run checks now.
  --json            Emit JSON instead of text.
  --ttl <seconds>   Cache TTL (default: 21600 / 6h).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hook)
      HOOK_MODE=1
      shift
      ;;
    --full)
      MODE="full"
      shift
      ;;
    --refresh)
      FORCE_REFRESH=1
      shift
      ;;
    --json)
      JSON_MODE=1
      shift
      ;;
    --ttl)
      TTL_SECONDS="${2:?missing value for --ttl}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

mkdir -p "$CACHE_DIR"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

json_escape() {
  local input="$1"
  input="${input//\\/\\\\}"
  input="${input//\"/\\\"}"
  input="${input//$'\n'/\\n}"
  input="${input//$'\r'/}"
  input="${input//$'\t'/\\t}"
  printf '%s' "$input"
}

cache_file() {
  printf '%s/update-check-%s.json' "$CACHE_DIR" "$MODE"
}

semver_newer() {
  local a="$1" b="$2"
  [[ -n "$a" && -n "$b" ]] || return 1
  [[ "$a" == "$b" ]] && return 1
  [[ "$(printf '%s\n%s\n' "$a" "$b" | sort -V | tail -n1)" == "$a" ]]
}

discover_demarch_root() {
  local candidate

  if git_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    if [[ "$(basename "$git_root")" == "Demarch" && -f "$git_root/install.sh" ]]; then
      printf '%s\n' "$git_root"
      return 0
    fi
  fi

  candidate="$(cd "$SCRIPT_DIR/../../.." && pwd 2>/dev/null || true)"
  if [[ -f "$candidate/install.sh" && "$(basename "$candidate")" == "Demarch" ]]; then
    printf '%s\n' "$candidate"
    return 0
  fi

  return 1
}

local_clavain_root() {
  local candidate="$CODEX_HOME/clavain"
  if [[ -d "$candidate/.git" ]]; then
    printf '%s\n' "$candidate"
    return 0
  fi
  return 1
}

installed_clavain_version() {
  local latest=""
  local path version
  for path in "$PLUGIN_CACHE_ROOT"/*/clavain/*; do
    [[ -d "$path" ]] || continue
    version="$(basename "$path")"
    if [[ -z "$latest" ]] || semver_newer "$version" "$latest"; then
      latest="$version"
    fi
  done
  [[ -n "$latest" ]] && printf '%s\n' "$latest"
}

repo_remote_diff_status() {
  local repo="$1"
  local upstream branch local_sha remote_sha remote_ref

  [[ -d "$repo/.git" ]] || return 2

  local_sha="$(git -C "$repo" rev-parse HEAD 2>/dev/null || true)"
  [[ -n "$local_sha" ]] || return 2

  upstream="$(git -C "$repo" rev-parse --abbrev-ref --symbolic-full-name @{upstream} 2>/dev/null || true)"
  if [[ -z "$upstream" ]]; then
    remote_ref="$(git ls-remote --symref origin HEAD 2>/dev/null | awk '/^ref:/ {sub("refs/heads/", "", $2); print $2; exit}')"
    [[ -n "$remote_ref" ]] || remote_ref="main"
    upstream="origin/$remote_ref"
  fi

  branch="${upstream#origin/}"
  remote_sha="$(git ls-remote origin "refs/heads/$branch" 2>/dev/null | awk 'NR==1 {print $1}')"
  [[ -n "$remote_sha" ]] || return 3

  if [[ "$local_sha" == "$remote_sha" ]]; then
    return 0
  fi
  return 1
}

repo_dirty_status() {
  local repo="$1"
  git -C "$repo" status --porcelain --untracked-files=no 2>/dev/null \
    | grep -vE '^[ MADRCU?!]{2} \.beads/backup/' \
    | grep -q .
}

append_result() {
  local severity="$1" key="$2" label="$3" status="$4" summary="$5" action="$6"
  RESULTS+=("$(printf '%s|%s|%s|%s|%s|%s' "$severity" "$key" "$label" "$status" "$summary" "$action")")
}

check_git_repo() {
  local key="$1" label="$2" repo="$3" action="$4"
  if [[ ! -d "$repo/.git" ]]; then
    return 0
  fi

  local dirty="false"
  if repo_dirty_status "$repo"; then
    dirty="true"
  fi

  if repo_remote_diff_status "$repo"; then
    if [[ "$dirty" == "true" ]]; then
      append_result "warn" "$key" "$label" "dirty-local" "local repo has uncommitted changes; update safely before pulling" "$action"
    fi
    return 0
  fi

  local status=$?
  case "$status" in
    1)
      if [[ "$dirty" == "true" ]]; then
        append_result "warn" "$key" "$label" "behind-and-dirty" "origin differs from local HEAD and the repo has uncommitted changes" "$action"
      else
        append_result "info" "$key" "$label" "behind" "origin differs from local HEAD" "$action"
      fi
      ;;
    3)
      append_result "warn" "$key" "$label" "check-failed" "could not resolve origin branch head" "$action"
      ;;
    *)
      append_result "warn" "$key" "$label" "check-failed" "could not inspect repo update status" "$action"
      ;;
  esac
}

recommended_plugins() {
  local rig=""
  if [[ -f "$CODEX_HOME/clavain/agent-rig.json" ]]; then
    rig="$CODEX_HOME/clavain/agent-rig.json"
  elif [[ -f "$SCRIPT_DIR/../agent-rig.json" ]]; then
    rig="$SCRIPT_DIR/../agent-rig.json"
  fi

  if [[ -n "$rig" && -f "$rig" ]]; then
    jq -r '
      .plugins.recommended[]?
      | .source // empty
      | select(endswith("@interagency-marketplace"))
      | split("@")[0]
    ' "$rig" | sort -u
    return
  fi

  cat <<'EOF'
interdoc
interflux
interphase
interline
interpath
interwatch
interlock
intercheck
tldr-swinton
tool-time
interslack
interform
intercraft
interdev
interdeep
interknow
intermonk
intername
interplug
interpulse
interrank
interscribe
intersense
intership
intersight
interskill
intertest
interpeer
intersynth
intermap
internext
intermem
interspect
intertrace
intertrack
intertree
intertrust
EOF
}

run_checks() {
  RESULTS=()

  local demarch_root=""
  if demarch_root="$(discover_demarch_root)"; then
    check_git_repo \
      "demarch_repo" \
      "Demarch checkout" \
      "$demarch_root" \
      "cd \"$demarch_root\" && bash install.sh --update"
  fi

  local clavain_root=""
  if clavain_root="$(local_clavain_root)"; then
    check_git_repo \
      "codex_clavain_clone" \
      "Codex Clavain clone" \
      "$clavain_root" \
      "git -C \"$clavain_root\" pull --ff-only && bash \"$clavain_root/scripts/install-codex-interverse.sh\" install --source \"$clavain_root\""

    local clone_version installed_version
    clone_version="$(jq -r '.version // empty' "$clavain_root/.claude-plugin/plugin.json" 2>/dev/null || true)"
    installed_version="$(installed_clavain_version || true)"
    if [[ -n "$clone_version" && -n "$installed_version" ]] && semver_newer "$clone_version" "$installed_version"; then
      append_result \
        "info" \
        "claude_plugin_version" \
        "Installed Claude plugin" \
        "version-behind" \
        "installed plugin cache is $installed_version, local Clavain clone is $clone_version" \
        "claude plugin marketplace update interagency-marketplace && claude plugin update clavain@interagency-marketplace"
    fi
  fi

  if [[ "$MODE" == "full" ]]; then
    local plugin repo
    while IFS= read -r plugin; do
      [[ -n "$plugin" ]] || continue
      repo="$CODEX_HOME/$plugin"
      check_git_repo \
        "companion_${plugin}" \
        "Companion repo: $plugin" \
        "$repo" \
        "git -C \"$repo\" pull --ff-only"
    done < <(recommended_plugins)
  fi
}

write_cache() {
  local file now status updates warnings
  file="$(cache_file)"
  now="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  updates=0
  warnings=0

  local entry severity key label st summary action
  for entry in "${RESULTS[@]}"; do
    IFS='|' read -r severity key label st summary action <<< "$entry"
    [[ "$severity" == "warn" ]] && warnings=$((warnings + 1))
    [[ "$st" == "behind" || "$st" == "behind-and-dirty" || "$st" == "version-behind" ]] && updates=$((updates + 1))
  done

  status="ok"
  [[ "$updates" -gt 0 ]] && status="updates-available"
  [[ "$warnings" -gt 0 ]] && status="attention-needed"

  {
    printf '{\n'
    printf '  "checked_at":"%s",\n' "$now"
    printf '  "mode":"%s",\n' "$MODE"
    printf '  "status":"%s",\n' "$status"
    printf '  "update_count":%s,\n' "$updates"
    printf '  "warning_count":%s,\n' "$warnings"
    printf '  "results":[\n'
    local comma=""
    for entry in "${RESULTS[@]}"; do
      IFS='|' read -r severity key label st summary action <<< "$entry"
      printf '%s    {"severity":"%s","key":"%s","label":"%s","status":"%s","summary":"%s","action":"%s"}\n' \
        "$comma" \
        "$(json_escape "$severity")" \
        "$(json_escape "$key")" \
        "$(json_escape "$label")" \
        "$(json_escape "$st")" \
        "$(json_escape "$summary")" \
        "$(json_escape "$action")"
      comma=","
    done
    printf '  ]\n'
    printf '}\n'
  } > "$file"
}

cache_fresh() {
  local file="$1"
  [[ -f "$file" ]] || return 1
  local modified now age
  modified="$(stat -c %Y "$file" 2>/dev/null || stat -f %m "$file" 2>/dev/null || echo 0)"
  now="$(date +%s)"
  age=$((now - modified))
  [[ "$age" -lt "$TTL_SECONDS" ]]
}

load_or_refresh() {
  local file
  file="$(cache_file)"

  if [[ "$FORCE_REFRESH" -eq 0 ]] && cache_fresh "$file"; then
    cat "$file"
    return 0
  fi

  run_checks
  write_cache
  cat "$file"
}

render_text() {
  local json="$1"
  local checked_at status update_count warning_count
  checked_at="$(jq -r '.checked_at' <<< "$json")"
  status="$(jq -r '.status' <<< "$json")"
  update_count="$(jq -r '.update_count // 0' <<< "$json")"
  warning_count="$(jq -r '.warning_count // 0' <<< "$json")"

  echo "Conservative update check (${MODE})"
  echo "Checked: $checked_at"
  echo

  if [[ "$status" == "ok" ]]; then
    echo "No update drift detected."
    return 0
  fi

  jq -r '
    .results[]
    | "- \(.label): \(.summary)"
    | @text
  ' <<< "$json"
  echo
  echo "Suggested actions:"
  jq -r '
    .results[]
    | select(.action != "")
    | "  " + .action
  ' <<< "$json" | awk '!seen[$0]++'
}

render_hook_notice() {
  local json="$1"
  local status
  status="$(jq -r '.status' <<< "$json")"
  [[ "$status" == "ok" ]] && return 0

  local notices
  notices="$(jq -r '
    [.results[]
     | select(.status == "behind" or .status == "behind-and-dirty" or .status == "version-behind" or .severity == "warn")
     | "\(.label): \(.summary)"]
    | .[0:3]
    | join("; ")
  ' <<< "$json")"

  [[ -n "$notices" ]] || return 0

  echo "Demarch update check: $notices" >&2
  echo "Run: bash ~/.codex/clavain/scripts/check-install-updates.sh --full --refresh" >&2
  if demarch_root="$(discover_demarch_root)"; then
    echo "Apply Demarch updates from checkout: cd \"$demarch_root\" && bash install.sh --update" >&2
  fi
}

main() {
  local json
  json="$(load_or_refresh)"

  if [[ "$JSON_MODE" -eq 1 ]]; then
    printf '%s\n' "$json"
    return 0
  fi

  if [[ "$HOOK_MODE" -eq 1 ]]; then
    render_hook_notice "$json"
    return 0
  fi

  render_text "$json"
}

main
