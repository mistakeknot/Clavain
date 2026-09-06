# Governed Flere dispatch

Flere is an explicit read-only backend. Automatic routing is unchanged. Configure
an absolute reviewed `CLAVAIN_FLERE_BIN` and `CLAVAIN_FLERE_PROFILE` outside the
project root. A launcher that needs a separate reviewed entrypoint also sets
`CLAVAIN_FLERE_ENTRYPOINT`. The profile supplies the exact provider/model and a
literal API key; ambient credentials and configuration are unavailable.

Submit through Intercore so admission binds the run and attempt:

```sh
ic dispatch spawn --type=flere --run-id=RUN --project=/absolute/project \
  --prompt-file=/absolute/prompt.md --output=/outside/project/result.md \
  --model=provider/model --sandbox=read-only --timeout=120s \
  --dispatch-sh=/absolute/Clavain/scripts/dispatch.sh
```

Use the actual options supported by `ic dispatch spawn`; its `--run-id` enforces
stored policy and prevents an ambient run from substituting for the submitted
run. The explicit `--to flere` dispatcher route rejects tier/role routing,
mutable sandbox settings, image inputs, and arbitrary backend arguments. It
requires the admitted `IC_RUN_ID`, `IC_DISPATCH_ID`, and source prompt hash.

The supervisor verifies effective identity and policy before sending the prompt.
It writes private start, submitted prompt, raw RPC, stderr, native session,
output, and terminal receipt artifacts next to the output. Source and assembled
prompt hashes are separate. Reusing an output attempt is rejected. Enrollment
and manifest identity are carried when supplied; unenrolled work gains no
retroactive acceptance or measurement credit.

The fixed tools enforce canonical-root access at the application level, with
credential/session exclusions and no shell tool. This is not an OS sandbox.
Provider/session automatic retry is disabled. Native usage includes failed
terminal responses when those counters can be reconciled; an unfinished or
unverifiable response keeps incomplete measurement coverage.

Process death, malformed replies, timeout, cancellation, or missing terminal
proof is a failed attempt with `worker_outcome_indeterminate` where the outcome
is unknown. The supervisor terminates its owned process group and retains
evidence. A later `ic dispatch reconcile ID` appends proof without rewriting the
failed attempt. Any further attempt needs a new explicit admission. A completed
execution does not independently accept the task.
