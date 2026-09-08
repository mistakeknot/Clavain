# Reasoning routing verification — 2026-09-08

Implementation is tracked as `Sylveste-drqs`. The CI campaign mix remains scoped
to `mk-ag2s`; the global default retains Astra and Fable.

## Verified

- Intercore `go test ./...` passed with macOS process inspection enabled. The
  sandboxed run could not inspect processes; that environmental failure was
  retained and rerun with the required access, without weakening tests.
- Clavain structural suite after rollout fixes: **1,015 passed, 1 skipped**.
- Interflux structural suite: **239 passed**.
- Narrow synchronization/adapter tests: **24 passed** across eight host surfaces,
  with standalone paths containing spaces, policy drift, symlinks, file modes,
  malformed markers, local content preservation, legacy Kimi migration, portable
  selection across machine homes, and narrow Hermes profile activation.
- Focused shell suite: **30 passed**, covering Claude review permissions,
  Zaka dispatch and quality-gate consumers.
- `reasoning-contract-test.sh`: identical resolved decisions across all eight
  rendered host surfaces; Claude effort is passed explicitly. Governed children
  receive the shared contract without user settings. A policy change after
  resolution is rejected before the model starts.
- `role-dispatch-test.sh` and `role-dispatch-integration-test.sh`: role fallback,
  canonical reviewer identity, immutable policy hashes in SQLite audit records,
  and usage/failure receipts passed. Model backends in these tests are fixtures.
- `hermes-native-probe.py` ran against the installed Hermes runtime in a fresh
  isolated profile through native plugin discovery. The actual default profile
  also passed discovery, contract injection, governed tool registration and the
  delegation block. Neither probe made model calls.
- The installed local `ic` was updated through Intercore commit `2463614`; invoking
  `ic --json route dispatch --role=planning` from `/private/tmp` resolved the
  selected Clavain installation. The previous binary is retained in
  `/private/tmp/reasoning-ic-before` for rollback.
- The additional symlink-parent regression failed before the fix, then passed.
  Routing and CLI package tests passed with required process-inspection access.
  An independent reviewer verified the path fix and portable renderer.
- Final Intercore `go test ./...` passed after adding successful direct and
  scheduled governed admission tests. Those tests exposed an empty-fallback
  serialization mismatch; admission now compares the serialized contract while
  preserving the distinction between absent and explicitly empty model access.
  Forged effort remains rejected. CLI fixtures explicitly select their policy,
  so a user's installed model assignments cannot contaminate the test.
- Follow-up tests passed: two Clavain Python tests (five subtests), one dotfiles
  Python test (three subtests), and all three routing shell scripts. These cover
  missing validator receipts, unsupported-adapter fallback and installer defaults.

Intercore regression tests cover frontier requirements, explicit policy errors,
review alias separation, missing access, active investigation and handoff,
scoped alternate profiles, operational vs capability failures, immediate premise
escalation, complete backend/effort preservation across fresh retry chains,
blocked-failure durability, and rejection of unverifiable admission contracts.

## Fresh-session evidence and local rollout

The user approved the prepared payload after the earlier automatic-review
rejection. Fresh Fable and Astra sessions passed its policy decisions. Subsequent
probes supplied only the scenario: both hosts retrieved the installed policy hash
and portable selection mode from their native instructions and applied the rules.
The Claude no-settings control found no contract; enabling its user source found
it. Exact prompts and sanitized model/usage evidence are retained in the
[fresh-session receipt](reasoning-routing-probe-receipt.json).

A real `dispatch.sh --role plan-review` probe then selected Fable for an
Astra-authored foundational plan, injected the contract with user settings
excluded, and retained actual session model/usage plus durable Intercore decision
and attempt IDs. See the [governed dispatch receipt](reasoning-routing-dispatch-receipt.json).
This probe tests routing behavior; it is not an implementation-review verdict.
Codex's runtime context records Astra/high. Fable's provider output confirms its
model; high effort was requested and accepted by the CLI but not independently
echoed by the provider. One Fable response used a Markdown JSON fence; semantic
acceptance passed, strict JSON formatting did not.

All eight local host instruction surfaces were narrowly synchronized and checked
for idempotence, preserved local content, symlinks and file modes. Shared dotfiles
use machine-neutral policy selection. Older conflicting Claude escalation and
short-task exceptions were removed. Hermes's default profile now links and enables
the packaged adapter; every preexisting config byte was preserved. Provider
credentials, personalities and running parent models were unchanged.

After these probes, concurrent commit `5fb851a` changed ordinary validation-seat
assignments. The drift check detected it. That update was preserved and only the
managed instruction receipt hashes were refreshed; all eight blocks check current.
The current resolver still selects Fable for foundational review and excludes the
Astra author. Earlier model receipts retain their original policy hash rather
than claiming verification of the concurrent change. The committed standalone
`3305c17` package also passed its routing-contract checks outside a Git checkout.

Fresh native Kimi, OpenCode and Hermes sessions subsequently retrieved the new
hash and passed the same scenario. Their runtime receipts identify K3/high,
GLM-5.3-Flash (effort unknown), and Sol (high requested), respectively. Kimi's
effort comes from its existing profile; governed wrapper effort selection remains
unsupported. OpenCode returned zero usage counters despite a nonempty answer,
so attributable usage stays unknown. Gemini failed before inference with
`IneligibleTierError` / `UNSUPPORTED_CLIENT`; its account rejected the installed
client. See the [additional host receipt](reasoning-routing-additional-host-receipt.json).
Editor model behavior, alternate-profile model behavior and remote installations
remain unverified. Standalone behavior has fixture coverage. Native instruction
discovery does not establish kernel admission or delegated-model enforcement.

## Independent implementation review

Fable independently reviewed eight named commits authored by Astra and returned
**PASS with no correctness blockers**. It ran no tests. All six nonblocking
findings were addressed through fixes or an explicit kernel single-candidate
scope statement. The positive scheduler test found a real serialization bug,
which was fixed and reviewed again without weakening admission checks. The
[review receipt](reasoning-routing-review-receipt.json) retains scope, actual
model usage, exact prompt/result hashes, findings and dispositions. Its verdict
does not cover the concurrent validation-seat change in `5fb851a`.

## Outstanding delivery gates

The fleet service was reachable and immutable repository IDs were checked.
Sylveste, Clavain, Intercore, Interflux and dotfiles remain pending CI migration;
their existing `mk-ag2s` tasks were claimed, without duplicate tasks or trigger
changes. Required GitHub checks blocked the Sylveste philosophy and Interflux
consumer pushes (`Generator and parity checkers` and `audit`, respectively).
These status gates were preserved. Corrected requests using full 40-character
commit SHAs passed the existing sudo rule but both were rejected by the fleet
service: `reviewed manual execution registration required`. The earlier sudo
failure came from abbreviated SHAs, not missing operator authority. No check was
fabricated, bypassed or disabled. Final source push status is recorded in the
task tracker and session handoff. Remote installation and remaining host model
verification are not implied by the local rollout.
