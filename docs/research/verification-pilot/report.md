# Verification pilot

Task `Sylveste-5ewg` links the [plan](../../plans/2026-09-08-verification-pilot.md)
and its dependency manifest. `Sylveste-uo7b`, `sylveste-xoki.2` and CI campaign
`mk-ag2s.25` retain their broader acceptance criteria.

The runner and orchestrator adapter are integrated locally. User authorization
cleared adapter ownership and external Claude QA. Model-policy files are untouched.
Manifests without checks must explicitly declare
`verification: {required: false, checks: []}`; this permits independent review
without a machine acceptance or vetting signal. Journals preserve verification
state, failure kind, receipt path/hash and machine eligibility.

## Fresh local evidence

The installed CLI produced source-stable VERIFIED receipts on the dirty working
state based on `ffc42453b24fbc0e80fd63a6f83eef92848d47cc`:

- Clavain: 232 focused verification/orchestrator tests, zero skips or failures.
- Beads: 33 Python tests and three isolated transport shell suites, all passing,
  against dependency `affe02be3755254a7c7204bd33df945ba430bc09`.
- Broader structural run: 1,112 passes and one upstream-clone skip, before the
  last four CI guard cases; those four subsequently passed separately and in
  the 232-test focused run.
- Delivery/worker suites: 79 passes and 15 passing subtests.
- Broad shell run: 740 passes, 34 failures, 56 skips. Eight session-start and six
  installer failures reproduce unchanged at baseline `0f60f404`. Eighteen
  Intercore seam cases pass after restoring sandbox-denied Go-cache access.
  Two runtime-evidence canaries initially stopped on clean-source/cache
  prerequisites; their post-commit results are retained with the fleet evidence.
  This is not a claim that the full shell gate passes.

A real concurrent routing-documentation commit changed HEAD/index during an
otherwise passing 232-test run. The runner returned UNVERIFIABLE and preserved
that receipt. A fresh run at the stable new HEAD passed. No unrelated work was
reverted, inspected for content, or included in this pilot's edits.

Pipeline tests instrument dispatcher calls: operational failures spawn zero
repair/review agents, assertions retain the existing two-repair bound, and
optional empty checks invoke review with machine eligibility false. These are
fixture counts, not production model savings. Beads fixtures use disposable
repositories and stub databases; they do not prove native Dolt correctness or
live cross-host synchronization.

## Independent review

Six external Claude reviews completed. They drove reproduced fixes for index
refresh invalidation, shell-function shadowing, artifact namespace collisions,
complete report-name validation, nested XML outcomes, journal evidence binding,
error attribution, missing test dependencies, schema resolution and CI artifact
retention/specification pinning. The final substantive review independently
passed all then-current 228 tests and roundtripped the complete evidence archive.

It left two low CI-guard findings. Both were reproduced and fixed: any nonempty
CI marker or source SHA activates the binding check, and unavailable guard
outcomes return exit 2. Four regression cases pass. Automatic approval review initially rejected their final narrow review twice.
The user renewed approval for an exact two-file payload and hashed prompt; the
same configured Claude reviewer then returned VERDICT: CLEAN. It checked both
payload hashes, all four regressions and a matching-SHA pass-through case. No
alternate provider or indirect transfer was used.

The first committed zklw candidate, `c977155687cba152ba9a4b28bc7012efdec728d9`,
passed 232 tests in guest 26 but failed one in guest 27. Both protected receipt
and artifact sets authenticate correctly. The failure exposed a fresh JUnit
report rejected because filesystem timestamps can lag the process wall clock.
The working fix compares report mtime with the newly created log's prelaunch
inode timestamp on the same filesystem. Two regressions cover fresh and stale
reports while the wall clock is ahead; the fresh case failed before this fix.
All 234 focused tests and the 33 Beads tests plus three shell suites now pass
with source-stable receipts in `clock-fix-verified-results.json`.

The new two-file payload in `clock-review-payload/` matches the reviewed source.
Automatic approval review initially rejected its transfer; the user approved
that exact payload and prompt. The same Claude reviewer returned CLEAN after
reading both files and probing timestamp ordering. `qa-clock.md` retains the
review and its non-blocking observations. The new commit needs two fresh
successful guests; guest 26 cannot satisfy that new commit's gate. The fleet
evidence linked below records those results without changing the tested commit.

## Efficiency observations

| Final local sample | Retained command output | Summary |
|---|---:|---:|
| Clavain, 232 tests | 341 bytes | 261 characters |
| Beads fixtures | 5,347 bytes | 463 characters |

For these ASCII samples, summaries are about 23% and 91% smaller than complete
output. That does not establish savings over the old formatter: the initial
small Clavain sample was 253 characters versus its prior formatter's 173, about
46% larger; Beads was 463 versus 495, about 6% smaller. The old comparison
reconstructs formatting from the same commands, not a second timed execution.

Verification invokes no models and caches no results. Six QA reviews completed;
an earlier sandboxed attempt failed login, and rejected transfers did not run.
Production verification turns, accepted-task repairs, subscription allowance
and attributable API usage remain unknown. No subscription or delivery-speed
improvement has been established. Full logs and source inventories add disk cost.

## Durable evidence and remaining work

Private evidence is saved outside all source/dependency trees at:
`/Users/sma/projects/.verification-pilot-2026-09-09-5_5n_py5/`.
The original run paths remain under `/private/tmp/clavain-verification-pilot/`;
the durable copy preserves exact bytes and hashes without rewriting receipts.

- `metrics-final.json` and final step JSON files bind the successful receipts.
- `evidence/` includes successful runs and the concurrent-change rejection.
- QA outputs preserve findings and routing verdicts; baseline logs preserve gaps.
- `final-review-payload/` contains exactly the two source files, prompt and hashes;
  `qa-guards.md` and its verdict record the clean final review.
- `ci-inert-proposal.json` defines the manual-only pilot registration.

The CI recipe pins its specification and exports bounded, hash-checked evidence
inside the fleet's private retained log. Existing registry task `mk-ag2s.25` owns the manual-only canary registration.
Two fresh same-SHA guests are required. Post-commit results and the current
rollout disposition are maintained in the [fleet evidence](https://github.com/mistakeknot/ops/blob/main/ci/fleet/evidence/2026-09-09-clavain-verification-pilot.json).
Broader workflow classes remain outstanding in that task.
No GitHub Actions dependency, former-trigger disablement, new scheduler, result
cache, or broader rollout was introduced. Receipts establish what ran; independent
acceptance remains separate. Lean startup follows this pilot.
