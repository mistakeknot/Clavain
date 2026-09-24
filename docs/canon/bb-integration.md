# BB integration: ownership and evidence

Status: Plan B rev 2 implementation, branch-only; acceptance and publication
remain separate. Scope is the enrolled zklw host. `bb-host.py` requires
`BB_THREAD_ID`, `BB_SERVER_URL`, successful CLI status, matching thread identity,
and the host ID in `config/bb-integration.json`. A Mac with BB variables is not
enrolled. Failure leaves the existing direct paths unchanged.

## Ownership

| State or operation | Owner |
| --- | --- |
| Session visibility and messages inside BB | BB thread tree |
| Session visibility and messages outside BB | intermux and interlock |
| File reservations | interlock |
| Scheduled BB-native jobs | BB automations, using queued messages |
| Builds, tests and CI orchestration | zklw-ci |
| Issue tracking | Beads; BB Tasks is not a second tracker |
| Runs, goals and attempt lifecycle | Intercore |
| Retry, cancellation and transport selection | dispatch |

Intercore is the sole writer of admission/running/terminal attempt state. BB
events are observations reconciled by dispatch; BB cannot complete an Intercore
attempt. A BB turn completing proves a transport outcome, not independent task
acceptance. Steering an admitted task is a recorded task change. Scheduled work
must use queued messages, not steering.

Each seat has a durable Intercore state mapping of bead, run, dispatch, attempt,
BB thread, submitted request and turn. A local journal is written before spawn
and updated immediately when its ID arrives; this is crash recovery evidence,
not a competing lifecycle store. Event sequence numbers make replay idempotent.
Unclear spawn responses are final and require reconciliation; they never trigger
a second spawn. A process lock excludes competing recovery of a live supervisor.
Version 2 journals distinguish `intent` (no spawn attempted) from `spawning`
(acceptance may be unclear). Recovery retires an unstarted intent without looking
for a child; old ambiguous journals still require child reconciliation. The live
BB thread list is an array; the adapter also accepts a `threads` wrapper.

Interlock remains authoritative for reservations. Reservation leases belong to
the attempt, with `BB_THREAD_ID` as agent identity. Only confirmed termination
permits release. The seat adapter must not infer lease ownership or release
another agent's reservations. No new Interlock API is invented here: automatic
lease coupling remains unavailable until an existing admission supplies a lease.

## Transports and identities

`--via bb` is an explicit transport for `plan-review`, `validation`,
`routine-execution`, and `deep-execution`. A role-to-sandbox allowlist is
enforced by both dispatch and the seat adapter: review roles permit only
`read-only`, while execution roles retain `workspace-write` and
`danger-full-access`. Dispatch defaults review roles to `read-only` and rejects
an explicit writable sandbox before spawning a child. Unknown roles are also
rejected before spawn. The transport retains the resolved backend, model and
effort, maps service tier `standard` to BB `default`, and creates an isolated
worktree from the exact source commit. Dirty source changes are not silently
omitted: the adapter refuses a dirty checkout. Project resolution follows `-C`,
not an unrelated ambient project. No routing profiles change.

BB review seats use provider-native plan mode (`bb thread spawn --plan`) with
BB permission mode `auto`; execution seats keep the existing writable `auto`
launch unchanged. The version 2 seat journal and receipt record both `role` and
the requested `sandbox`. Because the installed BB event schema does not attest
the effective provider permission mode, the adapter leaves
`effective_permission_mode` unknown rather than copying the request. It also
checks the isolated child worktree at termination: any tracked, committed, or
untracked review-seat mutation changes the outcome to `sandbox-violation` and
blocks acceptance. Token-usage events are reduced to an explicit numeric field
allowlist before they enter the journal or receipt; arbitrary event payload
fields are never retained. Cross-lab review and every role absent from the
allowlist remain unsupported.

Inside enrolled BB, next-goal helpers use `CLAUDE_SESSION_ID` when present,
otherwise `BB_THREAD_ID`. The Stop receipt consumer uses the same fallback.
This repairs `unknown.json` collisions without changing plain terminal identity.
Native provider session IDs and BB thread/turn IDs remain distinct receipt
fields; none is substituted as an observed model or an observed effort.

Direct pooling uses the installed BB provider's corrected mechanism: Codex
responses endpoint `/api/v1/plugins/account-pool/http/v1`, an explicit
`bb-account-pool` provider configuration, and an environment-sourced
`x-bb-account-pool-token` header from `CODEX_POOL_AUTH_TOKEN`. No nested-server
parent token (`BB_ACCOUNT_POOL_PARENT_TOKEN`) is reused. See [the spike
evidence](../research/bb-direct-pool-spike.md).
Codex pooling is enabled by default after the successful hub-correlated spike.
Before a cross-provider attempt, dispatch asks BB's authenticated thread-scoped
availability endpoint for the target provider. BB uses the same routing, parent
availability, account and thread-bypass decision as provider environment
contribution. A missing, malformed or unauthorized response stops the attempt
with `terminal_configuration`; it cannot silently select an unrelated local
login. Older BB servers return only provider-wide availability. Native pooled
routes inherited for the same provider keep working on those servers, while
cross-provider borrowing waits for the thread-scoped response.

**Cross-provider dispatch.** BB contributes the pool route and its machine
bearer only for the parent thread's provider. When the target provider is
currently eligible, a Codex attempt can borrow the bearer from a Claude
parent, and a Claude attempt can borrow it from a Codex parent. The inherited
route must exactly match this BB server and the target provider variables must
be absent. Explicit nonpool endpoints and empty variables used by isolation
remain untouched. When an inherited pool route becomes ineligible after launch,
the child drops that stale route and uses its own provider login.
- Trust assumption: the hub accepts the machine bearer on both provider routes
  (verified live 2026-09-23).
- Scope: the export happens only while building the target provider command,
  inside the per-candidate child dispatch process. `_bb_pool_available` is
  side-effect free, so an alias never reaches the parent retry shell or other
  candidates.
- A native Codex-thread token always wins.
- Kill switch: `CLAVAIN_BB_DIRECT_POOL=0` removes inherited pool routing from
  the child and disables borrowing, so the child uses its own provider login.
- Enrollment asks the BB CLI and can be forged by a process that controls
  `BB_CLI` or `PATH`. It selects a transport and is not an authorization
  boundary, because the borrowed bearer is one the process already holds. When
  pool-shaped variables are present but enrollment cannot be verified, dispatch
  stops with `terminal_configuration` instead of trying an unrelated login.
- Raw provider captures are tracked separately (sylveste-2tpo).

Quota classification consumes structured provider errors, never quoted task
text. Permission, configuration, policy or unclear acceptance is terminal and
dominates earlier quota evidence. One retry group spans the account/model axes;
each physical invocation retains its own immutable attempt ID. A bounded
same-profile pool retry precedes model fallback. `CLAVAIN_REQUIRE_USAGE=1`
forbids automatic retries after a started attempt, including quota failures.
Unknown usage/account evidence cannot be treated as zero or as accepted
budgeted work.
The pool retry repeats the same provider configuration. The hub chooses the
account; no account exclusion hint is supplied. When the first invocation was
already pooled, a different account on retry is **unverified**, not guaranteed
by the retry-order test or the successful hub spike.

Claude quota classification remains unverified against a real failure stream.
The synthetic envelope test proves parser mechanics only; actual Claude values
such as `rate_limit` and `billing_error` currently remain terminal unknown errors
until a real fixture establishes their semantics. No live Claude quota success
is claimed. Generic Codex standalone stream errors are provisional when followed
by a successful `turn.completed`; policy, configuration and quota codes, and
explicit failed turns/tasks, remain terminal.

Codex now uses `--json` even on the stock-awk path so provider failures remain
available to the classifier. On hosts without GNU awk this changes streamed
stdout to JSONL; the output file still contains the last agent message.

## Execution headroom

`scripts/pool-headroom.sh` makes one read-only `bb pool status --json` call with
a three-second deadline. `--stdin` runs the pure JSON fixture core. The summary
retains account IDs, headroom and reset times; it omits labels, email addresses
and credentials. It reads Codex `limitWindows` and Claude provider/family windows.
The best enabled account can differ by family. Unknown telemetry never proves
exhaustion, and a pool error produces `status: unknown` with no routing change.

Only `routine-execution`, `deep-execution`, and `scout` consume the forecast.
The default floor is 10% weekly headroom and the five-hour switch threshold is
the pool's `switchThreshold`, defaulting to 0.98. Routine and deep execution may
prefer a declared candidate from another provider with more headroom; scout
only excludes seats below the floor. Planning, review, validation and escalation
keep their existing routes and observed-failure fallback rules.

Dispatch records the snapshot, forecast exclusions and any ordering change.
`profile_ref` identifies Intercore's resolved profile, while `resolved_profile`
identifies the attempted seat. The BB seat journal also retains both profile
references and the requested provider/model/effort. These requested settings do
not populate its observed identity fields. The existing BB transport carries the
selected backend/model without a separate spawn helper.

This is a provider/family forecast, not an account reservation. The hub still
chooses the account; a best-account summary does not prove which account ran.
Telemetry can change between the probe and invocation. Disable the forecast
with `CLAVAIN_POOL_HEADROOM=0`; observed quota handling remains active.

Tests: `test_pool_headroom.py`, `test_headroom_dispatch.py`, and
`test_bb_seat.py::test_headroom_resolved_claude_seat`. Real Claude quota-stream
classification and a live headroom-routed worker remain unverified.

## Parity matrix

Tests named below are evidence contracts, not claims that an unrun cell passes.
`BB` refers to `tests/structural/test_bb_seat.py`; `direct` refers to
`tests/structural/test_dispatch_bb.py`; `roles` refers to
`tests/routing/role-dispatch-test.sh`.

| Roles / transport | Sandbox and read-only | Receipt | Cancellation | Usage / account | Fallback |
| --- | --- | --- | --- | --- | --- |
| Execution / direct-unpooled | Codex workspace-write; Git required (`direct.test_write_non_git_refused_before_provider`) | Existing role audit (`role-dispatch-integration-test.sh`) | Existing process termination; live cancellation not verified | Provider accounting (`test_claude_usage.py`); account unknown | Structured errors and terminal denials (`direct`, `roles`) |
| Read-only / direct-unpooled | Codex read-only; non-Git skip permitted (`direct.test_read_only_non_git_gets_skip_flag`); Claude application controls | Same role audit; independent producer required (`roles`) | Same direct limitation | Same usage gate (`direct.test_budget_error_remains_terminal_accounting`) | Same policy, no retry after budgeted start (`test_claude_usage.py`) |
| Execution / direct-pooled | Same local sandbox as unpooled (`direct` + spike; execution live canary outstanding) | `transport=direct-pooled`, account unknown (spike) | Same direct limitation; no pool cancellation canary | Exact hub-session tie proved by spike; no supported request account API | Account before model (`roles`); forced live exhaustion not run |
| Read-only / direct-pooled | Same read-only boundary; scratch plan-review canary passed (spike) | Same role audit, no inferred account | Same direct limitation | Codex raw usage retained (spike); Claude hub canary outstanding | Same budget gate (`test_claude_usage.py`) |
| Execution / bb-seat | Writable `auto`, exact commit worktree (`BB.test_spawn_contract`) | Thread/turn, observed fields or unknown, prompt/artifact hashes (`BB.test_completion`) | Stop and confirmation; orphan recovery (`BB.test_timeout`, `BB.test_orphan`) | Only turn event evidence; unknown blocks required accounting (`BB.test_unknown_evidence`) | Terminal uncertainty never retries (`BB.test_unclear_spawn`) |
| Read-only / bb-seat | Review roles require `read-only`, spawn with provider plan mode, and fail on worktree mutation (`BB.test_review_roles_accept_only_read_only_and_record_receipt`, `BB.test_read_only_review_mutation_is_a_terminal_seat_failure`) | Version 2 receipt records role and sandbox; effective permission remains observed-or-unknown | Same stop/archive path as execution seats | Only turn event evidence; unknown still blocks required accounting | Writable review requests and unknown roles stop before spawn (`BB.test_review_roles_reject_writable_sandboxes_before_bb`, `BB.test_unknown_role_rejected_before_bb`) |

## Startup and acceptance

Only enrolled BB startup is shortened. Health findings retain individual lines,
including stale, missing, unreadable and peer findings; optional detail and skip
lines are omitted. Instruction-contract state, ownership uncertainty and runtime
blockers retain their content. Remontoire retains inspect/resume/replay/doctor
commands and approval boundaries, deduplicated by thread/cycle/stage/evidence
hash. `bd where --json` owns workspace resolution; an unknown failure does not
silently skip the primer. Tests: `test_bb_startup.py`, `test_startup.py`,
`test_remontoire_facade.py` and dotfiles `test_bb_startup_hooks.py`.
The routing instruction is retained too. Personal hooks resolve the managed
`clavain` skills symlink to its package root; Beads absence is recognized through
the `no_beads_directory` JSON error, while unknown workspace errors fail open.

Seat results are exported before archive, including failures that have reached
confirmed termination. Review-seat export also provides the mutation
postcondition described above. An export or stop failure retains the seat for recovery.
The adapter must report missing model/effort/permission evidence rather than
copying requested settings into observed fields. The scratch seat completed,
exported and archived, but the installed BB schema supplies no model/effort/
permission attestation, so acceptance remains blocked. BB provider retries also
lack a supported per-seat disable control. See [the canary](../research/bb-seat-canary.md).
Independent review and unresolved parity cells remain acceptance gates. The
coordinator corrected the reviewer to governed Fable because Astra produced this
implementation; an additional Astra review cannot establish independence.
Nothing in this record authorizes pushing, publishing, releasing or deployment.
