#!/usr/bin/env bash
set -euo pipefail

# Pull latest changes for all upstream repos that Clavain integrates with.
# Repos live in /root/projects/upstreams/ as read-only mirrors.
#
# Usage:
#   ./scripts/pull-upstreams.sh           # Pull all, show summary
#   ./scripts/pull-upstreams.sh --status  # Just show behind/ahead counts
#   ./scripts/pull-upstreams.sh --diff    # Show new commits since Clavain's last sync

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
UPSTREAMS_DIR="/root/projects/upstreams"
UPSTREAMS_JSON="$PROJECT_ROOT/upstreams.json"

# Map directory names to upstreams.json names (they differ for some repos)
declare -A DIR_TO_NAME=(
  [superpowers]=superpowers
  [superpowers-lab]=superpowers-lab
  [superpowers-dev]=superpowers-dev
  [compound-engineering]=compound-engineering
  [beads]=beads
  [oracle]=oracle
  [mcp-agent-mail]=mcp-agent-mail
)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

mode="${1:---pull}"

if [[ ! -d "$UPSTREAMS_DIR" ]]; then
  echo "ERROR: $UPSTREAMS_DIR does not exist. Run scripts/clone-upstreams.sh first."
  exit 1
fi

if [[ ! -f "$UPSTREAMS_JSON" ]]; then
  echo "ERROR: $UPSTREAMS_JSON not found."
  exit 1
fi

get_synced_commit() {
  local name="$1"
  python3 -c "
import json, sys
data = json.load(open('$UPSTREAMS_JSON'))
for u in data['upstreams']:
    if u['name'] == '$name':
        print(u['lastSyncedCommit'][:7])
        sys.exit(0)
print('unknown')
"
}

get_synced_commit_full() {
  local name="$1"
  python3 -c "
import json, sys
data = json.load(open('$UPSTREAMS_JSON'))
for u in data['upstreams']:
    if u['name'] == '$name':
        print(u['lastSyncedCommit'])
        sys.exit(0)
print('')
"
}

echo "=== Clavain Upstream Repos ==="
echo "Upstreams dir: $UPSTREAMS_DIR"
echo ""

total=0
updated=0
behind=0

for dir in "$UPSTREAMS_DIR"/*/; do
  dir_name=$(basename "$dir")
  upstream_name="${DIR_TO_NAME[$dir_name]:-$dir_name}"
  total=$((total + 1))

  if [[ ! -d "$dir/.git" ]]; then
    printf "  ${RED}%-25s NOT A GIT REPO${NC}\n" "$dir_name"
    continue
  fi

  synced=$(get_synced_commit "$upstream_name")
  synced_full=$(get_synced_commit_full "$upstream_name")

  if [[ "$mode" == "--pull" ]]; then
    # Fetch and fast-forward
    output=$(git -C "$dir" pull --ff-only 2>&1) || true
    head_short=$(git -C "$dir" rev-parse --short HEAD)

    if ! echo "$output" | grep -q "Already up to date"; then
      updated=$((updated + 1))
      printf "  ${CYAN}%-25s PULLED new commits (HEAD: %s)${NC}" "$dir_name" "$head_short"
    else
      printf "  %-25s up to date (HEAD: %s)" "$dir_name" "$head_short"
    fi

    # Count commits since last Clavain sync
    if [[ -n "$synced_full" ]] && git -C "$dir" cat-file -e "$synced_full" 2>/dev/null; then
      new_count=$(git -C "$dir" rev-list --count "${synced_full}..HEAD" 2>/dev/null || echo 0)
      if [[ "$new_count" -gt 0 ]]; then
        printf " — ${YELLOW}%s new since sync %s${NC}\n" "$new_count" "$synced"
        behind=$((behind + 1))
      else
        printf " — ${GREEN}synced${NC}\n"
      fi
    else
      printf "\n"
    fi

  elif [[ "$mode" == "--status" ]]; then
    head_short=$(git -C "$dir" rev-parse --short HEAD)
    synced_full=$(get_synced_commit_full "$upstream_name")

    if [[ -z "$synced_full" ]] || [[ "$synced_full" == "" ]]; then
      printf "  ${YELLOW}%-25s HEAD: %s — not tracked in upstreams.json${NC}\n" "$dir_name" "$head_short"
      continue
    fi

    # Check if synced commit exists in this repo
    if ! git -C "$dir" cat-file -e "$synced_full" 2>/dev/null; then
      printf "  ${RED}%-25s HEAD: %s — synced commit %s NOT FOUND (fetch needed)${NC}\n" "$dir_name" "$head_short" "$synced"
      continue
    fi

    new_count=$(git -C "$dir" log --oneline "${synced_full}..HEAD" 2>/dev/null | wc -l)
    if [[ "$new_count" -eq 0 ]]; then
      printf "  ${GREEN}%-25s HEAD: %s — fully synced${NC}\n" "$dir_name" "$head_short"
    else
      printf "  ${YELLOW}%-25s HEAD: %s — %s commits behind (synced: %s)${NC}\n" "$dir_name" "$head_short" "$new_count" "$synced"
      behind=$((behind + 1))
    fi

  elif [[ "$mode" == "--diff" ]]; then
    synced_full=$(get_synced_commit_full "$upstream_name")
    head_short=$(git -C "$dir" rev-parse --short HEAD)

    if [[ -z "$synced_full" ]]; then
      printf "  ${YELLOW}%-25s — not tracked in upstreams.json${NC}\n" "$dir_name"
      continue
    fi

    if ! git -C "$dir" cat-file -e "$synced_full" 2>/dev/null; then
      printf "  ${RED}%-25s — synced commit %s not found${NC}\n" "$dir_name" "$synced"
      continue
    fi

    new_count=$(git -C "$dir" log --oneline "${synced_full}..HEAD" 2>/dev/null | wc -l)
    if [[ "$new_count" -eq 0 ]]; then
      printf "  ${GREEN}%-25s — no new commits${NC}\n" "$dir_name"
    else
      printf "\n  ${CYAN}%-25s — %s new commits since sync:${NC}\n" "$dir_name" "$new_count"
      git -C "$dir" log --oneline "${synced_full}..HEAD" 2>/dev/null | head -20 | while read -r line; do
        echo "    $line"
      done
      if [[ "$new_count" -gt 20 ]]; then
        echo "    ... and $((new_count - 20)) more"
      fi
      behind=$((behind + 1))
    fi
  fi
done

echo ""
echo "Total: $total repos"
if [[ "$mode" == "--pull" ]]; then
  echo "Updated: $updated | Behind sync: $behind"
elif [[ "$mode" == "--status" ]] || [[ "$mode" == "--diff" ]]; then
  echo "Behind sync: $behind"
fi
