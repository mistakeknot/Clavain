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
- [ ] Shipped-surface sweep (if readers/users see the change): no pipeline
  vocabulary on reader surfaces; every interaction the copy names exists
  (affordance parity); each viewer mode matches that viewer's capabilities
  (audience parity); one CTA per action per view; controls on different
  scopes look different; status copy spatially true. Judge as the fresh
  reader, not the builder.

### Step 4: Present Options via AskUserQuestion

1. **Commit and push** — commit to main, push to remote
2. **Commit locally** — commit, don't push
3. **Changelog first** — run `/clavain:changelog`, then commit
4. **Review first** — show `git diff`, return to options

On a feature branch or linked worktree (`git rev-parse --absolute-git-dir` differs from `git rev-parse --path-format=absolute --git-common-dir`), note the worktree path and branch in the conversation and confirm the base branch. Commit pending work, then offer this menu instead: merge locally into base, push and open PR, keep as is. Offer discard only when asked. On a detached HEAD, offer only keep, or create a branch first.

### Step 5: Execute

Stage specific files (not `git add .`), commit with a conventional message +
Co-Authored-By, then push when that option was chosen. A local-only commit leaves
its beads open.

```bash
git push  # only for the commit-and-push option
```

- **Merge locally:** find the checkout on base with `git worktree list --porcelain`; if none, or it is dirty, stop and ask. There: `git pull --ff-only`, merge, re-run tests on the merged result; on failure keep branch and worktree. Beads stay open until base is pushed. Branch deletion waits for Step 5.7.
- **Push and open PR:** `git push -u origin <branch>`, `gh pr create`; register with a PR watcher (such as Sonnerie) if installed, and run one pass of `references/pr-follow-up.md` per update. Keep branch, worktree and beads open until merge; Steps 5.5–5.6 do not apply.
- **Discard:** show the commits and worktree that will be lost; proceed only after the user types `discard`.

### Step 5.5: Post-Push Canary

After a push to the base branch, if in a sprint: `sprint_canary_check "$CLAVAIN_BEAD_ID"`. On failure: warn, emit `quality_failure` to Interspect, do NOT close bead. Skip with `CLAVAIN_SKIP_CANARY=true`.

### Step 5.6: Close After Push

After a push to the base branch and the canary succeed (a PR push does not count), close each selected bead through
`"${CLAUDE_PLUGIN_ROOT}/scripts/gates/bead-close.sh" "$bead_id" "Landed in pushed commit"`,
run `bd dolt push`, then `git push` again. If the gate rejects a bead, leave it
open and report the failure.

### Step 5.7: Worktree Cleanup

After a green local merge, a discard, or a PR merge. Skip when there is no worktree path or HEAD is detached. Remove only worktrees under `.worktrees/` or `worktrees/`, or when the user asks; leave host-managed ones. From the base checkout, never inside the worktree: require `git -C <worktree-path> status --porcelain --ignored` to print nothing, run `git worktree remove <worktree-path>` without `--force`, then delete the branch (`-d`, or `-D` after a typed discard); git refuses to delete a branch a worktree still has checked out. Plain removal silently deletes ignored files; if anything is listed, ask whether to commit, move or delete it.

### Step 6: Capture Learnings (optional)

If notable learnings: run `/clavain:compound` or update memory files.

## Red Flags

Never push without passing tests. Never close before push. Never `git add .`. Never push without the user choosing a push option. Never force-push unless asked. Never `git branch -D` without a typed `discard`. Never `git worktree remove --force`.

---

*For detailed integration points or common mistakes, read SKILL.md.*
