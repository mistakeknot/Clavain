# Reasoning routing operations

Operational recipes and historical rationale for the [required routing canon](reasoning-routing.md). Read the relevant section when the task needs capacity recovery, host synchronization, or calibration. The short canon governs if wording differs.

Clavain owns model assignments and the executable policy in `config/routing.yaml`.
Sylveste owns the principle; Intercore enforces declared judgments; adapters carry
the packaged contract to each host. A standalone Clavain checkout contains this
canon, policy, instructions, adapters, and dispatch scripts. Intercore (`ic`),
Python 3, jq, and the selected model CLI are runtime dependencies.

## Capacity failure and fallback

Capacity exhaustion is an operational failure. It consumes no capability strike,
and it must neither silently downgrade the work nor silently stall it. The remedy
is a declared, ordered fallback that is visible in the receipt.

The user's 2026-09-10 ruling makes Opus 5 the capacity substitute for a frontier
seat, including independent plan review. As of mk-9yyt that substitution lives in
the packaged default policy rather than in a per-caller snapshot: `claude-opus-5`
is listed in `reasoning.frontier_models`, and `review-opus`, `deep-opus`,
`routine-sonnet`, `scout-sonnet` and `release-sonnet` are the last entries of the
chains that reach them. `plan-review`, `deep-execution`, `routine-execution`,
`scout` and `release-preparation` therefore each have a reachable destination
outside the Codex lane. Ordering carries the preference: a substitute is selected
only after the seats ahead of it are excluded, so the default routes are unchanged
while the primaries are up.

One role deliberately has no capacity substitute. `release-authority` belongs to
the running main session; substituting it is an authority change rather than a
fallback, and that stays unchanged — commit/push/deploy/publication approval
stays with the main integrator regardless of Codex availability.

`main-integrator` previously had no capacity substitute for the same reason
(resolving it elsewhere would not change the running parent model). mk ruled
2026-09-25 that Codex exhaustion must never block development on any project,
so `main-sol` now falls back to `pilot-opus`. That fallback is informational,
not delegated: it tells the running session which model it should itself claim
when both Astra and Sol are out, the same way the `ci-campaign-pilot` profile
already used `pilot-opus` for this role in its scoped campaign. `pilot-opus`
declares `backend: main`, and `_dispatch_role_profile` (`scripts/dispatch.sh`)
still refuses to spawn any `backend: main` candidate as a delegated subprocess
— a `main-integrator` fallback_chain entry is read by the running session
choosing its own model, never fed to a dispatched worker.

Ordinary execution roles reached the same floor earlier: `fast`/`fast-clavain`
(routine-execution/scout tier aliases) fall back to the Sonnet capacity seats
`routine-sonnet`/`scout-sonnet` already declared for those roles, and
`deep`/`deep-clavain` fall back to `deep-opus`, matching `deep-astra`'s own
Opus terminus. These tier names are resolved by bare `--tier <name>` (not
`--role`), a separate surface `ic route dispatch --tier=...` does not walk —
`scripts/dispatch.sh` reads each tier's `fallbacks:` directly (see
`scripts/tier-fallback-chain.py`) and retries through the same
`quota_exhausted`/`model_unavailable`/... classes as role dispatch.

`validation-sol` gained the same terminal fallback: `[validation-opus,
validation-sonnet]`. Before this it was the one Codex seat in the `validation`
chain with no declared exit — reachable as the *first* candidate whenever
`cross_lab_first` reorders a Claude producer's chain ahead of `validation-opus`
(see below), so a Codex outage on a Claude-authored review had nothing to fall
to in that reordered position. `producer_model_conflict` and the existing
`validation-opus -> validation-sonnet -> validation-sol -> validation-kimi`
chain are unaffected: Intercore dedupes an already-visited profile_ref, so the
new edge cannot reintroduce a seat the walk already excluded or already used.

Frontier authoring — `planning`, `frontier-planning`, `escalation` — runs
`planning-astra`, then `planning-fable`, then `planning-opus` (mk ruling
2026-09-18). It previously failed closed when both frontier labs were out. mk
ruled that asymmetric: `claude-opus-5` is already in `reasoning.frontier_models`
and is already authorised to independently review a frontier-authored plan, which
is the harder job, so refusing to let it author in an emergency was arbitrary.
The substitute stays last, so a reachable Astra still authors every plan.

The review and authoring lanes remain separate profile chains
(`review-fable`/`review-astra`/`review-opus` against
`planning-astra`/`planning-fable`/`planning-opus`) so that adding a seat to one
cannot reach the other. That separation, not a refusal, is what keeps a
review-side substitute from silently changing who authors a plan;
`tests/routing/reasoning-contract-test.sh` asserts an authoring receipt is
unchanged by edits to the review lane, and that Astra is still preferred while
reachable.

**Scope correction (mk-9yyt).** The earlier wording — *scope a capacity snapshot
to reviews of the bound producer from another lab; reviews of Claude-authored work
keep the default independent route* — excluded the exact failure it existed to
remedy. Routing-table v2 puts the `strategized` and `planned` phases on Fable, so
most plans are Claude-authored; "keep the default independent route" sent those
reviews back to Astra, the seat that was down, and `plan-review` resolved with an
empty `fallback_chain`. The rule is corrected to read: **a capacity substitute is
scoped by the seat that failed, not by the producer's lab.** Cross-lab review
remains preferred and is still ordered first; same-lab review by a distinct
frontier model is the declared degradation when no cross-lab seat is reachable.
The preference is a preference, not a gate — a stalled review gate is the worse
outcome, and the receipt records which seats were excluded and why.

**Both directions walk at runtime (mk-esex).** The chains were symmetric after
mk-9yyt, but only a Codex limit classified as `quota_exhausted`. The Claude CLI
reports a subscription limit as `error: "rate_limit"` — the same code as a
transient 429 — with the limit named in the text ("You've hit your weekly
limit · resets …"), so a Fable seat out of quota landed as `terminal_error` and
dispatch suppressed its fallback: an Opus-authored plan review blocked instead of
reaching Astra. `scripts/provider-errors.py` now classifies that text on a Claude
error event as `quota_exhausted`; a `rate_limit` without it stays terminal.
`tests/routing/plan-review-capacity-test.sh` drives the real dispatch walk in both
directions, and the case where every non-producer seat is out still blocks.
A pooled Codex lane whose own retries ran out (`exceeded retry limit, last
status: 429`) now classifies as `rate_limited` rather than `terminal_error`. An
exhausted-retries 429 is capacity, not a reason to keep hammering the same
model: it gets the identical single account-pool retry `quota_exhausted` gets,
then walks to the profile's declared fallback (mk ruling 2026-09-25, mk-nh6v;
`tests/routing/role-dispatch-test.sh`).

Reviewer separation is not part of that degradation. It is enforced structurally,
below the policy layer: a candidate whose canonical identity matches the producer
is removed with reason `producer_model_conflict`, primary and fallbacks alike, and
no policy edit can express "the author reviews itself". A capacity fallback must
therefore always resolve to a model distinct from the bound producer. Graceful
degradation never becomes collapsed independence. `review-opus` carries no
fallbacks of its own, so Opus cannot review Opus.

Selecting a substitute takes **two gates, not one**: `reasoning.frontier_models`
supplies eligibility and `dispatch.roles.<role>` plus the tier's ordered
`fallbacks` supply selection. Setting only the second returns
`role "plan-review": no eligible model satisfies reasoning contract`.

### Code review goes to another lab first

Mk ruling 2026-09-24. A static chain
cannot prefer "the other lab" for every producer, so `dispatch.cross_lab_first`
names the review roles (`validation`, `cross-lab-review`) where the resolver,
after removing the producer, stably moves seats from a frontier lab other than
the producer's ahead of same-lab seats. Frontier labs are those of
`reasoning.frontier_models`; Kimi keeps its policy position. The receipt records
any change as `cross_lab_reorder: {from, to}` over the seats that survive the
reasoning contract. For `validation`, Claude-produced code therefore reaches Sol
first. When the Codex lane is out, observed as a capacity failure, the same-lab
substitute is Opus. Do not wait for the Codex reset and do not escalate to Fable:
Fable is not in the `validation` chain, and `validation-fable` is explicit-tier
only. Codex-produced work keeps the policy order, with Opus first.
`cross-lab-review` keeps Fable as its designed first-pass seat; for a Claude
producer it now resolves Sol, then Fable, then Kimi. Requires Intercore `ic` at or
after commit 2caa435; an older `ic` ignores `cross_lab_first` and keeps the
policy order.

### Execution headroom forecasts

Before role resolution, dispatch may read `bb pool status --json` for
`routine-execution`, `deep-execution`, and `scout`. A forecast excludes a
candidate only when every enabled account for its provider/family is below the
floor: less than 10% weekly headroom, or five-hour utilization at or above the
pool's `switchThreshold` (0.98 when absent). Provider and family limits both
apply. Missing telemetry is unknown; an unreachable pool leaves routing intact.

The snapshot is saved as `.clavain/capacity/<date>-<unique>-headroom.json` in
the task checkout. `capacity-fallback.sh --forecast --seat ...` derives a context
whose rationale says `forecast from bb pool headroom`. It preserves existing
availability exclusions and re-resolves through Intercore. No model assignments
change. Receipts label these exclusions `headroom_exclusion`, separately from
observed `model_unavailable` failures.
If every eligible seat is below the floor, resolution fails before a model starts;
the evidence and derived context remain available for inspection.

For routine and deep execution, dispatch stably orders known cross-provider
candidates from the eligible chain by remaining headroom. It compares the first
known candidate per provider and preserves policy order within each provider.
Headroom is the minimum remaining fraction across its known provider/family
windows. Unknown candidates retain their positions, and ties retain policy order. Scout may exclude exhausted
seats but does not reorder them. The receipt retains Intercore's `profile_ref`
and records `headroom_reorder: {from, to, snapshot_at}` alongside the actual
`resolved_profile`. `CLAVAIN_POOL_HEADROOM=0` disables forecasts.

**Execution roles only:** `planning`, `plan-review`, `validation`, `escalation`,
and `cross-lab-review` receive no headroom input, even when Fable is below the
forecast floor. Those roles retain the observed-failure procedure below,
frontier eligibility and independent reviewer requirements.

### Recording an observed capacity failure

Do not edit the packaged policy for an outage, and do not infer a capacity failure
from a prior report. Probe the seat, keep the actual error, and record what was
observed:

1. Write the evidence to `.clavain/capacity/<date>-<seat>-<failure>.md`: the probe
   command and its verbatim output, the time of the probe, and the reset time if
   the provider gave one. Usage after a quota error is **unknown**, never zero, and
   a failed attempt is retained rather than rewritten.
2. Add `available_models` to the decision context with the models actually
   observed available. The field is authoritative when present: omission of the
   field means unprobed, an empty array means none, and any model absent from a
   present array is excluded. Unavailable seats then leave the chain with reason
   `model_unavailable` and the resolver walks to the next declared candidate.
3. Re-resolve and keep the receipt. The exclusions, the selected profile and the
   policy hash are the audit trail; no snapshot is needed for any chain that
   already reaches a distinct eligible seat.

```bash
scripts/capacity-fallback.sh --seat gpt-6-astra \
  --context .clavain/decisions/<plan>.json \
  --evidence .clavain/capacity/<date>-astra-usage-limit.md \
  --role plan-review --producer-identity claude-fable-5-1
```

The helper merges `available_models` into a copy of the decision context, refuses
to proceed without capacity evidence, re-resolves each named role, and fails when
a resolution would land on the producer. It changes no policy file.

A frozen policy snapshot remains the last resort, for the case where even the
widened chain reaches nothing eligible. Build it as the packaged default plus the
smallest possible addition, so the entire scope of the exception is visible in one
`diff`; bind its SHA256, the producer identity and the capacity evidence before
starting; and preserve the packaged default unmodified.

A started dispatch with incomplete accounting still stops its dependent work;
the fallback is a separately authorized attempt with its own receipt.

## Handoff and escalation

Keep frontier involvement while investigation or experiments change the plan.
Execution can hand off once `handoff` supplies nonempty `decisions`, `constraints`,
`verification`, and `escalation`, and `investigation_active` is false. Verification
must retain playtests, experiments, user evidence, or production canaries where
applicable; structural tests alone do not satisfy empirical acceptance.

`ic dispatch spawn --role=...` accepts the same policy/context/profile/producer
flags. Governed dispatch requires the packaged wrapper, records the contract
before execution, and preserves it in scheduled jobs and retry receipts. Legacy
model-only APIs remain available and are not classified as governed dispatch.

`ic dispatch retry --escalate --policy=... --failure-mode=...` counts capability,
verdict, and criteria failures as strikes. Two strikes request the policy's
escalation role; `premise-failure` requests it immediately. Authentication,
rate limits, permission, infrastructure, timeout, generic error, and unknown
failures remain operational and consume no capability strikes. The caller must
classify the failure; an exit code alone cannot establish capability failure.
Retries retain backend and effort in the decision receipt. Review escalation
requires a newly resolved independent review contract. Policy drift requires
reclassification. Retry commands create records, not running processes.

## Host delivery and evidence

`config/agent-instructions.md` is shared; `config/host-adapters.json` and the
small Codex adapter supply host details. The historical managed marker is retained
so upgrades replace the existing block once. Narrow sync follows instruction
symlinks, preserves unrelated bytes and modes, refuses malformed markers and
concurrent edits, and exposes package/contract/policy drift:

```bash
python3 scripts/sync-agent-instructions.py --source /selected/Clavain \
  --host codex --file /selected/profile/AGENTS.md --dry-run
python3 scripts/sync-agent-instructions.py --source /selected/Clavain \
  --host codex --file /selected/profile/AGENTS.md
python3 scripts/sync-agent-instructions.py --source /selected/Clavain \
  --host codex --file /selected/profile/AGENTS.md --check
```

Use the declared native surface: Claude `CLAUDE.md` plus session-start, Codex and
Kimi `AGENTS.md`, Gemini `GEMINI.md`, OpenCode `AGENTS.md`, Cursor an always-applied
`.mdc` rule, VS Code `.github/copilot-instructions.md` or a user
`prompts/*.instructions.md` file with `applyTo: "**"`. Select each profile's file
explicitly. Dotfiles consume the rendered block, never own a fork of the policy.
For Cursor, retain the native `alwaysApply: true` frontmatter outside the block.
The check reports potential unmanaged model overrides without copying local text.

For instruction files shared between machines through dotfiles, add
`--portable-policy` to sync and check. This keeps machine paths out of shared
content and selects `CLAVAIN_ROUTING_POLICY` when set, otherwise the installation
linked by `~/.agents/skills/clavain`. Each machine must have that managed link and
an Intercore version that resolves symlinks before parent-directory traversal.
Missing selections fail closed. The receipt identifies this selection mode;
rerender after installation changes to refresh the recorded policy hash. Keep
the default explicit selection for standalone installations without a managed link.

Hermes: use the selected Hermes virtualenv's Python (with PyYAML) to run:

```bash
python scripts/sync-hermes-adapter.py --source /selected/Clavain \
  --home /selected/hermes-profile --dry-run
python scripts/sync-hermes-adapter.py --source /selected/Clavain \
  --home /selected/hermes-profile
python scripts/sync-hermes-adapter.py --source /selected/Clavain \
  --home /selected/hermes-profile --check
```

This links `adapters/hermes` into that profile and enables only `clavain` using
the native plugin allowlist. It preserves config bytes outside the plugin section,
unrelated plugin settings, symlinks and file modes. Unsupported YAML structures
and unmanaged adapter targets fail explicitly. It runs no migrations or model
calls. The native plugin
uses `pre_llm_call`, `pre_tool_call`, `on_session_start`, and `subagent_stop`;
`clavain_dispatch` carries role/context/producer to the shared wrapper. Native
`delegate_task` is blocked to prevent silent inheritance. Session and child
observation remain in Hermes telemetry. No profile personalities or credentials
are rewritten. The installed Hermes hook API was inspected; hook registration
alone does not prove behavioral enforcement. Older hosts that ignore blocking
directives are unsupported. See the [Hermes plugin hook contract](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks).

Governed dispatch supplies the shared contract and resolved decision to the child
after context compaction. It verifies the policy hash again before execution and
rejects drift. This is needed for Claude review seats, which intentionally exclude
user settings: that also excludes the global instruction file, as described in
the [Claude Code settings-source contract](https://code.claude.com/docs/en/agent-sdk/claude-code-features).
Resolving a role does not itself establish kernel spawn or budget admission.

The wrapper's `--role` entry point tries the eligible ordered fallbacks when an
adapter reports a recognized availability or unsupported-adapter failure. Kernel spawn
admits one resolved candidate and records its outcome; it does not repeat the
wrapper's availability loop. A caller must resolve another eligible candidate
after an operational failure. Such failures do not consume capability strikes.

Instruction sync reports `instructional`, wrapper calls produce
`dispatch-enforced` receipts, and only a fresh-session probe can establish
behavioral verification. Changing settings does not switch a running parent
model. Report missing tools, unsupported native routing, and absent frontier
access explicitly. Do not claim all hosts verified from a renderer test.

## Calibration and rollout

Use existing `routing_decisions.policy_hash` and `context_json` for decisions,
exclusions, profile, failure class and per-attempt results. The dispatch audit
and existing Interstat/Interspect outcome pipeline retain actual execution,
accepted outcomes, defects, retries and attributable usage. QA must record the
validator model and policy hash from its receipt, never hard-coded constants.
Missing or blank identity/hash makes conformance unknown and acceptance false.
Unknown usage or
unrun empirical acceptance stays unknown. Calibration may change eligible choices
but cannot relax frontier requirements, reviewer independence, quality floors,
or authority gates.

Run routing, retry, adapter synchronization and host integration tests; retain
fresh-session model/effort receipts. Compare identical contexts from nested repos,
outside Git roots, standalone installs and alternate profiles. Upgrade only the
selected instruction block or adapter. Roll back by selecting the previous
version's policy and rerendering its block; preserve receipts and local content.
Build/release/deployment automation remains independently scheduled on zklw.
