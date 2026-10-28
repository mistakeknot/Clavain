---
name: full-stop
description: Use when told "full stop", or when asked to own a change end to end up to a merge-ready pull request. Verify, cross-lab review, open the PR ready, register the watcher, fix CI, escalate, then stop. Never merges.
---

<!-- compact: SKILL-compact.md — if it exists in this directory, load it instead of following the full instructions below. -->

# Full Stop

"Full stop" means: you own this change from where it stands to a merge-ready pull request, then you stop. You do not merge, and you do not wait on a person except through a decision card.

**Announce:** "I'm using the full-stop skill: owning this to a merge-ready PR."

## Hard limits

- Never merge, enable auto-merge, enqueue a merge, or ask another agent to merge. The merge belongs to whoever the project's rules name (the vizier under the standing approvals, or the owner).
- Never force-push, delete a branch, create or change a tag or release, or push the default branch. Push a work branch only.
- Never bypass the pre-push guard or any hook. If a gate or permission denies an action, report the denial and stop.
- Ask a human only through the project's decision-card channel. A question left in the thread is not asked.
- A public repository's PR title, body, comments and footer carry no ruling IDs, card keys, private paths, hostnames or secrets. Determine visibility first (`gh repo view --json isPrivate`); if unknown, treat it as public. Check every payload you post, including copied review output and CI logs.

## Process

### 1. Verify
Follow `clavain:landing-a-change` Steps 1–3 (tests, plan compliance, evidence checklist) on a work branch. Commit in logical commits.

### 2. Open the PR ready
Push the work branch and open the PR **ready for review, not draft** (`gh pr create`, no `--draft`). Use `/describe-pr` for the body. Then `sonnerie register owner/repo#N`. The PR exists before review because the review receipt is keyed to the PR number and head SHA.

### 3. Cross-lab review loop
Run the packaged reviewer against the exact head and base:

```bash
dispatch.sh --role cross-lab-review -s read-only --producer-identity <model that authored the change, from its receipt> \
  --repo OWNER/NAME --repo-id ID --pr N --head <head sha> --base <base sha> \
  --prompt-file review.prompt -o review.out -C <worktree>
```

The prompt ends with "Verdict: PASS|PASS WITH NOTES|FAIL". A bare transcript is not a receipt. Receipts normalize FAIL to BLOCK.

- Record every round: round number, head SHA, reviewer model, verdict. A BLOCK is never dropped from the record, even when a later round passes; say how each BLOCK was resolved.
- Fix findings with new commits, then re-review at the new head under `clavain:code-review-discipline`: the brief carries the previous open findings verbatim, the reviewed head and base, and the fix diff, and the reviewer verdicts each finding ADDRESSED or NOT ADDRESSED. A fresh reviewer's PASS does not close an unaddressed earlier finding.
- Escalation: a disproven premise escalates immediately. Two demonstrated failures request escalation (canon, `docs/canon/reasoning-routing.md`); do not start another autonomous round once a Critical or Important finding has survived a fix. The loop cap is three failed rounds, then escalate before a fourth. If this runs inside the final review of subagent-driven development or executing-plans, their stricter limit governs: one fix round and one scoped re-review, then a human blocker. One confirming review after a pass is allowed. Do not add a commit only to obtain a fresh receipt after a BLOCK; escalate at that head.
- Operational failures (quota, auth, timeout) are not verdicts; retry or use the packaged fallback, and report an unavailable seat rather than skipping review.

### 4. CI
Watch the PR's checks. Fix failures with new commits. After any commit, re-run verification and the review at the final head. Merge-ready means: checks green, a passing receipt at the current head and base, and nothing changed since.

### 5. Footer
Before escalating, set the PR body's review footer with `/describe-pr` rules: rounds, reviewer model, per-round verdicts, final verdict, and the final head SHA. If a review returned BLOCK at any point, the footer says so.

### 6. Escalate and stop
Send the PR URL, what merging it does, and the review evidence to the project's escalation channel. State whether a standing merge class covers it or it stays with the owner. If the change touches instruction files, hooks, settings, credentials or CI workflows, say so. Then stop.
