#!/usr/bin/env bash
# SessionStart hook: keep a source-checkout Codex install of Clavain fresh.
#
# Why: on hosts where symlinks degrade to copies (MSYS/Git Bash without
# Windows Developer Mode), the installed skill tree stops tracking its source
# checkout the moment it is created. This hook makes that staleness
# self-healing: at most once per interval it fetches the source repo, and only
# when upstream actually moved does it ff-pull and re-run the installers.
# On symlink-capable hosts it is a cheap freshness check for the checkout.
#
# Opt out:  export CLAVAIN_SESSION_REFRESH=0
# Interval: CLAVAIN_REFRESH_INTERVAL_SECONDS (default 86400 = daily)
#
# A hook must never break session start: every failure degrades to a silent
# no-op (exit 0).
set -uo pipefail

[[ "${CLAVAIN_SESSION_REFRESH:-1}" == "0" ]] && exit 0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 0
SOURCE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)" || exit 0
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
STAMP="$CODEX_HOME/.clavain-refresh-stamp"
INTERVAL="${CLAVAIN_REFRESH_INTERVAL_SECONDS:-86400}"

# Throttle: epoch stamp in a file — portable across GNU/BSD/MSYS (no stat -c).
now="$(date +%s 2>/dev/null)" || exit 0
last="$(cat "$STAMP" 2>/dev/null || echo 0)"
[[ "$last" =~ ^[0-9]+$ ]] || last=0
(( now - last < INTERVAL )) && exit 0
printf '%s' "$now" > "$STAMP" 2>/dev/null || true

git -C "$SOURCE_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
git -C "$SOURCE_DIR" fetch --quiet 2>/dev/null || exit 0
local_head="$(git -C "$SOURCE_DIR" rev-parse HEAD 2>/dev/null)" || exit 0
remote_head="$(git -C "$SOURCE_DIR" rev-parse '@{u}' 2>/dev/null)" || exit 0
[[ "$local_head" == "$remote_head" ]] && exit 0

# ff-only: a dirty or diverged checkout is left strictly alone.
git -C "$SOURCE_DIR" pull --ff-only --quiet 2>/dev/null || exit 0

bash "$SOURCE_DIR/.codex/agent-install.sh" --source "$SOURCE_DIR" --skip-doctor >/dev/null 2>&1 || true
if [[ -f "$SOURCE_DIR/scripts/install-codex-interverse.sh" ]]; then
  bash "$SOURCE_DIR/scripts/install-codex-interverse.sh" install >/dev/null 2>&1 || true
fi

echo "Clavain: source updated to $(git -C "$SOURCE_DIR" rev-parse --short HEAD 2>/dev/null); Codex install refreshed."
exit 0
