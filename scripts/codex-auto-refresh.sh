#!/usr/bin/env bash
# Keep a local Clavain Codex install aligned with the latest Clavain main.
#
# What it does:
# - Ensures ~/.codex/clavain exists (or clones it).
# - Fetches and fast-forwards latest changes.
# - Regenerates Codex skill links/wrappers when upstream changed.
# - Runs Codex doctor checks.
#
# Optional env vars:
#   CLAVAIN_DIR (default: $HOME/.codex/clavain)
#   CLAVAIN_REPO_URL (default: https://github.com/mistakeknot/Clavain.git)
#   CLAVAIN_AUTO_REFRESH_LOG (default: $HOME/.local/share/clavain/codex-refresh.log)
#   CLAVAIN_AUTO_REFRESH_LOG_DIR (default: $HOME/.local/share/clavain)

set -euo pipefail

CLAVAIN_DIR="${CLAVAIN_DIR:-$HOME/.codex/clavain}"
REPO_URL="${CLAVAIN_REPO_URL:-https://github.com/mistakeknot/Clavain.git}"
LOG_DIR="${CLAVAIN_AUTO_REFRESH_LOG_DIR:-$HOME/.local/share/clavain}"
LOG_FILE="${CLAVAIN_AUTO_REFRESH_LOG:-$LOG_DIR/codex-refresh.log}"
LOCK_FILE="${CLAVAIN_AUTO_REFRESH_LOCK_FILE:-$HOME/.local/share/clavain/codex-auto-refresh.lock}"

mkdir -p "$(dirname "$LOG_FILE")"
mkdir -p "$(dirname "$LOCK_FILE")"

ensure_clone() {
  if [[ -d "$CLAVAIN_DIR/.git" ]]; then
    return
  fi

  if [[ -e "$CLAVAIN_DIR" ]]; then
    echo "Refusing to bootstrap: $CLAVAIN_DIR exists and is not a git repo" | tee -a "$LOG_FILE"
    exit 1
  fi

  echo "Cloning Clavain into $CLAVAIN_DIR" | tee -a "$LOG_FILE"
  git clone "$REPO_URL" "$CLAVAIN_DIR"
}

run_refresh() {
  if command -v codex >/dev/null 2>&1; then
    if command -v make >/dev/null 2>&1 && [[ -f "$CLAVAIN_DIR/Makefile" ]]; then
      (cd "$CLAVAIN_DIR" && make codex-refresh codex-doctor)
    else
      bash "$CLAVAIN_DIR/scripts/install-codex.sh" install --source "$CLAVAIN_DIR"
      bash "$CLAVAIN_DIR/scripts/install-codex.sh" doctor --source "$CLAVAIN_DIR"
    fi
  else
    echo "codex CLI missing; skipped make targets; paths and wrappers may be stale" | tee -a "$LOG_FILE"
    bash "$CLAVAIN_DIR/scripts/install-codex.sh" install --source "$CLAVAIN_DIR"
    bash "$CLAVAIN_DIR/scripts/install-codex.sh" doctor --source "$CLAVAIN_DIR"
  fi
}

main() {
  ensure_clone

  if [[ ! -d "$CLAVAIN_DIR/.git" ]]; then
    echo "invalid repo path: $CLAVAIN_DIR" | tee -a "$LOG_FILE"
    exit 1
  fi

  if ! command -v git >/dev/null 2>&1; then
    echo "git unavailable; cannot check for updates" | tee -a "$LOG_FILE"
    exit 1
  fi

  if [[ -n "$(git -C "$CLAVAIN_DIR" status --porcelain --untracked-files=no)" ]]; then
    echo "local repo has uncommitted changes; skipping auto-refresh to avoid conflict" | tee -a "$LOG_FILE"
    exit 0
  fi

  before="$(git -C "$CLAVAIN_DIR" rev-parse HEAD)"
  echo "Checking $CLAVAIN_DIR for upstream changes" | tee -a "$LOG_FILE"
  git -C "$CLAVAIN_DIR" pull --ff-only || {
    echo "failed to pull latest Clavain" | tee -a "$LOG_FILE"
    exit 1
  }
  after="$(git -C "$CLAVAIN_DIR" rev-parse HEAD)"

  if [[ "$before" == "$after" ]]; then
    echo "already up to date: $after" | tee -a "$LOG_FILE"
    exit 0
  fi

  echo "updated from $before to $after" | tee -a "$LOG_FILE"
  run_refresh
}

if command -v flock >/dev/null 2>&1; then
  exec 9>"$LOCK_FILE"
  if ! flock -n 9; then
    echo "another auto-refresh is already running; exiting" >> "$LOG_FILE"
    exit 0
  fi
fi

main | tee -a "$LOG_FILE"
