# bp8 Remaining Work — Implementation Plan
**Phase:** planned (as of 2026-02-20T06:58:40Z)

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Close the bp8 insights-gap epic by shipping the last remaining item: a SessionEnd backup handoff hook. (bp8.7 Codex dispatch was closed as superseded by Track C Agency Architecture.)

**Architecture:** One new bash hook script + hooks.json entry for SessionEnd backup handoff.

**Tech Stack:** Bash (hook), JSON (hooks.json)

---

### Task 1: SessionEnd Backup Handoff Hook

**Files:**
- Create: `hooks/session-end-handoff.sh`
- Modify: `hooks/hooks.json:93-103`

**Step 1: Create the hook script**

Create `hooks/session-end-handoff.sh`:

```bash
#!/usr/bin/env bash
# SessionEnd hook: lightweight backup handoff when Stop hook didn't fire
#
# Belt-and-suspenders safety net. The primary handoff runs on Stop
# (session-handoff.sh — blocks Claude, gets a thoughtful narrative).
# This backup runs async on SessionEnd and writes a machine-generated
# handoff with git diff, active beads, and recent commits.
#
# Skips if the Stop hook already fired (sentinel file exists).
#
# Input: Hook JSON on stdin (session_id)
# Output: None (async, fire-and-forget)
# Exit: 0 always

set -euo pipefail

# Guard: fail-open if jq is not available
if ! command -v jq &>/dev/null; then
    exit 0
fi

# Read hook input
INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')

# Check if Stop handoff already fired — if so, nothing to do
if [[ -f "/tmp/clavain-handoff-${SESSION_ID}" ]]; then
    exit 0
fi

# Check if .clavain directory exists (we're in a Clavain-aware project)
if [[ ! -d ".clavain" ]]; then
    exit 0
fi

mkdir -p ".clavain/scratch" 2>/dev/null || true

TIMESTAMP=$(date +%Y-%m-%dT%H%M)
SESSION_SHORT="${SESSION_ID:0:8}"
HANDOFF_PATH=".clavain/scratch/handoff-${TIMESTAMP}-${SESSION_SHORT}.md"

# Gather signals
DIFF_STAT=""
STAGED_STAT=""
RECENT_COMMITS=""
if command -v git &>/dev/null && git rev-parse --is-inside-work-tree &>/dev/null 2>&1; then
    DIFF_STAT=$(git diff --stat 2>/dev/null || true)
    STAGED_STAT=$(git diff --cached --stat 2>/dev/null || true)
    RECENT_COMMITS=$(git log --oneline -5 2>/dev/null || true)
fi

IN_PROGRESS_BEADS=""
if command -v bd &>/dev/null; then
    IN_PROGRESS_BEADS=$(bd list --status=in_progress 2>/dev/null || true)
fi

# Only write handoff if there are signals worth saving
if [[ -z "$DIFF_STAT" && -z "$STAGED_STAT" && -z "$IN_PROGRESS_BEADS" ]]; then
    exit 0
fi

# Write minimal machine-generated handoff
{
    echo "# Session Handoff (auto-generated backup)"
    echo ""
    echo "**Session:** ${SESSION_SHORT}"
    echo "**Generated:** $(date -Iseconds)"
    echo "**Note:** Stop hook did not fire — this is an automated backup."
    echo ""
    if [[ -n "$DIFF_STAT" ]]; then
        echo "## Unstaged Changes"
        echo '```'
        echo "$DIFF_STAT"
        echo '```'
        echo ""
    fi
    if [[ -n "$STAGED_STAT" ]]; then
        echo "## Staged Changes"
        echo '```'
        echo "$STAGED_STAT"
        echo '```'
        echo ""
    fi
    if [[ -n "$IN_PROGRESS_BEADS" ]]; then
        echo "## In-Progress Beads"
        echo '```'
        echo "$IN_PROGRESS_BEADS"
        echo '```'
        echo ""
    fi
    if [[ -n "$RECENT_COMMITS" ]]; then
        echo "## Recent Commits"
        echo '```'
        echo "$RECENT_COMMITS"
        echo '```'
    fi
} > "$HANDOFF_PATH"

# Update latest symlink
ln -sf "$(basename "$HANDOFF_PATH")" ".clavain/scratch/handoff-latest.md" 2>/dev/null || true

# Prune old handoffs: keep last 10
# shellcheck disable=SC2012
ls -1t .clavain/scratch/handoff-*.md 2>/dev/null | tail -n +11 | xargs -r rm -f 2>/dev/null || true

# Sync beads if available
if command -v bd &>/dev/null; then
    bd sync 2>/dev/null || true
fi

exit 0
```

**Step 2: Verify script syntax**

Run: `bash -n hooks/session-end-handoff.sh`
Expected: no output (clean syntax)

**Step 3: Add hook to hooks.json**

In `hooks/hooks.json`, modify the `SessionEnd` block (line 93-103) to add the new hook after the existing `dotfiles-sync.sh` entry:

```json
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/dotfiles-sync.sh",
            "async": true
          },
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/session-end-handoff.sh",
            "async": true
          }
        ]
      }
    ]
```

**Step 4: Validate hooks.json**

Run: `python3 -c "import json; json.load(open('hooks/hooks.json'))"`
Expected: no output (valid JSON)

**Step 5: Update CLAUDE.md hook count**

The hook count in CLAUDE.md says 21 hooks. Adding session-end-handoff.sh makes it 22. Update the bash -n line list and the count.

**Step 6: Commit**

```bash
git add hooks/session-end-handoff.sh hooks/hooks.json CLAUDE.md
git commit -m "feat(hooks): add SessionEnd backup handoff — belt-and-suspenders safety net"
```

---

### Task 2: Close bp8 Epic

**Step 1: Close remaining beads**

```bash
bd close Clavain-bp8.2 --reason="Shipped: hooks/session-end-handoff.sh — SessionEnd backup handoff"
bd close Clavain-bp8 --reason="Epic complete: 5/7 already shipped (verified + closed), bp8.2 shipped this session, bp8.7 superseded by Track C"
```

**Step 2: Bump version**

Run: `bash scripts/bump-version.sh 0.6.44`

**Step 3: Commit version bump**

```bash
git add -A
git commit -m "chore: bump to 0.6.44 — close bp8 insights-gap epic"
```
