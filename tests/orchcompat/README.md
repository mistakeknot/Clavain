# orchcompat: characterization tests for Clavain's routing and roster defaults

These tests pin what Clavain does today, so the later slice that splits the
routing and roster config into neutral defaults plus an operator overlay can
prove nothing moved. They are characterization tests: a failing test means
behavior changed, not necessarily that the change is wrong. Update a golden
only after reading the diff.

They add files only. No existing source, config or test file is edited.
Bead: mk-j1zww.12 (slice S2, Clavain part).

## What is pinned

| Area | Test module | Golden / fixtures |
|------|-------------|-------------------|
| Role resolution: backend, model, effort for every role and every decision-context reason set, from `ic route dispatch` with the policy passed explicitly | `test_role_resolution.py` | `golden/role_resolution.json` |
| `roster-slugs.yaml`, `roster-families.yaml`, `fleet-registry.yaml`: slug-to-family lookup, unknown slugs, validation errors, `lib-fleet.sh` queries | `test_roster_config.py` | `golden/roster_config.json` |
| Contract generator `scripts/sync-agent-instructions.py` and `check-instruction-contract.sh`: rendered block, receipt line (policy SHA256, profile), failures | `test_contract_generator.py` | `golden/contract_render.json`, `fixtures/contract/` |
| `scripts/dispatch.sh` argument handling that does not launch a model, and the receipt it writes, against fake `codex`, `claude` and `ic` on PATH | `test_dispatch_args.py` | `golden/dispatch_dry_run.json`, `fixtures/dispatch/` |

See `COVERAGE.md` for the table including what is not covered and why.

## Run

From the repository root:

    nice -n 19 python3 -m pytest -q -p no:cacheprovider tests/orchcompat

The suite needs `python3` with `pytest` and `pyyaml`, plus `bash`, `jq` and
`yq` v4 (for the fleet reader). Without the real `ic` binary the
`requires_ic` tests are deselected, and without `yq` the fleet-reader tests
are skipped; both are printed in the run header and summary. Pass
`--orchcompat-require-ic` for the strict gate: a missing `ic`, `yq` or `jq`
then stops the run with an error instead. Use it in any run that is meant to
gate a change (the flag keeps its name; it now covers all three tools).

## Hermeticity: what is isolated and what is not

Every script runs with an allowlisted environment, built from nothing: temp
`HOME` and `TMPDIR`, a fixed `PATH` (fakes first), `LANG`/`LC_ALL`, and
`TZ` if the caller has one. Nothing else is inherited, so `BASH_ENV`, `ENV`,
`CLAVAIN_*`, `PYTHONPATH` and the like cannot reach a script. `INTERBAND_LIB`
points at an empty file in the temp HOME: `dispatch.sh` sources that variable
first and stops at the first library it finds, so no interband library next to
the checkout or in the operator's home is ever loaded. The policy path is
passed explicitly, so the tests do not read or write the operator's state.
The rig's own `git` calls (initializing the scratch repo, and the ancestry check
that picks the baseline or main expectations) go through the same allowlist, with
system and global git config switched off (`GIT_CONFIG_NOSYSTEM=1`,
`GIT_CONFIG_GLOBAL=/dev/null`), no `GIT_DIR` or `GIT_WORK_TREE`, and an empty
template, so a caller's git variables or gitconfig cannot redirect them
(`orchlib.run_git`). Fake CLIs record their arguments and exit; no model is
launched and no network is used.

One exception, by necessity: `scripts/dispatch.sh` hard-codes its state files
as `/tmp/clavain-dispatch-<pid>.json` (plus `.tmp`, `.stderr` and
`.events.jsonl`), so `TMPDIR` does not move them and the script cannot be
edited here. The rig does not claim to isolate them. It launches bash directly,
so the child's pid names the files. A role dispatch also runs `dispatch.sh`
again for the resolved backend, and that inner run has its own pid; the fake
CLIs record their ancestor pids, so the rig finds the inner pid from them.
After each run it asserts that only those four suffixes exist for each such
pid, records them, and deletes exactly those files (`orchlib.reap_dispatch_tmp`).
An unknown name fails the test and is left in place, and so is anything that is
not a regular file owned by the current user (a symlink, say). The helper takes
a directory, so its own tests run in a pytest temp directory and never touch
real `/tmp`. A run killed by the OS or
a timeout of the test process itself, or one that dies before any fake CLI
starts below the launched bash, can still leave its files behind; they hold no
secrets and carry a dead pid.

Environment overrides:

* `ORCHCOMPAT_IC`: path of a specific `ic` build to use.
* `ORCHCOMPAT_POLICY`: the routing policy under test (default
  `config/routing.yaml` of this checkout). The follow-up slice points this at
  the policy produced by neutral defaults plus the overlay.
* `ORCHCOMPAT_GOLDEN_POLICY`: the recorded policy hash the resolved policy
  must equal when it is not the checkout's own file.
* `ORCHCOMPAT_DISPATCH_GEN`: `baseline` or `main`; see Version awareness.

Each role resolution also asserts that the `policy_hash` `ic` returns is the
sha256 of the policy file that was passed.

## Goldens

Role-resolution and dry-run tables are keyed by the sha256 of the policy
file, and may carry several policies at once. The committed files carry the
baseline policy this suite was written against and the policy on main at the
time of writing; they differ only in the `planning`, `frontier-planning` and
`escalation` rows. A test run selects the table whose key matches the policy
under test and fails, naming the hash, if none does.

Regenerate (review the diff; a changed row is a changed routing decision):

    python3 tests/orchcompat/gen_golden.py                 # role_resolution.json
    python3 tests/orchcompat/gen_golden.py --roster        # roster_config.json
    python3 tests/orchcompat/gen_golden.py --contract      # contract_render.json
    python3 tests/orchcompat/gen_golden.py --dispatch      # dispatch_dry_run.json

Existing keys for other policies are kept.

## Version awareness

The suite passes at the baseline commit and at current main. Where the two
differ, the expected behavior is chosen from the git history of the checkout,
never from what the script under test does: `dispatch.sh` receipts carry
`observed_*` and `usage_*` fields only on main, and main refuses
`--review-scratch` and `--repo` on non-review roles where the baseline warns
and runs the seat. `orchlib.DISPATCH_FEATURES` names the commit that
introduced each behavior; if it is an ancestor of `HEAD` the new behavior is
required, otherwise the old one. So a change that brings the old behavior
back into a current tree fails, and so does one that drops a field. The choice
reads the commit graph, not the working tree: run the suite on a committed
checkout. `ORCHCOMPAT_DISPATCH_GEN=baseline|main` overrides it (mutcheck uses
this; its scratch copy has no `.git`), and a checkout where git cannot answer
is an error, not a guess. A shallow checkout is one of those: a shallow
boundary can cut the introducing commit off from `HEAD` and make git answer
"not an ancestor", which would read as baseline behavior. So `orchlib.is_ancestor`
raises when `git rev-parse --is-shallow-repository` is true, naming the override;
fetch full history or set `ORCHCOMPAT_DISPATCH_GEN` explicitly. This is an error,
not a skip.

## Known drift pinned, not fixed

`scripts/roster/generate.py --self-test tests/fixtures/roster/truth-table.json`
reports 58 of 59 at both commits; the case `repo-routing-end-to-end` is
stale. `test_roster_config.py` pins exactly that result and passes when the
stale case is removed, so fixing the table later will need one deliberate
edit to that test.

## Mutation check

`mutcheck.py` copies the files the suite reads into a temp dir, applies one
exact text replacement, and runs the tests there. The control run must pass
first. A mutant counts as CAUGHT only when tests ran and failed; collection
errors and zero tests are ERROR.

    python3 tests/orchcompat/mutcheck.py --all
    python3 tests/orchcompat/mutcheck.py FILE OLD NEW [TESTS ...] [--count N]

Exit 0 caught, 1 survived, 2 error. The tracked tree is never edited. The
name of the first failing test is printed. The last three standing mutants
break behavior that exists on main only (observed receipt fields, usage
fields, the scope refusal); run `--all` at main, where the baseline would
report them as ERROR because the text they replace is not there.

A mutation to `config/routing.yaml` changes the policy hash, so by default the
role tests fail with "no recorded table" before they compare any row. That is
intended (any policy edit forces a golden review), but to see a row-level
catch, pin the golden to the unmutated hash:

    ORCHCOMPAT_GOLDEN_POLICY=$(sha256sum config/routing.yaml | cut -d' ' -f1) \
      python3 tests/orchcompat/mutcheck.py config/routing.yaml OLD NEW tests/orchcompat/test_role_resolution.py
