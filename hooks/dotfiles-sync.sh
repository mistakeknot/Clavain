#!/usr/bin/env bash
# SessionEnd hook: sync dotfiles after session ends
#
# Runs the dotfiles sync script if it exists, pushing any config
# changes (CLAUDE.md, settings.json, reference docs) to GitHub.
#
# Runs async and silently no-ops if:
#   - The sync script doesn't exist
#   - The sync repo isn't cloned
#   - Git push fails (logged but not surfaced)

set -euo pipefail

# Derive paths relative to the user's home directory
SYNC_SCRIPT="${HOME}/projects/dotfiles-sync/sync-dotfiles.sh"

# Skip if sync infrastructure doesn't exist
if [[ ! -x "$SYNC_SCRIPT" ]]; then
    exit 0
fi

# Run the sync (capture output to log, don't block session exit)
bash "$SYNC_SCRIPT" >>/var/log/dotfiles-sync.log 2>&1 || true

exit 0
