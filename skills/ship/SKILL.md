---
name: ship
description: Use when work is done and you need to commit, push, close beads, and sync in one shot. The quick session-close ceremony.
---

# Ship

One-shot session close: commit, push, close beads, sync. Use when verification is already done. For careful landing with verification, use `landing-a-change` instead.

**Announce:** "I'm using the ship skill to close out this work."

## Inputs

- **Bead IDs** to close (ask if not provided)
- **Commit message** (draft from staged changes if not provided)

## Step 1: Check State

```bash
git status && git diff --cached --stat
```

- Unstaged changes → ask what to stage
- No changes and no beads to close → "Nothing to ship" and stop

## Step 2: Commit

1. Stage specific files (prefer over `git add -A`)
2. Draft concise commit message or use provided one
3. `git commit -m "..." -m "Co-Authored-By: Claude <noreply@anthropic.com>"`

## Step 3: Push

```bash
git push
```

If push fails (diverged), stop and report — do not force push.

## Step 4: Close Beads

```bash
bd close <id1> <id2> ...
```

If no IDs provided, list `in_progress` beads for this session and ask which to close.

## Step 5: Sync Beads

```bash
bash .beads/push.sh
```

## Step 6: Final Push

```bash
git push
```

## Step 7: Confirm

Report: commit hash + message, files changed, beads closed, push status.
