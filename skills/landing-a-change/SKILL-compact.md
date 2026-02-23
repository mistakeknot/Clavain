# Landing a Change (compact)

Verify → Review evidence → Document → Commit → Confirm.

## Process

### Step 1: Verify Tests

Run project test suite. **If tests fail: STOP.** Fix first.

### Step 2: Verify Plan Compliance

If a plan document exists: check all checkboxes, resolve TODOs, load `verification-before-completion` skill. If no plan: skip.

### Step 3: Evidence Checklist

- [ ] Tests pass
- [ ] Plan checkpoints complete
- [ ] No unresolved TODO comments in changed files
- [ ] No debug artifacts (console.log, fmt.Println)
- [ ] Changes in logical commit units
- [ ] Deploy verification plan (if deploy-relevant)

### Step 4: Present Options via AskUserQuestion

1. **Commit and push** — commit to main, push to remote
2. **Commit locally** — commit, don't push
3. **Changelog first** — run `/clavain:changelog`, then commit
4. **Review first** — show `git diff`, return to options

### Step 5: Execute

Close beads (`bd close <ids>`), stage specific files (not `git add .`), `bd sync`, commit with conventional message + Co-Authored-By, push if chosen.

### Step 6: Capture Learnings (optional)

If notable learnings: run `/clavain:compound` or update memory files.

## Red Flags

Never push without passing tests. Never `git add .`. Never auto-push without user choosing it.

---

*For detailed integration points or common mistakes, read SKILL.md.*
