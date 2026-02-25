#!/usr/bin/env bash
# Install Clavain + curated Interverse Codex skills via native skill discovery.
#
# What this script sets up:
# - Runs Clavain Codex install/doctor via scripts/install-codex.sh
# - Installs companion skill links in ~/.agents/skills:
#   - interdoc
#   - tool-time (Codex variant)
#   - tldrs-agent-workflow
# - Cleans up legacy ~/.codex/skills/<name> symlinks (symlink-only, safe)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

ACTION="install"
if [[ $# -gt 0 && "${1#-}" == "$1" ]]; then
  ACTION="$1"
  shift
fi

CLONE_ROOT="${CLAVAIN_CLONE_ROOT:-$HOME/.codex}"
SKILLS_DIR="${AGENTS_SKILLS_DIR:-$HOME/.agents/skills}"
LEGACY_SKILLS_DIR="${CODEX_SKILLS_DIR:-$HOME/.codex/skills}"
INSTALL_PROMPTS=1
DOCTOR_JSON=0

companion_specs() {
  # name|repo_url|skill_rel_path|link_name
  cat <<'EOF'
interdoc|https://github.com/mistakeknot/interdoc.git|skills/interdoc|interdoc
tool-time|https://github.com/mistakeknot/tool-time.git|skills/tool-time-codex|tool-time
tldr-swinton|https://github.com/mistakeknot/tldr-swinton.git|.codex/skills/tldrs-agent-workflow|tldrs-agent-workflow
EOF
}

usage() {
  cat <<'EOF'
Usage:
  install-codex-interverse.sh install [options]
  install-codex-interverse.sh update [options]
  install-codex-interverse.sh doctor [options]
  install-codex-interverse.sh uninstall [options]

Options:
  --source <path>             Clavain checkout path (default: script parent)
  --clone-root <path>         Clone root for companion repos (default: ~/.codex)
  --skills-dir <path>         Codex native skills dir (default: ~/.agents/skills)
  --legacy-skills-dir <path>  Legacy skills dir for symlink cleanup (default: ~/.codex/skills)
  --no-prompts                Skip Clavain prompt wrapper generation
  --json                      Emit doctor output as JSON
  -h, --help                  Show this help

Notes:
  - Native Codex skill discovery path is ~/.agents/skills
  - Legacy ~/.codex/skills links are removed only when they are symlinks
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source)
      SOURCE_DIR="${2:?missing value for --source}"
      shift 2
      ;;
    --clone-root)
      CLONE_ROOT="${2:?missing value for --clone-root}"
      shift 2
      ;;
    --skills-dir)
      SKILLS_DIR="${2:?missing value for --skills-dir}"
      shift 2
      ;;
    --legacy-skills-dir)
      LEGACY_SKILLS_DIR="${2:?missing value for --legacy-skills-dir}"
      shift 2
      ;;
    --no-prompts)
      INSTALL_PROMPTS=0
      shift
      ;;
    --json)
      DOCTOR_JSON=1
      shift
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

SOURCE_DIR="$(cd "$SOURCE_DIR" && pwd)"

is_clavain_root() {
  local dir="$1"
  [[ -f "$dir/README.md" && -d "$dir/skills" && -d "$dir/commands" && -d "$dir/scripts" ]]
}

json_escape() {
  local input="$1"
  input="${input//\\/\\\\}"
  input="${input//\"/\\\"}"
  input="${input//$'\n'/\\n}"
  input="${input//$'\r'/}"
  input="${input//$'\t'/\\t}"
  printf '%s' "$input"
}

safe_link() {
  local target="$1"
  local link_path="$2"
  mkdir -p "$(dirname "$link_path")"

  if [[ -L "$link_path" ]]; then
    local current
    current="$(readlink "$link_path")"
    if [[ "$current" == "$target" ]]; then
      return 0
    fi
    rm -f "$link_path"
  elif [[ -e "$link_path" ]]; then
    echo "Non-symlink path blocks install: $link_path" >&2
    return 1
  fi

  ln -s "$target" "$link_path"
  return 0
}

cleanup_legacy_link() {
  local link_name="$1"
  local legacy_path="$LEGACY_SKILLS_DIR/$link_name"
  if [[ -L "$legacy_path" ]]; then
    rm -f "$legacy_path"
    echo "Removed legacy symlink: $legacy_path"
  elif [[ -e "$legacy_path" ]]; then
    echo "Legacy path exists as non-symlink; skipped cleanup: $legacy_path" >&2
  fi
}

cleanup_legacy_predecessors() {
  # Remove superpowers and compound-engineering artifacts that conflict with Clavain.
  # Only removes symlinks and known safe targets; warns about manual cleanup needed.
  local cleaned=0

  # 1. Superpowers Codex skills (real dirs installed by superpowers bootstrap)
  local sp_skills_dir="$LEGACY_SKILLS_DIR"
  local sp_known_skills=(interpeer cloudflare-deploy security-best-practices security-ownership-map)
  for skill in "${sp_known_skills[@]}"; do
    local skill_path="$sp_skills_dir/$skill"
    if [[ -L "$skill_path" ]]; then
      rm -f "$skill_path"
      echo "Removed legacy superpowers skill symlink: $skill_path"
      cleaned=$((cleaned + 1))
    elif [[ -d "$skill_path" ]]; then
      echo "Legacy superpowers skill directory found: $skill_path (remove manually if unwanted)"
    fi
  done

  # 2. Superpowers prompt wrappers (non-Clavain prompts in ~/.codex/prompts)
  local prompts_dir="${CODEX_PROMPTS_DIR:-$HOME/.codex/prompts}"
  if [[ -d "$prompts_dir" ]]; then
    local pf
    for pf in "$prompts_dir"/*.md; do
      [[ -f "$pf" ]] || continue
      local base
      base="$(basename "$pf")"
      # Keep clavain-* prompts, remove known superpowers/compound prompts
      case "$base" in
        clavain-*) continue ;;
        workflows-compound.md|workflows-brainstorm.md|workflows-plan.md|workflows-review.md|workflows-work.md)
          rm -f "$pf"
          echo "Removed legacy prompt wrapper: $pf"
          cleaned=$((cleaned + 1))
          ;;
        agent-native-audit.md|changelog.md|create-agent-skill.md|deepen-plan.md|deploy-docs.md|feature-video.md|generate_command.md|heal-skill.md|lfg.md|plan_review.md|release-docs.md|report-bug.md|reproduce-bug.md|resolve_parallel.md|resolve_pr_parallel.md|resolve_todo_parallel.md|test-browser.md|triage.md|xcode-test.md)
          rm -f "$pf"
          echo "Removed legacy prompt wrapper: $pf"
          cleaned=$((cleaned + 1))
          ;;
      esac
    done
  fi

  # 3. Superpowers clone directory
  local sp_clone="$CLONE_ROOT/superpowers"
  if [[ -d "$sp_clone/.git" ]]; then
    local sp_remote
    sp_remote="$(git -C "$sp_clone" remote get-url origin 2>/dev/null || true)"
    if [[ "$sp_remote" == *"superpowers"* ]]; then
      echo "Legacy superpowers clone found: $sp_clone (remove with: rm -rf $sp_clone)"
    fi
  fi

  if [[ "$cleaned" -gt 0 ]]; then
    echo "Cleaned $cleaned legacy superpowers/compound artifacts."
  fi
}

ensure_repo() {
  local name="$1" repo_url="$2"
  local repo_dir="$CLONE_ROOT/$name"
  mkdir -p "$CLONE_ROOT"

  if [[ -d "$repo_dir/.git" ]]; then
    echo "Updating $name in $repo_dir"
    git -C "$repo_dir" pull --ff-only
    return 0
  fi

  if [[ -e "$repo_dir" ]]; then
    echo "Refusing to clone into existing non-git path: $repo_dir" >&2
    return 1
  fi

  echo "Cloning $repo_url -> $repo_dir"
  git clone "$repo_url" "$repo_dir"
}

install_companions() {
  local failures=0
  local name repo_url skill_rel link_name

  while IFS='|' read -r name repo_url skill_rel link_name; do
    [[ -n "$name" ]] || continue
    local repo_dir="$CLONE_ROOT/$name"
    local skill_target="$repo_dir/$skill_rel"
    local link_path="$SKILLS_DIR/$link_name"

    if ! ensure_repo "$name" "$repo_url"; then
      failures=$((failures + 1))
      continue
    fi

    if [[ ! -d "$skill_target" ]]; then
      echo "Missing skill path for $name: $skill_target" >&2
      failures=$((failures + 1))
      continue
    fi

    if ! safe_link "$skill_target" "$link_path"; then
      failures=$((failures + 1))
      continue
    fi

    cleanup_legacy_link "$link_name"
    echo "Linked: $link_path -> $skill_target"
  done < <(companion_specs)

  return "$failures"
}

clavain_install() {
  local args=(install --source "$SOURCE_DIR")
  if [[ "$INSTALL_PROMPTS" -eq 0 ]]; then
    args+=(--no-prompts)
  fi
  AGENTS_SKILLS_DIR="$SKILLS_DIR" \
  CODEX_SKILLS_DIR="$LEGACY_SKILLS_DIR" \
  bash "$SOURCE_DIR/scripts/install-codex.sh" "${args[@]}"
}

clavain_doctor() {
  local args=(doctor --source "$SOURCE_DIR")
  if [[ "$DOCTOR_JSON" -eq 1 ]]; then
    args+=(--json)
  fi
  AGENTS_SKILLS_DIR="$SKILLS_DIR" \
  CODEX_SKILLS_DIR="$LEGACY_SKILLS_DIR" \
  bash "$SOURCE_DIR/scripts/install-codex.sh" "${args[@]}"
}

doctor_companions_text() {
  local status=0
  local name repo_url skill_rel link_name

  echo "== Interverse Codex Companion Doctor =="
  echo "Clone root: $CLONE_ROOT"
  echo "Skills dir: $SKILLS_DIR"
  echo

  while IFS='|' read -r name repo_url skill_rel link_name; do
    [[ -n "$name" ]] || continue
    local repo_dir="$CLONE_ROOT/$name"
    local skill_target="$repo_dir/$skill_rel"
    local link_path="$SKILLS_DIR/$link_name"
    local ok=true

    if [[ ! -d "$repo_dir/.git" ]]; then
      echo "[FAIL] repo missing: $repo_dir"
      ok=false
    fi
    if [[ ! -d "$skill_target" ]]; then
      echo "[FAIL] skill missing: $skill_target"
      ok=false
    fi
    if [[ -L "$link_path" ]]; then
      local resolved
      resolved="$(readlink -f "$link_path" 2>/dev/null || true)"
      if [[ "$resolved" != "$skill_target" ]]; then
        echo "[FAIL] link mismatch: $link_path -> $resolved (expected $skill_target)"
        ok=false
      fi
    else
      echo "[FAIL] link missing: $link_path"
      ok=false
    fi

    if [[ "$ok" == true ]]; then
      echo "[OK]   $name"
    else
      status=1
    fi
  done < <(companion_specs)

  return "$status"
}

doctor_companions_json() {
  local status=0
  local first=true
  local name repo_url skill_rel link_name
  local array_file
  array_file="$(mktemp)"

  printf '[\n' > "$array_file"

  while IFS='|' read -r name repo_url skill_rel link_name; do
    [[ -n "$name" ]] || continue
    local repo_dir="$CLONE_ROOT/$name"
    local skill_target="$repo_dir/$skill_rel"
    local link_path="$SKILLS_DIR/$link_name"
    local repo_ok=false
    local skill_ok=false
    local link_ok=false
    local target=""

    [[ -d "$repo_dir/.git" ]] && repo_ok=true
    [[ -d "$skill_target" ]] && skill_ok=true
    if [[ -L "$link_path" ]]; then
      target="$(readlink -f "$link_path" 2>/dev/null || true)"
      if [[ "$target" == "$skill_target" ]]; then
        link_ok=true
      fi
    fi

    if [[ "$repo_ok" != true || "$skill_ok" != true || "$link_ok" != true ]]; then
      status=1
    fi

    if [[ "$first" != true ]]; then
      printf ',\n' >> "$array_file"
    fi
    first=false

    printf '    {\n' >> "$array_file"
    printf '      "name":"%s",\n' "$(json_escape "$name")" >> "$array_file"
    printf '      "repo_dir":"%s",\n' "$(json_escape "$repo_dir")" >> "$array_file"
    printf '      "skill_path":"%s",\n' "$(json_escape "$skill_target")" >> "$array_file"
    printf '      "link_path":"%s",\n' "$(json_escape "$link_path")" >> "$array_file"
    printf '      "link_target":"%s",\n' "$(json_escape "$target")" >> "$array_file"
    printf '      "repo_ok":%s,\n' "$repo_ok" >> "$array_file"
    printf '      "skill_ok":%s,\n' "$skill_ok" >> "$array_file"
    printf '      "link_ok":%s\n' "$link_ok" >> "$array_file"
    printf '    }' >> "$array_file"
  done < <(companion_specs)

  printf '\n  ]\n' >> "$array_file"

  local status_text="ok"
  if [[ "$status" -ne 0 ]]; then
    status_text="fail"
  fi

  printf '{\n'
  printf '  "status":"%s",\n' "$status_text"
  printf '  "clone_root":"%s",\n' "$(json_escape "$CLONE_ROOT")"
  printf '  "skills_dir":"%s",\n' "$(json_escape "$SKILLS_DIR")"
  printf '  "companions":'
  cat "$array_file"
  printf '}\n'

  rm -f "$array_file"

  return "$status"
}

if ! is_clavain_root "$SOURCE_DIR"; then
  echo "Invalid Clavain source directory: $SOURCE_DIR" >&2
  exit 1
fi

case "$ACTION" in
  install|update)
    cleanup_legacy_predecessors
    clavain_install
    if install_companions; then
      echo "Interverse companion skills installed."
      echo "Restart Codex so it reloads discovered skills."
      exit 0
    fi
    echo "Interverse companion install completed with errors." >&2
    exit 1
    ;;
  doctor)
    status=0

    if [[ "$DOCTOR_JSON" -eq 1 ]]; then
      if ! clavain_doctor >/tmp/clavain-codex-doctor.$$.json 2>/tmp/clavain-codex-doctor.$$.err; then
        status=1
      fi
      if ! doctor_companions_json >/tmp/interverse-codex-doctor.$$.json; then
        status=1
      fi

      if command -v jq >/dev/null 2>&1; then
        jq -n \
          --slurpfile clavain /tmp/clavain-codex-doctor.$$.json \
          --slurpfile companions /tmp/interverse-codex-doctor.$$.json \
          '{
             status: (if (($clavain[0].status // "fail") == "ok" and ($companions[0].status // "fail") == "ok") then "ok" else "fail" end),
             clavain: ($clavain[0] // {}),
             interverse_companions: ($companions[0] // {})
           }'
      else
        echo '{"status":"fail","error":"jq is required for --json composite output"}'
        status=1
      fi

      rm -f /tmp/clavain-codex-doctor.$$.json /tmp/clavain-codex-doctor.$$.err /tmp/interverse-codex-doctor.$$.json
      exit "$status"
    fi

    if ! clavain_doctor; then
      status=1
    fi
    echo
    if ! doctor_companions_text; then
      status=1
    fi
    exit "$status"
    ;;
  uninstall)
    local_failed=0
    while IFS='|' read -r name repo_url skill_rel link_name; do
      [[ -n "$name" ]] || continue
      rm -f "$SKILLS_DIR/$link_name" || local_failed=1
      cleanup_legacy_link "$link_name"
      echo "Removed skill link: $SKILLS_DIR/$link_name"
    done < <(companion_specs)

    if [[ "$local_failed" -eq 0 ]]; then
      echo "Interverse companion skill links removed."
      exit 0
    fi
    echo "Uninstall completed with errors." >&2
    exit 1
    ;;
  *)
    echo "Unknown action: $ACTION" >&2
    usage >&2
    exit 1
    ;;
esac
