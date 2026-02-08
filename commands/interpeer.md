---
name: interpeer
description: Quick cross-AI peer review — auto-detects host agent and calls the other for a second opinion
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

If the user wants deeper review:
- **"go deeper"** or **"use Oracle"** → Switch to `prompterpeer` skill
- **"get consensus"** or **"council"** → Switch to `winterpeer` skill
- **"what do they disagree on?"** → Switch to `splinterpeer` skill
