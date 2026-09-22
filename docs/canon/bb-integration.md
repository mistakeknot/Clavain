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

`--via bb` is an explicit execution transport for `routine-execution` and
`deep-execution` only. It retains the resolved backend, model and effort, maps
service tier `standard` to BB `default`, and creates an isolated worktree from
the exact source commit. Dirty source changes are not silently omitted: the
adapter refuses a dirty checkout. Project resolution follows `-C`, not an
unrelated ambient project. No routing profiles change.

BB `auto` is writable. Plan review, validation, cross-lab review and every
other read-only role cannot use BB seats until BB offers enforced read-only
access to an immutable snapshot. Direct Claude's tool restrictions and mutation
snapshot are application controls, not OS read-only enforcement.

Inside enrolled BB, next-goal helpers use `CLAUDE_SESSION_ID` when present,
otherwise `BB_THREAD_ID`. The Stop receipt consumer uses the same fallback.
This repairs `unknown.json` collisions without changing plain terminal identity.
Native provider session IDs and BB thread/turn IDs remain distinct receipt
fields; none is substituted as an observed model or an observed effort.

Direct pooling uses the installed BB provider's corrected mechanism: Codex
responses endpoint `/api/v1/plugins/account-pool/http/v1`, an explicit
`bb-account-pool` provider configuration, and an environment-sourced
`x-bb-account-pool-token` header from `CODEX_POOL_AUTH_TOKEN`. No parent token
is reused. See [the spike evidence](../research/bb-direct-pool-spike.md).
Codex pooling is enabled by default after the successful hub-correlated spike;
`CLAVAIN_BB_DIRECT_POOL=0` selects the legacy path. Claude retains its inherited
`ANTHROPIC_BASE_URL`; a Codex pool token never establishes Claude pool availability.

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
is claimed. Codex standalone `error` events are provisional when followed by a
successful `turn.completed`; explicit failed turns/tasks remain terminal.

Codex now uses `--json` even on the stock-awk path so provider failures remain
available to the classifier. On hosts without GNU awk this changes streamed
stdout to JSONL; the output file still contains the last agent message.

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
| Read-only / bb-seat | Unsupported; rejected before spawn (`BB.test_read_only_refused`) | No seat receipt may claim read-only execution | Not applicable: no seat starts | Not applicable: no invocation | Never falls into a writable seat (`BB.test_read_only_refused`) |

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
confirmed termination. An export or stop failure retains the seat for recovery.
The adapter must report missing model/effort/permission evidence rather than
copying requested settings into observed fields. The scratch seat completed,
exported and archived, but the installed BB schema supplies no model/effort/
permission attestation, so acceptance remains blocked. BB provider retries also
lack a supported per-seat disable control. See [the canary](../research/bb-seat-canary.md).
Independent review and unresolved parity cells remain acceptance gates. The
coordinator corrected the reviewer to governed Fable because Astra produced this
implementation; an additional Astra review cannot establish independence.
Nothing in this record authorizes pushing, publishing, releasing or deployment.
