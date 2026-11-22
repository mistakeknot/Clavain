# Review by risk: two-week trial

Window: two weeks starting on the actual merge date in America/Los_Angeles.
The merge step sets the single `reasoning.review_policy.merge_day` config value
to that Pacific calendar date (`YYYY-MM-DD`). It is null until then, which keeps
full review active. The last day is derived as `merge_day + 13 days`, inclusive;
on day 14 the trial expires. No separately maintained end date is needed.
The policy lives in
`config/routing.yaml` under `reasoning.review_policy`; the decision helper is
`scripts/review_policy.py` and the round limit is enforced in
`scripts/review-round-limit.py` (called by `scripts/dispatch.sh` before any
review seat starts).

| Change class | Review |
|---|---|
| text-only, doc-only, test-only, declared one-shot prototype, when every path is a named safe path | none; the author's check, tests and CI carry it |
| routine: code under a named source directory | one cross-lab round; a second only after a P1/High finding (no severity counts as high) |
| everything else: the keep-list (spend, credentials, sign-ins, payments, save formats and migrations, releases and publishes, instruction files, hooks, CI workflows, routing policy) and any path no safe class names | unchanged: three fix rounds and a confirming review |

Reduced review is an allow-list. A change is reduced only when every changed path is a named safe path
and no keep-list pattern matches any path. The named safe paths are: prose under a `docs/` directory and
an exact root README, CHANGELOG or LICENSE (bare or with `.md`, `.rst`, `.txt`, `.adoc`); files under a tests directory or named like a test; and code and
asset files (`ts tsx js jsx mjs css scss html svg png jpg jpeg gif webp py go rs gd lua cs java kt swift c h cpp`)
under `src/`, `app/`, `apps/`, `web/`, `ui/`, `components/`, `pages/`, `public/`, `styles/`, `assets/`
or `examples/`. A declared one-shot prototype may also hold web and media assets (`html css js jsx ts tsx
mjs svg png jpg jpeg gif webp ogg wav mp3 glb gltf`) anywhere outside the keep-list. Anything else, for
example scripts, tools, `cmd/`, shell, JSON or YAML, dependency manifests, or markdown outside `docs/`,
keeps full review, whether or not a keep-list pattern names it. The keep-list still wins over every safe path.

A change with no changed-path list is unclassifiable and keeps full review. One
keep-list round on a bead keeps the whole bead on the full cap. Frontier floors,
reviewer independence and the seat tables are not touched.

## Roll back

- Set `enabled: false` in `review_policy` (one line), or revert the commit that added the block.
- Export `CLAVAIN_REVIEW_POLICY=off` for a single dispatch.
- Do nothing: 14 days after `merge_day` the policy reports `full` for every change.

## Measure

`scripts/review-trial-report.py` reads review receipts, `agent-cli outcomes` and `gh`, and writes one JSON
report per window on the same definitions (rounds per change, findings that changed code per round, review
tokens as a share of tokens, reverts and fix PRs within 7 days of merge).

Read the start date from `reasoning.review_policy.merge_day`; derive the last day
by adding 13 days. Pass those dates as `--since` and `--until` to
`scripts/review-trial-report.py --label trial --out trial.json` on the last day
(Pacific). The token window counts back from the day it runs, so a later first
run shifts it off the trial. Take a matching two-week baseline immediately before
that start date. Compare with `--compare baseline.json trial.json`.

Merges in the final week lack seven follow-up days at the first report. They stay
`merged_follow_up_incomplete` and outside the escape rate. Run again eight days
after the last day with the same `--since` and `--until`, plus
`--tokens-from trial.json --out trial-final.json`, to retain the original token share.

The policy helper reads paths from `git diff --no-renames --name-only`, because a rename hides its old path
(a protected file renamed to a `.md` name would otherwise look like a doc). A path it cannot trust
(backslash, absolute, `.` or `..` segment, control character) is keep-list. An incomplete or invalid
`review_policy` block means no trial: full review. The trial date can only come from the clock, read in
Pacific time (America/Los_Angeles); if that zone cannot be read there is no trial.
Limits: receipts before plugin 0.6.334 carry no `changed_paths` or findings, so they report as `no-paths`
and cannot be split by class; "findings that changed code" is a proxy (a later round ran on a new head); the
token share covers dispatch-recorded roles on closed beads only.
