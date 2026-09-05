# GPT-6 Astra rollout

State as of 2026-09-05: **Astra access verified; comparative evaluation and estate canary still pending**.

## Activation evidence

- Invoked standalone Codex is 0.153.3; Astra-capable profiles require at least 0.153.1.
- `$CODEX_HOME/astra.config.toml` is selected with `codex --profile astra`. It sets `gpt-6-astra`, `xhigh`, Standard processing (`service_tier = "default"` in Codex vocabulary), and experimental context management.
- The user selected Astra/xhigh/Standard for the interactive base profile. Experimental context management remains confined to the separate Astra profile.
- The initial 2026-09-03 preflight returned account-access HTTP 400. On 2026-09-05, a real ChatGPT-authenticated Astra/high/Standard App Server session completed structured question/answer and mid-turn steering probes. Access is no longer the blocker; this does not satisfy comparative quality or estate promotion gates.

## Rollout state

Role routing is opt-in through `dispatch.sh --role`; existing tier consumers and direct Chat Completions clients are unchanged. This is the shadow stage: role resolutions and fallbacks can be inspected without switching default traffic.

Promotion order:

1. opt-in Astra profile;
2. interactive `main-integrator`;
3. `deep-execution`;
4. selected downstream consumers.

After the comparison passes, run a narrow canary for 20 completed tasks or 14 days. Protocol probes and benchmark cells are not counted as accepted estate tasks. Observe main-integrator context per turn against 100K and report absolute main-integrator cost per completed task; neither token share nor cost share is a promotion gate.

The 0.153.2 Sol result remains historical evidence. The fresh three-route comparison uses the same frozen source/evaluator commit `adfb92239a9b6b021034a3981bbe0e6c4d6b0075` and CLI 0.153.3. It ignores user configuration for all cells, keeping experimental context management out of this treatment. See the tldr-swinton evaluation report for cell results and repeats.

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
