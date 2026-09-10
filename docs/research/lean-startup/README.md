# Lean startup (sylveste-z55b)

Alignment: reduce startup mutation and ambiguity while retaining current authority,
review and verification requirements. Conflict/risk: fewer implicit side effects
can expose callers that depended on startup environment exports or service starts.

## Operations

`hooks/session-start.sh` calls `scripts/startup.py render`. Rendering reads files
only; the optional hook ledger is the sole write. No installation repair, Beads
query, service startup, environment-file export, manifest consumption or sibling
cache rewrite occurs. Missing Python or renderer produces an explicit unknown
context. The complete serialized JSON, including escapes and newline, is capped
at 10,000 UTF-8 bytes. Essential state summaries and the operating contract take
priority over diagnostic detail. Truncation is visible; never infer clear ownership
from an incomplete local export.

The default private state directory is `/var/tmp/clavain-startup-<uid>`, mode 0700.
Override with `CLAVAIN_STARTUP_STATE_DIR` or `--state-dir` for a private runtime
directory. Symlinked state directories are refused.
It deliberately sits outside home because some supported operators track home
with Git. Explicit state paths inside any worktree are refused. Telemetry failure
leaves context usable and reports missing coverage. No tools run during render.

Run maintenance explicitly from the selected installation:

```sh
python3 scripts/startup.py doctor --source-repo /path/to/Clavain
python3 scripts/startup.py refresh --project /path/to/project
# Optional, potentially slow evidence reconciliation (20-second timeout):
python3 scripts/startup.py refresh --project /path/to/project \
  --runtime-audit scripts/runtime-evidence-audit.sh
python3 scripts/startup.py render --project /path/to/project --telemetry <<<'{}'
```

`refresh` atomically writes a versioned local snapshot; it does not repair the
installation or start services. Runtime audit findings survive staleness and remain
warnings until refreshed. `doctor` checks selection, hook targets and source-version
agreement, reports current snapshot status and hook errors since the latest
refresh, and retains the historical ledger. A clean doctor is not host acceptance.
Version-matched provenance does not establish full artifact equivalence.

Use existing explicit tools for other maintenance: `check-install-updates.sh
--refresh`, the relevant installer's narrow instruction-sync operation, and
`clavain-cli cxdb-start` when that service is required. Automatic sibling-version
replacement is removed. Preserve old directories for running sessions; do not
rewrite them into reciprocal symlinks. Installation repair must select verified,
version-matching source and record the previous selection for rollback.

## Instruction and identity delivery

The renderer accepts a matching explicit or portable instruction block only as
instructional evidence. An older managed block is reported stale, not duplicated.
Synchronize only that block, selecting the same package and policy:

```sh
python3 scripts/sync-agent-instructions.py --source /selected/Clavain \
  --host codex --file ~/.codex/AGENTS.md --portable-policy --dry-run
# After review, repeat without --dry-run, then with --check.
```

Claude uses `--host claude --file ~/.claude/CLAUDE.md`. No broad installer is needed.
Specialist skill discovery and current routing assignments remain unchanged.

The native hook `session_id` appears in context and telemetry. Callers that need a
child join pass it explicitly as `DISPATCH_SESSION_ID`; do not infer a parent from
whichever private ledger row happens to be newest. `BD_ACTOR` should likewise be
set explicitly when claiming work. No trace identifier is invented. Host version,
model and effort remain null when the native payload omits them. Native transcripts
and governed dispatch receipts remain the authority for actual model/usage.

## Attribution

Interstat accepts optional `startup_evidence: [{path, sha256}]` entries in the
existing task-attribution manifest. The collector verifies each sealed ledger and
joins records to an unambiguous provider/session/run binding. The supplemental
`startup` section reports missing sessions separately. It cannot change native
usage totals, independent acceptance or allowance savings. Use `sylveste-7aj8.9`
for remaining collector coverage; do not add another scoring system.

## Behavioral comparison contract

Baseline and candidate must first have a trustworthy selected package. Pin each
source snapshot, settings hash, host version, model and effort before starting.
Codex/Astra and Claude/Fable are separate host cohorts. The six scenarios are:
small edit, substantive bug fix, supplied-plan execution, explicit specialist
skill, compaction/resume, and a permission-bound action. For each host/scenario,
run baseline and candidate in separate fresh sessions, with randomized pair order
from recorded seed 5509: 2 hosts × 6 scenarios × 2 conditions = 24 subjects.
Use an independent frontier reviewer as judge; these subjects are not validators.

For the warm comparison, explicitly refresh each condition immediately before
its session. Test cold/stale conditions separately. Keep the source fixture,
verification contract, permissions, model and effort fixed within each pair.
Do not enable production triggers in fixtures. Use private host profiles and
project directories; preserve native session logs, hook ledger and dispatch
receipts with session/run/task bindings. Record time to useful work, skill loads,
turns, repair attempts, approval behavior, retained state, native token categories,
and independently accepted outcomes. Missing coverage remains unknown.

Stop the candidate cohort on an authority or acceptance regression. An unavailable
host/model or missing independent judge blocks that part of the comparison. Do not
replace a requested host or downgrade a model to fill the matrix. Prompt bytes and
API-equivalent cost do not establish subscription allowance savings. Correctness
can be reported separately without an efficiency claim.

The user authorized the listed provider payload. The native comparison stopped
at subject 19 after independent review found a missed verification-skill load:
20 subjects ran, 19 were accepted, and four planned subjects remain unrun.
[The report](pilot-report.md) preserves the failure and separates correction probes
from the stopped comparison. Efficiency is inconclusive.

Rollout requires independent frontier review and fresh native host evidence.
Roll back by selecting the prior verified package/instruction block, preserving
receipts and unrelated files. Do not roll back to a package whose startup hook
rewrites sibling cache directories. Existing CI migration and publication gates
remain outstanding where not independently proven.
