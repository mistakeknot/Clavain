# GPT-6 Astra rollout

State as of 2026-09-05: **Astra access verified; repeated comparison and scoped releases complete; narrow Mac canary started with zero enrolled tasks**.

## Activation evidence

- Invoked standalone Codex is 0.153.3; Astra-capable profiles require at least 0.153.1.
- `$CODEX_HOME/astra.config.toml` is selected with `codex --profile astra`. It sets `gpt-6-astra`, `xhigh`, Standard processing (`service_tier = "default"` in Codex vocabulary), and experimental context management.
- The user selected Astra/xhigh/Standard for the interactive base profile. Experimental context management remains confined to the separate Astra profile.
- The initial 2026-09-03 preflight returned account-access HTTP 400. On 2026-09-05, a real ChatGPT-authenticated Astra/high/Standard App Server session completed structured question/answer and mid-turn steering probes. Access is no longer the blocker; this does not satisfy comparative quality or estate promotion gates.

## Rollout state

Role routing remains opt-in through `dispatch.sh --role`; existing tier consumers and direct Chat Completions clients are unchanged. The narrow canary covers explicitly enrolled work on this Mac only. It does not enroll zklw, production Intercom, routine/bulk traffic, or either interserve class.

Promotion order:

1. opt-in Astra profile;
2. interactive `main-integrator`;
3. `deep-execution`;
4. selected downstream consumers.

Track the narrow canary in bead `Sylveste-kbh5`; the parent adoption bead remains open. Review at 20 completed tasks or 14 days, whichever comes first. Reaching that checkpoint is not automatic promotion, and an empty or insufficient sample cannot establish quality. Protocol probes, benchmark cells, and work begun before enrollment do not count. Observe main-integrator context per turn against 100K and report absolute main-integrator cost per completed task; neither token share nor cost share is a promotion gate.

Measured scope is narrower than exposure: the user-selected interactive base
already runs Astra/xhigh, including un-enrolled work. Such work earns no canary
task credit, but a known high-severity escape there also halts enrollment. This
canary does not claim to contain all Astra exposure or measure un-enrolled work.
Do not run the global Codex installer or codex-bootstrap on this host until
`Sylveste-8nov` resolves the MCP-schema discrepancy; record any other relevant
tool/configuration change as a new evidence boundary before enrolling more work.

The 0.153.2 Sol result remains historical evidence. The fresh three-route comparison uses the same frozen source/evaluator commit `adfb92239a9b6b021034a3981bbe0e6c4d6b0075` and CLI 0.153.3. It ignores user configuration and does not select the separate experimental Astra profile; resolved feature-flag state was not captured.

All three routes passed 18/18 cells (first pass plus two tie repeats). Fable
reviewed all 36 Astra cells, and the main Astra integrator reviewed all 18 Sol
cells. No introduced P0/P1 was found. A directory-pattern scope concern was
accepted after native Git replay; the inherited containment gap remains tracked
as tldr-swinton bead `Sylveste-lca`. The
[completed report and durable receipt](https://github.com/mistakeknot/tldr-swinton/blob/c44a63813828e50cf8bedb4d7b311535e4b04d4c/docs/research/2026-09-05-astra-common-cli-results.md)
were pushed before this consumer update. Task-store decision 24 records the main
integrator's disposition with zero estate tasks and no release approval.

The observed aggregate task-time reduction was 57.1% for Astra/high versus Sol,
not a fleet latency guarantee. Executor costs are bounded Standard-equivalent
estimates because per-request context was not retained. A separate mixed-work
main window averaged 145,285 input tokens across 59 model requests, above the
100K observational target; full cost per benchmark task was not imputed.

The user authorized the protected-main PR path and scoped publication. Interflux
PRs 25 and 26 are merged. `ic publish --scoped`, released and installed at
Intercore `314bfa8`, published Clavain 0.6.308, Interstat 0.3.5 and Interflux
0.2.88. Selected installed manifests match those versions, and each publisher
post-release probe passed. The preservation receipt covers 200,796 unrelated
cache metadata entries, unrelated installed records, and the ahead user
marketplace checkout: all matched the pre-publication snapshot. No broad
cleanup or peer checkout synchronization ran. Claude SessionStart canaries are
separate and may remain pending until new sessions load; existing sessions were
not restarted or counted as runtime acceptance.

Codex's three current Interflux skill links and 22 generated command wrappers
now use the released canonical checkout. The two obsolete skill links and
replaced wrappers were backed up. The global companion installer was not run.
Its remaining MCP-schema doctor discrepancy is tracked in `Sylveste-8nov`;
working MCP configuration is unchanged. See the updated
[instruction audit](astra-instruction-audit.md).

The [release and canary receipt](../research/data/astra-release-canary-2026-09-05.json)
binds the start decision, profiles, release commits and zero-task baseline.
Intercore preparation decision 540 lives in the Sylveste task store. The receipt
preserves that historical start and the pre-enrollment hold, then binds a new
activation decision and 14-day deadline after review remediation. The active
window starts at hold release, not during preparation. This is manual enrollment, not
an unattended monitor or automatic traffic switch. The six completed
implementation/evaluation Beads were closed through zklw's normal signed gates,
with explicit confirmation under the user's standing authorization; no signer
key or approval policy was changed.
The publisher's sealed review rows and complete reports are exported in the
hash-bound artifact named in the receipt, so its evidence does not depend on
the original temporary store surviving. Fable reviewed `e99ad8f`; `314bfa8`
adds two documentation lines disclosing canonical discovery and one test-only
`IC_MARKETPLACE_CLONES` reset. Production code is unchanged. Publisher and CLI
tests passed on that final delta; full Go CI and Secret Scan also passed.

### Enrollment and acceptance

Before each eligible task starts, record its bead, objective, acceptance criteria,
contract kind (`brief` or `exact`), task-store location and unique enrollment ID
under `Sylveste-kbh5`. Use `astra-mac-20260905:<repository>:<bead>` once per
task; retries retain that enrollment ID and get separate attempt IDs. A terminal
enrollment ID cannot be reused or rewritten as a later success. Link remedial
work to the original result; do not give a repeat of the same task fresh sample
credit. Only a materially distinct objective gets a new bead/enrollment. Dispatch
bounded work with `--role deep-execution`; use `--via zaka` for long or
clarification-prone work. The main-integrator consumes a bounded result packet
(checkout diff/commit, checks, failures, unresolved questions) and verifies the
actual checkout. A capable executor receives a `brief` by default, not a
prewritten implementation.

Consequential Astra output requires a sealed first-pass Fable/Claude review
through `--role validation --producer-identity gpt-6-astra`, including acceptance
replay and independent beyond-the-gauge findings. All validator fallbacks must
still differ from the canonical producer. A completed dispatch is not an
accepted task. Record final acceptance separately in the task's Intercore
store, linked to exact producer and validator attempts and commit/check evidence.

Record all enrolled attempts, failures and abandonments; count unique tasks,
not retries or ledger rows. Here a completed task is any terminal enrollment:
accepted, failed, or abandoned after starting. Started means the first dispatch
was submitted. Enrolled but undispatched tasks must be disclosed at checkpoint
as pending or withdrawn with a reason; they are not successes and cannot count
toward the 20-terminal-task sample. Abandonment is stopping without
acceptance and counts as non-success, never as removal from the denominator.
The acceptance ratio is accepted tasks divided by all terminal enrollments;
pending tasks are disclosed separately. "Plan-to-execution" is the legacy gate
label; the measured outcome is satisfaction of the enrolled contract. Report
`brief` and `exact` strata separately, without equating this sample with the
benchmark's task/contract distribution. Keep per-request input/output/cached/context tokens,
wall time, retries, tool calls and main-integration turns. Record absolute task
cost only when the complete attribution is available; otherwise use explicit
unknowns/bounds and explain the missing evidence. Apply long-context pricing
per request, never to aggregate task tokens.

Stop enrollment immediately for a high-severity escape, policy-block retry or
fallback, same-model consequential validation, or missing durable evidence.
Evaluate the 0.909 acceptance ratio at the checkpoint, not after each early
task. With fewer than 20 terminal enrollments at the 14-day checkpoint, report
insufficient evidence and hold promotion; do not infer quality from the ratio.
The integrator prepares the checkpoint packet, then a sealed different-model
validator reviews the aggregate evidence, denominator and scope before mk's
promotion decision. Only mk can change doctrine or consequential shipping
authority. Routine/bulk routes remain Sol.

## Routing and async evidence

Intercore resolves `dispatch.model_aliases` and compares canonical producer identities before returning eligible profiles. Same-model primary and fallback candidates are excluded with reasons. The dispatch audit retains the immutable full route and selected profile, dispatch/attempt IDs, actual settings, checkout IDs, and lifecycle state. A failed start-record write prevents execution.

Codex `--via zaka` uses App Server with explicit sandbox and approval policy; it requires a current Zaka build with `--transport`. The transport enables `default_mode_request_user_input` locally, not in the user's base configuration. `zaka status`, `questions`, `answer`, and `steer` address the returned handle. Submission is not completion; the linked durable worker event log carries subsequent answers, outputs, errors, and turn completion. Other Zaka adapters remain tmux-backed.

Before accepting each App Server turn, the main integrator must run
`bash scripts/collect-zaka.sh <session>`. It returns JSON and exits 3 while work or
questions are pending, 0 after recording completion, or 1 for failure (including
failure to record evidence). It preserves the original route/attempt identity,
records the exact thread/turn, final message and failure classification in
Intercore, and leaves the worker available for further steering. A final message
is evidence, not independent acceptance: inspect the actual checkout and checks.
Run/bead lineage is retained from dispatch metadata. Collection is serialized per
session and returns an existing terminal record on repeat; gates count unique
dispatch/attempt/thread/turn tuples, not ledger rows. A turn completed before
worker shutdown can still be collected when the exact durable completion event
exists. A partial/unreadable event log fails closed; retry collection, not the
model task. Inspect stale collection locks before removing them.

Synchronous role dispatch resets its generated report body and verdict sidecar
after recording the new start. A process exiting zero without a fresh report
produces a warning, never a pass inherited from a previous attempt. Nonterminal
records have no verdict. Inspect the verdict and actual checkout before
acceptance; `completed` describes execution, not integrator approval.

Synchronous execution retains bounded 429 retries and explicit-unavailability
fallback. App Server startup failures can use that policy, but once a turn is
submitted, **no automatic replay or model fallback occurs**: steering may already
have changed its task or side effects. Collection classifies delayed errors,
including policy denials, without resubmission. The main integrator decides any
new attempt with fresh authorization and scope. Transient 5xx/transport failures
also remain terminal rather than silently selecting another model.

The audit database is discovered from the task checkout, not the routing config
checkout. Provision it with `ic init` before dispatch; missing writable audit
storage fails closed. Cross-repository queries must name each task's store.

Installed-path check (2026-09-05): Zaka commit
`5454ccddfdc2e9c7998cd1053c65c788c65e16bd` was pushed and installed, with
`go version -m` reporting that exact clean revision. A real Astra/high/Standard
read-only role dispatch returned session `as-03ce21cbda7de1d79e17da50`; terminal
collection recorded its final probe message with no replay. Intercore records
523/524/525 in the Sylveste task store share dispatch
`E0C47840-CF56-4E94-8D1F-4C8E4CEE18EF` and attempt
`E6D4E8FB-2225-4DEF-9E3B-19706722BCFB`, covering started/submitted/completed.
The completed worker was stopped after collection; its private evidence remains.
This verifies the installed consumer boundary, not software-task acceptance.

Catalog check (2026-09-05): AgMoDB production snapshot at producer commit
`1666546773920333770653daf182d1a09c9fd20d` exposes the canonical Astra family.
An actual Interrank MCP `refresh_snapshot` followed by `resolve_routing_name`
for `astra` and all five supported efforts returned `gpt-6-astra`, the requested
effort, 1,050,000 context and 128,000 maximum output. The non-reasoning alias
returned a tool error. Verified catalog digest:
`67ce101e254ef04c9ece119d6488057a22f4f4b73c4e6f4ad126e01cd8fbb80b`.

Required gates:

- no loss of accepted high-severity findings;
- plan-to-execution success at least 0.909;
- producer and validator never resolve to the same model on consequential work;
- policy blocks never retry or change backend/model;
- routing decisions and verdicts are durable and queryable.

## Existing executor-routing corpus

Phase one from `Sylveste-d3m` is complete and was not repeated. The configured corpus path, `~/.clavain/executor-routing-shadow.jsonl`, is absent on this Mac and on canonical zklw (checked 2026-09-05). Therefore neither `interserve-fast` nor `interserve-deep` has new parity evidence, and neither class was added to `executor_routing.classes`. They continue through the safe `codex` default until real rows and blinded defensibility judgments exist.

## Rollback

Restore the role mapping to its declared GPT-5.6 Sol fallback. Keep the isolated Astra profile and collected decision/evaluation evidence for diagnosis. Rollback never changes release authority or silently switches direct API clients.
