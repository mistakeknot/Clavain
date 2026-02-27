#!/usr/bin/env bash
# Install Clavain + Interverse recommended Codex capabilities via native skill discovery.
#
# What this script sets up:
# - Runs Clavain Codex install/doctor via scripts/install-codex.sh
# - Ensures all Interverse plugins in agent-rig.json (recommended tier) are cloned under ~/.codex
# - Installs Codex skill links for companion plugins that expose SKILL.md entrypoints
# - Cleans up legacy ~/.codex/skills/<name> paths (symlink or directory)
#   using backup-first removal

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
BACKUP_ROOT="${CLAVAIN_BACKUP_ROOT:-$CLONE_ROOT/.clavain-backups}"
INSTALL_PROMPTS=1
DOCTOR_JSON=0
BACKUP_SESSION_ROOT=""

recommended_interverse_plugins_fallback() {
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
intertest
interpeer
intersynth
intermap
internext
intermem
EOF
}

interverse_recommended_plugins() {
  local rig="$SOURCE_DIR/agent-rig.json"
  if command -v jq >/dev/null 2>&1 && [[ -f "$rig" ]]; then
    jq -r '
      .plugins.recommended[]?
      | .source // empty
      | select(endswith("@interagency-marketplace"))
      | split("@")[0]
    ' "$rig" | sort -u
    return
  fi
  recommended_interverse_plugins_fallback
}

skill_specs() {
  # plugin_name|skill_rel_path|link_name
  cat <<'EOF'
interdoc|skills/interdoc|interdoc
interflux|skills/flux-drive|flux-drive
interflux|skills/flux-research|flux-research
interphase|skills/beads-workflow|beads-workflow
interpath|skills/artifact-gen|artifact-gen
interwatch|skills/doc-watch|doc-watch
interlock|skills/coordination-protocol|coordination-protocol
interlock|skills/conflict-recovery|conflict-recovery
intercheck|skills/status|status
tldr-swinton|.codex/skills/tldrs-agent-workflow|tldrs-agent-workflow
tool-time|skills/tool-time-codex|tool-time
interslack|skills/slack-messaging|slack-messaging
interform|skills/distinctive-design|distinctive-design
intercraft|skills/agent-native-architecture|agent-native-architecture
interdev|skills/mcp-cli|mcp-cli
interdev|skills/working-with-claude-code|working-with-claude-code
intertest|skills/systematic-debugging|systematic-debugging
intertest|skills/test-driven-development|test-driven-development
intertest|skills/verification-before-completion|verification-before-completion
interpeer|skills/interpeer|interpeer
internext|skills/next-work|next-work
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
  - Recommended Interverse plugin list comes from agent-rig.json (fallback list if jq is unavailable)
  - Legacy ~/.codex/skills paths are removed with backup-first safety
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

plugin_repo_url() {
  local plugin="$1"
  printf 'https://github.com/mistakeknot/%s.git' "$plugin"
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

start_backup_session() {
  if [[ -n "$BACKUP_SESSION_ROOT" ]]; then
    return 0
  fi
  local ts
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  BACKUP_SESSION_ROOT="$BACKUP_ROOT/$ts"
  mkdir -p "$BACKUP_SESSION_ROOT"
}

backup_move_path() {
  local src="$1"
  [[ -e "$src" || -L "$src" ]] || return 0
  start_backup_session
  local dest="$BACKUP_SESSION_ROOT/${src#/}"
  mkdir -p "$(dirname "$dest")"
  mv "$src" "$dest"
  echo "Moved to backup: $src -> $dest"
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
  if [[ -L "$legacy_path" || -e "$legacy_path" ]]; then
    backup_move_path "$legacy_path"
  fi
}

cleanup_legacy_predecessors() {
  # Remove superpowers and compound-engineering artifacts that conflict with Clavain.
  # Clean-break mode removes known legacy targets using backup-first semantics.
  local cleaned=0

  # 1. Superpowers Codex skills (real dirs installed by superpowers bootstrap)
  local sp_skills_dir="$LEGACY_SKILLS_DIR"
  local sp_known_skills=(interpeer cloudflare-deploy security-best-practices security-ownership-map)
  for skill in "${sp_known_skills[@]}"; do
    local skill_path="$sp_skills_dir/$skill"
    if [[ -L "$skill_path" || -d "$skill_path" || -f "$skill_path" ]]; then
      backup_move_path "$skill_path"
      cleaned=$((cleaned + 1))
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
          backup_move_path "$pf"
          cleaned=$((cleaned + 1))
          ;;
        agent-native-audit.md|changelog.md|create-agent-skill.md|deepen-plan.md|deploy-docs.md|feature-video.md|generate_command.md|heal-skill.md|lfg.md|plan_review.md|release-docs.md|report-bug.md|reproduce-bug.md|resolve_parallel.md|resolve_pr_parallel.md|resolve_todo_parallel.md|test-browser.md|triage.md|xcode-test.md)
          backup_move_path "$pf"
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
      backup_move_path "$sp_clone"
      cleaned=$((cleaned + 1))
    fi
  fi

  if [[ "$cleaned" -gt 0 ]]; then
    echo "Cleaned $cleaned legacy superpowers/compound artifacts (backup-first)."
  fi

  # 4. Broken Intermem skill link cleanup (SKILL.md lacks required frontmatter).
  local intermem_link="$SKILLS_DIR/synthesize"
  if [[ -L "$intermem_link" ]]; then
    local resolved
    resolved="$(readlink -f "$intermem_link" 2>/dev/null || true)"
    if [[ "$resolved" == "$CLONE_ROOT/intermem/skills/synthesize" ]]; then
      rm -f "$intermem_link"
      echo "Removed invalid intermem skill link: $intermem_link"
    fi
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

ensure_recommended_repos() {
  local failures=0
  local plugin repo_url

  while IFS= read -r plugin; do
    [[ -n "$plugin" ]] || continue
    repo_url="$(plugin_repo_url "$plugin")"
    if ! ensure_repo "$plugin" "$repo_url"; then
      failures=$((failures + 1))
    fi
  done < <(interverse_recommended_plugins)

  return "$failures"
}

install_skill_links() {
  local failures=0
  local plugin skill_rel link_name
  declare -A seen_links=()

  while IFS='|' read -r plugin skill_rel link_name; do
    [[ -n "$plugin" ]] || continue

    local repo_dir="$CLONE_ROOT/$plugin"
    local skill_target="$repo_dir/$skill_rel"
    local link_path="$SKILLS_DIR/$link_name"

    if [[ ! -d "$repo_dir/.git" ]]; then
      echo "Missing repo for skill link ($plugin): $repo_dir" >&2
      failures=$((failures + 1))
      continue
    fi

    if [[ ! -d "$skill_target" ]]; then
      echo "Missing skill path for $plugin: $skill_target" >&2
      failures=$((failures + 1))
      continue
    fi

    if [[ -n "${seen_links[$link_name]+set}" && "${seen_links[$link_name]}" != "$skill_target" ]]; then
      echo "Conflicting link target for $link_name: ${seen_links[$link_name]} vs $skill_target" >&2
      failures=$((failures + 1))
      continue
    fi
    seen_links["$link_name"]="$skill_target"

    if ! safe_link "$skill_target" "$link_path"; then
      failures=$((failures + 1))
      continue
    fi

    cleanup_legacy_link "$link_name"
    echo "Linked: $link_path -> $skill_target"
  done < <(skill_specs)

  return "$failures"
}

install_companions() {
  local repo_failures=0
  local link_failures=0

  if ensure_recommended_repos; then
    repo_failures=0
  else
    repo_failures=$?
  fi
  if install_skill_links; then
    link_failures=0
  else
    link_failures=$?
  fi

  if [[ "$repo_failures" -ne 0 || "$link_failures" -ne 0 ]]; then
    echo "Install failures: repos=$repo_failures skill_links=$link_failures" >&2
    return 1
  fi
  return 0
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
  local plugin skill_rel link_name

  echo "== Interverse Codex Companion Doctor =="
  echo "Clone root: $CLONE_ROOT"
  echo "Skills dir: $SKILLS_DIR"
  echo
  echo "-- Recommended Interverse plugins --"

  while IFS= read -r plugin; do
    [[ -n "$plugin" ]] || continue
    local repo_dir="$CLONE_ROOT/$plugin"
    if [[ -d "$repo_dir/.git" ]]; then
      echo "[OK]   repo: $plugin"
    else
      echo "[FAIL] repo missing: $repo_dir"
      status=1
    fi
  done < <(interverse_recommended_plugins)

  echo
  echo "-- Skill links --"
  while IFS='|' read -r plugin skill_rel link_name; do
    [[ -n "$plugin" ]] || continue
    local repo_dir="$CLONE_ROOT/$plugin"
    local skill_target="$repo_dir/$skill_rel"
    local link_path="$SKILLS_DIR/$link_name"
    local ok=true

    if [[ ! -d "$repo_dir/.git" ]]; then
      echo "[FAIL] repo missing for skill: $repo_dir"
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
      echo "[OK]   skill: $link_name ($plugin)"
    else
      status=1
    fi
  done < <(skill_specs)

  return "$status"
}

doctor_companions_json() {
  local status=0
  local plugin skill_rel link_name
  local plugins_file skills_file
  local plugin_count=0
  local skill_count=0

  plugins_file="$(mktemp)"
  skills_file="$(mktemp)"
  printf '[\n' > "$plugins_file"
  printf '[\n' > "$skills_file"

  local first=true
  while IFS= read -r plugin; do
    [[ -n "$plugin" ]] || continue
    local repo_dir="$CLONE_ROOT/$plugin"
    local repo_ok=false
    local repo_url
    repo_url="$(plugin_repo_url "$plugin")"

    [[ -d "$repo_dir/.git" ]] && repo_ok=true
    if [[ "$repo_ok" != true ]]; then
      status=1
    fi

    if [[ "$first" != true ]]; then
      printf ',\n' >> "$plugins_file"
    fi
    first=false

    printf '    {\n' >> "$plugins_file"
    printf '      "name":"%s",\n' "$(json_escape "$plugin")" >> "$plugins_file"
    printf '      "repo_url":"%s",\n' "$(json_escape "$repo_url")" >> "$plugins_file"
    printf '      "repo_dir":"%s",\n' "$(json_escape "$repo_dir")" >> "$plugins_file"
    printf '      "repo_ok":%s\n' "$repo_ok" >> "$plugins_file"
    printf '    }' >> "$plugins_file"
    plugin_count=$((plugin_count + 1))
  done < <(interverse_recommended_plugins)
  printf '\n  ]\n' >> "$plugins_file"

  first=true
  while IFS='|' read -r plugin skill_rel link_name; do
    [[ -n "$plugin" ]] || continue
    local repo_dir="$CLONE_ROOT/$plugin"
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
      printf ',\n' >> "$skills_file"
    fi
    first=false

    printf '    {\n' >> "$skills_file"
    printf '      "plugin":"%s",\n' "$(json_escape "$plugin")" >> "$skills_file"
    printf '      "link_name":"%s",\n' "$(json_escape "$link_name")" >> "$skills_file"
    printf '      "repo_dir":"%s",\n' "$(json_escape "$repo_dir")" >> "$skills_file"
    printf '      "skill_path":"%s",\n' "$(json_escape "$skill_target")" >> "$skills_file"
    printf '      "link_path":"%s",\n' "$(json_escape "$link_path")" >> "$skills_file"
    printf '      "link_target":"%s",\n' "$(json_escape "$target")" >> "$skills_file"
    printf '      "repo_ok":%s,\n' "$repo_ok" >> "$skills_file"
    printf '      "skill_ok":%s,\n' "$skill_ok" >> "$skills_file"
    printf '      "link_ok":%s\n' "$link_ok" >> "$skills_file"
    printf '    }' >> "$skills_file"
    skill_count=$((skill_count + 1))
  done < <(skill_specs)
  printf '\n  ]\n' >> "$skills_file"

  local status_text="ok"
  if [[ "$status" -ne 0 ]]; then
    status_text="fail"
  fi

  printf '{\n'
  printf '  "status":"%s",\n' "$status_text"
  printf '  "clone_root":"%s",\n' "$(json_escape "$CLONE_ROOT")"
  printf '  "skills_dir":"%s",\n' "$(json_escape "$SKILLS_DIR")"
  printf '  "counts":{\n'
  printf '    "recommended_plugin_count":%s,\n' "$plugin_count"
  printf '    "skill_link_count":%s\n' "$skill_count"
  printf '  },\n'
  printf '  "recommended_plugins":'
  cat "$plugins_file"
  printf ',\n'
  printf '  "companions":'
  cat "$skills_file"
  printf '}\n'

  rm -f "$plugins_file" "$skills_file"
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
      echo "Interverse recommended plugin repos and Codex skill links installed."
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
    declare -A seen=()
    while IFS='|' read -r plugin skill_rel link_name; do
      [[ -n "$link_name" ]] || continue
      if [[ -n "${seen[$link_name]+set}" ]]; then
        continue
      fi
      seen["$link_name"]=1
      rm -f "$SKILLS_DIR/$link_name" || local_failed=1
      cleanup_legacy_link "$link_name"
      echo "Removed skill link: $SKILLS_DIR/$link_name"
    done < <(skill_specs)

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
