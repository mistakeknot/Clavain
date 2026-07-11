# Auto-proceed gate wrappers

Wrappers around irreversible ops that resolve one explicit authorization
domain, require a ready signer, consult `clavain-cli policy check`, and write a
signed audit row before the operation. Safety parsing requires `jq`; wrappers
fail before the operation when it is missing or unusable. See
`docs/canon/policy-merge.md` for merge semantics.

## Installation

These scripts live inside the Clavain repo. For per-project activation,
symlink them onto your `$PATH` or call them directly:

```bash
export PATH="$PATH:$(pwd)/os/Clavain/scripts/gates"
```

Individual plugins/commands that invoke irreversible ops should prefer
the wrappers over raw `bd close` / `git push` / `ic publish --patch` /
`bash .beads/push.sh`.

## Wrappers

| Op                 | Script                    | Underlying command              |
|--------------------|---------------------------|---------------------------------|
| `bead-close`       | `bead-close.sh`           | `bd close <bead-id>`            |
| `git-push-main`    | `git-push-main.sh`        | Push authorized SHA to main     |
| `bd-push-dolt`     | `bd-push-dolt.sh`         | `dolt push origin main`         |
| `ic-publish-patch` | `ic-publish-patch.sh`     | `ic publish --patch <plugin>`   |

## Environment integration

Flows (e.g. `/clavain:work` Phase 3, `/clavain:sprint` Steps 6-7) export
vetting context that the wrappers forward to `policy check`:

| Env var                       | Meaning                                        |
|-------------------------------|------------------------------------------------|
| `CLAVAIN_AGENT_ID`            | Identity for the `--agent` audit field         |
| `CLAVAIN_AUTHZ_PROJECT_ROOT`  | Explicit DB, policy, and signing-key owner      |
| `CLAVAIN_VETTED_AT`           | Unix seconds when tests last passed            |
| `CLAVAIN_VETTED_SHA`          | HEAD SHA when tests last passed                |
| `CLAVAIN_TESTS_PASSED=1`      | Tests passed for the latest vetted snapshot    |
| `CLAVAIN_SPRINT_OR_WORK=1`    | This invocation is inside a vetted flow        |

Missing vars are absent at check time, which will fail `requires` that
demand those signals — the wrapper then falls back to confirm or block
per policy.

Root resolution is stable for the whole operation: an explicit
`CLAVAIN_AUTHZ_PROJECT_ROOT` wins, then the active `BEADS_DIR`/`bd context`
repo, then the target Git root. `policy doctor --require-signer` runs before
proof-state writes, token consumption, or the irreversible command.

## Registry

Each wrapper has a companion marker in `.clavain/gates/<op>.gate` at
project root. `clavain-cli policy lint` walks this dir and fails if any
declared op has no matching rule (and no catchall) in the merged policy.

## TOCTOU

The policy hash emitted by `policy check` is pinned and passed through to the
atomic `policy record-signed` call. Git pushes also pin the resolved source
commit, normalized destination ref, and configured push URL set, then push the
immutable authorized SHA. If any signed precondition changes, the wrapper
refuses before the underlying command.
