# Routing check

These systemd **user** unit templates follow `docs/runbooks/codex-sync.md`
and the rig-health timer convention. They are supplied for review; nothing is
installed or enabled by this change. The service assumes the canonical checkout
at `~/projects/Sylveste/os/Clavain`. Adjust `ExecStart` and `Documentation` for
another checkout. Python 3 and PyYAML (already used by this repository) must be
available to the service interpreter. It runs daily on the dev host with independent
scheduling and sends its JSON report to the journal. It does not write health,
edit configuration, change seats, or file beads by default.

Run the read-only audit against saved evidence:

```sh
python3 scripts/routing-check.py --released-models released-models.json --seats seat-records.json
python3 scripts/routing-check.py --released-models released-models.json --seats seat-records.json --precheck routine-execution
```

`--routing FILE` defaults to the script checkout's `config/routing.yaml`.
The checker reads `dispatch.roles`, `dispatch.tiers`, `dispatch.model_aliases`,
`reasoning.profiles[*].roles`, `reasoning.projects`, and
`reasoning.project_profiles`. Project profiles use the real schema consumed by
`route-spawn.sh`: `project_profiles` maps a project slug to a **profile name**,
and that `reasoning.profiles` entry must carry `scope: project:<slug>` and the
role overrides (for example `clavain: project-clavain`). A record's optional
`project` selects that profile's override after any `policy_profile` override;
a project with no profile uses the fleet row, and a project outside
`reasoning.projects` (plus the mapped slugs) is drift. `--precheck` traverses
project-profile chains for the role. It resolves
model aliases transitively and walks fallback chains with a visited set (the
real policy deliberately has cycles). Full audits check **all** tier pins,
including directly selectable tiers outside a role's default chain, and all
alias pins. Retired alias spellings cannot conceal a stale pin. Profile
and project override references must also be valid.

The retired-model rule is enforced anywhere in the policy, not only on dispatch
tiers and aliases. A full audit also scans every string under any key whose name
contains `model`, `fallback`, or `categor` (recursively), for example
`subagents.defaults.model`, `subagents.overrides.*.model`,
`subagents.defaults.categories.*`, `complexity.overrides.*.subagent_model` and
`reasoning.frontier_models`, resolving aliases first. These fields hold shorthand
such as `sonnet` and `haiku`, so they are checked against the retired list only,
not the released-model list. `--precheck` stays role-scoped and skips this global scan.

The released-model snapshot is JSON with a nonempty `models` array:

```json
{
  "models": [
    {"id": "claude-sonnet-5-5"},
    {"id": "gpt-6.1-sol"},
    {"id": "claude-sonnet-6", "better_than": ["claude-sonnet-5-5"]}
  ]
}
```

IDs must be unique canonical model IDs, not UI aliases. Include every released
endpoint selectable by the policy, including Astra, Opus and Kimi. Optional
`better_than` lists canonical model IDs this release is known to improve on.
Those comparisons yield **consider** findings only, even when bead filing is
enabled: mk decides seat changes. The checker does not infer quality from
version numbers or compare unrelated model families. The example future ID is
illustrative, not a release assertion. A single auto-updating release source
and its quality-comparison evidence are outside this change's scope.

The seat snapshot normalizes BB threads and dispatch receipts into these fields:

```json
{
  "seats": [
    {"thread": "thr_example", "role": "coordinator-seat",
     "model": "claude-sonnet-5-5", "reasoning_effort": "medium"}
  ],
  "receipts": [
    {"thread": "thr_execution", "role": "routine-execution",
     "model": "gpt-6.1-sol", "reasoning_effort": "medium",
     "profile_ref": "routine-sol", "policy_profile": "default"}
  ]
}
```

`seats` is required; an empty array is valid and means no observed live seats.
`receipts` is optional. Every record requires `role`, `model`, and
`reasoning_effort`. Optional `thread` labels evidence; `profile_ref` restricts
matching to that exact reachable tier. Optional `policy_profile` selects a
`reasoning.profiles` override (default `default`); optional `project` selects
a project override after the profile override. Without `profile_ref`, any
declared fallback with the same model and effort may match. Aliases are resolved
for seats too. A missing model, unknown effort, or malformed snapshot cannot
produce a pass. Unknown roles/profiles in records are drift findings.

Effort must match the applicable table entry exactly. Above the greatest effort
declared for that role/model (or the specified tier) is an **over-cap** finding;
lower effort or another model is **seat-drift**. The current table supersedes
the spec's historical medium-effort review examples: its high/xhigh review and
planning tiers are valid. This is a static table audit, not a replacement for
Intercore's runtime filtering, producer independence, effort floors or headroom
resolution. Context-elevated dispatch receipts need their actual effective role
and an applicable table entry; the checker does not claim to replay that context.

Default retired IDs are `gpt-6`, `gpt-6-sol`, `gpt-5.6-sol`, `claude-sonnet-5`,
and `sonnet-5`. Astra (`gpt-6-astra`) remains valid. `--retired-models FILE`
replaces this list with a JSON array of case-sensitive glob patterns, for example
`["gpt-5.6-sol*", "claude-sonnet-5"]`. A model appearing in both the retired and
released lists still fails. Neither input is edited.

The report contains findings, argv arrays in `bead_commands`, and shell-quoted
commands in `printed_commands`. By default it only prints proposed
`bd --actor clavain-coord create ...` commands. Explicit `--file-beads` executes
them for errors and advisory findings; it still never edits routing or seats.
No BB call or model call is made. Repeated opted-in runs can create duplicate
beads; the timer deliberately leaves filing disabled. Failure to file is an
operational failure, not a passing audit.

The report carries `status` (`clean`, `consider`, `drift`, `unknown`, `error`),
an `evidence` count (`seats`, `receipts`, `matched`) and an `unknown` list.
**UNKNOWN** means there is no seat or receipt evidence at all (full audit) or
none for the prechecked role. It is never reported as clean: `status` is
`unknown`, the reason is in `unknown`, and a `routing-check: UNKNOWN` line goes
to stderr. Without `--strict` it exits 0 so ad-hoc runs stay usable; with
`--strict` it exits **3**. Drift still outranks UNKNOWN (exit 1).

Exit codes: **0** clean, consider-only, or UNKNOWN without `--strict`; **1** stale
pin/drift/over-cap; **2** invalid or unavailable input, unknown precheck role, or
bead filing failure; **3** UNKNOWN evidence under `--strict`.
The service passes `--strict` and requires the two externally maintained snapshots
at `~/.config/clavain/released-models.json` and `~/.config/clavain/seat-records.json`;
missing snapshots fail closed and empty evidence fails as UNKNOWN. Snapshot
freshness and fleet coverage are the producer's responsibility.

**Evidence collectors are out of scope.** This change supplies the audit and
the guard, not an auto-updating released-model source or a live BB seat/receipt
collector. Those collectors are tracked in a follow-up bead; until they exist the
snapshots are maintained by hand and the timer reports UNKNOWN rather than
passing when they are empty or absent.

## Dispatch guard (opt-in)

`scripts/dispatch.sh` runs `routing-check.py --strict` (scoped with
`--precheck <role>` for role dispatch) for
governed `--role` dispatch, replayed `--role-resolved` decisions, and policy-backed
`--tier` dispatch **only** when `CLAVAIN_ROUTING_PRECHECK=1`. Resolved decisions
must supply a role in `requested_role` or `profile.role`; missing, malformed or
conflicting roles fail closed. Bare policy tiers audit the full policy and
evidence, including their fallbacks. Unset,
empty, or `0` returns immediately, so behaviour is unchanged. The check runs
after role/environment validation and before any `ic`, pool or model call, using
the resolved decision's `policy_source` for replayed decisions, or the selected
policy (`CLAVAIN_ROUTING_POLICY`, tier policy discovery, or the packaged
`config/routing.yaml`), and the evidence paths in `CLAVAIN_RELEASED_MODELS` and
`CLAVAIN_SEAT_RECORDS`.

```sh
CLAVAIN_ROUTING_PRECHECK=1 CLAVAIN_RELEASED_MODELS=~/.config/clavain/released-models.json \
  CLAVAIN_SEAT_RECORDS=~/.config/clavain/seat-records.json scripts/dispatch.sh --role routine-execution ...
```

When enabled it fails closed with `Error: routing precheck ...` and exit 1 on:
drift or stale pins for the role, UNKNOWN seat evidence, an unknown role, invalid
or unreadable evidence, either evidence variable unset, a missing
`routing-check.py`, or a value other than `1`/`0`/unset. The checker report is
written to stderr, never dispatch stdout. Only the outer role-resolution path is
guarded; the `--role-resolved` child it spawns, and legacy `--tier`/`--model`
dispatch, are not. `tests/structural/test_dispatch_routing_precheck.py` covers
this with a stub `ic`; no model call happens.

---

# Overhead check

These are systemd **user** unit templates for the dev host, following the user-unit
convention in `docs/runbooks/codex-sync.md` and the rig-health timers in dotfiles.
They are supplied for review; this change does not install or enable them.
The service assumes the canonical checkout at `~/projects/Sylveste/os/Clavain`.
Adjust `ExecStart` and `Documentation` if the checkout is elsewhere. BB must be
available on the service PATH and connected to the intended local instance.
The timer runs daily; it writes health but leaves bead creation disabled.

Preview without writing health or beads:

```sh
python3 scripts/overhead-check.py --dry-run
python3 scripts/overhead-check.py --dry-run --file-beads
```

To evaluate a saved stream offline, pass `--events events.json --thread THREAD`.
The input is the bare array produced by `bb thread log THREAD --json --all`.
The check reads every unarchived, undeleted thread, including idle threads.
It groups complete assistant turns by `scope.turnId`, counts each turn once,
and excludes any turn with a tool item. All message sentences must match fixed
status patterns, with fewer than 60 words across the whole turn. Unknown item
types disqualify a turn conservatively. Unfinished turns are not classified.
Pattern coverage is intentionally conservative: unmatched wording is not flagged.

`--limit N` defaults to 3; more than N turns in `(now - 24 hours, now]` fails.
`--now 2026-10-02T12:00:00Z` pins the evaluation time. `--source nothing-new`
is a one-shot verification that requires zero overhead turns from that source
in the current window. Source names are `status-only`, `nothing-new`, `rotation`,
`goal-clear`, `next-goal`, and `confirm-only`; they describe pattern classes.
The JSON report lists threads, sources, reasons and example turn IDs.

Declared fixes are read from `--state-file FILE`, defaulting to
`~/.claude/health/state/overhead-turns.json` (an absent default means no declarations):

```json
{"sources": {"rotation": {"fixed_at": "2026-10-02T00:00:00Z"}}}
```

Any matching turn after its fixed timestamp fails, even outside the current
24-hour window. The checker never edits declarations. It can only evaluate
history BB still retains; missing/pruned history cannot prove a fix was clean.

`--no-dry-run` writes only through `--health-dir`, whose default is
`~/.claude/health`. Scheduled runs write `overhead-turns.json`; manual and
source-verification runs preserve an existing scheduled record and append a
`last_nonauthoritative` result, following `rig-health-write.py`. Dry runs publish
nothing. For an isolated actual report, supply a temporary `--health-dir`.

Bead creation needs both `--file-beads` and `--no-dry-run`. Dry runs print the
proposed command in JSON and never call `bd`. Filing uses actor `clavain-coord`
and includes the thread, source, and example IDs. Repeated opted-in executions
can create repeated beads; scheduling should keep filing disabled until an
operator has decided how to handle duplicate findings.

Exit codes: 0 passes, 1 reports overhead, 2 reports invalid or unavailable
evidence or a health/bead write failure. A malformed event or failed BB call
cannot produce a clean health verdict.
