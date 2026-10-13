# RK-CI-GUARD: running the public-repo guard in the CI service (read-only investigation)

Beads mk-6ghz4 / mk-54hzc. Nothing in the dev server, the CI registry or hooks was changed.

## What the guard is
- Dispatcher `dotfiles/cloud/pre-push.sh` calls `dotfiles/cloud/pre-push-public-repo.sh`
  (488 lines), which uses `public-repo-scan.py` + `public-repo-patterns.tsv` and gitleaks
  (`cloud/.gitleaks-push.toml`).
- Flow: resolve the real push destination, ask `gh api repos/O/R --jq .private` on every push,
  and for a public mistakeknot/gensysven repo scan every commit the destination does not already
  have (from `git ls-remote` of the destination, not local refs). Findings block the push.
- Audit: `~/.local/state/public-repo-guard/audit.log`; human overrides in `bypass.log`.
- STRICT mode (`PUBLIC_REPO_GUARD_STRICT=1`, used by `git-autosync-promote.sh`) ignores the bypass,
  blocks on any gh outage, and prints `PUBLIC_REPO_GUARD: SCANNED <n> commit(s)` or `NOT-PUBLIC`
  on stdout only after a completed verdict. This is the interface a CI job should consume.
- `rig-public-guard-unchecked.py` (run daily by `rig-health-check.sh`) fails on any `unchecked-*` line.

## Running it in the CI service (proposal, design choice)
A pre-push hook is client-side and preventive; CI runs after the push and is only detective.
It adds value as a second control for pushes that bypass hooks (`--no-verify`, other clients,
agents on the Mac, autosync lanes). Proposed job class `public-guard`, per public
mistakeknot/gensysven repo (visibility read from the GitHub API at job start, never from the registry):
1. Fresh isolated guest checks out the exact pushed commit with full history of the pushed ref.
2. Compute the range `<previous known head of the ref>..<pushed sha>` from the the CI service event record
   (for a new ref, all commits not reachable from the default branch).
3. Feed the range to the same scanner. Two options: (a) call `pre-push-public-repo.sh` with
   `PUBLIC_REPO_GUARD_STRICT=1`, synthesised pre-push stdin and a file:// "remote" pointing at the
   previous state (reuses 100% of logic, but the script resolves a destination via git remote
   config, so it needs a small seam); (b) a thin wrapper that runs gitleaks and
   `public-repo-scan.py` directly over the range (smaller, but a second copy of the plumbing to keep in sync).
   Recommend (a) with a `PUBLIC_REPO_GUARD_RANGE` seam, so there is one implementation.
4. Pass criteria: exit 0 and the `SCANNED`/`NOT-PUBLIC` line. A gh outage fails the job (STRICT), never passes it.
5. Pin the dotfiles `cloud/` revision (scripts, patterns, gitleaks config) by sha in the registry row,
   so a push cannot weaken the rules that judge it; allowlist `.public-hygiene-allow` is already read
   from the destination's existing commit.
6. Per migration policy: two successful executions at the same commit in fresh guests before this
   class is treated as transferred. A red job must not be described as server-enforced protection:
   it reports, it does not block the push (GitHub branch protection is a separate matter).
Prerequisites to confirm with the CI owner: gitleaks and gh credentials (read-only, repo metadata)
available in the guest; network egress to api.github.com; where the previous-head record lives.

## Why 23 pushes went unchecked in the last 7 days (window 2026-10-06..13)
All 23 are `unchecked-gh-unreachable-cached-private`, all on 2026-10-07 08:30Z through 2026-10-08 01:30Z, all `the server user`:
dotfiles 1, garden-salon 13 (9+4), ops 3 (2+1), gsvdotcom 2, swarmwinder 2, Undersketch 2.
Mechanism: `gh api` did not answer, no fresh answer was possible, and the cache said "private",
so the guard let the push through unscanned (documented behaviour; the cache is consulted only in an outage).
Events cluster on :30 hours (hourly cadence), which matches the unattended autosync/promote timers rather than interactive pushes.
Not seen since 2026-10-08T01:30Z (about 5 days). Overall log (2816 lines): 1500 clean-nothing-to-publish,
813 blocked, 452 clean, 25 gh-unreachable-cached-public (still scanned), 23 unchecked, 2 bypassed (recorded, reasoned), 1 skipped-non-github.
Current check: `gh api` answers `private=true` for all six repos today, so no public content is known to have gone unscanned.
Caveats / unknown: the log records no gh error text, so the root cause of the outage (network, auth, rate limit) is not established;
journal search for that window found nothing. The cached-private path is still a gap: a repo made public during an outage would pass.
Suggested follow-ups (not done): log gh's exit/stderr class in the audit line; run the guard in STRICT mode on the autosync path
(promote already does) so unattended pushes cannot take the cached-private path; add the CI job above as the backstop.
