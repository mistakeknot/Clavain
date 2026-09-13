# Read-only work intake preview

`clavain-cli work` is an explicit, non-admitting diagnostic preview. It can
enumerate registered Beads trackers, rank possible related work, and show a
tracker task by its qualified identity. It does not bind a session, authorize
implementation, claim or release a Bead, or establish an enforcement boundary.

Every successful human or JSON response reports:

- `binding_authority=not_live`
- `implementation_allowed=false`
- `coverage=none` with `coverage_scope=enforcement`
- optional Alwe history as `unavailable`
- attached sessions as `unknown`

Errors report the same safety fields and set the authority status to
`unavailable`. An unavailable, malformed, timed-out, truncated, or nonzero
authority read is an error, never an empty result.
Successful discovery also reports `result_status=candidates_found` or
`result_status=no_results`, keeping a verified empty tracker result distinct
from unavailable authority.

## Explicit registry

There is no default registry and no automatic discovery or registration. Every
invocation requires `--registry` and an exact `--authority` identity matching the
registry. The registry is strict JSON: unknown fields, duplicate JSON keys,
duplicate tracker UUIDs, duplicate roots, and ambiguous repository aliases or
worktree paths are rejected.

```json
{
  "version": 1,
  "authority_endpoint": {
    "kind": "local",
    "identity": "clavain-canonical-local"
  },
  "trackers": [
    {
      "tracker_uuid": "11111111-1111-4111-8111-111111111111",
      "root": "/absolute/path/to/authoritative/tracker",
      "repositories": [
        {
          "alias": "clavain",
          "worktree": "/absolute/path/to/Clavain"
        }
      ]
    }
  ]
}
```

Tracker identity is the UUID, never a database name. Roots and worktrees must be
absolute, clean, non-root paths. Before any local read, the command validates the
`project_id` UUID in the authoritative root's `.beads/metadata.json` against the pinned
registry UUID. If a registered worktree has Beads metadata, its UUID must match
the same tracker. Missing or conflicting identity blocks the entire read; the
tool never creates or repairs a mapping.

Only an explicitly selected `local` endpoint is executable in this slice. The
fixed command is:

```text
bd --readonly --directory ROOT list --all --limit 0 --include-gates --json
```

It runs from ROOT with a 10-second timeout, a further 250-millisecond pipe-drain
bound, and limits of 4 MiB stdout and 64 KiB stderr, directly as an argument vector
without a shell. User text, plan contents, titles, descriptions, labels, and
artifact references are data only. A `remote` endpoint returns
`required authority unavailable`; there is no SSH implementation and no local
fallback.

## Commands

```bash
clavain-cli work discover \
  --registry=/absolute/path/work-registry.json \
  --authority=clavain-canonical-local \
  --text='ownership and canonical tracker' \
  --plan=/absolute/path/PLAN.md

clavain-cli work status \
  --registry=/absolute/path/work-registry.json \
  --authority=clavain-canonical-local \
  --task=11111111-1111-4111-8111-111111111111:Clavain-abc.3 \
  --json

clavain-cli work explain \
  --registry=/absolute/path/work-registry.json \
  --authority=clavain-canonical-local \
  --task=11111111-1111-4111-8111-111111111111:Clavain-abc.3
```

`discover` enumerates every registered canonical or related tracker. It ranks
lexical overlap only across title, objective, description, labels, artifact
references, acceptance criteria, notes, design, and external reference fields.
Every in-progress task is retained even with a zero score.

The exact classification limit is important: only an explicit
`trackerUUID:BeadID` reference identifies the same tracker task. All other
matches are ambiguous shared-evidence candidates for agent disposition. Even an
exact reference is evidence, not implementation authority, because binding
authority is not live.

`status` and `explain` require that qualified identity. They show Beads status
and assignee as authoritative tracker fields only. The assignee is labeled
`BEADS assignee`; it is not a verified implementation binding. Unknown tasks fail
instead of returning an empty success.

## Deliberately absent

There are no `bind`, `release`, `handoff`, `create`, `update`, `close`, SQL, or
admission paths in this command. Unsupported verbs fail clearly. Optional Alwe
history is not implemented, so the command neither reads raw private session
histories nor invents seven-day coverage.

This partial slice establishes no host or security boundary and has no installed
workflow, hook, startup, policy, Intercore, registration, or canary wiring. The
full shared-ownership plan remains blocked on authority confinement, serialized
release/handoff, native dependency work, wrapper qualification, bypass rejection,
and four-combination canary evidence. Source review and independent zklw checks
remain landing gates; this preview contributes no enforcement coverage.

Future admission fixtures and state-machine verification remain outstanding.
The diagnostic tests do not prove ownership transitions, draining, generation
fencing, release/handoff, heartbeat, or rollback behavior.

The child environment contains only process essentials; inherited Beads, Dolt,
and XDG selectors are excluded. Environment-only authentication is unsupported.
Metadata validation cannot distinguish an authority from a replica carrying the
same UUID. This local diagnostic requires a trusted registry and executable and
does not prove authority confinement or descendant-process termination.
