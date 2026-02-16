#!/usr/bin/env bash
# Install Clavain for Codex from any shell context (including Codex CLI agents).
#
# Usage:
#   ~/.codex/clavain/.codex/agent-install.sh
#   ~/.codex/clavain/.codex/agent-install.sh --no-prompts
#   ~/.codex/clavain/.codex/agent-install.sh --dir "$HOME/.codex/clavain" --update
#   ~/.codex/clavain/.codex/agent-install.sh --json

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: agent-install.sh [options]

Options:
  --source PATH       Use an existing local Clavain checkout as source.
  --dir PATH          Target checkout path for Clavain install (default: $HOME/.codex/clavain).
  --repo URL          Git remote to clone if no source/checkout exists.
                      Default: https://github.com/mistakeknot/Clavain.git
  --update            Pull latest from origin before installing if checkout exists.
  --no-prompts        Install without generated prompt wrappers.
  --skip-doctor       Skip post-install doctor checks.
  --json              Emit doctor checks as JSON.
  --help              Show this message.
EOF
}

CLAVAIN_DIR="${HOME}/.codex/clavain"
CLAVAIN_REPO="https://github.com/mistakeknot/Clavain.git"
SOURCE_DIR=""
UPDATE=0
SKIP_DOCTOR=0
DOCTOR_JSON=0
INSTALL_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source)
      SOURCE_DIR="${2:?missing value for --source}"
      shift 2
      ;;
    --dir)
      CLAVAIN_DIR="${2:?missing value for --dir}"
      shift 2
      ;;
    --repo)
      CLAVAIN_REPO="${2:?missing value for --repo}"
      shift 2
      ;;
    --update)
      UPDATE=1
      shift
      ;;
    --no-prompts)
      INSTALL_ARGS+=(--no-prompts)
      shift
      ;;
    --skip-doctor)
      SKIP_DOCTOR=1
      shift
      ;;
    --json)
      DOCTOR_JSON=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ -n "$SOURCE_DIR" ]]; then
  if [[ "$UPDATE" -eq 1 && -d "$SOURCE_DIR/.git" ]]; then
    if command -v git >/dev/null 2>&1; then
      echo "Updating source checkout: $SOURCE_DIR"
      (cd "$SOURCE_DIR" && git pull --ff-only || true)
    else
      echo "git not found; skipping update step."
    fi
  fi
else
  SOURCE_DIR="$CLAVAIN_DIR"

  if [[ -d "$SOURCE_DIR/.git" ]]; then
    if [[ "$UPDATE" -eq 1 ]]; then
      if command -v git >/dev/null 2>&1; then
        echo "Updating existing Clavain checkout: $SOURCE_DIR"
        (cd "$SOURCE_DIR" && git pull --ff-only || true)
      else
        echo "git not found; skipping update step."
      fi
    fi
  else
    if [[ -e "$SOURCE_DIR" ]]; then
      echo "Target path exists but is not a git repo: $SOURCE_DIR"
      echo "Either choose a different --dir or run with --source."
      exit 1
    fi

    if command -v git >/dev/null 2>&1; then
      echo "Cloning Clavain into $SOURCE_DIR"
      git clone "$CLAVAIN_REPO" "$SOURCE_DIR"
    else
      echo "git is required to bootstrap this install."
      exit 1
    fi
  fi
fi

if [[ ! -d "$SOURCE_DIR/.git" ]]; then
  echo "Invalid source directory (missing git repo): $SOURCE_DIR"
  exit 1
fi

echo "Running Clavain Codex install from $SOURCE_DIR"
bash "$SOURCE_DIR/scripts/install-codex.sh" install --source "$SOURCE_DIR" "${INSTALL_ARGS[@]}"

if [[ "$SKIP_DOCTOR" -eq 0 ]]; then
  if [[ "$DOCTOR_JSON" -eq 1 ]]; then
    DOCTOR_CHECK_OUTPUT="$(mktemp)"
    if bash "$SOURCE_DIR/scripts/install-codex.sh" doctor --source "$SOURCE_DIR" --json >"$DOCTOR_CHECK_OUTPUT" 2>&1; then
      cat "$DOCTOR_CHECK_OUTPUT"
      rm -f "$DOCTOR_CHECK_OUTPUT"
    elif grep -q "Unknown option: --json" "$DOCTOR_CHECK_OUTPUT"; then
      echo "install-codex.sh in this checkout does not expose --json; running doctor without JSON."
      bash "$SOURCE_DIR/scripts/install-codex.sh" doctor --source "$SOURCE_DIR"
      rm -f "$DOCTOR_CHECK_OUTPUT"
    else
      cat "$DOCTOR_CHECK_OUTPUT"
      rm -f "$DOCTOR_CHECK_OUTPUT"
      exit 1
    fi
  else
    bash "$SOURCE_DIR/scripts/install-codex.sh" doctor --source "$SOURCE_DIR"
  fi
fi

echo "Codex installation completed."
