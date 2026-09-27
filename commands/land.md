---
name: land
description: Run the landing workflow for trunk-based handoff
argument-hint: "[change set, PR, or branch to land]"
allowed-tools: Skill(landing-a-change)
disable-model-invocation: true
---

Invoke the landing-a-change skill for: $ARGUMENTS

**After the skill pushes to the base branch**, register the landed artifact (skip it for a PR, kept branch, local commit or discard):
```bash
clavain-cli set-artifact "$CLAVAIN_BEAD_ID" "landed" "$(git rev-parse HEAD)" 2>/dev/null || true
```
