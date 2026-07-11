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

Stage specific files (not `git add .`), commit with a conventional message +
Co-Authored-By, then push when that option was chosen. A local-only commit leaves
its beads open.

```bash
git push  # only for the commit-and-push option
```

### Step 5.5: Post-Push Canary

After push, if in a sprint: `sprint_canary_check "$CLAVAIN_BEAD_ID"`. On failure: warn, emit `quality_failure` to Interspect, do NOT close bead. Skip with `CLAVAIN_SKIP_CANARY=true`.

### Step 5.6: Close After Push

After the push and canary succeed, close each selected bead through
`"${CLAUDE_PLUGIN_ROOT}/scripts/gates/bead-close.sh" "$bead_id" "Landed in pushed commit"`,
run `bd dolt push`, then `git push` again. If the gate rejects a bead, leave it
open and report the failure.

### Step 6: Capture Learnings (optional)

If notable learnings: run `/clavain:compound` or update memory files.

## Red Flags

Never push without passing tests. Never close before push. Never `git add .`. Never auto-push without user choosing it.

---

*For detailed integration points or common mistakes, read SKILL.md.*
