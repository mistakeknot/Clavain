# Review by risk: two-week trial (bead mk-h9541)

Window: 2026-11-17 through 2026-11-30 (inclusive). The policy lives in
`config/routing.yaml` under `reasoning.review_policy`; the decision helper is
`scripts/review_policy.py` and the round limit is enforced in
`scripts/review-round-limit.py` (called by `scripts/dispatch.sh` before any
review seat starts).

| Change class | Review |
|---|---|
| text-only, doc-only, test-only, declared one-shot prototype | none; the author's check, tests and CI carry it |
| routine reversible code | one cross-lab round; a second only after a P1/High finding (no severity counts as high) |
| keep-list: spend, credentials, sign-ins, payments, save formats and migrations, releases and publishes, instruction files, hooks, CI workflows, routing policy | unchanged: three fix rounds and a confirming review |

A change with no changed-path list is unclassifiable and keeps full review. One
keep-list round on a bead keeps the whole bead on the full cap. Frontier floors,
reviewer independence and the seat tables are not touched.

## Roll back

- Set `enabled: false` in `review_policy` (one line), or revert the commit that added the block.
- Export `CLAVAIN_REVIEW_POLICY=off` for a single dispatch.
- Do nothing: after `last_day` the policy reports `full` for every change.

## Measure

`scripts/review-trial-report.py` reads review receipts, `agent-cli outcomes` and `gh`, and writes one JSON
report per window on the same definitions (rounds per change, findings that changed code per round, review
tokens as a share of tokens, reverts and fix PRs within 7 days of merge).

    python3 -I scripts/review-trial-report.py --label baseline --since 2026-11-02 --until 2026-11-15 --out baseline.json
    python3 -I scripts/review-trial-report.py --label trial --since 2026-11-17 --until 2026-11-30 --out trial.json
    python3 -I scripts/review-trial-report.py --compare baseline.json trial.json

Run the trial report on 2026-11-30 or 2026-12-01: the token window counts back from the day it runs.
Limits: receipts before plugin 0.6.334 carry no `changed_paths` or findings, so they report as `no-paths`
and cannot be split by class; "findings that changed code" is a proxy (a later round ran on a new head); the
token share covers dispatch-recorded roles on closed beads only.
