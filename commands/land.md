---
name: land
description: Run the landing workflow for trunk-based handoff
argument-hint: "[change set, PR, or branch to land]"
allowed-tools: Skill(landing-a-change)
---

Invoke the landing-a-change skill for: $ARGUMENTS

**After the skill completes**, register the landed artifact:
```bash
clavain-cli set-artifact "$CLAVAIN_BEAD_ID" "landed" "$(git rev-parse HEAD)" 2>/dev/null || true
```
