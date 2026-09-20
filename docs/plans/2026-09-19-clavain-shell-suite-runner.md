---
artifact_type: plan
bead: Sylveste-psey
stage: design
requirements: [F1, F2, F3, F4]
---
# Clavain shell-suite runner implementation plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Bead:** Sylveste-psey

**Goal:** Restore useful shell-test feedback and give both the shell suite and the relocated `ic` tests an independently scheduled, observable home on zklw.

**Architecture:** Repair the installer fixture and classify the structural tests that need `ic`. Run committed snapshots of Clavain and its source dependencies in a fresh temporary directory from the existing rig-health scheduler; preserve its status writer, watchdog, SessionStart reader, and daily cadence. Share a small result summarizer between the repaired Actions step and the scheduled checks so skips cannot become passes.

**Tech stack:** Bash 3.2-compatible orchestration, bats 1.13, Python 3.12+, pytest/uv, Git, existing GNU `timeout`/`gtimeout`, launchd and systemd user services.

**Requirements contract:** [PRD](../prds/2026-09-19-clavain-shell-suite-runner.md), especially its corrected F1 and F3. The [brainstorm](../brainstorms/2026-09-19-clavain-shell-suite-runner-brainstorm.md) supplies the two-lane decision, but its “eight real” diagnosis is superseded. The PRD's opening Solution paragraph also retains that obsolete number; the corrected feature criteria control.

**Prior learnings:** `Sylveste-ytm` repaired a baseline without giving it a runner. `dotfiles/common/.local/bin/rig-health-check.sh` supplies the `guard-tests` tally, `intercore-tests` designation, `bound`, and `ALL_CHECKS` precedents. `Sylveste/ops/rig-self-checks.md` requires real scheduler fault injection and explains why manual writes cannot replace scheduled verdicts. These are references, not files to edit in Sylveste.

## Must-Haves

**Truths**

- The six installer failures become passing tests on both machines without changing the production instruction-template requirement.
- An `ic`-less structural run executes the Zaka rejection test, explicitly deselects 28 dependent cases, and explains the missing dependency. A designated runner missing `ic` fails.
- zklw runs both suites daily against fresh committed snapshots, independently of developer checkout dirtiness.
- An undesignated machine writes two quiet `skip` statuses; a designated machine missing a required tool writes a named failure.
- Failed assertions, missing/truncated results, stale source, and timeouts cannot produce a current passing verdict.
- Summaries distinguish passed, failed, and skipped cases and enumerate skip reasons. Healthy subset coverage is never advertised as full coverage.
- The new checks finish within their bounds, and an actual complete health run demonstrates that existing checks still receive fresh results inside 2,400 seconds.

**Artifacts**

- Clavain `tests/shell/test_codex_installer.bats`: complete instruction-rendering fixture and a real missing-template negative control.
- Clavain `tests/structural/test_claude_usage.py`, `tests/structural/conftest.py`, `tests/pyproject.toml`: `requires_ic`, dependency-aware collection, and `--require-ic`.
- Clavain `scripts/suite-report.py`: validated TAP/JUnit counts, reasons, failure names, and JSON/text summaries; `tests/structural/test_suite_report.py` verifies its contract.
- Clavain `.github/workflows/test.yml`: existing Tier 1 reaches existing Tier 2, a 15-minute job ceiling, and direct shell exit capture with a visible summary.
- Dotfiles `common/.local/bin/rig-health-check.sh`: `clavain-shell` and `clavain-structural`, bounded clean snapshots, explicit overrides, and watchdog membership.
- Dotfiles `server/.config/clavain/test-machine` plus its `install-server.sh` link: tracked designation of zklw; no Mac designation.
- Dotfiles `common/.claude/hooks/report-rig-health.py`: both checks in `EXPECTED`, including on undesignated hosts where a fresh skip is the expected record.
- Dotfiles `common/.claude/hooks/tests/test-rig-clavain-suites.sh` and `docs/rig-clavain-suites.md`: behavior tests and scheduler drill/runbook.

**Key Links**

- Installer fixture → shared template, host adapter registry, Codex adapter, routing policy → real `sync-agent-instructions.py` → unchanged installer validation.
- `requires_ic` collection → visible deselection → designated `--require-ic` execution → JUnit proof that all 29 accounting-file cases passed.
- Deployed marker → preflight → source HEAD capture → clean detached clones → real test exit status and complete result grammar → existing `write_status`.
- Daily scheduler → deployed harness → `ALL_CHECKS`/watchdog → authoritative health records → `EXPECTED`/SessionStart reporting.
- Clavain fixes and reporting land first → dotfiles integration lands unarmed → zklw verification → designation/deployment → scheduler acceptance.

## Decisions and boundaries

### Suite scope, timing, and ownership

Run the **whole structural suite** with `cd tests && uv run pytest structural/ -v --tb=short --require-ic --junitxml=...`. It tests the same source as the shell lane, catches collection/marker mistakes, and avoids maintaining a second positive selection that can silently omit new dependent cases. Require the accounting module's current 29 cases, including all 28 relocated cases, to appear as passing JUnit cases; a mere exit 0 is insufficient. The structural cap is 300 seconds. Its actual designated-host duration is an execution measurement, not established by the brief. If the full suite cannot pass within that budget, stop for scope/budget review; do not silently narrow it to 28 tests.

The **five-minute Actions ceiling is no longer defensible as a planning assumption**. The last green job used 268 of 300 seconds at 830 cases, leaving 32 seconds. There are now 872 cases, and the Mac's 521-second measurement is a different host, not an Actions benchmark. Change only the existing job's `timeout-minutes` to **15**, a provisional bound with room for setup, structural tests, and shell tests. Acceptance needs an actual main-branch job whose Tier 2 completes within that cap. Do not add steps, actions, toolchain builds, checkouts, or Linux triggers; preserve the separate smoke job.

Use a new **Clavain-specific designation**, `~/.config/clavain/test-machine`, deployed from `dotfiles/server/.config/clavain/test-machine`. Both machines already carry the Intercore build marker, so reusing it would wrongly designate the Mac. An absent marker means both checks write `skip` before checking tools or source directories. A present but unreadable/invalid marker, including a broken deployed symlink, means `fail`, not skip. Its only nonblank, non-comment line is `clavain-suite-runner-v1`; include comments naming zklw and its required capabilities. This content identifies the marker format, while server-only deployment designates the host. Loss of the deployed marker is a deployment discrepancy; do not treat it as intentional host reassignment.

### Physical execution and source freshness

Use **fresh independent local clones on every run**, not the developer checkout, a persistent checkout that can lag, or worktrees sharing its Git administration. The disposable layout is:

```text
<run-root>/tree/os/Clavain
<run-root>/tree/core/intercore
<run-root>/tree/interverse/interspect
<run-root>/tree/interverse/interstat
<run-root>/artifacts/             # outside every tested tree
<run-root>/venv/                  # UV_PROJECT_ENVIRONMENT
```

Capture each source repository's committed HEAD once. Clone with `git -c core.hooksPath=/dev/null clone --no-local --no-checkout SOURCE DEST`, then `git -C DEST -c core.hooksPath=/dev/null checkout --detach CAPTURED_SHA`. Do not use `--shared`, alternates, hard links, archives without Git metadata, or symlinks to a dirty Intercore tree. Intercore's canary guard rejects tracked **and untracked** dirt; isolating only Clavain is insufficient. Interspect's tests load sibling source, and the existing workflow explicitly carries Interstat; retain their paths and record their source SHAs too. Missing required sibling source is a named preflight failure, not an opportunistic test skip.

Default source roots come from `~/projects/Sylveste/{os/Clavain,core/intercore,interverse/interspect,interverse/interstat}`. Never copy the Sylveste superproject or commit files there. A task-specific source override must not silently fall back to these defaults.

This lane tests **the committed HEAD available in the named local source**, not uncommitted edits or an asserted latest GitHub commit. Dirty source files are ignored, recorded as excluded input, and untouched. Do not fetch/reset/pull the developer checkout. Each subsequent run reclones its newly captured HEAD; there is no retained old test tree to reuse on preparation failure. Record captured source SHAs and re-read source HEADs at completion. If any moved, retain the result for the captured tuple but change an otherwise passing status to `warn: source advanced during run; newer HEAD not tested`; a failed result stays failed. An unreadable final HEAD is a failure to establish freshness, never equality. The next scheduled run tests the new tuple. Remote-main freshness is explicitly outside this local-source claim.

Verify clean snapshots before testing and after each lane. Run structural first, then shell. A test that changes tracked input fails the relevant check and prevents the next lane from claiming a clean run. Keep Python environments, logs, JUnit, wrapper binaries, and other runner-generated files outside the snapshots. Preserve the runtime canary's production guard unchanged.

### Bounds and placement

Place the new block immediately after watchdog/helper initialization and **before `guard-tests`**, so it cannot sit behind the existing 900-second Intercore bound and the sum of guard suite bounds. Keep the 2,400-second run ceiling and systemd's existing 2,700-second `TimeoutStartSec` unchanged.

| Phase | Maximum | Behavior at limit |
|---|---:|---|
| Preflight and all snapshot preparation together | 120s | Fail both checks with preparation diagnostic |
| Entire structural invocation, including uv environment preparation | 300s | Fail structural; keep partial log; shell may still run if snapshots are clean |
| Entire recursive bats invocation | 900s | Fail shell; name timeout and incomplete TAP |
| Result finalization, source recheck, snapshot removal | 30s | Fail affected checks if identity/finalization cannot finish; retain cleanup diagnostic |

The nominal sum is 1,350 seconds, leaving 1,050 seconds for existing checks; allow the existing five-second TERM→KILL grace in the measured total. Clamp each bound to the remaining overall deadline, reserving finalization time. On a designated host require working `timeout`/`gtimeout`; do not take `bound()`'s unbounded fallback for these new heavy checks. Statuses for exhausted budget must say not executed/partial and must not invent zero passed cases. Actual full-run timing and freshness of older checks are rollout gates: early placement alone does not prove non-starvation.

Respect `RIG_HEALTH_NESTED`: nested fixture runs must not recursively launch these suites or stamp their authoritative statuses. Add `RIG_CLAVAIN_CHECKS_ONLY=1` solely for isolated tests/drills of this real block; clearly label the invocation as partial, return after it, and never set it in the deployed daily unit. A normal default run remains the acceptance proof for total runtime and reachability.

### Dependency overrides and skip policy

New overrides must be exercised against the real block, never a copied implementation:

| Variable | Contract |
|---|---|
| `RIG_CLAVAIN_MARKER` | Exact marker path; absent path forces undesignated behavior |
| `RIG_CLAVAIN_DIR` | Exact Clavain source Git repository |
| `RIG_CLAVAIN_INTERCORE_DIR` | Exact Intercore source for this lane; avoid altering unrelated checks through `RIG_INTERCORE_DIR` |
| `RIG_CLAVAIN_INTERSPECT_DIR`, `RIG_CLAVAIN_INTERSTAT_DIR` | Exact companion sources |
| `RIG_CLAVAIN_RUN_ROOT` | Owned, otherwise-empty disposable root; reject a live/source checkout and paths outside the created run subtree during cleanup |
| `RIG_CLAVAIN_BATS_BIN`, `RIG_CLAVAIN_YQ_BIN`, `RIG_CLAVAIN_GAWK_BIN`, `RIG_CLAVAIN_IC_BIN` | Exact executable selection; an explicit nonexistent/nonexecutable value fails without PATH fallback |
| `RIG_CLAVAIN_BATS_LIBS` | Exact helper root containing readable `bats-support/load.bash` and `bats-assert/load.bash` |
| `RIG_CLAVAIN_SHELL_SECONDS`, `RIG_CLAVAIN_STRUCTURAL_SECONDS` | Positive lower test/drill bounds; reject values above 900/300 or malformed values |
| `RIG_HEALTH_DIR` | Existing isolated status destination for drills |

Validate actual tool execution, not just file existence. In addition to bats, yq, gawk, ic and both bats libraries, require Git, jq, Go, uv/Python 3.12+, sqlite3, and the timeout mechanism used by the real suites. Preserve the existing helper search order when resolving defaults. The selected binaries must also be the binaries the children execute: build a per-run wrapper/symlink bin directory placed first on the child PATH. Give `tests/shell/test_helper.bash` an explicit `CLAVAIN_BATS_LIBS` override which is validated and loaded, with the existing optional autodetection retained for ordinary local runs. An explicit invalid helper root must fail rather than fall back. Missing shell-only prerequisites fail `clavain-shell`; missing `ic` fails both lanes; a valid structural lane may still run when only a shell prerequisite is missing.

The shell lane declares an initial **maximum expected skip count of six**, bounded by **five `interphase not installed`** and **one `Intercore calibration candidate not available`**. These are allowances, not required skips. The source of `tests/shell/shims.bats` hard-codes `/root/projects/interphase` in five cases; installed interphase on a user's host does not prove those cases execute. Do not create that root path or rewrite those tests in this scope. The calibration case references a temporary candidate binary. Both omissions remain visible.

The designated zklw floor allows **zero yq skips and zero gawk skips**. A count above six, a reason above its allowance, or any new reason yields at least `warn`, even if the suite exits 0. Missing mandatory tools fail at preflight. Unknown/malformed results or nonzero suite exits fail. Structural allows zero skips and zero deselections on the designated host. Exceeding that floor prevents arming/acceptance. Actions uses a zero-skip reporting threshold and emits visible warnings for withheld coverage; those warnings do not erase bats failures or expand Actions dependencies.

Record the supplied Mac observation as historical evidence, not a permanent pass count: 872 TAP cases, 862 `ok` lines including 57 skips, 10 `not ok`, exit 1, 521s. Exclusive counts are therefore **805 passed, 10 failed, 57 skipped**. Its skip histogram is 41 yq, 10 gawk, five interphase, one calibration candidate. New tests will increase the TAP plan; never hard-code 872 as the future suite length.

## Ordered tasks

Commands below are for implementation, not claims of work performed while writing this plan. Set `CLAVAIN_SRC` to the independent Clavain repository and `DOTFILES_SRC` to the independent dotfiles repository. Use committed disposable clones for whole-suite commands. Capture exit status immediately, outside pipes. Each task is one logical commit on the repository's `main`, after its tests and required review; stage only listed files. This plan-only delivery does not commit, push, deploy, claim migration work, or create a companion execution manifest.

### Task 1: Repair the complete installer fixture contract (F1)

**Depends on:** none.

**Files:** Modify `Clavain/tests/shell/test_codex_installer.bats`. Read, do not modify, `scripts/install-codex.sh`, `scripts/sync-agent-instructions.py`, `scripts/sync-codex-instructions.py`, and `config/{agent-instructions.md,host-adapters.json,routing.yaml,codex-instructions.md}`.

**Test first:** Preserve the six existing positive failures as the regression tests. Correct the negative test to remove `agent-instructions.md`, not `codex-instructions.md`; assert the shared template exists before removing it. Verify refusal occurs before links/config writes. This prevents the old negative test from passing merely because the fixture was already broken.

Run at the recorded pre-fix commit in a disposable checkout on **each** host:

```bash
bats tests/shell/test_codex_installer.bats > installer-before.tap 2>&1
installer_rc=$?
printf 'exit=%s\n' "$installer_rc"
```

Expected: nonzero, with the supplied six positives failing on `Missing instruction template: .../config/agent-instructions.md`. Retain the exact revision and TAP. If that cause no longer reproduces, stop and reconcile the baseline rather than transplant the old count.

**Implementation:** `_write_stub_clavain_source` must copy the real shared template, host registry, routing policy, and existing Codex adapter. It must also copy `scripts/sync-codex-instructions.py`: the real renderer resolves that helper from **the supplied source directory**, not its own script directory. Copying only the first missing template merely moves the failure. Use this fixture code in place of the old single-adapter copy:

```bash
local repo_root="$BATS_TEST_DIRNAME/../.." fixture_file
for fixture_file in agent-instructions.md host-adapters.json routing.yaml codex-instructions.md; do
    cp -f "$repo_root/config/$fixture_file" "$SOURCE_DIR/config/$fixture_file"
done
cp -f "$repo_root/scripts/sync-codex-instructions.py" \
    "$SOURCE_DIR/scripts/sync-codex-instructions.py"
```

Keep the fixture's stub manifest/MCP contents and real renderer. Do not bypass rendering, mock successful installation, or remove the installer's guard.

```bash
bats tests/shell/test_codex_installer.bats
```

Expected: every installer case passes on both machines, including removal of the now-present shared template. Then, from a clean committed Clavain clone with clean Intercore at `../../core/intercore`:

```bash
bats tests/shell/test_runtime_evidence_canary.bats
```

Expected: exit 0; both substantive source/installed canaries execute rather than skip. No runtime-canary source change. Commit: `test: complete Codex installer instruction fixture`.

<verify>
- run: `bats tests/shell/test_codex_installer.bats`
  expect: exit 0
- run: `bats tests/shell/test_runtime_evidence_canary.bats`
  expect: exit 0
</verify>

### Task 2: Make absent-ic selection explicit and testable (F2)

**Depends on:** Task 1 for the landing sequence.

**Files:** Modify `Clavain/tests/structural/test_claude_usage.py`, `Clavain/tests/structural/conftest.py`, `Clavain/tests/pyproject.toml`; create `Clavain/tests/structural/test_ic_selection.py`.

**Test first:** Add subprocess collection tests covering present `ic`, genuinely absent `ic`, explicit `--require-ic` with absent `ic`, and a present executable that exits nonzero. Use a filtered temporary PATH with symlinks to required non-ic tools and invoke the already-resolved Python interpreter directly; assert `shutil.which('ic') is None` inside the child for the absent case. Do not use an `ic` stub to claim the 29 real tests pass. Collect the real accounting file and assert exactly 28 expanded node IDs bear `requires_ic`, and the Zaka rejection case does not. Test terminal explanation and the deselection hook, including a mixed run where unrelated tests remain selected.

```bash
cd "$CLAVAIN_SRC/tests"
uv run pytest structural/test_ic_selection.py -v
```

Expected before implementation: failures for missing marker/selection/reporting behavior. Afterwards: all selection tests pass.

**Implementation:** Register `requires_ic` in pytest configuration; decorate the dependent test functions explicitly, including their parameterized cases. Do not mark the module or the Zaka test. Add `--require-ic` to the existing structural conftest. In collection, discover `ic` with `shutil.which`. If absent in default mode, remove only marked items, call `config.hook.pytest_deselected(items=held_back)`, and retain the count for `pytest_terminal_summary`, which prints `28 tests deselected: requires_ic; ic executable not found on PATH; covered by zklw clavain-structural`. With `--require-ic`, absence raises a pytest usage/collection error instead. A present but broken ic stays selected and fails normally. Existing test assertions and production metering stay unchanged.

```bash
uv run pytest structural/test_claude_usage.py -v --require-ic
uv run pytest structural/ -v --tb=short --require-ic
```

Expected with real ic: 29/29 accounting cases pass, no deselection; then the full structural suite passes. The new subprocess regression must prove actual no-ic accounting execution yields `1 passed, 28 deselected`, the explanation, and exit 0. Capture its child transcript; do not substitute collection-only output for this assertion. Commit: `test: report structural tests requiring Intercore`.

<verify>
- run: `cd tests && uv run pytest structural/test_ic_selection.py -v`
  expect: exit 0
- run: `cd tests && uv run pytest structural/test_claude_usage.py -v --require-ic`
  expect: contains "29 passed"
</verify>

### Task 3: Count real results and repair the existing workflow (F2, F4)

**Depends on:** Tasks 1–2.

**Files:** Create `Clavain/scripts/suite-report.py`, `Clavain/tests/structural/test_suite_report.py`; modify `Clavain/tests/shell/test_helper.bash`, `.github/workflows/test.yml`; create `Clavain/tests/shell/test_helper_override.bats`.

**Test first:** Exercise the summarizer CLI with complete TAP, mixed pass/fail/skip, the 41/10/5/1 skip histogram, a nonzero exit despite all `ok` lines, bailout, duplicate/missing test numbers, truncated or empty TAP, and `1..0`. Verify `ok ... # skip ...` is excluded from passed. For JUnit, test failures/errors/skips, malformed/empty XML, no accounting file, and 28 versus 29 accounting cases. The required module check must reject skipped/failed cases and verify the unmarked Zaka case plus the 28 others. Test case identities, not an unrelated set of 29 tests. Add a bats test where an explicit invalid helper directory fails despite available fallback helpers, and a valid explicit directory loads both libraries. Create tiny temporary helper libraries exporting distinct sentinels for this loader test, so it also runs on the Mac without installing packages; actual assertion-library compatibility is established by the real zklw suite. Ordinary autodetection remains optional.

```bash
cd "$CLAVAIN_SRC/tests"
uv run pytest structural/test_suite_report.py -v
cd ..
bats tests/shell/test_helper_override.bats
```

Expected before implementation: failures for the missing CLI and ignored explicit override; afterwards: all pass.

**Implementation:** Define this stable CLI:

```text
python3 scripts/suite-report.py --format tap|junit --input PATH
  --exit-code INTEGER --max-skipped INTEGER --output-json PATH
  [--shell-skip-policy] [--require-claude-usage]
```

Write JSON fields `status`, `summary`, `complete`, `planned`, `observed`, `passed`, `failed`, `skipped`, `skip_reasons`, `failures`, and `exit_code`; print the same human summary to stdout. Always print `passed: P   failed: F   skipped: S`, followed by the allowed skip maximum and any reason-policy violation; unknown counts say `unavailable`, not zero. `passed + failed + skipped == observed`; errors count as failed. Incomplete output records observed counts as partial and fails. Return 0 for pass, 3 for warn, 1 for fail; input/usage errors also must not appear successful. TAP parsing recognizes bats' actual top-level TAP grammar and directives, preserves diagnostics and failed case names, and validates the plan against records. For JUnit aggregate leaf test cases, not both suite totals and their children. `--require-claude-usage` enforces the Task 2 accounting-module invariant. `--shell-skip-policy` enforces the six-case reason allowances above; absent that option the supplied numeric threshold still reports all reasons. Unexpected failure of the reporter itself fails the caller.

Change the existing Tier 2 `run` body in place; retain its command and directly captured return code:

```bash
tap_file="$RUNNER_TEMP/clavain-shell.tap"
summary_file="$RUNNER_TEMP/clavain-shell-summary.json"
suite_rc=0
bats tests/shell/ --recursive --tap > "$tap_file" 2>&1 || suite_rc=$?
cat "$tap_file"
report_rc=0
python3 scripts/suite-report.py --format tap --input "$tap_file" \
  --exit-code "$suite_rc" --max-skipped 0 --output-json "$summary_file" || report_rc=$?
if [ "$report_rc" -eq 3 ]; then
  echo '::warning::Shell coverage has skipped cases; see counts and reasons above.'
elif [ "$report_rc" -ne 0 ]; then
  exit 1
fi
exit "$suite_rc"
```

Set the existing structural-and-shell job ceiling to 15 minutes. No new Actions steps or dependencies. Tier 1's unchanged command gets the visible selection behavior through conftest. Run the focused tests and a real recursive bats run in a committed clean clone; on zklw require no failures and only the declared omissions. On Mac retain the two known calibration failures and missing-dependency skips; do not call it a green full suite.

Commit: `test: expose suite coverage and restore shell workflow reachability`. An actual main-branch Actions run is verified in Task 6 after authorized push, not inferred here.

<verify>
- run: `cd tests && uv run pytest structural/test_ic_selection.py structural/test_suite_report.py -v`
  expect: exit 0
- run: `bats tests/shell/test_helper_override.bats`
  expect: exit 0
</verify>

### Task 4: Add bounded snapshot execution to rig-health, unarmed (F3, F4)

**Depends on:** Tasks 1–3; their committed Clavain revision must be available on zklw.

**Files:** Modify `dotfiles/common/.local/bin/rig-health-check.sh`; create `dotfiles/common/.claude/hooks/tests/test-rig-clavain-suites.sh`.

**Test first:** In the existing shell-test style, drive the **real harness** with `RIG_CLAVAIN_CHECKS_ONLY=1`, isolated `RIG_HEALTH_DIR`, and throwaway Git sources. Clear inherited `RIG_HEALTH_RUN` in the child when deliberately exercising this block; the checks-only exit prevents it from recursing into guard-tests. Test the nested-suppression branch separately with that variable set. Test absent marker before tool probes, invalid marker, individually missing bats/yq/gawk/ic/helpers, wrong source path, old source without the reporter, dirty original source, snapshot preparation failure, and source advancement. Tiny fake test executables may prove orchestration and result handling in fixtures; label that evidence as fixture-only. Do not replace actual suites in scheduler success acceptance.

Also test complete TAP with a named failed assertion; excessive skips; malformed results; structural JUnit missing any required accounting case; a child that ignores TERM and launches a grandchild; shortened per-lane timeout; exhausted overall budget; nested execution; and cleanup constrained to owned run directories. A timed-out/truncated report must never pass, and no test process may survive its bound. Test `ALL_CHECKS` behavior by forcing the watchdog before the new block can refresh statuses. A fixture nested in guard-tests must suppress expensive recursive integration cases explicitly and tally those skips.

```bash
cd "$DOTFILES_SRC"
/bin/bash common/.claude/hooks/tests/test-rig-clavain-suites.sh
```

Expected red-before implementation: missing statuses/overrides and failing assertions. Expected after: `failed: 0`, with any deliberately nested skips reported separately.

**Implementation:** Add a Bash 3.2-compatible block using indexed arrays, `while IFS= read -r`, ordinary variables, and the existing `bound`/`write_status`; no `mapfile`, namerefs, associative arrays, or `wait -n`. Implement the designation, overrides, snapshot layout, binary selection, shared preparation deadline, per-lane limits, cleanliness checks, and source recheck described above. Keep all synchronous subprocesses, including Git/npm/tool version queries, within the preparation/finalization deadlines; a collection of individual 120-second bounds is not a 120-second phase.

Call the cloned Clavain reporter, capture its exit separately from the suite, and validate its JSON before invoking the existing writer. Use detail files containing source tuple, working directory, commands, elapsed time, raw exit, totals/reasons, and failing test names with diagnostics. Preserve partial logs on timeout. `write_status` embeds detail before temporary cleanup; save full run artifacts under `~/.local/state/rig-clavain-suites/runs/<start-epoch>-<pid>/` (last seven runs), outside the tested tree. For isolated tests/drills put retained artifacts beneath their isolated `RIG_HEALTH_DIR` instead, so they cannot prune real evidence. Only prune this runner's own prior directories. Failure to write/parse a result is a failure of the check, not a silent omission. Set `FAILED=1` for either failed lane; warnings retain the harness's existing exit convention.

Add both names to `ALL_CHECKS`. At preflight/preparation failure emit both applicable statuses rather than leaving the second one absent. Do not let the structural lane's failure prevent an otherwise runnable shell lane from reporting. Do not remove or modify existing bounds and checks.

```bash
/bin/bash -n common/.local/bin/rig-health-check.sh
/bin/bash common/.claude/hooks/tests/test-rig-clavain-suites.sh
/bin/bash common/.claude/hooks/tests/test-rig-health-bounds.sh
```

Expected: syntax exit 0 on Mac `/bin/bash` 3.2 and Linux; new behavior suite has zero failures; existing bounds suite has zero failures with its platform/nesting skips stated. Commit: `feat: run Clavain suites from bounded clean snapshots`. This commit is unarmed: no designation has been deployed yet.

<verify>
- run: `/bin/bash -n common/.local/bin/rig-health-check.sh`
  expect: exit 0
- run: `/bin/bash common/.claude/hooks/tests/test-rig-clavain-suites.sh`
  expect: exit 0
- run: `/bin/bash common/.claude/hooks/tests/test-rig-health-bounds.sh`
  expect: exit 0
</verify>

### Task 5: Wire designation and the existing reader (F3, F4)

**Depends on:** Task 4 and a real clean-snapshot baseline on zklw at the intended Clavain commit. Use Task 6's pre-arming drill protocol at this point; Task 6's final acceptance follows deployment, so there is no dependency on a deployed marker to establish this baseline.

**Files:** Create `dotfiles/server/.config/clavain/test-machine`, `dotfiles/docs/rig-clavain-suites.md`; modify `dotfiles/install-server.sh`, `dotfiles/common/.claude/hooks/report-rig-health.py`, and `dotfiles/common/.claude/hooks/tests/test-rig-clavain-suites.sh`.

**Test first:** Extend the harness suite to assert that deleting either status is reported as `NEVER`, an aged status is `STALE`, fresh undesignated skips stay quiet on their own, and a failed test's name remains available in detail. Test installer declaration of the server-only marker and absent Mac marker. Record the observer's actual output; a source string alone does not prove the reader reports a missing result. Run `/bin/bash common/.claude/hooks/tests/test-rig-clavain-suites.sh` before editing the reader/installer: expect nonzero because the new checks are not expected and the marker is not declared.

**Implementation:** Add `link server/.config/clavain/test-machine .config/clavain/test-machine` next to the existing Intercore marker link in `install-server.sh`. Add both status names to the reader's `EXPECTED`, since both hosts write a result, including skips. Do not edit scheduler units to set manual authority or duplicate the daily timer. Document default sources, overrides, skip allowance, measured baseline/timing, deployed files, restoration, and the commands in Task 6. The existing Sylveste operations document remains a reference; this runbook lives in dotfiles to keep the landing strictly two-repository.

```bash
cd "$DOTFILES_SRC"
/bin/bash common/.claude/hooks/tests/test-rig-clavain-suites.sh
python3 -m py_compile common/.claude/hooks/report-rig-health.py
```

Expected: no failed assertions and Python syntax success. Before the marker is deployed, run the real snapshot suites through the actual scheduler using a temporary designation override and isolated health destination, as Task 6 describes. Require both lanes to pass within bounds and no unexpected skips before making daily designation live. Commit: `feat: designate zklw for Clavain suite health checks`. A tracked marker and installer line are configuration, not proof of deployment or scheduling.

<verify>
- run: `/bin/bash common/.claude/hooks/tests/test-rig-clavain-suites.sh`
  expect: exit 0
</verify>

### Task 6: Prove both lanes, fault reporting, and restoration (F1–F4)

**Depends on:** Tasks 1–5 for final production acceptance, required independent review, and execution/deployment authority. The pre-arming portion is also Task 5's baseline prerequisite.

**Files:** Update only `dotfiles/docs/rig-clavain-suites.md` with results and evidence locations. Runtime evidence belongs in private per-run directories, not Sylveste source. Use `Sylveste-psey` for execution tracking when the tracker is available; do not create a second migration bead.

**Test first:** Run the fault matrix before arming daily designation. Stage a throwaway Clavain source clone with a **committed** additional bats test `@test "psey forced assertion" { false; }`. A dirty uncommitted injected test is not part of the runner's input and would not test failure propagation. Stage a second committed variant with a sleeping child for the timeout case. Keep both outside live source checkouts.

**Scheduler commands and evidence:** On zklw use transient systemd services to run the installed real harness with the same PATH as the real unit, actual `INVOCATION_ID`, isolated output, and explicit overrides. This representative missing-yq command assumes `DRILL_ROOT` is an absolute private directory containing a regular `test-machine` marker and no file named `missing-yq`:

```bash
systemd-run --user --wait --collect --unit=psey-no-yq \
  --property=Type=oneshot --property=TimeoutStartSec=2700 \
  --setenv="PATH=$HOME/.local/bin:$HOME/.local/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
  --setenv="RIG_HEALTH_DIR=$DRILL_ROOT/no-yq/health" \
  --setenv="RIG_CLAVAIN_MARKER=$DRILL_ROOT/test-machine" \
  --setenv="RIG_CLAVAIN_YQ_BIN=$DRILL_ROOT/missing-yq" \
  --setenv=RIG_CLAVAIN_CHECKS_ONLY=1 \
  "$HOME/.local/bin/rig-health-check.sh"
jq -e '.status == "fail" and (.summary | contains("yq"))' \
  "$DRILL_ROOT/no-yq/health/clavain-shell.json"
```

Expected: service command nonzero for the failed check; jq exits 0. Preserve service/journal evidence before collected units disappear. Repeat separately with the bats and gawk overrides; use the ic override and assert **both** statuses fail mentioning ic. Do not infer one missing-tool branch from another. An absent-marker run with the same unusable tool paths must instead write two skips and perform no suite execution. Clear each override for the subsequent healthy run.

On the Mac, generate a throwaway LaunchAgent plist in `DRILL_ROOT` whose `ProgramArguments` invoke `/bin/bash` and the deployed harness. Its `EnvironmentVariables` carry `RIG_HEALTH_DIR`, `RIG_CLAVAIN_MARKER` pointing to an absent file, and `RIG_CLAVAIN_CHECKS_ONLY=1`; stdout/stderr paths stay in the same private directory. Give it label `com.arouth.psey-clavain-drill`. Do not replace the production LaunchAgent or forge `RIG_RUN_KIND`. Use actual launchd:

```bash
launchctl bootstrap "gui/$(id -u)" "$DRILL_ROOT/com.arouth.psey-clavain-drill.plist"
launchctl kickstart "gui/$(id -u)/com.arouth.psey-clavain-drill"
launchctl print "gui/$(id -u)/com.arouth.psey-clavain-drill"
jq -e '.status == "skip"' "$DRILL_ROOT/mac/health/clavain-shell.json"
jq -e '.status == "skip"' "$DRILL_ROOT/mac/health/clavain-structural.json"
launchctl bootout "gui/$(id -u)/com.arouth.psey-clavain-drill"
```

Wait for process completion/status timestamps before the jq assertions. Expected: both fresh skip records, zero suite invocations, and launchd completion. Then repeat with a temporary marker and an explicitly nonexistent bats path to prove the designated failure branch also executes under macOS Bash 3.2; full Mac-suite success is not a requirement.

For real zklw success, run a transient service with the temporary marker and **no checks-only selector**, using actual installed tools, actual committed sources, and isolated health output. Record the start/end times, every expected status timestamp, source tuple, and elapsed time. Both new checks must pass, the original canaries must execute, all 29 accounting cases must pass, and every older expected harness check must be refreshed before 2,400s. Existing unrelated red checks are recorded and need not be repaired; distinguish their exit contribution from these two checks. If anything is starved, do not deploy the daily marker.

After the authorized narrow deployment, verify actual unit definitions and links, then force the real daily service without overrides:

```bash
systemctl --user cat rig-health.service rig-health.timer
systemctl --user is-enabled rig-health.timer
systemctl --user is-active rig-health.timer
systemctl --user start rig-health.service
systemctl --user show rig-health.service -p Result -p ExecMainStatus -p InvocationID
jq '{status,summary,ran_at_epoch,detail}' "$HOME/.claude/health/clavain-shell.json"
jq '{status,summary,ran_at_epoch,detail}' "$HOME/.claude/health/clavain-structural.json"
```

Expected: timer enabled/active with daily cadence; fresh authoritative new-check passes at the intended source tuple; raw detail reports skips separately. Also retain one subsequent **timer-triggered**, unattended invocation, not only the forced service start. Verify reader output with `python3 "$HOME/.claude/hooks/report-rig-health.py" </dev/null`. A source checkout script run by hand is not this evidence.

After authorized Clavain push, identify the actual main-branch run rather than rerunning an old SHA:

```bash
gh run list --repo mistakeknot/Clavain --workflow test.yml --branch main --limit 5 \
  --json databaseId,headSha,status,conclusion
gh run view "$ACTIONS_RUN_ID" --repo mistakeknot/Clavain --json headSha,jobs
gh run view "$ACTIONS_RUN_ID" --repo mistakeknot/Clavain --log
```

Expected: `headSha` includes Tasks 1–3; Tier 1 finishes with its reported no-ic deselection; `Tier 2 — Shell tests (bats)` starts and concludes success; direct bats exit is 0; summary exposes skips; entire job completes below 900 seconds. A job blocked at the intervening Task attribution step does not meet acceptance and is an escalation, not permission to remove that step.

Repeat the committed assertion and shortened timeout drills under systemd using `RIG_CLAVAIN_DIR` and isolated output; assert failing case name in detail, timeout/nonzero status, no surviving child, and no changed source checkout. Restore all temporary scheduler configuration, remove the temporary LaunchAgent, and confirm the next normal scheduled result. Preserve drill evidence. Commit the runbook evidence update only after facts exist: `docs: record Clavain scheduled suite verification`.

## Acceptance Criteria

The numbered criteria below are the acceptance contract. Commands involving new files are evaluated after implementation. A fixture result cannot substitute for the explicitly required host/scheduler evidence.

1. **F1 — fixture repair is red-before-green on both hosts.** At the retained pre-fix SHA, the installer TAP names the six known failures; at the repaired SHA, every installer case passes. The missing-template negative test removes the shared template and proves refusal before consumer writes. Production installer and canary guards are unchanged.

   ```check
   bats tests/shell/test_codex_installer.bats
   # exit 0 on Clavain and zklw; attach before/after SHA and TAP
   ```

2. **F1/F3 — the two substantive runtime canaries execute successfully from clean snapshots.** Neither is skipped for missing Go, missing Intercore source, or checkout dirt. Dirty live checkout files remain byte-identical before and after the run.

   ```check
   bats tests/shell/test_runtime_evidence_canary.bats
   # exit 0; source and installed workload cases are ok without # skip
   ```

3. **F2 — dependency selection is honest.** Real ic present: 29 accounting cases pass. Real ic absent: one passes, 28 are deselected, the terminal states the number/reason/destination, and exit is 0. `--require-ic` with no ic fails; a present broken ic is not deselected. The expanded marker set contains exactly the 28 dependent cases.

   ```check
   cd tests
   uv run pytest structural/test_ic_selection.py -v
   uv run pytest structural/test_claude_usage.py -v --require-ic
   # exit 0 for both; second reports 29 passed, zero skipped/deselected
   ```

4. **F2 — the existing Actions lane actually reaches and completes Tier 2.** Retain a main-branch run ID/head SHA, successful Tier 1 and Tier 2 conclusions, separate skipped counts, and whole-job elapsed time below 900 seconds. Workflow diff adds no action, checkout, dependency-installation step, or trigger. A green badge or fixture-only workflow test is insufficient.

5. **F3 — committed-source isolation and freshness work.** A dirty live source still produces clean detached snapshots at recorded HEADs; no developer tree/index changes. A committed source advance is captured on the next run. Advancement during a run changes an otherwise passing verdict to a superseded-source warning; failed preparation never reuses an older tree. Deliberately dirty Intercore source is also isolated.

   ```check
   /bin/bash common/.claude/hooks/tests/test-rig-clavain-suites.sh
   # exit 0; retain actual scheduler clean-snapshot and source-advance evidence too
   ```

6. **F3 — designation cannot hide lost tools.** Actual launchd on Mac and systemd on zklw write fresh skips for an absent marker without invoking suites. Actual systemd runs with a present marker and each of bats, yq, gawk, and ic individually forced missing write named failures; ic absence fails both checks. No PATH fallback defeats an explicit override. Invalid/unreadable designation fails. These observations come from scheduler runs, not only shell fixtures.

7. **F3 — assertion failures and infrastructure failures remain red.** A committed throwaway failing bats test yields `clavain-shell=fail`, nonzero execution, and `psey forced assertion` in detail. A scheduled timeout yields fail with partial/incomplete output and no surviving child. Missing reports, malformed results, empty collections, or fewer than the required accounting cases cannot pass.

8. **F3 — both suites fit without starving the harness.** A default full zklw scheduler run, using no checks-only selector, completes under 2,400 seconds and refreshes every original expected harness status plus both new statuses. Preparation ≤120s, structural ≤300s, shell ≤900s, finalization ≤30s, with recorded TERM/KILL grace. Both new names are covered by watchdog “not reached” reporting. Failure of this timing/freshness condition blocks arming.

9. **F3 — daily ownership is demonstrated.** The server-only marker is deployed, the existing timer is enabled and active, a forced production service run succeeds for both checks, and a subsequent unattended timer-triggered run refreshes them again. Each structural report contains 29 passing accounting cases and zero skipped/deselected structural cases. No new Linux Actions scheduling or fleet registration is introduced.

10. **F4 — counts are exclusive and complete.** Valid TAP has `passed + failed + skipped == planned`; incomplete output is explicitly partial and failed. Histograms name every skip reason. The historical 872/862-ok/10-not-ok/57-skip example yields 805 passed, 10 failed, 57 skipped, with 41/10/5/1 reasons. The zklw skip ceiling is six, with no more than five interphase and one calibration omission; extra/new reasons warn and block acceptance until resolved or explicitly reviewed. Structural accepts no skips.

    ```check
    cd tests
    uv run pytest structural/test_suite_report.py -v
    # exit 0; covers counts, policy, malformed TAP/JUnit, and required accounting cohort
    ```

11. **F3/F4 — the existing reader notices missing and stale execution.** Both checks are in `EXPECTED`; a deleted status produces `NEVER`, an expired one produces `STALE`, and fresh undesignated skips alone remain quiet. Authoritative scheduled results cannot be refreshed/replaced by a manual fixture run. Full failure names and skip reasons survive in detail after the temporary clones are removed.

12. **Scope and restoration hold.** Only Clavain and dotfiles receive implementation commits. No production installer requirement, runtime dirty guard, fleet recipe/hash/trigger, `tests/verification-pilot.json`, Sylveste file, or unrelated dirty file changes. No Mac toolchain installation or calibration fix. Temporary services, overrides, and designation are removed after drills; the normal scheduled path is verified again. Shell changes parse and behavior tests pass under Mac `/bin/bash` 3.2.

## Landing order, review, and handoff

1. Land reviewed Tasks 1–3 in **mistakeknot/Clavain**, immutable repository ID **1151593132**, and verify installer results on both hosts. Push only within execution authority; obtain the main-branch Actions evidence. Make that exact committed source available on zklw through the existing Git synchronization path.
2. Land Task 4 in **mistakeknot/dotfiles**, immutable repository ID **1137350173**, unarmed. Deploy only the changed harness/reader paths through existing narrowly scoped links; do not run a broad agent installer. Prove the real zklw baseline and bounds with temporary designation in isolated scheduled runs.
3. Land Task 5 in dotfiles and deploy the server marker only after the clean baseline and full-run budget gates pass. Perform Task 6's production and unattended proofs. Keep `Sylveste-psey` open until all acceptance evidence exists. No files land in the Sylveste repository itself.

Live read-only fleet inspection during planning confirmed Clavain remains `verification-pilot-passed-broader-migration-open`, `triggers: [manual]`, task **mk-ag2s.25**, with pinned verification recipe. Dotfiles remains `pending-inventory`, disabled, task **mk-ag2s.32**. Those campaigns remain outstanding; this plan neither claims completion nor claims/duplicates their migration tasks. Do not edit `scripts/ci-verification.sh`, its pinned `9a4a13c3…` verification-contract digest, the fleet recipe, or registration. Beads access from this planning sandbox failed on the workspace Dolt lock (`openat LOCK: operation not permitted`); no tracker mutation or substitute tracker was created.

Preserve the supplied governed decision: selected package **0.6.318**, policy `/Users/sma/.claude/plugins/cache/interagency-marketplace/clavain/0.6.318/config/routing.yaml`, policy SHA256 **8148151129e30324c18147dec516223b5e672c82dd8cd0c99bd529bd3cc98fea**, profile **default**, role **planning**, profile **planning-astra**, model **gpt-6-astra**, effort **xhigh**, service tier **standard**, classification **difficult-verification**, frontier required, review requirement **existing-gates**. The role was resolved again while authoring and returned the same selection/hash. That is routing evidence, not a new invocation/usage receipt.

Accountable handoff context (embedded here to honor the one-file planning request):

```json
{
  "reasons": ["difficult-verification"],
  "rationale": "The design follows an existing harness, but acceptance requires real launchd/systemd execution, forced missing dependencies, clean committed source snapshots and measured whole-run timing. Fixtures and configuration cannot prove those outcomes.",
  "domain": "test infrastructure",
  "available_models": null,
  "investigation_active": false,
  "handoff": {
    "decisions": ["whole structural suite", "fresh independent committed clones", "server-only designation", "15-minute existing Actions ceiling", "early bounded checks in existing rig-health"],
    "constraints": ["F1 before F3 arming", "two repositories only", "no fleet change", "no new Linux Actions dependency", "Bash 3.2", "no weakened assertions or hidden skips"],
    "verification": ["red-before-green installer on both hosts", "real no-ic collection and execution", "main-branch Actions Tier 2", "actual scheduled fault matrix", "default full-run timing", "subsequent unattended timer run"],
    "escalation": ["baseline premise disproved", "unexpected failures or coverage omissions", "timing or source isolation cannot meet contract", "review or operational blocker", "two capability failures"]
  }
}
```

Execution resolves its role from this context and uses the packaged dispatcher with `CLAVAIN_ROUTING_POLICY` and `CLAVAIN_DECISION_CONTEXT`. Preserve the supplied independent **review-fable / claude-fable-5-1 / high / standard** seat and bind `--producer-identity` from the actual author receipt, not this document's model string. This authoring turn does not claim that independent review occurred. Preserve existing review gates before implementation/landing; use the standing `claude-opus-5` fallback only upon a documented Fable quota limit, with the separate exception policy and both receipts. A permission/authentication failure is not that exception. Keep frontier involvement for deviations and scheduler acceptance.

## Non-claims and escalation

This document is a plan. It does not claim the installer is fixed, the suites pass now, Actions is green, the scheduled lane is deployed, the fleet migration is complete, tests cover uncommitted edits/latest remote main, the Mac executes all assertions, or skipped tests are equivalent to passes. No implementation, test baseline remeasurement, deployment, publication, or independent review was performed during authorship. The quoted measurements are the brief's evidence; proposed limits and future verification outcomes are not measurements.

Stop the affected execution and return with evidence if:

- The recorded installer cause no longer reproduces, the accounting cohort is no longer 29/28, or clean snapshots still trigger runtime-canary dirt failures. A disproved premise needs immediate frontier reassessment.
- The complete zklw suites have unexpected failures, missing helper/tool/source dependencies, extra skips, shared-state side effects, or source mutations. Do not quarantine cases, install new prerequisites without scope, or alter production guards to arm the lane.
- A suite touches another session's live state. In particular, existing sprint tests contain literal `/tmp/sprint-*` cleanup paths; a private clone/HOME is not process or filesystem isolation. If those paths can collide on the designated host, pause scheduled arming and resolve isolation as a separate design decision rather than claiming the fresh clone makes all effects private.
- The structural suite exceeds 300 seconds, shell exceeds 900, full health execution starves existing checks/exceeds 2,400, or Actions still cannot complete below 15 minutes. Return measured phase times; do not silently raise global ceilings, reduce coverage, or add Actions dependencies.
- A new failure lies in the intervening Actions task-attribution step, Mac calibration, fleet automation, or unrelated dirty work. Identify it without expanding this plan or calling the blocked acceptance complete.
- Actual scheduler proof, deployment authority, required independent review, source/tool identity, or tracker access is unavailable. Preserve the open gate and continue only independent authorized work. A bare nonzero exit is not evidence of a quota or capability failure; two demonstrated capability failures require escalation.

If deployed behavior regresses, stop scheduling these new suites by restoring the previous reviewed harness/marker deployment within rollback authority, retain all status/log evidence, and explicitly record the resulting coverage gap. Never manufacture a passing record or relax skip limits as rollback. Restore temporary overrides and verify the ordinary scheduler path before ending execution.
