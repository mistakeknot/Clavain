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
| Issue tracking | Beads is authoritative for each tracker until that tracker's Weaver Stage 4 activation receipt, then Aleph tasks (decision 2026-10-08, bead mk-gqds); never both for one tracker |
| Runs, goals and attempt lifecycle | Intercore |
| Retry, cancellation and transport selection | dispatch |

Every `bd` instruction in canon, skills and hooks applies to a tracker only while
that tracker is on Beads. A tracker's activation receipt is the Weaver Stage 4
record naming that tracker (see the Weaver migration plan, `docs/weaver-migration-plan.md`
in the Aleph repository); it covers only the tracker it names. After the receipt,
new work for that tracker goes to Aleph tasks and the Beads copy is read-only.

Intercore is the sole writer of admission/running/terminal attempt state. BB
events are observations reconciled by dispatch; BB cannot complete an Intercore
attempt. A BB turn completing proves a transport outcome, not independent task
acceptance. Steering an admitted task is a recorded task change. Scheduled work
must use queued messages, not steering.

Each seat has a durable Intercore state mapping of task, run, dispatch, attempt,
BB thread, submitted request and turn. The task is identified by its canonical
`task_ref`; the legacy bead ID is kept as an alias on the same mapping (version
the mapping when the field is added; readers accept alias-only records written
before the tracker's activation receipt). Switching trackers never changes
attempt ownership: Intercore remains the sole writer of attempt state, and the
task tracker only supplies the `task_ref`. A local journal is written before spawn
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

`--via bb` is an explicit transport for `plan-review`, `validation`, `cross-lab-review`,
`routine-execution`, and `deep-execution`. A role-to-sandbox allowlist is
enforced by both dispatch and the seat adapter: review roles permit only
`read-only`, while execution roles retain `workspace-write` and
`danger-full-access`. Dispatch defaults review roles to `read-only` and rejects
an explicit writable sandbox before spawning a child. Unknown roles are also
rejected before spawn. A review seat also requires a BB backend whose provider
can enforce read-only operation; the helper rejects unsupported backends before
calling BB. The transport retains the resolved backend, model and effort, maps
service tier `standard` to BB `default`, and creates an isolated worktree from
the exact source commit. Dirty source changes are not silently omitted: the
adapter refuses a dirty checkout. Project resolution follows `-C`, not an
unrelated ambient project. No routing profiles change.

On the installed BB release, Claude review seats use `bb thread spawn --plan`,
which selects Claude Code's plan permission mode; execution seats keep the
existing writable `auto` launch unchanged. Plan mode is a provider-harness
control, not an operating-system read-only sandbox. In particular, there is a
plan-approval race: if a human approves the plan in the BB UI before the seat
supervisor stops the child, the provider can switch to writable `auto` mode.
The completion predicate therefore requires an effective `plan` attestation for
review seats and `auto` for execution seats. BB's Codex provider currently maps
every exposed permission mode to a writable sandbox, and its `--plan` flag
changes the prompt action without changing that sandbox. Both live and dry-run
dispatch reject a read-only Codex BB candidate as `unsupported_adapter`, which
allows only a declared read-only-capable fallback to continue instead of
silently entering a writable BB seat.

The version 2 seat journal and receipt record both `role` and the requested
`sandbox`. Because the installed BB event schema does not attest the effective
provider permission mode, the adapter leaves
`effective_permission_mode` unknown rather than copying the request. It also
checks the isolated child worktree as a termination postcondition: `HEAD` must
still match the source commit, the tracked diff from that commit must be empty,
and there must be no nonignored untracked files. A failure changes the outcome
to `sandbox-violation` and blocks acceptance, including during recovery. This is
defence in depth, not sandbox enforcement: it cannot see writes to ignored
paths, shared-repository refs or tags, shared `.git/config`, or paths outside the
child worktree. Plan deltas, completed plan items, and pending plan approvals
are folded by item ID so a terminal plan can replace its partial delta without
losing the review output. Token-usage events are reduced to an explicit numeric
field allowlist before they enter the journal or receipt; arbitrary event
payload fields are never retained. Cross-lab review uses the same read-only
allowlist as plan review and validation. Only Claude currently qualifies; a
Codex candidate remains `unsupported_adapter` until BB enforces a read-only
provider sandbox. Model and permission evidence remain unknown and acceptance
stays blocked until BB attests them for the submitted request and accepted
turn. Thread settings and requested model names cannot supply that evidence.
The separate `--review-scratch` path still rejects `--via` and retains its
existing sandbox, passthrough and source-mutation checks. Every role absent
from the allowlist remains unsupported.

Inside enrolled BB, next-goal helpers use `CLAUDE_SESSION_ID` when present,
otherwise `BB_THREAD_ID`. The Stop receipt consumer uses the same fallback.
This repairs `unknown.json` collisions without changing plain terminal identity.
Native provider session IDs and BB thread/turn IDs remain distinct receipt
fields; none is substituted as an observed model or an observed effort.

Direct pooling uses the installed BB provider's corrected mechanism: Codex
responses endpoint `/api/v1/plugins/account-pool/http/v1`, an explicit
`bb-account-pool` provider configuration, and an environment-sourced
`x-bb-account-pool-token` header from `CODEX_POOL_AUTH_TOKEN`. No nested-server
parent token (`BB_ACCOUNT_POOL_PARENT_TOKEN`) is reused.
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
- Raw provider captures are tracked separately.

**Bearer tokens in the child environment, and the post-run leak scan.**
Scope: this covers the main engine launches and the artifacts listed below. It
is not a guarantee that no child or file ever sees a token; the known limits
at the end of this section say where it stops.
`scripts/dispatch.sh` unsets `BB_ACCOUNT_POOL_PARENT_TOKEN` and
`CLAUDE_CODE_MESSAGING_TOKEN` at startup, so no child of any backend sees
either. `ANTHROPIC_AUTH_TOKEN` is kept for a Claude-backed dispatch and for a
zaka agent named `claude` or `claude-code`; every other backend (codex, kimi,
flere, other zaka agents) has it unset in its own child, after the pooled-Codex
alias has been built. The `codex --version` probe (including its `sed` and `tail`
helpers) and the `codex sandbox` preflight run without it, and without
`CODEX_POOL_AUTH_TOKEN`; the sandbox preflight is a probe and makes no model
call. In a Codex run the unset happens right after the pooled alias is built,
before the sandbox preflight. Children that start earlier in `dispatch.sh`
(argument parsing, routing and other startup work) still inherit
`ANTHROPIC_AUTH_TOKEN`. A pooled
Codex child still receives `CODEX_POOL_AUTH_TOKEN`, which carries the same
bearer. A declined or unavailable pool route still drops it as before.

Before any unset, dispatch captures the values of `ANTHROPIC_AUTH_TOKEN` and
`CODEX_POOL_AUTH_TOKEN` in a shell array that is never exported and never
printed. After a run, the artifacts listed below are scanned for those values
(Claude, Codex pooled and direct, Kimi, Flere and the BB seat).
`scripts/token-leak-scan.py` receives the values through its own environment,
never a command line, and scans any nonempty value, raw and JSON-escaped, as
bytes. It scans the captured stderr, the provider events files, the prompt
capture, the output file and its sidecars (`.summary`, `.verdict`,
`.verdict.pre-error`, `.recheck.md`, `.receipt.json`), the failure and
intercept evidence, the dispatch state and interband files, the external review
receipt written under `CLAVAIN_REVIEW_RECEIPT_DIR` (or its default), the run
receipt file and, for Flere, every file under `<output>.attempt` (prompt, RPC
events, stderr, start record, home and session files, recursively). Scans run
before stderr is mirrored, again after the last artifact is written, and from
the EXIT trap. Flere has its own EXIT trap, installed before its worker
starts, so a normal return, an early exit and INT or TERM all scan; the shell
runs it once the foreground worker has returned.

The full real path of every artifact is resolved, parent directories
included. An artifact whose real path differs from its given path (a symlinked
file or a symlinked parent directory) is followed only when the resolved
regular file lies under the run's own roots: the output directory, the review
receipt directory, the run receipt directory and the interband directory.
Otherwise it is never opened or rewritten; it is reported by a sanitized name,
and the run fails closed. An artifact path with no symlink in it is scanned
wherever it is. When neither token is set, the scan is skipped; only a
Claude-engine dispatch prints a note saying so (the note omits any value), and
other engines skip silently.

On a hit the run fails: nonzero exit and an error verdict. Every occurrence is
redacted in place in a single pass. The marker is `[REDACTED:anthropic-token]`
unless the result would still contain a value (for example a value of `token`
or `e`); the scanner then uses a fixed-width marker of one character that
occurs in no value, and if no marker leaves the data free of every value the
file is left unmodified, reported as unscanned and the run fails. File names,
paths and metadata in the hits record, the hook argument and error text pass
through the same redaction. The scanner's own fixed diagnostic messages are
checked before they are printed (see the known limits below). A leak report (bead, role, run id, files, counts,
unscanned files, timestamp) is written to `<output>.token-leak.json`, or to a
temporary file when there is no `-o` or the path itself would carry the value;
if the temporary path would also carry a value, no report is written, the hook
does not run and dispatch prints a fixed message. The whole hit output of one scan is
joined and checked as one document before it is written (so a value that
spans a record boundary is caught). For a regular file opened for append the
check also covers the last bytes already in the file (so a value spanning two
scans is caught); that check needs the existing tail to be readable: if an
existing non-empty file cannot be read, nothing is written to it, one fixed
line is printed and the run fails (exit 4); for a path that is the same open file as stdout or stderr
(`/dev/stderr` and `/proc/self/fd/2` join stderr's buffer, any other match
stdout's) the records
join that stream's buffer. When stdout and stderr are the same open file, both
buffers (stdout's, then stderr's) are joined and checked as one document at
exit, so records and diagnostics are checked together in the order written;
if they carry a value, a fixed suppression line is written instead. The
report is a separate file written by atomic replacement and shares no
destination with the hits path or the diagnostics. Not covered: a hits path that is neither a regular file nor
stdout or stderr (for example another pipe) is checked per scan only, and a
stdout or stderr that is a regular file has no earlier content checked. The
check is against every value (the default variables plus each
`--token-env`: a named variable adds to the defaults and never replaces them);
if the document would carry a value it is replaced by a fixed value-free record
(without the count), and if even that would carry a value nothing is written. This
holds for the destinations listed above, including `/dev/stdout` and
`/dev/stderr` (bead mk-47vtm.5). `report` uses the same set of values. The run fails in
every such case. The report keys and fixed text are not redacted: if a value occurs anywhere in
the finished report (a single common letter does), no report is written, the
run still fails and the verdict does not point at a report. On an internal
error, including an import failure, the scanner prints one fixed line, or a
fixed suppression line when its output would carry a value, or nothing. If
`CLAVAIN_TOKEN_LEAK_HOOK` names an executable, it is run with the report path
as its only argument and without `ANTHROPIC_AUTH_TOKEN`,
`CODEX_POOL_AUTH_TOKEN`, `BB_ACCOUNT_POOL_PARENT_TOKEN` or
`CLAUDE_CODE_MESSAGING_TOKEN` in its environment, so a host can file a
rotation task; a failing hook only warns, and no hook runs without a report.

Remaining limits, stated plainly:

- stdout already mirrored to the terminal before the scan cannot be retracted;
- a receipt written before a later hit is found keeps its earlier status for
  that write, although the artifact is redacted and the run exits nonzero;
- the Flere worker records SHA-256 hashes of its attempt files in its receipt
  before the scan, so a redacted attempt file no longer matches its recorded
  hash;
- Flere `--dry-run` is not scanned, and a Flere signal exit scans only after
  the worker has returned;
- the shared `CLAVAIN_REVIEW_EVENTS` log and the Intercore routing database
  (`ic route record`) are not scanned;
- zaka runs submit a session and exit, so dispatch does not scan zaka artifacts
  at all;
- paths not named above are not scanned. Two files a run writes are known to
  be missed: the kimi seat's final-message capture (`KIMI_FINAL_FILE`, removed
  before the closing scan) and the routing and headroom evidence files written
  while a fallback is forecast. Follow-up: bead mk-47vtm.3;
- every message the scanner itself prints (stdout or stderr, including usage,
  `--help` and its fixed error messages) is queued in memory per stream and
  written once, at exit, by one output point. That point encodes the whole
  buffer exactly as the stream will write it (the stream's own encoding and
  error handler), and checks those bytes, message boundaries and newline
  terminators included, against the values of the default variables and of
  every `--token-env` named in argv (any prefix of `--token-env` of three or
  more characters is treated as that option, and the parser itself rejects
  abbreviations). Raw and JSON-escaped forms are checked, encoded as the stream
  encodes them and as UTF-8. If none occurs, those bytes are written in one
  write. If one occurs, the fixed line `token-leak-scan: diagnostics
  suppressed` is written instead when that line contains no value, and
  nothing is written otherwise; the exit status is the same in both cases. If
  the check cannot be decided, nothing is written. A failed write or flush
  points the stream at `/dev/null`, and the scanner ends with the status of
  the outcome (for `--help`, 0). `SIGINT` is set to its default action at the
  top of the script, so an interrupt ends the process by that signal (shell
  status 130, which `dispatch.sh` treats as a scan error and fails the run
  closed) with no Python traceback. Limits: diagnostics appear when the
  scanner exits, not as they occur; output the Python interpreter writes
  itself before the script installs its handlers (a startup failure, or a
  signal that arrives before the handler is installed) is not covered;
  messages printed by `dispatch.sh` itself are outside this check (bead
  mk-47vtm.4);
- a child that renders the token in a form other than the raw or JSON-escaped
  string (encoded, split or truncated) is not matched, and a fragment of one
  value that overlaps a different value is not matched separately;
- the scan is verified only by the dummy-value tests in
  `tests/shell/dispatch_token_leak.bats`; it does not prove that no value
  reached any other sink.

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

`scripts/pool-headroom.sh` makes one read-only `bb pool status --json` call
(60-second deadline, `CLAVAIN_POOL_HEADROOM_TIMEOUT`; the call takes 7-12 s on a
busy host). The snapshot is cached for 120 seconds in
`$XDG_CACHE_HOME/clavain/pool-status.json` (`CLAVAIN_POOL_HEADROOM_CACHE_TTL`,
0 disables). Accounts that are not `ready`, are held, carry a usage restriction
or were last observed over 30 minutes ago are skipped, and the weekly pace guard
subtracts 15 points, the same rules as the coordinator-side `executor-headroom`
helper. A provider whose accounts are all exhausted, held or restricted is below
the floor, so dispatch picks the other provider's seat up front; stale data is
unknown, not exhausted. `--stdin` runs the pure JSON fixture core. The summary
retains account IDs, headroom and reset times; it omits labels, email addresses
and credentials. It reads Codex `limitWindows` and Claude provider/family windows.
The best enabled account can differ by family. Unknown telemetry never proves
exhaustion, and a pool error produces `status: unknown` with no routing change.

Only `routine-execution`, `deep-execution`, `scout`, and `coordination` consume the forecast.
The default floor is 10% weekly headroom and the five-hour switch threshold is
the pool's `switchThreshold`, defaulting to 0.98. Routine and deep execution may
prefer a declared candidate from another provider with more headroom; scout
only excludes seats below the floor. Planning, review, validation and escalation
keep their existing routes and observed-failure fallback rules.

Dispatch records the snapshot, forecast exclusions and any ordering change.
`profile_ref` and `primary_profile_ref` identify Intercore's primary resolved
profile, while `executed_profile_ref` and `resolved_profile` identify the
attempted seat. Attribution consumers must key on `executed_profile_ref`. The
BB seat journal also retains both profile references and the requested
provider/model/effort. These requested settings do
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
| Read-only / bb-seat | Review roles require `read-only`; Claude uses enforced plan permission, while writable-only Codex is rejected (`BB.test_review_roles_accept_only_read_only_and_record_receipt`, `BB.test_codex_review_rejected_without_enforced_read_only_bb_permission`) | Version 2 receipt records role and sandbox; effective permission remains observed-or-unknown | Same stop/archive path; mutation evidence survives recovery (`BB.test_recovery_preserves_review_sandbox_violation`) | Only allowlisted turn-usage evidence; unknown still blocks required accounting | Writable review requests, unknown roles, commit/worktree mutations, and unsupported backends fail closed (`BB.test_review_roles_reject_writable_sandboxes_before_bb`, `BB.test_read_only_review_commit_is_a_terminal_seat_failure`) |

## Startup and acceptance

Only enrolled BB startup is shortened. Health findings retain individual lines,
including stale, missing, unreadable and peer findings; optional detail and skip
lines are omitted. Instruction-contract state, ownership uncertainty and runtime
blockers retain their content. Remontoire retains inspect/resume/replay/doctor
commands and approval boundaries, deduplicated by thread/cycle/stage/evidence
hash. `bd where --json` owns workspace resolution for any tracker still on Beads; an unknown failure does not
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
lack a supported per-seat disable control.
Independent review and unresolved parity cells remain acceptance gates. The
coordinator corrected the reviewer to governed Fable because Astra produced this
implementation; an additional Astra review cannot establish independence.
Nothing in this record authorizes pushing, publishing, releasing or deployment.
