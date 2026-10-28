# Full Stop (compact)

Own the change to a merge-ready PR, then stop. Never merge, enable auto-merge, force-push, delete a branch, touch tags/releases, push the default branch or bypass a hook. Ask humans only via a decision card. Public repo: no ruling IDs, card keys, private paths, hostnames or secrets in any posted text; unknown visibility counts as public.

1. Verify: `clavain:landing-a-change` Steps 1–3 on a work branch.
2. Open the PR ready (not draft), body from `/describe-pr`, then `sonnerie register owner/repo#N`.
3. Cross-lab review via packaged `dispatch.sh --role cross-lab-review` with `--repo --repo-id --pr --head --base`; prompt ends "Verdict: PASS|PASS WITH NOTES|FAIL". Record every round (head, model, verdict); never drop a BLOCK. Two failures request escalation; three failed rounds cap, escalate before a fourth; one confirming review allowed; no commit just to refresh a receipt after a BLOCK. Operational failures are not verdicts.
4. CI: fix with new commits, then re-verify and re-review at the final head. Merge-ready = green checks + passing receipt at current head and base.
5. Footer: rounds, reviewer model, per-round verdicts, final verdict, final head SHA; a BLOCK is stated.
6. Escalate the PR URL, effect of merging, review evidence, and whether a standing merge class covers it. Stop.
