---
name: cross-review
description: "Alias for interpeer — cross-AI peer review (Claude ↔ Codex/Oracle)"
argument-hint: "[files or description to review]"
---

# Cross-AI Peer Review

Get a quick second opinion from the other AI.

## Arguments

<review_target> #$ARGUMENTS </review_target>

**If empty:** Review the most recently changed files (`git diff --name-only HEAD~1..HEAD`).

## Execution

Load the `interpeer` skill and follow its workflow.

## Escalation

If the user wants deeper review, switch modes within `interpeer`:
- **"go deeper"** or **"use Oracle"** → Switch to `deep` mode
- **"get consensus"** or **"council"** → Switch to `council` mode
- **"what do they disagree on?"** → Switch to `mine` mode
