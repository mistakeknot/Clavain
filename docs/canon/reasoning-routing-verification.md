# Reasoning routing verification — 2026-09-08

Implementation is tracked as `Sylveste-drqs`. The CI campaign mix remains scoped
to `mk-ag2s`; the global default retains Astra and Fable.

## Verified

- Intercore `go test ./...` passed with macOS process inspection enabled. The
  sandboxed run could not inspect processes; that environmental failure was
  retained and rerun with the required access, without weakening tests.
- Clavain structural suite: **1,014 passed, 1 skipped**.
- Interflux structural suite: **239 passed**.
- Narrow synchronization/adapter tests: **14 passed** across eight host surfaces,
  with standalone paths containing spaces, policy drift, symlinks, file modes,
  malformed markers, local content preservation, and legacy Kimi migration.
- Focused shell suite: **30 passed**, covering Claude review permissions,
  Zaka dispatch and quality-gate consumers.
- `reasoning-contract-test.sh`: identical resolved decisions across all eight
  rendered host surfaces; Claude effort is passed explicitly.
- `role-dispatch-test.sh` and `role-dispatch-integration-test.sh`: role fallback,
  canonical reviewer identity, immutable policy hashes in SQLite audit records,
  and usage/failure receipts passed. Model backends in these tests are fixtures.
- `hermes-native-probe.py` ran against the installed Hermes runtime in a fresh
  isolated profile. Native hook registration, contract injection, governed tool
  registration and the delegation block passed. It made no model calls.
- The installed local `ic` was updated from Intercore commit `4c26c23`; invoking
  `ic --json route dispatch --role=planning` from `/private/tmp` resolved the
  selected Clavain installation. The previous binary is retained in
  `/private/tmp/reasoning-ic-before` for rollback.

Intercore regression tests cover frontier requirements, explicit policy errors,
review alias separation, missing access, active investigation and handoff,
scoped alternate profiles, operational vs capability failures, immediate premise
escalation, complete backend/effort preservation across fresh retry chains,
blocked-failure durability, and rejection of unverifiable admission contracts.

## Outstanding gates

The proposed fresh Fable session was rejected by automatic approval review:
exporting the rendered internal contract to that external service requires
payload-specific authorization. No external model execution receipt was produced.
The exact proposed prompt is [reasoning-routing-probe.md](reasoning-routing-probe.md).
Instruction/rendering tests and native hook probes do not establish actual model
or effort behavior in a fresh LLM session. Editor, Gemini, Kimi and OpenCode
surfaces are instructional; unsupported native capabilities are reported.

The fleet service was reachable and immutable repository IDs were checked.
Sylveste, Clavain, Intercore, Interflux and dotfiles remain pending CI migration;
their existing `mk-ag2s` tasks were claimed, without duplicate tasks or trigger
changes. Required GitHub checks blocked the Sylveste philosophy and Interflux
consumer pushes (`Generator and parity checkers` and `audit`, respectively).
These status gates were preserved. Intercore's commit was pushed. Final source
push status is recorded in the task tracker and session handoff.

No broad installer, provider credential, personality, or running parent-model
configuration was changed. The new dotfiles wrapper consumes the selected
Clavain package without owning a policy copy. Full host rollout remains subject
to the outstanding fresh-session evidence and required CI checks.
