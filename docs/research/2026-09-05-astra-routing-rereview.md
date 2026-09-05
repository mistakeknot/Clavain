# Astra routing rereview checkpoint

## Verified changes

Intercore `bc64530` resolves canonical producer identities and filters every
same-model validation candidate. Clavain `c20c448` makes policy denial dominate
earlier rate-limit, account-access and model-unavailable messages. This follow-up
adds immutable route/profile snapshots, per-attempt lifecycle records, and the
installed Zaka App Server transport (`5454ccd`).

Two independent Fable first-pass reviews informed the changes. The first review
could not inspect Git hunks and incorrectly called Interflux `c8de19f` prose-only;
the actual commit changes its selector, configuration and behavioral tests.
Its separate fixed-tier consumer finding was valid: Interflux `c9d261f` now
requires producer-aware validation, captures reports outside the reviewer
sandbox, and removes blind retry/backend substitution. Those Interflux commits
landed through protected-main PR 25; release PR 26 subsequently published them
as Interflux 0.2.88 (`bb1598f`).

The async lifecycle finding was resolved with explicit terminal collection,
not a blocking dispatch. The second review identified dropped run/bead lineage,
late-collection false failures and duplicate terminal rows. The collector now
preserves lineage, requires an exact durable turn-completion event when the
worker has stopped, and returns an existing terminal record under a per-session
lock. Pending questions, unavailable evidence, and recording failure stay
unaccepted. It never replays submitted work or grants release authority.

The [rollout runbook](../runbooks/astra-rollout.md) records actual installed
binary provenance, the live question/steering probes, and Intercore ledger
records 523/524/525. Recollecting after worker shutdown returned the existing
completed record and left the ledger at three lifecycle rows.

## Verification boundary

- Role-dispatch unit and real-Intercore SQLite integration suites pass.
- Async collection tests cover completion, policy precedence, run/bead identity,
  late collection, idempotency, pending questions and failed recording.
- All 16 Zaka dispatch tests pass, including cleanup after failed status capture.
- Full structural suite: 912 passed, one skipped.
- Full shell suite: 733 passed, 56 skipped, 11 failed. Nine failures reproduce
  unchanged on clean base commit `c20c448`: two Dolt-push authorization fixtures,
  two calibration-close authorization fixtures, and five Codex-installer
  fixtures. Two runtime-evidence canaries explicitly refuse the concurrently
  dirty sibling Intercore checkout. Its unrelated edits were preserved.

The broad suite is not described as green. These failures are outside this
change; targeted routing and installed async checks supply the release evidence
for this boundary. No promotion is inferred from them.

## Attempt-output freshness follow-up

A live review retry exposed a prior verdict attached to a new `started` record
when its output filename was reused. The regression test reproduced that case,
and independent Fable review identified its terminal analogue: a successful
process writing no new report could inherit the old report and pass verdict.
Both cases are now covered. Opt-in synchronous role dispatch prepares a fresh
report body and sidecar after the started audit record succeeds. Only a finished
backend with a newly extracted result may attach a sidecar to its terminal
record. An unwriteable output target is a terminal configuration failure with
no inherited verdict; App Server verdicts remain event-log-only.

The final independent Fable review was clean. Main ran the real-Intercore
integration fixture, role unit suite, async collector suite and all 42 targeted
Zaka/error/preflight shell tests successfully. The integration fixture also
checks a fresh completed pass and an unwriteable report target; rapid records
are ordered by their actual SQLite IDs instead of relying on timestamp ties.
The broad-suite baseline above remains unchanged, not silently relabeled green.

Fresh remote CI for `1c12041` remains red with the same ten shell failures as
`1a67a32`: the nine authorization/installer fixtures above plus a Linux test
invoking the macOS-only `md5` command. The routing-specific failure occurs before
its comparison assertion. Secret Scan passes. See
[current Plugin Tests](https://github.com/mistakeknot/Clavain/actions/runs/33957643814)
and the [preceding run](https://github.com/mistakeknot/Clavain/actions/runs/33955407888).

## Remaining rollout work

All three common-CLI routes now pass 18/18 with repeated cells and different-model
review. The completed tldr-swinton evidence is pushed at `c44a638`; the runbook
links the exact producer commit and records the limits and scope dispositions.
The scoped releases are now installed: Clavain 0.6.308 (`7a12377`), Interstat
0.3.5 (`6d7449e`), Interflux 0.2.88 (`bb1598f`), and clean Intercore `314bfa8`.
Fresh selected-manifest, routing and async collector checks pass. Clavain's
[release CI](https://github.com/mistakeknot/Clavain/actions/runs/33983525897)
retains the same ten named baseline failures; Secret Scan passes. Independent
Fable review of the scoped publisher was CLEAN, with main-run full Go tests,
vet, race and actual publication-preservation checks. The narrow Mac canary
is tracked separately as `Sylveste-kbh5`, starting from zero enrolled tasks;
this is not completion of the adoption/promotion goal. Local and canonical zklw
shadow-corpus paths are absent, so neither interserve class has new parity
evidence or a changed route.

Low-priority worker hardening remains worth testing separately: forced startup
termination across process groups and cleanup after the Codex child has already
been reaped. Normal startup, shutdown, stale-state handling and race tests pass;
the review did not reproduce those extreme process-lifetime cases.
