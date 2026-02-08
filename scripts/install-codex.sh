#!/usr/bin/env bash
# Install Clavain for Codex native skill discovery.
#
# What this script sets up:
# - ~/.agents/skills/clavain  -> <clavain>/skills
# - ~/.codex/skills/clavain   -> <clavain>/skills (best-effort compatibility)
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

AGENTS_SKILLS_DIR="${AGENTS_SKILLS_DIR:-$HOME/.agents/skills}"
CODEX_SKILLS_DIR="${CODEX_SKILLS_DIR:-$HOME/.codex/skills}"
CODEX_PROMPTS_DIR="${CODEX_PROMPTS_DIR:-$HOME/.codex/prompts}"

usage() {
  cat <<'EOF'
Usage:
  install-codex.sh install [options]
  install-codex.sh update [options]
  install-codex.sh doctor
  install-codex.sh uninstall [--remove-clone]

Options:
  --source <path>      Use an existing Clavain checkout as source.
  --clone-dir <path>   Clone/update target (default: ~/.codex/clavain)
  --repo-url <url>     Repo URL for clone/update.
  --no-prompts         Skip generating prompt wrappers in ~/.codex/prompts.
  --remove-clone       With uninstall, delete clone dir too.
  -h, --help           Show this help.
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
  local count=0
  local src
  for src in "$SOURCE_DIR"/commands/*.md; do
    [[ -f "$src" ]] || continue
    local name out
    name="$(basename "$src" .md)"
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
  echo "Generated $count prompt wrappers in $CODEX_PROMPTS_DIR"
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
  safe_link "$skills_target" "$CODEX_SKILLS_DIR/clavain" || true

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
  local agents_link="$AGENTS_SKILLS_DIR/clavain"
  local codex_link="$CODEX_SKILLS_DIR/clavain"

  echo "== Clavain Codex Doctor =="
  echo "Source dir: $SOURCE_DIR"
  echo

  if [[ -L "$agents_link" ]]; then
    echo "agents skills link: $agents_link -> $(readlink "$agents_link")"
  else
    echo "agents skills link missing: $agents_link"
  fi

  if [[ -L "$codex_link" ]]; then
    echo "codex skills link:  $codex_link -> $(readlink "$codex_link")"
  else
    echo "codex skills link missing: $codex_link"
  fi

  echo "skill dirs in source: $(find "$skills_target" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')"
  echo "prompt wrappers:      $(find "$CODEX_PROMPTS_DIR" -maxdepth 1 -type f -name 'clavain-*.md' 2>/dev/null | wc -l | tr -d ' ')"

  if command -v codex >/dev/null 2>&1; then
    echo "codex CLI:            present"
  else
    echo "codex CLI:            missing"
  fi
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
