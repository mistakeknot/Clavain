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
`yq` (for the fleet reader). Tests that need the real `ic` binary
(`requires_ic`) are deselected, with a printed notice, when `ic` is not on
PATH. Pass `--orchcompat-require-ic` to turn that into an error instead; use
it in any run that is meant to gate a change.

Everything runs in a temp HOME and temp data dirs with the policy path passed
explicitly, so the tests do not read or write the operator's real state.
Fake CLIs record their arguments and exit; no model is launched and no network
is used.

Environment overrides:

* `ORCHCOMPAT_IC`: path of a specific `ic` build to use.
* `ORCHCOMPAT_POLICY`: the routing policy under test (default
  `config/routing.yaml` of this checkout). The follow-up slice points this at
  the policy produced by neutral defaults plus the overlay.
* `ORCHCOMPAT_GOLDEN_POLICY`: the recorded policy hash the resolved policy
  must equal when it is not the checkout's own file.

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
differ, the test checks the version it finds: `dispatch.sh` receipts carry
`observed_*` and `usage_*` fields only on main, and main refuses
`--review-scratch` and `--repo` on non-review roles where the baseline warns
and runs the seat. The test detects which behavior the script has and asserts
that one, so a regression in either direction still fails.

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
name of the first failing test is printed.

A mutation to `config/routing.yaml` changes the policy hash, so by default the
role tests fail with "no recorded table" before they compare any row. That is
intended (any policy edit forces a golden review), but to see a row-level
catch, pin the golden to the unmutated hash:

    ORCHCOMPAT_GOLDEN_POLICY=$(sha256sum config/routing.yaml | cut -d' ' -f1) \
      python3 tests/orchcompat/mutcheck.py config/routing.yaml OLD NEW tests/orchcompat/test_role_resolution.py
