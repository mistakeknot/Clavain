---
name: landing-a-change
description: Use when implementation is complete and all tests pass — guides the disciplined process of verifying, documenting, and landing a change on trunk
---

# Landing a Change

## Overview

Guide the disciplined completion of work: verify everything is solid, document what was done, and land the change cleanly.

**Core principle:** Verify → Review evidence → Document → Commit → Confirm.

**Announce at start:** "I'm using the landing-a-change skill to complete this work."

## The Process

### Step 1: Verify Tests

**Before anything else, verify tests pass:**

```bash
# Run project's test suite
# go test ./... | npm test | pytest | cargo test
```

**If tests fail:** Stop. Don't proceed to Step 2. Fix the failures first.

**If tests pass:** Continue to Step 2.

### Step 2: Verify Plan Compliance

Check that the implementation matches the plan:

- Was there a plan document? If so, are all checkboxes checked?
- Are there any TODO comments that should have been resolved?
- Does the implementation match what was agreed upon?

**If there was a plan:** Load the `verification-before-completion` skill for thorough checking.

**If no plan existed:** Proceed to Step 3.

### Step 3: Review Evidence Checklist

Verify the following before committing:

- [ ] All tests pass (Step 1 confirmed)
- [ ] Plan checkpoints complete (if plan exists)
- [ ] No unresolved TODO comments in changed files
- [ ] No debugging artifacts left behind (console.log, fmt.Println debug lines, etc.)
- [ ] Changes are committed in logical units with descriptive messages
- [ ] If deploy-relevant: deployment verification plan exists

**If deploy-relevant changes:** Consider invoking the `deployment-verification-agent` for a Go/No-Go checklist.

### Step 4: Document the Change

Present exactly these options:

```
Implementation verified. How would you like to land this?

1. Commit and push to main
2. Commit locally (push later)
3. Generate a changelog entry first, then commit
4. I need to review the changes first
```

**Don't add explanation** — keep options concise.

### Step 5: Execute Choice

#### Option 1: Commit and push

```bash
# Close completed beads issues (if .beads/ exists)
bd close <issue-ids>

# Stage relevant files (NOT git add .)
git add <specific files>

# Sync beads state
bd sync --from-main

# Commit with conventional message
git commit -m "feat(scope): description of what and why

Co-Authored-By: Claude <noreply@anthropic.com>"

# Push
git push
```

#### Option 2: Commit locally

Same as Option 1 but skip the push.

#### Option 3: Changelog first

Run `/clavain:changelog` to generate a changelog entry, then proceed with Option 1 or 2.

#### Option 4: Review first

Show `git diff --stat` and `git diff` for the user to review, then return to Step 4.

### Step 6: Capture Learnings (Optional)

If anything notable was learned during this work:

- Run `/clavain:learnings` to document the solved problem
- Or note key insights in the project's memory files

## Integration

**Called by:**
- **subagent-driven-development** (after all tasks complete)
- **executing-plans** (after all batches complete)
- **work** command (Phase 4: Ship It)

**Invokes:**
- **verification-before-completion** — for thorough verification when a plan exists
- **deployment-verification-agent** — when changes are deploy-relevant
- **changelog** command — when user wants changelog before committing

## Common Mistakes

**Skipping test verification**
- **Problem:** Land broken code
- **Fix:** Always verify tests before offering options

**Forgetting to check for debug artifacts**
- **Problem:** Ship console.log, fmt.Println, or TODO comments
- **Fix:** Grep changed files for common debug patterns

**Committing everything at once**
- **Problem:** `git add .` catches unrelated files
- **Fix:** Stage specific files related to this change

**No confirmation for destructive actions**
- **Problem:** Push when user wasn't ready
- **Fix:** Present structured options, execute only the chosen one

## Red Flags

**Never:**
- Push without verifying tests pass
- Skip the evidence checklist
- Auto-push without user choosing Option 1
- Leave TODO comments unresolved

**Always:**
- Verify tests before offering options
- Present exactly 4 options
- Stage specific files, not `git add .`
- Offer changelog generation
