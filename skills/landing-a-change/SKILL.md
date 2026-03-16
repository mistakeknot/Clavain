---
name: landing-a-change
description: Use when implementation is complete and all tests pass — guides the disciplined process of verifying, documenting, and landing a change on trunk
---

<!-- compact: SKILL-compact.md — if it exists in this directory, load it instead of following the full instructions below. The compact version contains the same verify → review → document → commit → confirm process. -->

# Landing a Change

Verify → Review evidence → Document → Commit → Confirm.

**Announce:** "I'm using the landing-a-change skill to complete this work."

## Step 1: Verify Tests

Run project test suite (`go test ./...` / `npm test` / `pytest` / `cargo test`). If tests fail, stop and fix. Do not proceed.

## Step 2: Verify Plan Compliance

- Were all plan checkboxes checked?
- Any unresolved TODO comments?
- Implementation matches agreed scope?

If a plan existed, invoke `verification-before-completion` skill. Otherwise proceed.

## Step 3: Evidence Checklist

- [ ] Tests pass
- [ ] Plan checkpoints complete (if plan exists)
- [ ] No unresolved TODOs in changed files
- [ ] No debug artifacts (`console.log`, `fmt.Println`, etc.)
- [ ] Changes in logical commits with descriptive messages
- [ ] Deploy verification plan exists (if deploy-relevant)

If deploy-relevant, consider invoking `fd-safety`.

## Step 4: Present Options (AskUserQuestion)

```
question: "Implementation verified. How would you like to land this?"
options:
  - Commit and push
  - Commit locally
  - Changelog first (runs /clavain:changelog)
  - Review first (show git diff, return to this step)
```

## Step 5: Execute

**Commit and push / Commit locally:**
```bash
bd close <issue-ids>          # if .beads/ exists
git add <specific files>      # NOT git add .
git commit -m "feat(scope): description

Co-Authored-By: Claude <noreply@anthropic.com>"
git push                      # skip if "locally" chosen
```

**Changelog first:** Run `/clavain:changelog`, then commit.

**Review first:** Show `git diff --stat && git diff`, return to Step 4.

## Step 6: Capture Learnings (Optional)

Run `/clavain:compound` or note insights in project memory files.

## Red Flags

- Never push without verified tests
- Never `git add .` — stage specific files
- Never auto-push without user selecting Option 1
- Never skip the evidence checklist
