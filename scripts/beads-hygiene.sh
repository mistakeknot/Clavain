#!/usr/bin/env bash
set -euo pipefail

# Daily beads hygiene for the Interverse monorepo
# Run by clavain-beads-hygiene.timer (6:15 AM Pacific)
# Also safe to run manually.
#
# The beads database lives at the Interverse monorepo root only.
# Submodule .beads/ dirs are read-only historical archives.

LOG_TAG="beads-hygiene"
PROJECT_ROOT="/root/projects/Interverse"

if [[ ! -d "$PROJECT_ROOT/.beads" ]]; then
  echo "[$LOG_TAG] ERROR: No .beads at $PROJECT_ROOT — aborting"
  exit 1
fi

echo "[$LOG_TAG] === Interverse ==="

# 1. Doctor — fix common issues silently
(cd "$PROJECT_ROOT" && bd doctor --fix --yes 2>&1) || echo "[$LOG_TAG] WARNING: bd doctor failed"

# 2. Cleanup — delete closed issues older than 30 days
(cd "$PROJECT_ROOT" && bd admin cleanup --older-than 30 --force 2>&1) || echo "[$LOG_TAG] WARNING: bd admin cleanup failed"

# 3. Sync — commit any changes to git
(cd "$PROJECT_ROOT" && bd sync 2>&1) || echo "[$LOG_TAG] WARNING: bd sync failed"

echo ""
echo "[$LOG_TAG] Done. $(date)"
