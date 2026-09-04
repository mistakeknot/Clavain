# Pattern F contracts (offload execution)

These contracts apply when a plan is executed by a fresh-context executor subagent with a separate validator subagent: the offload shape of the routing doctrine in `commands/model-routing.md`, where Fable plans, Sonnet executes, and Opus validates against the plan's frozen criteria. They do not apply to the small-task lane of that doctrine (rule 4: a task under about thirty minutes skips the pipeline and one model runs it end-to-end). The design is in `docs/brainstorms/2026-09-03-main-thread-offload-pattern-f.md`.

## Roles

**Orchestrator** (frontier tier, Fable). Writes ONE execution-grade plan file, lints it, spawns the executor, spawns the validator after the executor reports, records both verdicts in the register, and reports. It never edits repo files itself and never runs the test suite itself.

**Executor** (Sonnet: `subagent_type: "general-purpose"`, `model: "sonnet"`). Applies the plan verbatim: checks the preconditions, applies every edit, runs the VERIFY block capturing each command's exit code directly, and commits with the plan's message file and pathspec only when every VERIFY line passes. It never expands scope, never runs `git add -A`, never pushes, and never commits over a defect: when the plan cannot be applied as written it stops and reports the exact defect.

**Validator** (Opus: `subagent_type: "general-purpose"`, `model: "opus"`, spawned only after the executor reports). Re-runs the plan's VERIFY block at the executor's commit and judges ONLY against the plan's frozen criteria, then reports what the gauge did not check. It never restates the plan and never fixes anything.

## Plan grammar (what the gauge linter reads)

The linter reads the edit pairs, the `Create` blocks, and the verify fences below and nothing else. It has no section awareness: the Preconditions and Commit sections, pathspecs, and the trailer are outside its reach only because they are not edit pairs, `Create` blocks, or verify fences, and it finds verify steps by a heuristic on the prose near a fence, not by the heading. A new file's complete content enters the dry run exactly as an edit's replacement text does, so a verify that forbids text a `Create` block writes fails the gauge (GAUGE001). Everything outside its reach is the orchestrator's to check by hand.

- Each edit to an existing file: a line naming the file in backticks and ending with a colon (In relative/path:), then a line reading old_string: followed by a fenced block with the exact current text, then a line reading new_string: followed by a fenced block with the replacement. New files: a line reading Create relative/path with: (the path in backticks) followed by one fenced block holding the COMPLETE file content.
- Each verify step: a heading `### Verify <task>` followed by ONE fenced `bash` block holding the commands (run from REPO PATH), then a prose line starting `Expected:` stating the observable result. Say "prints NOTHING" or "exit 1" ONLY when that is literally true (the linter treats those as zero-output claims and checks them against your own edits). For a command that must succeed, write `Expected: exit 0`.
- Sections in order: `## Preconditions` (one fenced bash block, must all exit 0), `## Task N` blocks with edits and their `### Verify` steps, `## Commit` (message file path + pathspec list).

The `## Commit` section names the pathspec list and the path of a message file the orchestrator writes with printf (never a heredoc inside a quoted argument); the message file's last line is exactly `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Every VERIFY line must be satisfiable by the edits above it.

## Gauge precondition

Before an executor is spawned, the plan must pass the gauge linter, run from the repo root:

```bash
python3 scripts/plan-gauge-lint.py <plan> --repo-root <repo>
```

It must exit 0. The spawn gate `hooks/gauge-gate-executor-spawn.sh` (a PreToolUse hook on `Task|Agent`, registered in `hooks/hooks.json`) runs the linter on the plan named by the executor prompt's first line and blocks any executor spawn whose plan fails it, or whose plan file is missing. A gauge defect counts against the plan author, never the executor: a VERIFY line that cannot pass as written is the orchestrator's defect.

Every refusal is itself a verdict. Before it prints the block decision, the gate writes one register row through `scripts/pattern-f-verdict.sh` with `--role gate --kind gate --verdict FAIL`, `--commit none`, and the refusal reason (the linter's GAUGE lines) as the note, into `$INTERSPECT_DB`, else `$CLAUDE_PROJECT_DIR/.clavain/interspect/interspect.db`, else that path under the repo named by the prompt's `REPO:` line. A failed write changes only stderr: the gate never fails open in order to record.

## Executor prompt

The executor is an Agent subagent (`subagent_type: "general-purpose"`, `model: "sonnet"`). Its prompt STARTS with the two marker lines below, both absolute paths; the spawn gate keys on them. The prompt is exactly:

```
PATTERN-F EXECUTOR PLAN: <plan path>
REPO: <repo path>
You are a Pattern F executor. Apply the plan at <plan path> to the repo at <repo path> verbatim. Do not expand scope. If the plan cannot be applied as written (a path is missing, a VERIFY line cannot pass as written, a precondition is false), stop, do not commit, and report the exact defect. Otherwise apply every edit, run the VERIFY block capturing each command's exit code directly (rc=$?, never through a pipe), and if all VERIFY lines pass commit with the plan's commit message file and pathspec (git commit -F <msg file> -- <paths>), never `git add -A`, never push. Report: the commit hash (or NO COMMIT and the defect), and the VERIFY output verbatim.
```

## Validator prompt

The validator is an Agent subagent (`subagent_type: "general-purpose"`, `model: "opus"`), spawned only after the executor reports. `<HASH>` is the executor's commit and `<REPORT>` is the executor's report pasted whole. The prompt is exactly:

```
You are a Pattern F validator. Read the plan at <plan path> and the executor report below. In the repo at <repo path>, at commit <HASH>, re-run the plan's VERIFY block yourself and judge ONLY against the plan's frozen criteria: output line 1 `VERDICT: PASS` or `VERDICT: FAIL`, line 2 `CRITERION: <the failing VERIFY line quoted, or none>`. Then output a section headed `BEYOND THE GAUGE:` listing, as bullets, real defects or risks in the change that the VERIFY block did not check (empty list allowed, say `- none`). Never restate the plan; never fix anything. Executor report: <REPORT>
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

A third kind, `gate`, is written only by the spawn gate (see Gauge precondition), never by the orchestrator. Notes and criteria are stored byte-for-byte: interspect's sanitizer refuses a context that contains any of six injection-like phrases, so when the plain context would be refused the script stores the note and the criterion base64-encoded and marks the row with `note_enc: "b64"`; `--list` decodes them. When even the encoded context is refused, the script exits 5 and writes nothing. `--list` prints one tab-separated line per row (ts, session, role, kind, verdict, plan, commit, note) with any tab or newline inside a note flattened to a space, so its output is safe to split.

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
