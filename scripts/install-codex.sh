#!/usr/bin/env bash
# Install Clavain for Codex native skill discovery.
#
# What this script sets up:
# - ~/.agents/skills/clavain  -> <clavain>/skills
# - ~/.codex/skills/clavain   -> <clavain>/skills (legacy compatibility, optional)
# - ~/.codex/prompts/clavain-*.md prompt wrappers generated from commands/*.md

set -euo pipefail

REPO_URL_DEFAULT="https://github.com/mistakeknot/Clavain.git"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ACTION="${1:-install}"
shift || true

SOURCE_DIR=""
CLONE_DIR="${CLAVAIN_CLONE_DIR:-$HOME/.codex/clavain}"
REPO_URL="${CLAVAIN_REPO_URL:-$REPO_URL_DEFAULT}"
INSTALL_PROMPTS=1
REMOVE_CLONE=0
DOCTOR_JSON=0

AGENTS_SKILLS_DIR="${AGENTS_SKILLS_DIR:-$HOME/.agents/skills}"
CODEX_SKILLS_DIR="${CODEX_SKILLS_DIR:-$HOME/.codex/skills}"
CODEX_PROMPTS_DIR="${CODEX_PROMPTS_DIR:-$HOME/.codex/prompts}"
CREATE_LEGACY_CODEX_SKILLS_LINK=0
if [[ "${CLAVAIN_LEGACY_SKILLS_LINK:-0}" == "1" ]]; then
  CREATE_LEGACY_CODEX_SKILLS_LINK=1
elif [[ "$CODEX_SKILLS_DIR" != "$HOME/.codex/skills" ]]; then
  CREATE_LEGACY_CODEX_SKILLS_LINK=1
fi

usage() {
  cat <<'EOF'
Usage:
  install-codex.sh install [options]
  install-codex.sh update [options]
  install-codex.sh doctor [--json]
  install-codex.sh uninstall [--remove-clone]

Options:
  --source <path>      Use an existing Clavain checkout as source.
  --clone-dir <path>   Clone/update target (default: ~/.codex/clavain)
  --repo-url <url>     Repo URL for clone/update.
  --no-prompts         Skip generating prompt wrappers in ~/.codex/prompts.
  --remove-clone       With uninstall, delete clone dir too.
  --json               Output doctor check results as JSON.
  -h, --help           Show this help.

Environment:
  CLAVAIN_LEGACY_SKILLS_LINK=1  Create ~/.codex/skills/clavain symlink too.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source)
      SOURCE_DIR="$2"
      shift 2
      ;;
    --clone-dir)
      CLONE_DIR="$2"
      shift 2
      ;;
    --repo-url)
      REPO_URL="$2"
      shift 2
      ;;
    --no-prompts)
      INSTALL_PROMPTS=0
      shift
      ;;
    --remove-clone)
      REMOVE_CLONE=1
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

is_clavain_root() {
  local dir="$1"
  [[ -f "$dir/README.md" && -d "$dir/skills" && -d "$dir/commands" && -d "$dir/scripts" ]]
}

ensure_clone() {
  mkdir -p "$(dirname "$CLONE_DIR")"
  if [[ -d "$CLONE_DIR/.git" ]]; then
    echo "Updating clone at $CLONE_DIR"
    git -C "$CLONE_DIR" pull --ff-only
  else
    if [[ -e "$CLONE_DIR" ]]; then
      echo "Refusing to clone into existing non-git path: $CLONE_DIR" >&2
      exit 1
    fi
    echo "Cloning $REPO_URL -> $CLONE_DIR"
    git clone "$REPO_URL" "$CLONE_DIR"
  fi
}

resolve_source_dir() {
  if [[ -n "$SOURCE_DIR" ]]; then
    SOURCE_DIR="$(cd "$SOURCE_DIR" && pwd)"
    if ! is_clavain_root "$SOURCE_DIR"; then
      echo "Invalid --source path (not a Clavain root): $SOURCE_DIR" >&2
      exit 1
    fi
    return
  fi

  local script_root
  script_root="$(cd "$SCRIPT_DIR/.." && pwd)"
  if is_clavain_root "$script_root"; then
    SOURCE_DIR="$script_root"
    return
  fi

  ensure_clone
  SOURCE_DIR="$CLONE_DIR"
}

safe_link() {
  local target="$1"
  local link_path="$2"
  mkdir -p "$(dirname "$link_path")"

  if [[ -L "$link_path" ]]; then
    local current
    current="$(readlink "$link_path")"
    if [[ "$current" == "$target" ]]; then
      echo "OK symlink: $link_path -> $target"
      return 0
    fi
    rm "$link_path"
  elif [[ -e "$link_path" ]]; then
    echo "Skip non-symlink path (manual cleanup needed): $link_path" >&2
    return 1
  fi

  ln -s "$target" "$link_path"
  echo "Linked: $link_path -> $target"
}

cleanup_legacy_codex_skills_link() {
  local legacy_link="$CODEX_SKILLS_DIR/clavain"
  if [[ -L "$legacy_link" ]]; then
    rm -f "$legacy_link"
    echo "Removed legacy codex skills symlink: $legacy_link"
    return 0
  fi

  if [[ -e "$legacy_link" ]]; then
    echo "Legacy codex skills path exists as non-symlink; skipped auto cleanup: $legacy_link" >&2
    return 1
  fi

  return 0
}

strip_frontmatter() {
  local file="$1"
  awk '
    NR == 1 && $0 == "---" { in_fm = 1; next }
    in_fm == 1 && $0 == "---" { in_fm = 0; next }
    in_fm == 0 { print }
  ' "$file"
}

generate_prompts() {
  mkdir -p "$CODEX_PROMPTS_DIR"
  local expected="$CODEX_PROMPTS_DIR/.clavain-expected-prompts"
  local count=0
  local removed=0

  : > "$expected"

  # Track currently known command names so stale wrappers can be removed.
  # This keeps wrapper generation idempotent when commands are added/removed.
  local src
  for src in "$SOURCE_DIR"/commands/*.md; do
    [[ -f "$src" ]] || continue
    local name out
    name="$(basename "$src" .md)"
    echo "$name" >> "$expected"
    out="$CODEX_PROMPTS_DIR/clavain-$name.md"
    {
      echo "# Clavain Command: /clavain:$name"
      echo
      echo "Codex prompt wrapper generated from Clavain command source."
      echo
      echo "- Source: \`$SOURCE_DIR/commands/$name.md\`"
      echo "- Rule: if this command references a skill, load that Clavain skill first."
      echo
      echo "---"
      echo
      strip_frontmatter "$src"
    } > "$out"
    count=$((count + 1))
  done

  local file cmd_name
  for file in "$CODEX_PROMPTS_DIR"/clavain-*.md; do
    [[ -f "$file" ]] || continue
    cmd_name="$(basename "$file" .md)"
    cmd_name="${cmd_name#clavain-}"
    if [[ -n "$cmd_name" ]] && ! grep -Fxq "$cmd_name" "$expected" 2>/dev/null; then
      rm -f "$file"
      removed=$((removed + 1))
    fi
  done

  rm -f "$expected"
  echo "Generated $count prompt wrappers in $CODEX_PROMPTS_DIR"
  echo "Removed $removed stale prompt wrappers in $CODEX_PROMPTS_DIR"
}

remove_prompts() {
  local removed=0
  if [[ -d "$CODEX_PROMPTS_DIR" ]]; then
    local file
    for file in "$CODEX_PROMPTS_DIR"/clavain-*.md; do
      [[ -f "$file" ]] || continue
      rm -f "$file"
      removed=$((removed + 1))
    done
  fi
  echo "Removed $removed prompt wrappers from $CODEX_PROMPTS_DIR"
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

install_all() {
  resolve_source_dir
  if [[ "$SOURCE_DIR" != "$CLONE_DIR" ]]; then
    # Keep ~/.codex/clavain in sync so docs and future updates are predictable.
    ensure_clone
  fi

  local skills_target="$SOURCE_DIR/skills"
  if [[ ! -d "$skills_target" ]]; then
    echo "Missing skills directory: $skills_target" >&2
    exit 1
  fi

  safe_link "$skills_target" "$AGENTS_SKILLS_DIR/clavain" || true
  if [[ "$CREATE_LEGACY_CODEX_SKILLS_LINK" -eq 1 ]]; then
    safe_link "$skills_target" "$CODEX_SKILLS_DIR/clavain" || true
  else
    cleanup_legacy_codex_skills_link || true
  fi

  if [[ "$INSTALL_PROMPTS" -eq 1 ]]; then
    generate_prompts
  else
    echo "Skipping prompt generation (--no-prompts)."
  fi

  echo
  echo "Install complete."
  echo "Restart Codex so it reloads discovered skills/prompts."
}

doctor() {
  resolve_source_dir
  local skills_target="$SOURCE_DIR/skills"
  local commands_dir="$SOURCE_DIR/commands"
  local scripts_dir="$SOURCE_DIR/scripts"
  local agents_link="$AGENTS_SKILLS_DIR/clavain"
  local codex_link="$CODEX_SKILLS_DIR/clavain"
  local status=0
  local skill_dir_count=0
  local command_count=0
  local expected_wrappers=0
  local present_wrappers=0
  local missing_wrappers=0
  local stale_wrappers=0
  local wrapper_count=0
  local source_agents_link=""
  local source_codex_link=""
  local issues=()
  local legacy_codex_skills_check="$CREATE_LEGACY_CODEX_SKILLS_LINK"
  local helper_dispatch_status="missing"
  local helper_debate_status="missing"
  local command_file
  local wrapper_file
  local command_name
  local wrapper_name
  local required_helper
  local root_ok="false"
  local agents_link_ok="false"
  local agents_link_match="false"
  local codex_link_ok="false"
  local codex_link_match="false"
  local codex_present="false"
  local command_dir_ok="false"
  local prompts_dir_ok="false"
  local issue
  local status_text="fail"

  if [[ "$DOCTOR_JSON" -eq 0 ]]; then
    echo "== Clavain Codex Doctor =="
    echo "Source dir: $SOURCE_DIR"
    echo
  fi

  if ! is_clavain_root "$SOURCE_DIR"; then
    issues+=("Source dir missing required Clavain structure: $SOURCE_DIR")
    status=1
  else
    root_ok="true"
  fi

  if [[ -L "$agents_link" ]]; then
    agents_link_ok="true"
    source_agents_link="$(readlink -f "$agents_link" 2>/dev/null || readlink "$agents_link")"
    if [[ "$source_agents_link" == "$skills_target" ]]; then
      agents_link_match="true"
      if [[ "$DOCTOR_JSON" -eq 0 ]]; then
        echo "agents skills link: $agents_link -> $source_agents_link"
      fi
    else
      issues+=("agents skills link target mismatch: $agents_link -> $source_agents_link (expected $skills_target)")
      status=1
    fi
  else
    issues+=("agents skills link missing: $agents_link")
    status=1
  fi

  if [[ "$legacy_codex_skills_check" -eq 1 ]]; then
    if [[ -L "$codex_link" ]]; then
      codex_link_ok="true"
      source_codex_link="$(readlink -f "$codex_link" 2>/dev/null || readlink "$codex_link")"
      if [[ "$source_codex_link" == "$skills_target" ]]; then
        codex_link_match="true"
        if [[ "$DOCTOR_JSON" -eq 0 ]]; then
          echo "codex skills link:  $codex_link -> $source_codex_link"
        fi
      else
        issues+=("codex skills link target mismatch: $codex_link -> $source_codex_link (expected $skills_target)")
        status=1
      fi
    else
      issues+=("codex skills link missing: $codex_link")
      status=1
    fi
  else
    codex_link_ok="true"
    codex_link_match="true"
    if [[ "$DOCTOR_JSON" -eq 0 ]]; then
      echo "codex skills link:  intentionally skipped (set CLAVAIN_LEGACY_SKILLS_LINK=1 for legacy link)"
    fi
  fi

  for required_helper in dispatch.sh debate.sh; do
    if [[ ! -f "$scripts_dir/$required_helper" ]]; then
      issues+=("required helper missing: $scripts_dir/$required_helper")
      status=1
    else
      if [[ "$required_helper" == "dispatch.sh" ]]; then
        helper_dispatch_status="present"
      else
        helper_debate_status="present"
      fi
    fi
  done

  if command -v codex >/dev/null 2>&1; then
    codex_present="true"
  fi

  if [[ "$DOCTOR_JSON" -eq 0 ]]; then
    if [[ "$codex_present" == "true" ]]; then
      echo "codex CLI:            present"
    else
      echo "codex CLI:            missing"
    fi
  fi

  if [[ -d "$skills_target" ]]; then
    skill_dir_count="$(find "$skills_target" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')"
  fi

  if [[ -d "$commands_dir" ]]; then
    command_dir_ok="true"
    while IFS= read -r command_file; do
      [[ -f "$command_file" ]] || continue
      command_name="$(basename "$command_file" .md)"
      command_count=$((command_count + 1))
      expected_wrappers=$((expected_wrappers + 1))
      if [[ -f "$CODEX_PROMPTS_DIR/clavain-$command_name.md" ]]; then
        present_wrappers=$((present_wrappers + 1))
      else
        missing_wrappers=$((missing_wrappers + 1))
        status=1
        issues+=("missing wrapper:        $CODEX_PROMPTS_DIR/clavain-$command_name.md")
      fi
    done < <(find "$commands_dir" -maxdepth 1 -type f -name '*.md')
  else
    status=1
    issues+=("commands dir missing:   $commands_dir")
  fi

  if [[ -d "$CODEX_PROMPTS_DIR" ]]; then
    prompts_dir_ok="true"
    wrapper_count="$(find "$CODEX_PROMPTS_DIR" -maxdepth 1 -type f -name 'clavain-*.md' | wc -l | tr -d ' ')"
    while IFS= read -r wrapper_file; do
      [[ -f "$wrapper_file" ]] || continue
      wrapper_name="$(basename "$wrapper_file" .md)"
      command_name="${wrapper_name#clavain-}"
      if [[ ! -f "$commands_dir/$command_name.md" ]]; then
        stale_wrappers=$((stale_wrappers + 1))
        status=1
        issues+=("stale wrapper:         $wrapper_file")
      fi
    done < <(find "$CODEX_PROMPTS_DIR" -maxdepth 1 -type f -name 'clavain-*.md')
  else
    wrapper_count=0
  fi

  if [[ "$DOCTOR_JSON" -eq 1 ]]; then
    if [[ "$status" -eq 0 ]]; then
      status_text="ok"
    fi

    printf '{\n'
    printf '  "status":"%s",\n' "$status_text"
    printf '  "source_dir":"%s",\n' "$(json_escape "$SOURCE_DIR")"
    printf '  "issues_count":%s,\n' "${#issues[@]}"
    printf '  "checks":{\n'
    printf '    "clavain_root":%s,\n' "$root_ok"
    printf '    "agents_skills_link_exists":%s,\n' "$agents_link_ok"
    printf '    "agents_skills_link_match":%s,\n' "$agents_link_match"
    printf '    "agents_skills_link_target":"%s",\n' "$(json_escape "$source_agents_link")"
    printf '    "codex_skills_link_exists":%s,\n' "$codex_link_ok"
    printf '    "codex_skills_link_match":%s,\n' "$codex_link_match"
    printf '    "codex_skills_link_target":"%s",\n' "$(json_escape "$source_codex_link")"
    printf '    "helpers":{\n'
    printf '      "dispatch.sh":"%s",\n' "$helper_dispatch_status"
    printf '      "debate.sh":"%s"\n' "$helper_debate_status"
    printf '    },\n'
    printf '    "codex_cli_present":%s,\n' "$codex_present"
    printf '    "commands_dir_exists":%s,\n' "$command_dir_ok"
    printf '    "prompts_dir_exists":%s\n' "$prompts_dir_ok"
    printf '  },\n'
    printf '  "counts":{\n'
    printf '    "skill_dirs":%s,\n' "$skill_dir_count"
    printf '    "command_count":%s,\n' "$command_count"
    printf '    "expected_wrappers":%s,\n' "$expected_wrappers"
    printf '    "present_wrappers":%s,\n' "$present_wrappers"
    printf '    "missing_wrappers":%s,\n' "$missing_wrappers"
    printf '    "stale_wrappers":%s,\n' "$stale_wrappers"
    printf '    "prompt_wrapper_total":%s\n' "$wrapper_count"
    printf '  },\n'
    printf '  "issues":['
    local comma=""
    for issue in "${issues[@]}"; do
      printf '%s\n    "%s"' "$comma" "$(json_escape "$issue")"
      comma=","
    done
    printf '\n  ]\n'
    printf '}\n'
  else
    echo
    echo "skill dirs in source:   $skill_dir_count"
    echo "commands in source:     $command_count"
    echo "prompt wrappers:        $present_wrappers/$expected_wrappers present; $missing_wrappers missing; $stale_wrappers stale; $wrapper_count total"
    echo
    if [[ "$status" -eq 0 ]]; then
      echo "Doctor checks passed."
      return 0
    fi
    echo "Doctor checks completed with issues."
    return 1
  fi

  if [[ "$status" -eq 0 ]]; then
    return 0
  fi
  return 1
}

uninstall_all() {
  rm -f "$AGENTS_SKILLS_DIR/clavain"
  rm -f "$CODEX_SKILLS_DIR/clavain"
  remove_prompts
  if [[ "$REMOVE_CLONE" -eq 1 ]]; then
    rm -rf "$CLONE_DIR"
    echo "Removed clone: $CLONE_DIR"
  fi
  echo "Uninstall complete."
}

case "$ACTION" in
  install)
    install_all
    ;;
  update)
    ensure_clone
    install_all
    ;;
  doctor)
    doctor
    ;;
  uninstall)
    uninstall_all
    ;;
  *)
    echo "Unknown action: $ACTION" >&2
    usage >&2
    exit 1
    ;;
esac
