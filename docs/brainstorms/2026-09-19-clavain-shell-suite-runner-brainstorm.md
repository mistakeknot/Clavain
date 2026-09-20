---
artifact_type: brainstorm
bead: Sylveste-psey
stage: discover
---

# Give Clavain's shell suite a runner that outlives the session that fixes it

## What we're building

Two lanes that execute Clavain's tests, and one repair so neither lane starts red.

**Lane 1 — a scheduled `clavain-shell` rig self-check on zklw.** A new check in `~/projects/dotfiles/common/.local/bin/rig-health-check.sh`, modelled on `intercore-tests`: gated on a designated-host marker, running `bats tests/shell/ --recursive` in the Clavain checkout, reporting through the existing `write_status` pass/fail/skip/warn lane that already surfaces at every SessionStart and enters the `finding-age` response budget. A sibling `clavain-structural` check runs the 28 `ic`-dependent structural tests on the same host, where `ic` actually exists.

**Lane 2 — repair the GitHub Actions Tier 1 so Tier 2 is reached again.** Mark the 28 tests in `tests/structural/test_claude_usage.py` as requiring `ic` and deselect them when the binary is absent. This is not a coverage waiver, because Lane 1 runs them on a host that has `ic`; the coverage moves rather than evaporates.

**The repair.** Eight real cross-platform bats failures, one root cause each, fixed before either lane is armed.

## Why this approach

Because the alternative has already been tried and measured. `Sylveste-ytm` closed on 2026-07-21 with *"Clavain 782 structural + 654 bats FAILCOUNT=0 … zklw: same suites all 0 failures … Zero quarantines needed"* — both platforms, verified, zero quarantines. Eight weeks later the suite is at 10 failures of 872. That epic greened the suite and installed nothing that would ever run it again, so the green had a half-life. The durable deliverable here is the runner, not the repairs.

The harness to host it already exists and already states the doctrine. `rig-health-check.sh` opens its `guard-tests` block with *"A test file that only runs when a human types it is a test that exits 0 — which is the sentence at the top of this script, and it applied to the test suites themselves."* That sentence is true of Clavain's 872 assertions today and nobody had pointed the harness at them.

zklw is the correct host on measured capability rather than preference. It carries `bats` 1.13, `bats-support`/`bats-assert`, `ic`, `yq`, `gawk`, `jq` and `interphase`; this Mac has none of `yq`, `gawk` or the bats helpers, so 51 of the 57 currently-skipped assertions can never execute here. zklw also matches the Linux that the last green CI run used.

Estate policy forbids adding a GitHub Actions dependency for Linux automation, and the fleet drift report already flags `test.yml` as `linux-actions-present` for repo 1151593132. Lane 1 is the policy-correct home. Lane 2 is a repair of an existing lane, not a new dependency, and it buys minutes-latency feedback while the campaign works through mk-ag2s.25.

## Key decisions

**Both lanes, ruled by mk 2026-09-19.** Lane 1 is the durable home; Lane 2 restores per-push feedback in the interim. Neither is armed until the eight real failures are fixed.

**The fleet CI lane is out of scope, on evidence.** `mistakeknot/Clavain` is registered (task `mk-ag2s.25`, `required_checks: [zklw/verification-pilot]`, disposition `verification-pilot-passed-broader-migration-open`) but `triggers: ["manual"]`, the registration pins `recipe_sha`/`recipe_sha256`, and `scripts/ci-verification.sh` hard-pins the SHA256 of `tests/verification-pilot.json`. Adding a bats check there needs two protected fresh guests at identical inputs — a campaign qualification, not a sprint change. Do not create a duplicate migration task.

**A designated-host marker, not `command -v bats`.** `intercore-tests` explains why in its own comment: keying off the binary lets a machine that loses its toolchain silently downgrade to `skip` and the check disappears. Undesignated host is a quiet skip; designated host with no `bats`, `yq` or `gawk` is a loud failure.

**Skips are reported separately from passes.** The suite currently skips 57 assertions — 41 on `yq not available (standalone CI)`, 10 on `gawk`, 5 on `interphase`, 1 on an Intercore calibration candidate — and a skip is indistinguishable from a pass in its TAP. `tests/verification-pilot.json` already sets `max_skipped: 0` for the structural lane; the shell lane has no such floor. The check reports the skip count in its summary, as `guard-tests` learned to do in August.

**Triage separates two classes of failure, which the bead originally conflated.** `test_codex_installer` ×6 and `test_runtime_evidence_canary` ×2 reproduce on zklw's Linux checkout and are real. `test_b3_calibration` ×2 pass on zklw at the same code and are a Mac-environment artefact.

**Root cause of the six is a fixture, not the installer.** `bc5e2f5` (2026-09-08) made `install-codex.sh:1067` require `config/agent-instructions.md`; `test_codex_installer.bats:33` creates `$SOURCE_DIR/config` but never writes that file. CI reported it correctly the same day, in run 34253613833 — Tier 1 green, Tier 2 red, naming those six tests. The next day `75fed68` moved the failure upstream and the badge stopped distinguishing. The signal fired, was accurate, and was lost to noise for eleven days.

## Open questions

Whether the eight repairs belong in this sprint or in a follow-on. Carried into planning as a scope call, with the assumption that they are in scope — arming a lane against a known-red baseline recreates the condition the bead names.

Whether the Actions job also needs its `timeout-minutes: 5` raised. The last green run finished in 4m28s with 830 tests; there are 872 now and the margin is thin. Measurable before it bites.

Whether `clavain-structural` should run the whole structural suite on zklw or only the 28 `ic`-dependent tests. The narrow version is honest about what moved; the wide version is cheap and catches more.
