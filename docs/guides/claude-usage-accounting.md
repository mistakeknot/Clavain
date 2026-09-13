# Claude dispatch usage

`CLAVAIN_REQUIRE_USAGE=1` admits the Codex JSON path and the Claude streaming
adapter. It requires `CLAVAIN_REVIEW_EVENTS`, rejects alternate transports before
launch, and disables automatic retries and fallbacks after invocation. A new
attempt needs supervisor admission against the remaining approved budget.

Claude keeps the Markdown response and verdict interfaces. Its raw stream is
retained beside the event ledger with a fresh invocation UUID. Normalized
`usage.cumulative` schema 1 records bind dispatch, invocation, session, requested
identity and observed identity. Input/cache counts are deduplicated by message;
assistant output placeholders are ignored. Partial output counters are lower
bounds. The final per-model totals reconcile the whole invocation.

Claude budget tokens are input + output + cache read + cache creation. Codex
input already contains cached input, so its budget remains input + output.
`CLAVAIN_TOKEN_BUDGET` supplies a positive per-invocation remaining ceiling to
the adapter when a supervisor has approved one; absent/zero means accounting
only and must not be described as an enforced budget. The execution supervisor
sets it from the approved request and also monitors kernel totals.

Every new cumulative record replaces its preceding record. Exact sequence
replays do not add usage; different invocations add their costs. Unknown schema,
conflicting identities/counters, missing final evidence and malformed records
prevent completion. Codex's plain-text diagnostic lines remain ignorable, but
brace-prefixed malformed JSON and unterminated final lines do not establish
complete accounting.

Kernel collection can overwrite interim token reports from summary text.
The supervisor therefore reports the final budget count after collection,
including partial counts on failure, with `--in=N --out=0 --cache=0`. A failed
report leaves `kernel_report_pending`; recovery retries accounting without
launching another worker. Receipts retain usage completeness and observed
overshoot separately from workflow status.

Cancellation allows an eight-second group drain before the final KILL. The
adapter handles INT/TERM, retains partial evidence and marks it incomplete.
In-flight requests can exceed a reported-token ceiling. Missing final provider
totals cannot authorize another phase. Raw events and prior attempts are kept.

Budgeted Claude seats disallow Agent, Task and Skill as well as the existing
reviewer mutation exclusions. Bash permission is preserved. An independent
model CLI launched through Bash would be outside this ledger; preparation
prompts forbid it, and observed out-of-band work invalidates a cost comparison.

Verification uses synthetic provider streams, actual process cancellation,
Go race tests and an isolated real Intercore collection/reconciliation fixture.
These do not replace a live budgeted Fable canary or human journey acceptance.

Provider contracts: [headless streaming](https://code.claude.com/docs/en/headless)
and [usage semantics](https://code.claude.com/docs/en/agent-sdk/cost-tracking).
