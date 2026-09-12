# Usage observations

Usage collection is opt-in. Intercore stores immutable evidence; Clavain collects
and presents it. Neither a usage record nor a compact report grants acceptance,
changes routing, or establishes subscription savings.

Run the collector explicitly at a prospectively enrolled task boundary:

```sh
python3 scripts/usage_collector.py --phase boundary --output-dir /private/task/before
```

After native completion, supply the actual Codex event file:

```sh
python3 scripts/usage_collector.py --phase completion \
  --events /private/task/events.jsonl --output-dir /private/task/after
```

The directory must be new. It is created with mode 0700; evidence files use 0600.
Each `*-observation.json` is an input for `ic usage observe --record FILE` in the
authoritative task database. The collection JSON retains process lifetime,
requested methods, statuses, and hashes of the observation files. Unsupported or
unavailable endpoints produce evidence with explicit reasons rather than zero
usage. Interrupted collection saves sanitized partial evidence and reaps its
App Server child.

Only `initialize`, `initialized`, `account/rateLimits/read`, and
`account/usage/read` are sent. Collection does not start a thread or model turn.
Its effect on account allowance remains unknown. Per-thread reads require an
unambiguous `thread.started` event; the parent session is never substituted.
Missing source timestamps remain null, so freshness is unknown. Reset times are
not measurement intervals.

Optional delayed reconciliation is a separate foreground invocation with
`--phase reconcile --completed-at SECONDS`. It requests reads at five and thirty
seconds after the supplied native completion timestamp. Dispatch teardown never
starts this process or waits for it. Each read appends new observations referencing
its predecessor where the source association is unambiguous; no earlier record is
rewritten.

An existing CodexBar CLI JSON snapshot can be supplied with
`--codexbar-record FILE`. Its OAuth/web usage and dashboard data retain distinct
source labels and source timestamps. Account identities, credentials and unrelated
dashboard fields are discarded before hashing or saving. Differences between
comparable fields are recorded without assuming the sources cover the same account.
The adapter retains remaining percentages as remaining percentages, without
converting them to used percentages. Snapshot import does not refresh CodexBar.

For receipt-linked collection, opt in through an enrolled dispatch:

```sh
python3 scripts/task-delivery.py --db /absolute/task/.clavain/intercore.db \
  dispatch --usage-output-dir /private/task/new-usage --enrollment-id ID \
  --role routine-execution -- -C /absolute/checkout -o /private/task/result.md "task"
```

The existing dispatch request seals the boundary manifest. The existing terminal
execution receipt seals the completion manifest. Collection failure remains
observational unavailability and does not change the native process outcome.
Standalone collector invocations retain evidence but do not establish these
receipt links automatically.

To bind stored usage to existing prospective execution evidence, use:

```sh
python3 scripts/task-delivery.py --db /absolute/task/.clavain/intercore.db \
  bind-usage --record /private/task/usage-binding.json
```

The binding input has exactly these fields:

```json
{
  "id": "new-observation-id",
  "observation_id": "existing-observation-id",
  "enrollment_id": "existing-enrollment-id",
  "dispatch_request_id": 123,
  "execution_id": 124,
  "attempt_id": "actual-attempt-id",
  "evidence_refs": [
    {"path": "/absolute/execution/events.jsonl", "sha256": "64-lowercase-hex-digits"},
    {"path": "/absolute/collection/0-collection.json", "sha256": "64-lowercase-hex-digits"}
  ]
}
```

The command checks decision ordering, enrollment/cohort/manifest agreement, the
actual attempt, artifact hashes, and recorded event-log identity. It appends a
successor through `ic usage observe`; it does not call `route record`. Missing
receipt-to-artifact linkage leaves usage unbound. A boundary observation without
a native identity keeps that identity missing and binds only to enrollment and
dispatch request; its execution and attempt references remain null. Account-wide
completion counters retain incomplete account coverage even when a native thread
identifies their collection context. A wrapper dispatch UUID is not
treated as a verified `dispatches.id` database key.

Account quota percentages, reported tokens, and estimated credits have different
units and meanings. Cache counters retain their declared subset relationships.
Whole-workflow usage remains unknown when parent, child, retries, review or
follow-up reads are missing. Twelve matched executions provide correctness smoke
and exploratory efficiency evidence only; they cannot establish a five-percentage-
point non-inferiority margin or a 10% Pro allowance reduction.

Disable collection by omitting collector invocations; retain existing evidence.
Compact presentation has its own opt-in flag and rollback. Release, installed-host
acceptance and required independent CI remain separate gates.

Interface references: [Codex App Server](https://learn.chatgpt.com/docs/app-server)
and [CodexBar CLI](https://github.com/steipete/CodexBar/blob/main/docs/cli.md).
The per-thread estimated-credit fields were also checked against the local
Codex-generated App Server schema; unsupported versions remain unavailable.
