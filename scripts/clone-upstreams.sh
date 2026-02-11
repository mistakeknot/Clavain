#!/usr/bin/env bash
set -euo pipefail

# One-time setup: clone all upstream repos that Clavain integrates with.
# Repos are cloned to /root/projects/upstreams/ as read-only mirrors.
# After cloning, use scripts/pull-upstreams.sh to keep them updated.
#
# Usage:
#   ./scripts/clone-upstreams.sh

UPSTREAMS_DIR="/root/projects/upstreams"

declare -A REPOS=(
  [superpowers]="https://github.com/obra/superpowers.git"
  [superpowers-lab]="https://github.com/obra/superpowers-lab.git"
  [superpowers-dev]="https://github.com/obra/superpowers-developing-for-claude-code.git"
  [compound-engineering]="https://github.com/EveryInc/compound-engineering-plugin.git"
  [beads]="https://github.com/steveyegge/beads.git"
  [oracle]="https://github.com/steipete/oracle.git"
)

mkdir -p "$UPSTREAMS_DIR"

echo "=== Cloning Clavain Upstreams ==="
echo "Target: $UPSTREAMS_DIR"
echo ""

for name in "${!REPOS[@]}"; do
  url="${REPOS[$name]}"
  dest="$UPSTREAMS_DIR/$name"

  if [[ -d "$dest/.git" ]]; then
    echo "  SKIP: $name (already cloned)"
  else
    echo "  CLONE: $name <- $url"
    git clone "$url" "$dest"
  fi
done

echo ""
echo "Done. Run scripts/pull-upstreams.sh to check for updates."
