---
name: remontoire
description: Use when operating the Remontoire portfolio agency - inspect status, run shadow or proposal cycles, make an explicit approval decision, resume approved work, or verify receipts
---

# Remontoire Operator

Operate Remontoire through Clavain's thin cross-host adapter. Remontoire owns
the cycle state machine and Intercore owns durable state. Do not recreate either
one in Clavain.

## Locate the Adapter

Use the first existing path:

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/remontoire-operator.sh
$HOME/.codex/clavain/scripts/remontoire-operator.sh
$HOME/projects/Sylveste/os/Clavain/scripts/remontoire-operator.sh
```

Run it with `bash`. It selects the local runtime when already on zklw and uses
batch SSH to zklw from other hosts. `REMONTOIRE_HOST=local` is the explicit
override for a local development runtime.

If the adapter is absent, report that Clavain needs updating. If the adapter is
present but Remontoire is not installed, use the Interverse agency installer
from the Sylveste root:

```bash
python3 scripts/interverse_agency.py install remontoire
```

## Route the Operation

| Intent | Adapter invocation | Effect |
|---|---|---|
| Health | `doctor` | Read-only runtime and dependency checks |
| Latest status | `status` | Read the latest canonical cycle |
| Ambient attention | `attention` | Read latest cycle plus canonical ready promotions; never mutate or decide |
| Specific status | `inspect CYCLE_ID` | Read one cycle and its evidence contract |
| Shadow cycle | `shadow` | Observe and rank without creating backlog work |
| Proposal cycle | `proposal` | May create one deduplicated P4 experiment, then stops |
| Principal approval | `approve CYCLE_ID --actor=ACTOR` | Record approval only |
| Principal decline | `decline CYCLE_ID --actor=ACTOR --reason=REASON` | Record decline and compound a receipt |
| Continue work | `resume CYCLE_ID` | Execute only when already approved; then review and compound |
| Receipt | `receipt show CYCLE_ID` | Show terminal evidence |
| Replay | `receipt replay CYCLE_ID` | Verify stored-content consistency |

The adapter always requests JSON and returns the Remontoire exit status without
changing its payload.

Scheduled operation is exception-driven. Do not run `status`, `shadow`, or
`proposal` merely because a new agent session started. The shared SessionStart
consumer calls only `attention`, remains silent for normal and completed stages,
and surfaces a command only for a principal decision or recoverable exception.
Ready promotions enter `next-goal` ranking separately; selecting one with
`/goal` starts ordinary implementation and does not alter the source cycle.

## Decision Boundary

Approval and execution are separate. An `approve` request must stop after the
approval record is written and show the resulting cycle state. Never infer approval.
Enthusiasm, a prior roadmap decision, or a request to inspect a proposal is not
approval. Never run `resume` unless the principal explicitly asks to execute or
continue that approved cycle.

Before approval, use `inspect` and surface:

- cycle ID, stage, candidate, and experiment bead;
- repository and allowed paths;
- immutable contract hash;
- metric baseline, target, and direction;
- benchmark, budget, and stop conditions.

Ask for a principal decision when any required field is missing or unclear.
Decline requires an explicit reason. Preserve the supplied actor and reason
verbatim as command arguments.

Remontoire cannot push, merge, deploy, or publish. Do not describe a successful
experiment as shipped; promotion produces separately human-landed work.

## Present Results

Keep the report operational:

1. Show cycle ID and current stage.
2. Show the one next valid action.
3. For a terminal cycle, show the signed receipt ID and offer the exact receipt
   command.
4. On failure, preserve the CLI error and recommend `doctor`, `status`, or
   `receipt replay` according to the failed stage.

Do not edit Remontoire state files, Intercore rows, or receipt projections to
repair a cycle. Use `resume` for idempotent recovery.
