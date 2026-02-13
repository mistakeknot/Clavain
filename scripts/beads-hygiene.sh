#!/usr/bin/env bash
set -euo pipefail

# Daily beads hygiene for all projects
# Run by clavain-beads-hygiene.timer (6:15 AM Pacific)
# Also safe to run manually.

LOG_TAG="beads-hygiene"

for beads_dir in /root/projects/*/.beads; do
  [[ -d "$beads_dir" ]] || continue
  project_dir="$(dirname "$beads_dir")"
  project_name="$(basename "$project_dir")"

  echo "[$LOG_TAG] === $project_name ==="

  # 1. Doctor — fix common issues silently
  (cd "$project_dir" && bd doctor --fix --yes 2>&1) || echo "[$LOG_TAG] WARNING: bd doctor failed for $project_name"

  # 2. Cleanup — delete closed issues older than 30 days
  (cd "$project_dir" && bd admin cleanup --older-than 30 --force 2>&1) || echo "[$LOG_TAG] WARNING: bd admin cleanup failed for $project_name"

  # 3. Sync — commit any changes to git
  (cd "$project_dir" && bd sync 2>&1) || echo "[$LOG_TAG] WARNING: bd sync failed for $project_name"

  echo ""
done

echo "[$LOG_TAG] Done. $(date)"
