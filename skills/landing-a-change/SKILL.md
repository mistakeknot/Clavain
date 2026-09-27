---
name: landing-a-change
description: Land verified work on trunk, or finish a feature branch or worktree, after tests and required review; preserve release authority.
---

<!-- compact: SKILL-compact.md — if it exists in this directory, load it instead of following the full instructions below. The compact version contains the same verify → review → document → commit → confirm process. -->

# Landing a Change

Verify → Review evidence → Document → Commit → Confirm.

**Announce:** "I'm using the landing-a-change skill to complete this work."

## Step 1: Verify Tests

**Artifact-cached skip:** If inside a sprint (`CLAVAIN_BEAD_ID` set), check whether tests already passed at current HEAD:

```bash
BEAD_ID="${CLAVAIN_BEAD_ID:-}"
if [[ -n "$BEAD_ID" ]]; then
    test_sha=$(clavain-cli get-artifact "$BEAD_ID" "test-pass-sha" 2>/dev/null) || test_sha=""
    current_sha=$(git rev-parse HEAD)
    if [[ "$test_sha" == "$current_sha" ]]; then
        echo "Tests verified at $test_sha (current HEAD). Skipping re-run."
        # Skip to Step 2
    fi
fi
```

If HEAD moved since the last recorded test pass, or no test-pass-sha artifact exists, or not in a sprint: run the full test suite (`go test ./...` / `npm test` / `pytest` / `cargo test`). If tests fail, stop and fix. Do not proceed.

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
- [ ] Shipped-surface sweep (if the change touches anything a reader/user sees —
  pages, UI strings, error messages, emails, docs meant for outsiders). Six
  parity questions, each answered against the *fresh reader*, not the builder:
  1. **No pipeline vocabulary** — lane/wave/slice/version labels, generator
     diagnostics, internal status enums visible to readers?
  2. **Affordance parity** — does every interaction the copy names actually
     exist on that surface?
  3. **Audience parity** — does each viewer mode only show instructions and
     widgets that viewer can actually use?
  4. **One CTA per action per view** — no duplicate entry points?
  5. **Scope-distinct controls** — do controls operating on different scopes
     look/read differently?
  6. **Spatially true status** — does status copy match where it renders
     ("below" means below)?
  Origin: Kublai soft launch, 2026-08-19 — thirteen outside-reader reports,
  all preventable by this sweep. Mechanical floor (banned-vocab lint) is
  per-repo where one exists; these six are the judgment half.

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

**On a feature branch or in a linked worktree**, detect that first and confirm the base branch with the user:

```bash
GIT_DIR=$(git rev-parse --absolute-git-dir)
GIT_COMMON=$(git rev-parse --path-format=absolute --git-common-dir)
[[ "$GIT_DIR" != "$GIT_COMMON" ]] && git rev-parse --show-toplevel   # linked worktree: its path
git branch --show-current                                           # empty on detached HEAD
```

Note the printed worktree path and branch name in the conversation; shell variables do not survive between tool calls. Commit any uncommitted work first, as in Step 5. Then offer this menu instead of the four options above: **Merge locally into `<base>`**, **Push and open PR**, **Keep the branch as is**. Offer **Discard** only when the user asks for it. On a detached HEAD, offer only Keep, or create a branch first (`git switch -c <name>`).

## Step 5: Execute

**Commit and push / Commit locally:**
```bash
git add <specific files>      # NOT git add .
git commit -m "feat(scope): description

Co-Authored-By: Claude <noreply@anthropic.com>"
git push                      # only for "Commit and push"
```

`Commit locally` leaves associated beads open. A close is only eligible after
the implementation commit is visible on the remote.

**Changelog first:** Run `/clavain:changelog`, then commit.

**Merge locally:** Find the checkout that has `<base>` checked out with `git worktree list --porcelain`. If none has it, or that checkout has uncommitted changes, stop and ask; never switch another checkout's branch. In that checkout run `git pull --ff-only` (when base has an upstream), `git merge <branch>`, then the full test suite on the merged result. If anything fails, stop and report; keep the branch and worktree. Beads stay open until base is pushed through "Commit and push". Branch deletion waits for Step 5.7.

**Push and open PR:** `git push -u origin <branch>`, then `gh pr create`. Keep the branch, worktree and beads open until the PR merges; Steps 5.5 and 5.6 do not apply to this push. If a PR watcher (such as Sonnerie) is installed, register the PR with it. Each update it delivers is a cue for one pass of [references/pr-follow-up.md](references/pr-follow-up.md); choosing this option authorises pushing fixes to the PR branch, never to base.

**Discard:** Show what will be lost (`git log --oneline <base>..<branch>` and the worktree path) and proceed only after the user types `discard`. Remove the worktree (Step 5.7), then `git branch -D <branch>`.

**Review first:** Show `git diff --stat && git diff`, return to Step 4.

## Step 5.5: Post-Push Canary (rsj.1.2)

After a push that puts the commit on the base branch succeeds, and inside a sprint (`CLAVAIN_BEAD_ID` set), run a lightweight canary check on the merged state:

```bash
if [[ -n "${CLAVAIN_BEAD_ID:-}" ]] && [[ "${CLAVAIN_SKIP_CANARY:-}" != "true" ]]; then
    source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-sprint.sh" 2>/dev/null || true
    if ! sprint_canary_check "$CLAVAIN_BEAD_ID"; then
        echo "⚠ Post-merge canary FAILED. Sprint NOT recorded as successful."
        echo "  Fix the issue and re-run, or set CLAVAIN_SKIP_CANARY=true to override."
        # Do NOT close the bead or record success
    fi
fi
```

If canary fails: warn user, emit `quality_failure` event to Interspect, do NOT record sprint as successful. If canary passes: normal flow continues.

## Step 5.6: Close After Push

Only after a push to the base branch and the post-push canary succeed, close
each selected bead through the canonical gate. A feature-branch or PR push does
not qualify; those beads close after the PR merges.

```bash
for bead_id in <issue-ids>; do
  "${CLAUDE_PLUGIN_ROOT}/scripts/gates/bead-close.sh" "$bead_id" "Landed in pushed commit $(git rev-parse --short HEAD)"
done
bd dolt push
git push
```

The wrapper verifies any installed-runtime evidence requirement before changing
tracker state. If it rejects a bead, leave that bead open and report the gate.

## Step 5.7: Worktree Cleanup

Runs after a local merge is green, after a discard, or after a PR merges. Skip it when Step 4 printed no worktree path or HEAD is detached. Remove the worktree only when it sits under the project's `.worktrees/` or `worktrees/` directory or the user asks; any other worktree belongs to the host or harness, so leave it and use the host's own exit tool if it has one. Keep it for "Push and open PR" until merge and for "Keep the branch".

Run from the checkout found in the merge step, never from inside the worktree:

```bash
git -C <worktree-path> status --porcelain --ignored   # must print nothing
git worktree remove <worktree-path>
git branch -d <branch>     # after a merge; after a typed discard, -D
```

Git refuses to delete a branch that a worktree still has checked out, so the branch goes last. If the status check prints anything, do not remove the worktree. Show the files and ask whether to commit, move or delete them. Never pass `--force`: plain `git worktree remove` already deletes ignored files (logs, `.env`, local caches) without warning, and `--force` also discards untracked and modified files.

## Step 6: Capture Learnings (Optional)

Run `/clavain:compound` or note insights in project memory files.

## Red Flags

- Never push without verified tests
- Never close a bead before its implementation commit is pushed
- Never `git add .` — stage specific files
- Never push without the user choosing a push option
- Never skip the evidence checklist
- Never force-push unless the user asks for it; a rejected push means fetch and investigate
- Never `git branch -D` outside an explicit, typed `discard`
- Never delete a merged branch before re-testing the merged result
- Never `git worktree remove --force`, or remove a worktree with untracked or ignored files
