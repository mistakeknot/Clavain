---
name: ship
description: Use when work is done and you need to commit, push, close beads, and sync in one shot. The quick session-close ceremony.
---

# Ship

## Overview

One-shot session close: commit staged changes, push, close completed beads, and sync. Use this when verification is already done and you just need to land and close out.

For careful, disciplined landing with verification and review, use `landing-a-change` instead.

**Announce at start:** "I'm using the ship skill to close out this work."

## Inputs

The user may provide:
- **Bead IDs** to close (e.g., `iv-abc12 iv-def34`). If not provided, ask which beads to close.
- **Commit message** — if not provided, draft one from staged changes.

## The Process

### Step 1: Check State

```bash
git status
git diff --cached --stat
```

- If there are unstaged changes, ask the user what to stage.
- If there are no changes at all and no beads to close, say "Nothing to ship" and stop.

### Step 2: Commit

If there are staged or stageable changes:

1. Stage the relevant files (prefer specific files over `git add -A`)
2. Draft a concise commit message (or use the user-provided one)
3. Commit with `Co-Authored-By: Claude <noreply@anthropic.com>` trailer

### Step 3: Push

```bash
git push
```

If push fails (e.g., diverged), stop and report — do not force push.

### Step 4: Close Beads

If bead IDs were provided:

```bash
bd close <id1> <id2> ...
```

Close all provided beads in a single command. Skip any that are already closed.

If no bead IDs were provided but there are `in_progress` beads for this session, list them and ask which to close.

### Step 5: Sync Beads

```bash
bash .beads/push.sh
```

### Step 6: Final Push

Push again to include the beads sync commit:

```bash
git push
```

### Step 7: Confirm

Report what was done:
- Commit hash and message
- Files changed count
- Beads closed
- Push status
