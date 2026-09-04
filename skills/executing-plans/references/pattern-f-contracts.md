# Pattern F contracts (offload execution)

These contracts apply when a plan is executed by a fresh-context executor with a separate validator: the offload shape of the routing doctrine in `commands/model-routing.md`. Roles, rather than model names, are authoritative. Resolve them through `ic route dispatch --role=<role> --json`; the producer and validator must resolve to different models for consequential work. They do not apply to the small-task lane of that doctrine (rule 4: a task under about thirty minutes skips the pipeline and one model runs it end-to-end).

## Roles

**Main integrator** (`main-integrator`). Writes one planning-contract file, lints it, dispatches the executor, dispatches the validator after the executor reports, records both verdicts, and verifies the actual checkout before acceptance. It receives a bounded packet: diff or commit, checks run, failures, and unresolved questions. Final commit, push, deploy, and consequential ship authority remain here unless the user explicitly grants narrower authority.

**Executor** (`routine-execution` or `deep-execution`). Under a `brief`, owns reconnaissance, implementation, and the coding/test loop within the stated scope, constraints, and authority. Under `exact`, applies the prescribed mechanics verbatim. It never expands authority or pushes/deploys implicitly. It reports only the bounded result packet.

**Validator** (`validation`, or `cross-lab-review` for a sealed first pass). Must resolve to a different model than the producer. It replays the frozen acceptance criteria and verification against the resulting checkout, then reports the independent `BEYOND THE GAUGE` channel. It never restates the plan and never fixes anything.

## Planning contracts

Every contract declares `Contract: brief` or `Contract: exact`. The linter also accepts `--contract`; absent either declaration it treats legacy plans as `exact`.

### `brief` (default for Astra and capable executors)

A brief prescribes outcomes, not edits. It has seven non-empty headings: `Objective`, `Scope`, `Constraints`, `Authority`, `Acceptance Criteria`, `Verification`, and `Deliverables`. `Verification` contains a fenced shell replay; the pre-execution gauge syntax-checks it but does not run it before implementation exists. `Deliverables` names the bounded packet: diff or commit, checks run, failures, and unresolved questions. The executor owns the implementation and test loop.

### `exact` (prescribed mechanics)

Use exact for migrations, compatibility with a weak executor, or risk that requires prescribed mechanics. The linter reads the edit pairs, the `Create` blocks, and verify fences. It has no section awareness: it finds verify steps by heuristics on nearby prose and first commands. Pathspecs and the trailer remain outside its reach.

- Each edit to an existing file: a line naming the file in backticks and ending with a colon (In relative/path:), then a line reading old_string: followed by a fenced block with the exact current text, then a line reading new_string: followed by a fenced block with the replacement. New files: a line reading Create relative/path with: (the path in backticks) followed by one fenced block holding the COMPLETE file content.
- Each verify step: a heading `### Verify <task>` followed by ONE fenced `bash` block holding the commands (run from REPO PATH), then a prose line starting `Expected:` stating the observable result. Say "prints NOTHING" or "exit 1" ONLY when that is literally true (the linter treats those as zero-output claims and checks them against your own edits). For a command that must succeed, write `Expected: exit 0`.
- Sections in order: `## Preconditions` (one fenced bash block, must all exit 0), `## Task N` blocks with edits and their `### Verify` steps, `## Commit` (message file path + pathspec list).

For an exact plan, the `## Commit` section names the pathspec list and the path of a message file. The contract must explicitly grant commit authority; it never implies push or deploy. Every VERIFY line must be satisfiable by the edits above it.

## Gauge precondition

Before an executor is spawned, the plan must pass the gauge linter, run from the repo root:

```bash
python3 scripts/plan-gauge-lint.py <plan> --contract <brief|exact> --repo-root <repo>
```

It must exit 0. The spawn gate `hooks/gauge-gate-executor-spawn.sh` (a PreToolUse hook on `Task|Agent`, registered in `hooks/hooks.json`) runs the selected contract linter on the plan named by the executor prompt's first line and blocks any executor spawn whose plan fails it, or whose plan file is missing. A contract/gauge defect counts against the main integrator, never the executor.

Every refusal is itself a verdict. Before it prints the block decision, the gate writes one register row through `scripts/pattern-f-verdict.sh` with `--role gate --kind gate --verdict FAIL`, `--commit none`, and the refusal reason (the linter's GAUGE lines) as the note, into `$INTERSPECT_DB`, else `$CLAUDE_PROJECT_DIR/.clavain/interspect/interspect.db`, else that path under the repo named by the prompt's `REPO:` line. A failed write changes only stderr, and the write is bounded to fifteen seconds so a slow or locked register cannot time the hook out: the gate never fails open in order to record.

## Executor prompt

The prompt starts with these three marker lines; the spawn gate keys on them and selects the corresponding lint contract:

```
PATTERN-F EXECUTOR PLAN: <plan path>
PATTERN-F EXECUTOR CONTRACT: <brief|exact>
REPO: <repo path>
You are the resolved <routine-execution|deep-execution> executor. Read the <brief|exact> contract at <plan path>. Stay within its scope, constraints, and authority. For a brief, own reconnaissance, implementation, and the test loop needed to satisfy its acceptance criteria. For exact, apply its prescribed mechanics verbatim. Never push or deploy unless Authority explicitly permits it. Return only a bounded packet: diff or commit, checks run with outcomes, failures, and unresolved questions.
```

## Validator prompt

The validator is dispatched only after the executor reports, with the producer identity passed to routing. `<REF>` is the commit or working-tree reference and `<REPORT>` is the bounded packet. The prompt is:

```
You are the resolved validation executor, and your resolved model must differ from the producer. Read the contract at <plan path> and the executor packet below. In <repo path> at <REF>, replay its Verification and judge only against its frozen Acceptance Criteria: output line 1 `VERDICT: PASS` or `VERDICT: FAIL`, line 2 `CRITERION: <the failing criterion, or none>`. Then output `BEYOND THE GAUGE:` with bullets for real defects or risks the replay did not check (`- none` allowed). Never restate the contract; never fix anything. Executor packet: <REPORT>
```

### Named outputs

The validator's report has three named outputs, in this order:

1. `VERDICT: PASS|FAIL` (line 1): the result of replaying the plan's VERIFY block at the executor's commit.
2. `CRITERION: <failing VERIFY line or none>` (line 2): the failing VERIFY line quoted verbatim when the verdict is FAIL, otherwise `none`.
3. `BEYOND THE GAUGE:`: the second channel. A bullet list of real defects or risks in the change that the VERIFY block did not check; `- none` is allowed and means the validator looked and found nothing.

The replay (lines 1 and 2) is expected to add no information when the executor already ran the same block and reported it honestly; it exists so the verdict rests on a second run rather than on the executor's word. The second channel is where the validator earns its cost: in goal 1b53da77, five of five replays passed and all six defects found came from the second channel.

## Two strikes

When the executor reports a defect, the orchestrator fixes the plan (never the repo) and re-spawns once; when the validator rejects, the same. When the executor fails a plan twice, or the validator rejects twice, the item goes back to the orchestrator, which either fixes the plan or takes the item frontier-in-the-loop and says so in its report. Never loop cheap retries.

## Verdict register (mandatory)

If a verdict is not in the register, it did not happen. After the validator reports, the orchestrator records every verdict with `scripts/pattern-f-verdict.sh`, using the same `--session` for every row of the run and the live register as `--db` (resolution: `--db`, else `$INTERSPECT_DB`, else `.clavain/interspect/interspect.db` under the Clavain checkout the script lives in, which is not the run's repo when Clavain runs from the plugin cache; pass `--db` explicitly). The rows:

One row for the executor's VERIFY run (kind `replay`):

```bash
bash scripts/pattern-f-verdict.sh --session <id> --plan <plan path> --commit <hash> --role executor --kind replay --verdict PASS|FAIL [--criterion "<failing VERIFY line>"] --goal <goal id> --db <db>
```

One row for the validator's replay (kind `replay`):

```bash
bash scripts/pattern-f-verdict.sh --session <id> --plan <plan path> --commit <hash> --role validator --kind replay --verdict PASS|FAIL [--criterion "<failing VERIFY line>"] --goal <goal id> --db <db>
```

One row per BEYOND THE GAUGE bullet that names a concrete defect (kind `independent`; independent rows carry `--verdict FAIL` and the finding in `--note`):

```bash
bash scripts/pattern-f-verdict.sh --session <id> --plan <plan path> --commit <hash> --role validator --kind independent --verdict FAIL --note "<the bullet>" --goal <goal id> --db <db>
```

Read the rows back:

```bash
bash scripts/pattern-f-verdict.sh --list --session <id> --db <db>
```

The script checks every write with a nonce read-back; when the write is not visible it exits non-zero (4) and says so. Report that loudly; do not retry more than once.

A third kind, `gate`, is written only by the spawn gate (see Gauge precondition), never by the orchestrator. Notes and criteria are stored verbatim except for interspect's secret redaction, which still runs on every row: the sanitizer refuses a context that contains any of six injection-like phrases, so when the plain context would be refused the script stores the note and the criterion base64-encoded and marks the row with `note_enc: "b64"`; `--list` decodes the note (the criterion is not among its eight columns; read it from the context with `json_extract`). When even the encoded context is refused, the script exits 5 and writes nothing. `--list` prints one tab-separated line per row (ts, session, role, kind, verdict, plan, commit, note) with any tab or newline inside a note flattened to a space, so its output is safe to split.

## Orchestrator report

The orchestrator's last message is a JSON object on one line, nothing after it, with these keys:

- `pilot`
- `plan_path`
- `lint_rc`
- `executor_commit`
- `executor_strikes`
- `validator_verdict`
- `validator_strikes`
- `beyond_gauge` (list of strings)
- `register_rows` (integer written)
- `register_rc`
- `notes` (string)
