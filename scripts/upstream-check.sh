#!/usr/bin/env bash
# upstream-check.sh — Check upstream repos for new releases/commits
#
# Usage:
#   ./scripts/upstream-check.sh              # Check all repos, print report
#   ./scripts/upstream-check.sh --json       # Output machine-readable JSON
#   ./scripts/upstream-check.sh --update     # Update upstream-versions.json with latest checked
#
# Requires: gh (GitHub CLI), jq
# Exit codes: 0 = changes detected, 1 = no changes, 2 = error

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VERSIONS_FILE="${REPO_ROOT}/docs/upstream-versions.json"

# Upstream repos to track
# Format: "owner/repo|skill1,skill2,..."
UPSTREAMS=(
  "steveyegge/beads|interphase (companion plugin)"
  "steipete/oracle|oracle-review"
  "obra/superpowers|multiple (founding source)"
  "obra/superpowers-lab|using-tmux-for-interactive-commands,slack-messaging,mcp-cli,finding-duplicate-functions"
  "obra/superpowers-developing-for-claude-code|developing-claude-code-plugins,working-with-claude-code"
  "EveryInc/compound-engineering-plugin|multiple (founding source)"
)

# Parse flags
JSON_MODE=false
UPDATE_MODE=false
for arg in "$@"; do
  case "$arg" in
    --json) JSON_MODE=true ;;
    --update) UPDATE_MODE=true ;;
  esac
done

# Load existing versions (or empty object)
if [[ -f "$VERSIONS_FILE" ]]; then
  EXISTING=$(cat "$VERSIONS_FILE")
else
  EXISTING='{}'
fi

# Collect results
RESULTS='[]'
HAS_CHANGES=false

for entry in "${UPSTREAMS[@]}"; do
  IFS='|' read -r repo skills <<< "$entry"

  # Get latest release tag
  # gh api dumps 404 JSON to stdout before --jq can filter it, so capture raw and parse
  raw_release=$(gh api "repos/${repo}/releases/latest" 2>/dev/null || true)
  latest_release=$(echo "$raw_release" | jq -r '.tag_name // empty' 2>/dev/null || true)
  [[ -z "$latest_release" ]] && latest_release="none"

  # Get latest commit SHA + message + date on default branch (single API call)
  commit_json=$(gh api "repos/${repo}/commits?per_page=1" 2>/dev/null || echo '[]')
  latest_commit=$(echo "$commit_json" | jq -r '.[0].sha[:7] // "unknown"' 2>/dev/null || echo "unknown")
  latest_commit_msg=$(echo "$commit_json" | jq -r '(.[0].commit.message // "") | split("\n")[0]' 2>/dev/null || echo "")
  latest_commit_date=$(echo "$commit_json" | jq -r '(.[0].commit.committer.date // "")[:10]' 2>/dev/null || echo "")

  # Compare against saved state
  synced_release=$(echo "$EXISTING" | jq -r --arg r "$repo" '.[$r].synced_release // "none"')
  synced_commit=$(echo "$EXISTING" | jq -r --arg r "$repo" '.[$r].synced_commit // "unknown"')

  release_changed=false
  commit_changed=false
  if [[ "$latest_release" != "$synced_release" && "$latest_release" != "none" ]]; then
    release_changed=true
    HAS_CHANGES=true
  fi
  if [[ "$latest_commit" != "$synced_commit" ]]; then
    commit_changed=true
    HAS_CHANGES=true
  fi

  # Build result entry
  result=$(jq -n \
    --arg repo "$repo" \
    --arg skills "$skills" \
    --arg latest_release "$latest_release" \
    --arg synced_release "$synced_release" \
    --arg latest_commit "$latest_commit" \
    --arg latest_commit_msg "$latest_commit_msg" \
    --arg latest_commit_date "$latest_commit_date" \
    --arg synced_commit "$synced_commit" \
    --argjson release_changed "$release_changed" \
    --argjson commit_changed "$commit_changed" \
    '{
      repo: $repo,
      skills: $skills,
      latest_release: $latest_release,
      synced_release: $synced_release,
      release_changed: $release_changed,
      latest_commit: $latest_commit,
      latest_commit_msg: $latest_commit_msg,
      latest_commit_date: $latest_commit_date,
      synced_commit: $synced_commit,
      commit_changed: $commit_changed
    }')

  RESULTS=$(echo "$RESULTS" | jq --argjson r "$result" '. + [$r]')
done

# Output
if $JSON_MODE; then
  echo "$RESULTS" | jq '.'
else
  # Human-readable report
  changed_repos=$(echo "$RESULTS" | jq -r '.[] | select(.release_changed or .commit_changed) | .repo')
  if [[ -z "$changed_repos" ]]; then
    echo "All upstream repos are up to date."
  else
    echo "Upstream changes detected:"
    echo ""
    echo "$RESULTS" | jq -r '.[] | select(.release_changed or .commit_changed) |
      "  \(.repo)" +
      (if .release_changed then "\n    Release: \(.synced_release) -> \(.latest_release)" else "" end) +
      (if .commit_changed then "\n    Latest:  \(.latest_commit) (\(.latest_commit_date)) \(.latest_commit_msg)" else "" end) +
      "\n    Skills:  \(.skills)"'
  fi
fi

# Update versions file if --update flag
if $UPDATE_MODE; then
  # Build new versions object from results
  NEW_VERSIONS=$(echo "$RESULTS" | jq '
    reduce .[] as $r ({};
      .[$r.repo] = {
        synced_release: $r.latest_release,
        synced_commit: $r.latest_commit,
        checked_at: (now | todate)
      }
    )')
  echo "$NEW_VERSIONS" | jq '.' > "$VERSIONS_FILE"
  if ! $JSON_MODE; then
    echo ""
    echo "Updated ${VERSIONS_FILE}"
  fi
fi

# Exit code: 0 = changes, 1 = no changes
if $HAS_CHANGES; then
  exit 0
else
  exit 1
fi
