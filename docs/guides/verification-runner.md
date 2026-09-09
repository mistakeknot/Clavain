# Fresh machine verification

`scripts/verification_runner.py` executes reviewed shell checks and returns the
existing `VerificationStep` JSON contract. It does not install dependencies,
repair the checkout, invoke a model or reuse passing results.

```sh
python3 scripts/verification_runner.py --spec /path/to/verification.json \
  --project-dir /path/to/repository --evidence-dir /private/tmp/my-verification \
  --run-id pilot --task-id task-1 --attempt 0
```

The evidence base must be an owned private directory (0700), separate from the
source and declared dependency repositories. The runner creates it if absent.
Use the physical path: symlink components, including macOS `/tmp`, are rejected;
use `/private/tmp`. Each invocation creates a unique private run directory.
The stdout JSON references the receipt and its SHA256; full logs and source
fingerprints stay in that directory. Summaries are capped at 6,000 characters.
Python 3.12 or newer is required, matching the repository's test environment.

```json
{
  "required": true,
  "inputs": ["local-test-input.json"],
  "timeout": 600,
  "output_limit": 67108864,
  "prerequisites": {
    "paths": ["tests"],
    "executables": [{"name": "python3", "version_args": ["--version"], "version_contains": "Python 3."}]
  },
  "checks": [{
    "id": "unit-tests",
    "run": "python3 -m pytest tests --junitxml=\"$VERIFY_EVIDENCE_DIR/pytest.xml\"",
    "expect": "exit 0",
    "test_count": {"parser": "pytest-junit", "report": "pytest.xml", "min_executed": 1, "max_skipped": 0}
  }]
}
```

All fields are validated before checks run; unknown fields and duplicate JSON
keys are errors. Checks may override timeout and output limit. `exit N` checks
the exact exit status. `contains "text"` requires both exit zero and a match in
complete retained output. Commands run with `/bin/bash -e -o pipefail`, no stdin,
and bounded process-group cleanup. Bash startup injection variables are removed.

Declare dependencies under `prerequisites.repositories`, with `path`, exact
40/64-character `revision`, and optional `inputs`. Each dependency receives the
same source fingerprint as the primary repository. Executable entries accept
`name`, expected resolved `path`, expected `sha256`, `version_args` and
`version_contains`. Supported probe vectors are `["--version"]`, `["-V"]` and
`["version"]`; probes have a 10-second, 1-MiB limit. No arbitrary probe shell is
accepted. The inventory covers declared executables only.
Executable names containing `/` resolve relative to the project directory.
The pilot declares `scripts/verification-toolchain.py --version`, a fixed probe
that imports pytest and PyYAML and records their versions. Missing imports are
prerequisite failures before any test command. Package bytes are provided by
the pinned CI image; this probe is not a full package dependency inventory.

Pytest uses one fresh xunit2 report with exactly one testsuite and consistent
testcase counts. Reports must be simple `.xml` filenames under
`$VERIFY_EVIDENCE_DIR`, distinct for each check; existing reports are rejected.
Missing, stale, malformed or zero-executed-test reports are unverifiable.
Completed count assertions (minimum executed, maximum skipped, failures/errors)
are failures. Skips default to zero, including pytest xfails and platform skips;
reviewed suites expecting these must explicitly set `max_skipped`. xunit1 is
unsupported; select `-o junit_family=xunit2` if the project overrides pytest's
default. Other test runners may use exit/output
assertions, but the receipt then supplies no structured test-count guarantee.

Stable dirty tracked files and staged changes are allowed. Before/after
fingerprints include HEAD, raw index, staged records, tracked bytes, modes and
symlink targets, plus explicitly declared untracked inputs. Unrelated untracked
files are neither read nor changed. Endpoint snapshots cannot detect a change
that is restored between snapshots, or undeclared external inputs. Declare
symlink referents as dependency/input coverage when checks consume their bytes.
This runner is not a sandbox for hostile commands and cannot contain a daemon
that deliberately creates a new session and closes its output descriptors.
Output is drained for up to 0.3 seconds after the shell exits; the receipt records
whether draining continued after leader exit. Short-lived descendants may finish
during this window. Output descriptors still open afterward, or process-group
members still running after drain, make evidence unverifiable. Checks must wait
for all intended work; the runner does not supervise detached sessions.

Evidence is retained until the operator removes it. There is no automatic pruning
or passing-result cache. Size scales with two source inventories plus complete
logs (up to the reviewed per-check limits); allow disk space accordingly.

Successful checks produce machine evidence eligible for independent review.
`UNVERIFIABLE` never grants machine acceptance. Explicit `required: false` with
empty `checks` permits review without a machine or vetting signal. CLI exit codes
are 0 for machine evidence, 1 for assertion failure/timeout and 2 for unavailable
evidence, including optional empty checks. Consumers must inspect structured
results to distinguish repairable assertions from operational timeouts.

Independent QA, required CI, live acceptance and publication gates still apply.
API cost estimates and subscription allowance usage are separate measurements;
missing usage coverage must remain unknown.

Execution manifests place this configuration under each task's `verification`
field; checks are combined with that task's valid plan `<verify>` entries.
`orchestrate.py --validate manifest.exec.yaml --plan plan.md` validates the
combined contract. The companion JSON schema and example live in `schemas/`.

`scripts/ci-verification.sh` is the bounded zklw pilot recipe. It exports a gzip
tar archive as base64 between `BEGIN_VERIFICATION_EVIDENCE_TGZ_BASE64` and
`END_VERIFICATION_EVIDENCE_TGZ_BASE64` in the fleet's private retained log. Verify
the announced archive SHA256 and each receipt/artifact hash before using it.
Extract only into an empty private directory and use the `.retained` test report;
the raw writable report and `step.json` are covered by the archive hash only.
The 32-MiB compressed export expands to about 43.3 MiB of base64, below the fleet's 64-MiB log limit;
export failure fails the job. The fleet log's existing 30-day retention applies.
In CI, the recipe requires `CI_SOURCE_SHA` to equal HEAD and pins the verification
specification's content hash. Compare two guests' source/policy and successful
coverage, not their receipt hashes: timestamps and guest paths differ per run.
