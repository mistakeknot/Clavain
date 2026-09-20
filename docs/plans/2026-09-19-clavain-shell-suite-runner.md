---
artifact_type: plan
bead: Sylveste-psey
stage: design
requirements: [F1, F2, F3, F4]
revision: 2
---
# Clavain shell-suite runner implementation plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Bead:** Sylveste-psey

**Revision gate:** Supersedes revision 1 (`f75c602`) in response to the independent Fable review (`0858165`). Rewrite the complete plan, extract and seal this revision's acceptance section once, then obtain one clean independent re-review before any implementation. The old seal and DO NOT SHIP review remain evidence; this document does not supersede the review verdict by assertion.

**Accountable revision decision:** The supplied planning dispatch selects `planning-astra`, `gpt-6-astra`, effort `xhigh`, profile `default`, with `existing-gates` review and policy SHA256 `8148151129e30324c18147dec516223b5e672c82dd8cd0c99bd529bd3cc98fea`. Preserve that decision and the actual producer receipt. Local guidance reads and this JSON record are not fresh model/usage receipts.

```json
{
  "reasons": ["difficult-verification"],
  "rationale": "Acceptance requires real launchd/systemd runs, forced dependency loss, proof that tests preserve live locks, measured fresh-clone coverage, and a readable failure among existing rig findings. Fixtures alone cannot establish these outcomes.",
  "domain": "test infrastructure",
  "available_models": null,
  "investigation_active": true
}
```

**Goal:** Restore useful shell-test feedback and give both the shell suite and the relocated `ic` tests an independently scheduled, observable home on zklw.

**Architecture:** Repair the installer fixture and classify the structural tests that need `ic`. Run committed snapshots of Clavain and its source dependencies in a fresh temporary directory from the existing rig-health scheduler; preserve its status writer, watchdog, SessionStart reader, and daily cadence. Share a small result summarizer between the repaired Actions step and the scheduled checks so skips cannot become passes.

**Tech stack:** Bash 3.2-compatible orchestration, bats 1.13, Python 3.12+, pytest/uv, Git, existing GNU `timeout`/`gtimeout`, launchd and systemd user services.

**Requirements contract:** [PRD](../prds/2026-09-19-clavain-shell-suite-runner.md), especially its corrected F1 and F3. The [brainstorm](../brainstorms/2026-09-19-clavain-shell-suite-runner-brainstorm.md) supplies the two-lane decision, but its “eight real” diagnosis is superseded. The PRD's opening Solution paragraph also retains that obsolete number; the corrected feature criteria control.

**Prior learnings:** `Sylveste-ytm` repaired a baseline without giving it a runner. `dotfiles/common/.local/bin/rig-health-check.sh` supplies the `guard-tests` tally, `intercore-tests` designation, `bound`, and `ALL_CHECKS` precedents. `Sylveste/ops/rig-self-checks.md` requires real scheduler fault injection and explains why manual writes cannot replace scheduled verdicts. These are references, not files to edit in Sylveste.

## Must-Haves

**Truths**

- The six installer failures become passing tests on both machines without changing the production instruction-template requirement.
- Tests never remove live sprint locks or execute an ambient candidate from a predictable `/tmp` path; `Sylveste-we1q` blocks arming until this is proved.
- An `ic`-less structural run executes the Zaka rejection test, explicitly deselects 28 dependent cases, and explains the missing dependency. A designated runner missing `ic` fails.
- zklw runs both suites daily against fresh committed snapshots, independently of developer checkout dirtiness.
- An undesignated machine writes two quiet `skip` statuses; a designated machine missing a required tool writes a named failure.
- Failed assertions, missing/truncated results, stale source, and timeouts cannot produce a current passing verdict.
- Summaries distinguish passed, failed, and skipped cases and enumerate skip reasons. Healthy subset coverage is never advertised as full coverage.
- The new checks finish within their bounds, and an actual complete health run demonstrates that existing checks still receive fresh results inside 2,400 seconds.

**Artifacts**

- Clavain `tests/shell/test_codex_installer.bats`: complete instruction-rendering fixture and a real missing-template negative control.
- Clavain `tests/shell/test_lib_sprint.bats`, `tests/shell/test_b3_calibration.bats`, and new `tests/structural/test_shell_suite_safety.py`: remove shared cleanup and implicit candidate execution, preserve claim assertions, and guard against recurrence.
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

## Revision evidence and review dispositions

P0-1 is owned by Task 0 and criterion 13, under existing dependency **Sylveste-we1q**. The 42 sprint cases perform 84 removals of `/tmp/intercore/locks/sprint-claim`. That is the production namespace used by shell and Go claims; neither a private HOME nor TMPDIR changes Intercore's hard-coded lock base. Delete the vestigial cleanup, rather than introducing a production lock override. All five current `sprint_claim` cases already mock both lock operations. The preceding `/tmp/sprint-*-lock-*` legacy globs are not the production hazard. Remove those and the retired discovery-cache cleanup too, without changing their already-delegated cache assertions.

P1-1 adds an explicit snapshot build and a 19-case execution gate. P1-2 makes all checks and verification blocks name a clean working directory. P1-3 uses per-check status and actual reader stdout amid existing red records. P1-4 replaces the zero-skip Actions warning with the measured hosted baseline. P2 coverage is in source/tool identity, timing and side-effect decisions below, the expiring interphase follow-up, and criteria 4, 5, 8, 9, 11 and 13.

**Read-only baseline checked during revision 2 (2026-09-20):** zklw's last `rig-health.service` start/end were 2026-09-19 09:19:36–09:23:00 UTC, about **204 seconds** (the review's approximately 205 seconds is consistent with final status writes). `Result=exit-code`, `ExecMainStatus=1`. The refresh found **11** status JSONs with `status=fail`: `estate-drift`, `estate-workflow-health`, `finding-age`, `guard-tests`, `hook-integrity`, `ic-provenance`, `job-outcomes`, `marketplace-divergence`, `peer-agreement`, `publish-drift`, `unit-overrides`. The earlier review observed 12; do not invent the unnamed twelfth or freeze either count as an acceptance requirement. Some are stale: retain their actual timestamps and the reader's actual FAIL/STALE labels. Record a new inventory before execution. These failures are context, not work added to this bead.

The selected zklw `ic` path was `/home/mk/.local/bin/ic`, SHA256 `bc15e5c0c8bc0d5546adde6e1475f2ae79adca8d393e63e1dd8f99e72c68c892`. `ic --version` is unsupported; use `ic version`. Version output was not successfully refreshed in this revision. The existing `ic-provenance` failure says the deployed binary is behind the source. Record the real binary independently of cloned source; do not label it built from that SHA. The timer was enabled/active with a next elapse at 2026-09-20 09:16:10 UTC; this is inventory, not a new timer-run proof.

**Hosted baseline:** Fable measured run **34150176247**, commit **0ac49e82**, plan **830**, with **274 skips across 10 exact reasons**; thus 556 real passes when all remaining cases pass. Revision 2 retrieved the run log but the large output was truncated; subsequent histogram retrieval failed due to network restrictions. The 274/10 histogram remains attributed to the independent review, not claimed as independently re-counted here. Task 3 must retain the full historical TAP and verify this histogram before implementation of the policy; disagreement returns to review rather than silently resetting the baseline.

| Count | Historical Actions skip reason |
|---:|---|
| 127, 37, 16 | Three distinct interspect-library-not-found reasons (retain exact strings from TAP) |
| 39 | Go build failed |
| 19 | clavain-cli-go not built |
| 18 | intercore source not available |
| 10 | ic not available |
| 5 | interphase not installed |
| 2 | sibling Intercore checkout is required |
| 1 | jsonschema not installed |

The four review confirmations remain controlling: the 29 accounting cases have exactly one ic-independent case, `test_zaka_rejected_before_any_model_call`; the instruction helper resolves from `--source`; the installer negative control removes the wrong template; and interspect resolves from the sibling checkout in the proposed snapshot layout.

## Decisions and boundaries

### Suite scope, timing, and ownership

Run the **whole structural suite** with `cd tests && uv run pytest structural/ -v --tb=short --require-ic --junitxml=...`. It tests the same source as the shell lane, catches collection/marker mistakes, and avoids maintaining a second positive selection that can silently omit new dependent cases. Require the accounting module's current 29 cases, including all 28 relocated cases, to appear as passing JUnit cases; a mere exit 0 is insufficient. The structural cap is 300 seconds. Its actual designated-host duration is an execution measurement, not established by the brief. If the full suite cannot pass within that budget, stop for scope/budget review; do not silently narrow it to 28 tests.

The **five-minute Actions ceiling is no longer defensible as a planning assumption**. The last green job used 268 of 300 seconds at 830 cases, leaving 32 seconds; the review measured 170 seconds in Tier 2 itself. There are now 872 cases, and the Mac's 521-second measurement is a different host, not an Actions benchmark. Set the existing job's `timeout-minutes` to **15**, and change only its existing Tier 2 body for reporting as Task 3 specifies. This is a provisional bound with room for setup, structural tests and shell tests. Acceptance needs an actual main-branch job whose Tier 2 completes within that cap. Do not add steps, actions, toolchain builds, checkouts or Linux triggers; preserve the separate smoke job. Python is already installed by the existing setup-python step.

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

This lane tests **the committed HEAD available in the named local source**, not uncommitted edits or an asserted latest GitHub commit. Dirty source files are ignored, recorded as excluded input, and untouched. Do not fetch/reset/pull the developer checkout. Each subsequent run reclones its newly captured HEAD; there is no retained old test tree to reuse on preparation failure. For each source record HEAD, commit date (`git show -s --format=%cI HEAD`), branch/detached state, `refs/heads/main`, and the already-fetched `refs/remotes/origin/main`. Show equal/ahead/behind/diverged and `git rev-list --left-right --count HEAD...refs/remotes/origin/main`; absent refs are explicit unknowns. Print these dates/ref comparisons in the human run summary as well as retained detail. An otherwise passing lane warns when HEAD differs from local main or is behind/diverged from origin/main, or either comparison is unavailable. Detached HEAD equal to main is recorded, not falsely labeled off-main. Origin/main is a local last-fetched observation, not live GitHub freshness.

Re-read source HEADs at completion. If any moved, retain the result for the captured tuple but change an otherwise passing status to `warn: source advanced during run; newer HEAD not tested`; a failed result stays failed. Keep the suite outcome separately as `test_status` so source movement does not look like an assertion failure. An unreadable final HEAD fails freshness verification, never implies equality. The next scheduled run tests the new tuple. Stable-source acceptance requires a non-superseded run; frequent commits do not justify hiding this limitation.

Verify clean snapshots before preparation, before testing and after each lane. Run structural first, then shell. A test that changes tracked input fails the relevant check and prevents the next lane from claiming a clean run. Keep Python environments, logs, JUnit, wrapper binaries and runner caches outside the snapshots; set `PYTHONDONTWRITEBYTECODE=1` and direct pytest's cache to the external artifact directory. The sole deliberate in-tree preparation artifact is the ignored `bin/clavain-cli-go` built below; record its hash and allow only this exact file when inspecting ignored preparation output. No tracked input may change. Preserve the runtime canary's production guard unchanged.

**Build from the captured source before either lane:** in `<run-root>/tree/os/Clavain`, run `GOFLAGS=-mod=readonly bash scripts/build-clavain-cli.sh`, with Go caches under the run root or a named cache outside tested trees. Go is already a required scheduled-host tool; this adds no Actions step. The helper can exit 0 without Go, so preflight must require a usable Go and preparation must require the executable `bin/clavain-cli-go` afterward, capture the build exit, hash the resulting file, and run a real `compose --stage=ship` probe. No developer binary is copied. Record build duration within the shared preparation bound. Build failure/timeout fails preparation instead of allowing the 7 compose and 12 tool-surface cases to skip. The full scheduled TAP must show all 19 cases executed and passed. A fresh-clone run must establish whether the six-skip hypothesis is attainable, including cold-build cost.

### Bounds and placement

Place the new block immediately after watchdog/helper initialization and **before `guard-tests`**, so it cannot sit behind the existing 900-second Intercore bound and the sum of guard suite bounds. Keep the 2,400-second run ceiling and systemd's existing 2,700-second `TimeoutStartSec` unchanged.

| Phase | Maximum | Behavior at limit |
|---|---:|---|
| Preflight, snapshots and clavain-cli-go build together | 120s | Fail both checks with preparation/build diagnostic |
| Entire structural invocation, including uv environment preparation | 300s | Fail structural; keep partial log; shell may still run if snapshots are clean |
| Entire recursive bats invocation | 900s | Fail shell; name timeout and incomplete TAP |
| Result finalization, source recheck, snapshot removal | 30s | Fail affected checks if identity/finalization cannot finish; retain cleanup diagnostic |

The new nominal maximum is 1,350 seconds. The rationale is the **measured approximately 205-second zklw full run**, giving roughly 1,555 seconds plus TERM→KILL grace, not a guarantee from subtracting bounds. Existing nominal bounds can far exceed 2,400 seconds (including per-guard-suite bounds); the 24 existing checks could wait the entire new block. Clamp each bound to the remaining overall deadline, reserving finalization and five-second kill grace. Require working `timeout`/`gtimeout`; do not use the unbounded fallback. Cold-build preparation and full-run timing must be measured. A full run with the shell lane held until its actual 900-second timeout must also refresh the original `ALL_CHECKS` set under 2,400 seconds. Shortened fixture timeouts alone do not prove this. Exhausted-budget records say not executed/partial, never invented zero passes. Early placement is provisional until these gates pass.

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

The shell lane proposes a **six-skip ceiling as a hypothesis until measured in a fresh clone on zklw**, after the explicit build: five interphase path cases and at most one calibration candidate omission. The five `tests/shell/shims.bats` cases hard-code `/root/projects/interphase` and cannot execute on either supported host layout, even though interphase is installed. Preserve raw TAP text but annotate these as `interphase path fixture unavailable on supported hosts`, never imply the plugin is absent. Do not manufacture that root path. Before arming, execution must search the existing workspace tracker for this exact follow-up, reuse it or create one under Sylveste-psey titled **Repair shims interphase fixture path for supported hosts**, and record its real ID in the skip policy/runbook. No placeholder ID can satisfy this gate. This one-file revision does not create a bead. The five-case allowance expires **2026-10-04T00:00:00Z** (14 days after revision); at/after expiry any such skip warns and prevents fresh acceptance until the follow-up removes it or a reviewed policy change explicitly renews it. It never silently renews.

Task 0 removes the calibration test's ambient `/tmp` fallback. An unset explicit `INTERCORE_CALIBRATION_CANDIDATE` still produces the single visible omission. A supplied but invalid candidate fails, not skips. The scheduled block clears inherited candidate selection; no unattended run may discover an executable in `/tmp`. Approved explicit candidate experiments remain separately attributable and do not repair the two Mac calibration assertions in this scope.

The designated zklw floor allows **zero yq skips and zero gawk skips**. A count above six, an expired allowance, a reason above its allowance, or any new reason yields at least `warn`, even if the suite exits 0. Missing mandatory tools fail at preflight. Unknown/malformed results or nonzero suite exits fail. Structural allows zero skips and zero deselections on the designated host. Exceeding that floor prevents arming/acceptance. Do not silently raise six if the first clean run disproves the hypothesis.

Actions instead compares against the historical **274 skips / 10 reasons**. Always show counts, histogram, baseline and delta; emit a coverage-change warning only when count, reason histogram or skipped case identities differ, including improvements. Store the exact historical skipped case identities as well as counts so equal-count substitutions remain visible. Unchanged known omissions get an ordinary coverage summary, not a perpetual warning. Any new reason or increased per-reason omission blocks acceptance; a decrease may be accepted with an explained coverage delta but does not silently rewrite the baseline. Criterion 4 caps skips at 274 and forbids new omissions, even if the workflow conclusion is success. This acknowledges hosted partial coverage while zklw owns the fuller lane.

Record the supplied Mac observation as historical evidence, not a permanent pass count: 872 TAP cases, 862 `ok` lines including 57 skips, 10 `not ok`, exit 1, 521s. Exclusive counts are therefore **805 passed, 10 failed, 57 skipped**. Its skip histogram is 41 yq, 10 gawk, five interphase, one calibration candidate. New tests will increase the TAP plan; never hard-code 872 as the future suite length.

## Ordered tasks

Commands below are for implementation, not claims of work performed while writing this plan. Set `CLAVAIN_SRC` to the independent Clavain repository and `DOTFILES_SRC` to the independent dotfiles repository. Use committed disposable clones for whole-suite commands. Capture exit status immediately, outside pipes. Each task is one logical commit on the repository's `main`, after its tests and required review; stage only listed files. This plan-only delivery does not commit, push, deploy, claim migration work, or create a companion execution manifest.

**Working-directory contract for every command:** `CLAVAIN_SNAPSHOT` is the absolute `<run-root>/tree/os/Clavain` path at the task's recorded candidate commit; its three siblings are separate clean clones at recorded commits. `DOTFILES_SNAPSHOT` is a separate disposable dotfiles checkout at the recorded candidate commit. `ARTIFACTS` and `DRILL_ROOT` are absolute private directories outside every source tree. Resolve variables with `: "${VAR:?}"` before use; never default them to the caller's current directory. Record `pwd`, source tuple, selected tools, initial/final Git status and exits beside each transcript. Candidate commits in disposable repositories make clean-tree verification possible before landing the reviewed logical change on main. Focused tests may use that task's disposable editing tree while developing; every `<verify>`/`check` below uses the named committed snapshot. Pre-fix runs use a separately named pre-fix snapshot. No whole-suite run is allowed before Task 0 passes.

### Task 0: Remove shared-state test hazards before any scheduled suite (F3; Sylveste-we1q)

**Depends on:** the revision-2 seal and clean independent re-review. Blocks Task 4/5 arming and every full shell baseline, including exploratory runs.

**Files:** Modify `Clavain/tests/shell/test_lib_sprint.bats` and `Clavain/tests/shell/test_b3_calibration.bats`; create `Clavain/tests/structural/test_shell_suite_safety.py`. Read the lock call sites in `hooks/lib-sprint.sh`, `hooks/lib-intercore.sh`, `cmd/clavain-cli/claim.go`, and sibling Intercore's `internal/lock/lock.go`; do not change production locking or the Intercore repository.

**Test first, safely:** add a regression which rejects setup/teardown removal of the shared lock namespace, the retired global sprint/cache globs, and the implicit dated candidate path. Its red-before result is a source/isolated-fixture check; NEVER reproduce the old deletion on a live host. Instrument the claim mocks to log lock name, scope and timeout into `IC_CALL_LOG`, assert `sprint-claim`, the test bead and `500ms`, and assert the expected unlock on success/active-session/TTL branches. Add an acquisition-denied case proving no agent is added when the mock returns failure. Keep all existing 42 case identities and their assertions. Check setup/teardown with guarded removal commands that log and refuse any path outside the case's owned temporary directory; this supplements, not replaces, executing the repaired tests.

**Decision:** delete both `/tmp/intercore/locks/sprint-claim` removals, all obsolete `/tmp/sprint-*` removal globs and retired `/tmp/clavain-discovery-brief-*.cache` cleanup. Do not scope production locks through a fictitious environment override: none exists. All five claim tests install function mocks after loading the library; their temporary logs and mocked agent state are their state, so global cleanup cannot legitimately prepare these assertions. Retain teardown of only the test-owned project. Passing the same cases plus denied-acquisition and argument assertions proves the removed cleanup was unnecessary to the tests; it does not newly prove production lock concurrency.

Change candidate selection to explicit opt-in only: unset/empty `INTERCORE_CALIBRATION_CANDIDATE` visibly skips that one case with the existing reason. An explicit non-executable/non-regular path fails with its diagnostic, with no fallback. Keep the golden-case comparisons intact when a valid explicit candidate is supplied. The new regression exercises unset, invalid and explicit private candidate selection; a synthetic candidate can prove selection only, not golden-case correctness. Static assertions forbid the old ambient default. The scheduled harness clears inherited candidate selection. This security correction does not fix or waive the two Mac-only calibration failures.

```bash
cd "$CLAVAIN_SNAPSHOT/tests"
uv run pytest structural/test_shell_suite_safety.py -v
cd "$CLAVAIN_SNAPSHOT"
bats tests/shell/test_lib_sprint.bats --tap > "$ARTIFACTS/sprint-safety.tap" 2>&1
sprint_rc=$?
printf 'sprint_exit=%s\n' "$sprint_rc"
```

Expected on equipped zklw: safety regression and all retained sprint cases pass without skips; new lock assertions also pass. Preserve explicit before/after case lists. On Mac the safety regression runs with Bash 3.2; absent assertion libraries are reported, not installed or counted as test passes.

Then, **only with the repaired committed suite**, hold a uniquely named `psey-safety-<random>` scope beneath the real `sprint-claim` lock through a persistent helper process with a live owner PID. Run the repaired sprint file with that sentinel held. The scheduled whole-shell sentinel leg occurs later in Task 6's pre-arming baseline, after the unarmed harness exists; it is not a prerequisite to writing Task 4. Before and after each run, assert the sentinel's owner metadata/inode remain unchanged and a separate competing acquisition is rejected; finally release only that owned scope. Do not remove or enumerate other owners' locks for cleanup. Retain holder/contender exits and raw TAP. No old hazardous suite is run in this live sentinel drill. Land the code after focused verification; close **Sylveste-we1q** only after the scheduled leg also has evidence. F3 arming stays blocked meanwhile. Commit: `test: stop shell suites touching shared lock and candidate paths`.

<verify>
- run: `cd "$CLAVAIN_SNAPSHOT/tests" && uv run pytest structural/test_shell_suite_safety.py -v`
  expect: exit 0
- run: `cd "$CLAVAIN_SNAPSHOT" && bats tests/shell/test_lib_sprint.bats --tap`
  expect: exit 0
</verify>

### Task 1: Repair the complete installer fixture contract (F1)

**Depends on:** Task 0's code/focused verification for the safe baseline/landing sequence; its later scheduled evidence remains an arming gate.

**Files:** Modify `Clavain/tests/shell/test_codex_installer.bats`. Read, do not modify, `scripts/install-codex.sh`, `scripts/sync-agent-instructions.py`, `scripts/sync-codex-instructions.py`, and `config/{agent-instructions.md,host-adapters.json,routing.yaml,codex-instructions.md}`.

**Test first:** Preserve the six existing positive failures as the regression tests. Correct the negative test to remove `agent-instructions.md`, not `codex-instructions.md`; assert the shared template exists before removing it. Verify refusal occurs before links/config writes. This prevents the old negative test from passing merely because the fixture was already broken.

Run at the recorded pre-fix commit in a disposable checkout on **each** host:

```bash
cd "$CLAVAIN_PRE_FIX_SNAPSHOT"
bats tests/shell/test_codex_installer.bats > "$ARTIFACTS/installer-before.tap" 2>&1
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
cd "$CLAVAIN_SNAPSHOT"
bats tests/shell/test_codex_installer.bats
```

Expected: every installer case passes on both machines, including removal of the now-present shared template. Then, from a clean committed Clavain clone with clean Intercore at `../../core/intercore`:

```bash
cd "$CLAVAIN_SNAPSHOT"
bats tests/shell/test_runtime_evidence_canary.bats
```

Expected: exit 0; both substantive source/installed canaries execute rather than skip. No runtime-canary source change. Commit: `test: complete Codex installer instruction fixture`.

<verify>
- run: `cd "$CLAVAIN_SNAPSHOT" && bats tests/shell/test_codex_installer.bats`
  expect: exit 0
- run: `cd "$CLAVAIN_SNAPSHOT" && bats tests/shell/test_runtime_evidence_canary.bats`
  expect: exit 0
</verify>

### Task 2: Make absent-ic selection explicit and testable (F2)

**Depends on:** Task 1 for the landing sequence.

**Files:** Modify `Clavain/tests/structural/test_claude_usage.py`, `Clavain/tests/structural/conftest.py`, `Clavain/tests/pyproject.toml`; create `Clavain/tests/structural/test_ic_selection.py`.

**Test first:** Add subprocess collection tests covering present `ic`, genuinely absent `ic`, explicit `--require-ic` with absent `ic`, and a present executable that exits nonzero. Use a filtered temporary PATH with symlinks to required non-ic tools and invoke the already-resolved Python interpreter directly; assert `shutil.which('ic') is None` inside the child for the absent case. Do not use an `ic` stub to claim the 29 real tests pass. Collect the real accounting file and assert exactly 28 expanded node IDs bear `requires_ic`, and the Zaka rejection case does not. Test terminal explanation and the deselection hook, including a mixed run where unrelated tests remain selected.

```bash
cd "$CLAVAIN_SNAPSHOT/tests"
uv run pytest structural/test_ic_selection.py -v
```

Expected before implementation: failures for missing marker/selection/reporting behavior. Afterwards: all selection tests pass.

**Implementation:** Register `requires_ic` in pytest configuration; decorate the dependent test functions explicitly, including their parameterized cases. Do not mark the module or the Zaka test. Add `--require-ic` to the existing structural conftest. In collection, discover `ic` with `shutil.which`. If absent in default mode, remove only marked items, call `config.hook.pytest_deselected(items=held_back)`, and retain the count for `pytest_terminal_summary`, which prints `28 tests deselected: requires_ic; ic executable not found on PATH; covered by zklw clavain-structural`. With `--require-ic`, absence raises a pytest usage/collection error instead. A present but broken ic stays selected and fails normally. Existing test assertions and production metering stay unchanged.

```bash
cd "$CLAVAIN_SNAPSHOT/tests"
uv run pytest structural/test_claude_usage.py -v --require-ic
uv run pytest structural/ -v --tb=short --require-ic
```

Expected with real ic: 29/29 accounting cases pass, no deselection; then the full structural suite passes. The new subprocess regression must prove actual no-ic accounting execution yields `1 passed, 28 deselected`, the explanation, and exit 0. Capture its child transcript; do not substitute collection-only output for this assertion. Commit: `test: report structural tests requiring Intercore`.

<verify>
- run: `cd "$CLAVAIN_SNAPSHOT/tests" && uv run pytest structural/test_ic_selection.py -v`
  expect: exit 0
- run: `cd "$CLAVAIN_SNAPSHOT/tests" && uv run pytest structural/test_claude_usage.py -v --require-ic`
  expect: contains "29 passed"
</verify>

### Task 3: Count real results and repair the existing workflow (F2, F4)

**Depends on:** Tasks 1–2.

**Files:** Create `Clavain/scripts/suite-report.py`, `Clavain/tests/structural/test_suite_report.py`, `Clavain/tests/fixtures/shell-skip-baselines.json`; modify `Clavain/tests/shell/test_helper.bash`, `.github/workflows/test.yml`; create `Clavain/tests/shell/test_helper_override.bats`. The baseline JSON contains the historical Actions run/SHA, exact skip reasons and case identities, and the scheduled policy's follow-up ID and expiry. Populate the latter from the actual tracker before arming; do not invent an ID.

**Test first:** Exercise the summarizer CLI with complete TAP, mixed pass/fail/skip, the 41/10/5/1 skip histogram, a nonzero exit despite all `ok` lines, bailout, duplicate/missing test numbers, truncated or empty TAP, and `1..0`. Verify `ok ... # skip ...` is excluded from passed. For JUnit, test failures/errors/skips, malformed/empty XML, no accounting file, and 28 versus 29 accounting cases. The required module check must reject skipped/failed cases and verify the unmarked Zaka case plus the 28 others. Test case identities, not an unrelated set of 29 tests. Add a bats test where an explicit invalid helper directory fails despite available fallback helpers, and a valid explicit directory loads both libraries. Create tiny temporary helper libraries exporting distinct sentinels for this loader test, so it also runs on the Mac without installing packages; actual assertion-library compatibility is established by the real zklw suite. Ordinary autodetection remains optional.

```bash
cd "$CLAVAIN_SNAPSHOT/tests"
uv run pytest structural/test_suite_report.py -v
cd ..
bats tests/shell/test_helper_override.bats
```

Expected before implementation: failures for the missing CLI and ignored explicit override; afterwards: all pass.

**Implementation:** Define this stable CLI:

```text
python3 scripts/suite-report.py --format tap|junit --input PATH
  --exit-code INTEGER --max-skipped INTEGER --output-json PATH
  [--shell-skip-policy | --actions-skip-baseline PATH] [--require-claude-usage]
```

Write JSON fields `status`, `summary`, `complete`, `planned`, `observed`, `passed`, `failed`, `skipped`, `skip_reasons`, `failures`, `exit_code`, and policy/baseline/delta information; print the same human summary to stdout. On failure, begin the summary with the first failed case name, then `passed: P   failed: F   skipped: S`, so the real reader's 120-character headline limit retains the actionable name. Detail begins with failed cases/diagnostics, then counts and identity. Unknown counts say `unavailable`, not zero. `passed + failed + skipped == observed`; errors count as failed. Incomplete output records observed counts as partial and fails. Return 0 for pass, 3 for warn, 1 for fail; input/usage errors also must not appear successful. TAP parsing recognizes bats' actual top-level TAP grammar and directives, preserves diagnostics and failed case names, and validates the plan against records. For JUnit aggregate leaf test cases, not both suite totals and their children. `--require-claude-usage` enforces the Task 2 accounting-module invariant. `--shell-skip-policy` enforces the six-case policy, real follow-up ID and expiry. `--actions-skip-baseline` compares exact historical counts/reasons/identities, warns on a delta in either direction, and fails on more than 274 skips or new/increased omissions. Absent a named policy, the numeric threshold still reports all reasons. Unexpected reporter failure fails the caller.

Before implementing the hosted policy, re-count the full log for run 34150176247 and bind the baseline file to its SHA. Add tests for unchanged 274/10 (no coverage warning), increased and decreased counts, a new reason at the same total, a changed skipped identity, an expired interphase allowance, and the first failing test name surviving the real reader headline cap. A changed baseline needs explicit review; no latest-run auto-learning of skips.

Change the existing Tier 2 `run` body in place; retain its command and directly captured return code:

```bash
# cwd: $GITHUB_WORKSPACE/os/Clavain (existing job default)
tap_file="$RUNNER_TEMP/clavain-shell.tap"
summary_file="$RUNNER_TEMP/clavain-shell-summary.json"
suite_rc=0
bats tests/shell/ --recursive --tap > "$tap_file" 2>&1 || suite_rc=$?
cat "$tap_file"
report_rc=0
python3 scripts/suite-report.py --format tap --input "$tap_file" \
  --exit-code "$suite_rc" --max-skipped 274 \
  --actions-skip-baseline tests/fixtures/shell-skip-baselines.json \
  --output-json "$summary_file" || report_rc=$?
if [ "$report_rc" -eq 3 ]; then
  echo '::warning::Shell coverage changed from run 34150176247; see delta and reasons above.'
elif [ "$report_rc" -ne 0 ]; then
  exit 1
fi
exit "$suite_rc"
```

Set the existing structural-and-shell job ceiling to 15 minutes. No new Actions steps or dependencies. Tier 1's unchanged command gets the visible selection behavior through conftest. Run the focused tests and a real recursive bats run in a committed clean clone; on zklw require no failures and only the declared omissions. On Mac retain the two known calibration failures and missing-dependency skips; do not call it a green full suite.

Commit: `test: expose suite coverage and restore shell workflow reachability`. An actual main-branch Actions run is verified in Task 6 after authorized push, not inferred here.

<verify>
- run: `cd "$CLAVAIN_SNAPSHOT/tests" && uv run pytest structural/test_ic_selection.py structural/test_suite_report.py -v`
  expect: exit 0
- run: `cd "$CLAVAIN_SNAPSHOT" && bats tests/shell/test_helper_override.bats`
  expect: exit 0
</verify>

### Task 4: Add bounded snapshot execution to rig-health, unarmed (F3, F4)

**Depends on:** reviewed code and focused verification from Tasks 0–3; their committed Clavain revision must be available on zklw. Task 4 may be implemented/deployed unarmed while Task 0's scheduled sentinel proof is outstanding. Sylveste-we1q is a hard arming dependency, not an escalation-only note.

**Files:** Modify `dotfiles/common/.local/bin/rig-health-check.sh`; create `dotfiles/common/.claude/hooks/tests/test-rig-clavain-suites.sh`.

**Test first:** In the existing shell-test style, drive the **real harness** with `RIG_CLAVAIN_CHECKS_ONLY=1`, isolated `RIG_HEALTH_DIR`, and throwaway Git sources. Clear inherited `RIG_HEALTH_RUN` in the child when deliberately exercising this block; the checks-only exit prevents it from recursing into guard-tests. Test the nested-suppression branch separately with that variable set. Test absent marker before tool probes, invalid marker, individually missing bats/yq/gawk/ic/helpers, wrong source path, old source without the reporter, dirty original source, snapshot preparation failure, and source advancement. Tiny fake test executables may prove orchestration and result handling in fixtures; label that evidence as fixture-only. Do not replace actual suites in scheduler success acceptance.

Also test a fresh clone with no Go binary before preparation, successful build plus 19 real compose/tool-surface results, failed build, build-helper exit 0 without an output binary, and expiration of the interphase allowance. Include exact ic path/version/hash in fixtures, hash drift during execution, off-main/detached source, missing origin/main, and ahead/behind/diverged comparisons. Test complete TAP with a named failed assertion; excessive skips; malformed results; structural JUnit missing any required accounting case; a child that ignores TERM and launches a grandchild; shortened per-lane timeout; exhausted overall budget; nested execution; and cleanup constrained to owned run directories. A timed-out/truncated report must never pass, and no test process may survive its bound. Test `ALL_CHECKS` behavior by forcing the watchdog before the new block can refresh statuses. A fixture nested in guard-tests must suppress expensive recursive integration cases explicitly and tally those skips.

```bash
cd "$DOTFILES_SNAPSHOT"
/bin/bash common/.claude/hooks/tests/test-rig-clavain-suites.sh
```

Expected red-before implementation: missing statuses/overrides and failing assertions. Expected after: `failed: 0`, with any deliberately nested skips reported separately.

**Implementation:** Add a Bash 3.2-compatible block using indexed arrays, `while IFS= read -r`, ordinary variables, and the existing `bound`/`write_status`; no `mapfile`, namerefs, associative arrays, or `wait -n`. Implement the designation, overrides, snapshot layout, binary selection, shared preparation deadline, per-lane limits, cleanliness checks, and source recheck described above. Keep all synchronous subprocesses, including Git/npm/tool version queries, within the preparation/finalization deadlines; a collection of individual 120-second bounds is not a 120-second phase.

Call the cloned Clavain reporter, capture its exit separately from the suite, and validate its JSON before invoking the existing writer. Detail starts with failed names/diagnostics, then totals, skip reasons, policy expiry/follow-up, source tuple/ref comparisons/dates, working directory, commands, elapsed time and raw exits. Record the selected installed ic's resolved path, `ic version` stdout/exit and SHA256; compare its hash again after testing. An unreadable version/hash or changed binary fails identity verification. The installed binary is distinct from the source-built runtime-canary ic and from the new clavain-cli-go; record each separately. Never infer binary provenance from the cloned Intercore SHA. Preserve partial logs on timeout. `write_status` embeds detail before temporary cleanup; save full run artifacts under `~/.local/state/rig-clavain-suites/runs/<start-epoch>-<pid>/` (last seven runs), outside the tested tree. For isolated tests/drills put retained artifacts beneath their isolated `RIG_HEALTH_DIR` instead, so they cannot prune real evidence. Only prune this runner's own prior directories. Failure to write/parse a result is a failure of the check, not a silent omission. Set `FAILED=1` for either failed lane; warnings retain the harness's existing exit convention.

Add both names to `ALL_CHECKS`. At preflight/preparation failure emit both applicable statuses rather than leaving the second one absent. Do not let the structural lane's failure prevent an otherwise runnable shell lane from reporting. Do not remove or modify existing bounds and checks.

```bash
cd "$DOTFILES_SNAPSHOT"
/bin/bash -n common/.local/bin/rig-health-check.sh
/bin/bash common/.claude/hooks/tests/test-rig-clavain-suites.sh
/bin/bash common/.claude/hooks/tests/test-rig-health-bounds.sh
```

Expected: syntax exit 0 on Mac `/bin/bash` 3.2 and Linux; new behavior suite has zero failures; existing bounds suite has zero failures with its platform/nesting skips stated. Commit: `feat: run Clavain suites from bounded clean snapshots`. This commit is unarmed: no designation has been deployed yet.

<verify>
- run: `cd "$DOTFILES_SNAPSHOT" && /bin/bash -n common/.local/bin/rig-health-check.sh`
  expect: exit 0
- run: `cd "$DOTFILES_SNAPSHOT" && /bin/bash common/.claude/hooks/tests/test-rig-clavain-suites.sh`
  expect: exit 0
- run: `cd "$DOTFILES_SNAPSHOT" && /bin/bash common/.claude/hooks/tests/test-rig-health-bounds.sh`
  expect: exit 0
</verify>

### Task 5: Wire designation and the existing reader (F3, F4)

**Depends on:** Task 4, resolved Sylveste-we1q, a real interphase follow-up ID/expiry, and a real clean-snapshot baseline on zklw at the intended Clavain commit, including the Go build and all 19 formerly binary-skipped tests. Six is a hypothesis, not pre-certified coverage. Use Task 6's pre-arming drill protocol at this point; Task 6's final acceptance follows deployment, so there is no dependency on a deployed marker to establish this baseline.

**Files:** Create `dotfiles/server/.config/clavain/test-machine`, `dotfiles/docs/rig-clavain-suites.md`; modify `dotfiles/install-server.sh`, `dotfiles/common/.claude/hooks/report-rig-health.py`, and `dotfiles/common/.claude/hooks/tests/test-rig-clavain-suites.sh`.

**Test first:** Extend the harness suite to assert that deleting either status is reported as `NEVER`, an aged status is `STALE`, fresh undesignated skips stay quiet on their own, and a failed test's name survives in stdout `hookSpecificOutput.additionalContext` as well as detail. Include a mixed-red fixture matching the observed host inventory. Test installer declaration of the server-only marker and absent Mac marker. Record actual observer stdout and stderr; a source string alone does not prove reporting. Run `cd "$DOTFILES_SNAPSHOT" && /bin/bash common/.claude/hooks/tests/test-rig-clavain-suites.sh` before editing the reader/installer: expect nonzero because the new checks are not expected and the marker is not declared.

**Implementation:** Add `link server/.config/clavain/test-machine .config/clavain/test-machine` next to the existing Intercore marker link in `install-server.sh`. Add both status names to the reader's `EXPECTED`, since both hosts write a result, including skips. Do not edit scheduler units to set manual authority or duplicate the daily timer. Document default sources, overrides, skip allowance, measured baseline/timing, deployed files, restoration, and the commands in Task 6. The existing Sylveste operations document remains a reference; this runbook lives in dotfiles to keep the landing strictly two-repository.

```bash
cd "$DOTFILES_SNAPSHOT"
/bin/bash common/.claude/hooks/tests/test-rig-clavain-suites.sh
python3 -m py_compile common/.claude/hooks/report-rig-health.py
```

Expected: no failed assertions and Python syntax success. Before the marker is deployed, run the real snapshot suites through the actual scheduler using a temporary designation override and isolated health destination, as Task 6 describes. Require both lanes to pass within bounds and no unexpected skips before making daily designation live. Commit: `feat: designate zklw for Clavain suite health checks`. A tracked marker and installer line are configuration, not proof of deployment or scheduling.

<verify>
- run: `cd "$DOTFILES_SNAPSHOT" && /bin/bash common/.claude/hooks/tests/test-rig-clavain-suites.sh`
  expect: exit 0
</verify>

### Task 6: Prove both lanes, fault reporting, and restoration (F1–F4)

**Depends on:** Tasks 0–5 for final production acceptance, required independent review, and execution/deployment authority. The pre-arming portion is also Task 5's baseline prerequisite.

**Files:** Update only `dotfiles/docs/rig-clavain-suites.md` with results and evidence locations. Runtime evidence belongs in private per-run directories, not Sylveste source. Use `Sylveste-psey` for execution tracking when the tracker is available; do not create a second migration bead.

**Test first:** Run the fault matrix before arming daily designation. Stage a throwaway Clavain source clone with a **committed** additional bats test `@test "psey forced assertion" { false; }`. A dirty uncommitted injected test is not part of the runner's input and would not test failure propagation. Stage a second committed variant with a TERM-resistant sleeping child for timeout. Keep both outside live source checkouts, retaining original and injected commit IDs.

**Full harness side effects and serialization:** `RIG_HEALTH_DIR` isolates status files, not all effects. The harness runs real guard suites, refreshes facts, exchanges peer facts, and invokes the restore helper. Peer escrow attestation is Darwin-only and requires the helper's interactive opt-in for live `op` reads; full tests here are on Linux and must not set `RIG_ESCROW_INTERACTIVE=1`. The restore helper uses `~/.local/state/rig/restore-drill.json` (override `RIG_DRILL_STATE`) and a seven-day success interval, independently of `RIG_HEALTH_DIR`; an empty health directory does not force another restore, but a due/failed restore can pull real bytes again. Peer exchange may still write the current host's facts on the peer. Do not advertise these full runs as effect-isolated, reset restore state, force a restore, or suppress existing checks to meet the budget.

Use checks-only transient services for the fault matrix, stopping before guard tests/peer/restore work. For full-run proofs, use the existing `rig-health.service` in a recorded maintenance window, one run at a time. Save service/timer definitions and timer state/next elapse; wait for any active run to finish, temporarily stop the timer, add only a task-owned runtime service drop-in for the temporary marker, isolated output and (for timeout) committed source override, then daemon-reload and start that same service. This serializes with ordinary starts of the same unit. Do not modify or remove unrelated drop-ins. Trap restoration removes only the task drop-in and restores the timer's original state even on failure. No recurring schedule or global ceiling changes. Retain the real restore state and normal peer configuration. Record whether restore was due and what actual side effects occurred. If these normal repeated side effects cannot run within existing execution/deployment authority, the full-run acceptance gate remains open. Never turn a partial run into full-run evidence.

Only two pre-arming full service drills are required: one healthy and one holding shell execution to its **actual 900-second** bound while keeping the other real checks. Then the no-override production force and the unattended daily run establish ownership. Extra full reruns need a concrete failure/change to investigate. The original `ALL_CHECKS` contains 24 names; compare the exact deployed array, not that historical count or the reader's broader `EXPECTED_BY_HOST` set.

**Scheduler commands and evidence:** On zklw use transient systemd services to run the installed real harness with the same PATH as the real unit, actual `INVOCATION_ID`, isolated output, and explicit overrides. This representative missing-yq command assumes `DRILL_ROOT` is an absolute private directory containing a regular `test-machine` marker and no file named `missing-yq`:

```bash
cd "$DRILL_ROOT"
systemd-run --user --wait --collect --unit=psey-no-yq \
  --property=Type=oneshot --property=TimeoutStartSec=2700 \
  --property="WorkingDirectory=$DRILL_ROOT" \
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

On the Mac, generate a throwaway LaunchAgent plist in `DRILL_ROOT` whose `ProgramArguments` invoke `/bin/bash` and the deployed harness, with `WorkingDirectory` set to the absolute `DRILL_ROOT`. Its `EnvironmentVariables` carry `RIG_HEALTH_DIR`, `RIG_CLAVAIN_MARKER` pointing to an absent file, and `RIG_CLAVAIN_CHECKS_ONLY=1`; stdout/stderr paths stay in the same private directory. Give it label `com.arouth.psey-clavain-drill`. Do not replace the production LaunchAgent or forge `RIG_RUN_KIND`. Use actual launchd:

```bash
cd "$DRILL_ROOT"
launchctl bootstrap "gui/$(id -u)" "$DRILL_ROOT/com.arouth.psey-clavain-drill.plist"
launchctl kickstart "gui/$(id -u)/com.arouth.psey-clavain-drill"
launchctl print "gui/$(id -u)/com.arouth.psey-clavain-drill"
jq -e '.status == "skip"' "$DRILL_ROOT/mac/health/clavain-shell.json"
jq -e '.status == "skip"' "$DRILL_ROOT/mac/health/clavain-structural.json"
launchctl bootout "gui/$(id -u)/com.arouth.psey-clavain-drill"
```

Wait for process completion/status timestamps before the jq assertions. Expected: both fresh skip records, zero suite invocations, and launchd completion. Then repeat with a temporary marker and an explicitly nonexistent bats path to prove the designated failure branch also executes under macOS Bash 3.2; full Mac-suite success is not a requirement.

For real zklw success, use the serialized full-service protocol above with the temporary marker and **no checks-only selector**, actual installed tools, committed sources and isolated health output. Record start/end times, per-phase/build elapsed time, source/binary identities and per-check status JSON. Both new checks must pass, the original canaries must execute, all 29 accounting cases and all 19 compose/tool-surface cases must pass, and every original `ALL_CHECKS` entry must be refreshed before 2,400s. Existing red statuses need not turn green; watchdog `not run` records do not count as completed checks. Repeat the full service with the committed timeout variant and the default 900-second shell cap: shell must fail and every original check must still execute before 2,400s. Keep survivor/process-group evidence. If anything is starved, do not deploy the daily marker.

**Visibility amid existing failures:** copy the current zklw health directory into a private reader-evidence directory without altering existing status values/timestamps; overlay only the two genuine scheduled records from the committed assertion drill. Run the installed real reader on zklw with `RIG_HEALTH_DIR` pointing to that directory, capture stdout JSON and stderr, and parse `.hookSpecificOutput.additionalContext`. Require a legible `FAIL clavain-shell` headline containing `psey forced assertion` alongside the existing FAIL/STALE headlines, before the total/line caps. Detail-only visibility fails acceptance. This invokes the reader's usual settings-history snapshot and heartbeat; record those normal effects. Also capture normal production reader output after restoration. The mixed-red inventory is not edited to make the test easier.

After the authorized narrow deployment, verify actual unit definitions and links, then force the real daily service without overrides:

```bash
cd "$HOME"
systemctl --user cat rig-health.service rig-health.timer
systemctl --user is-enabled rig-health.timer
systemctl --user is-active rig-health.timer
systemctl --user start rig-health.service
systemctl --user show rig-health.service -p Result -p ExecMainStatus -p InvocationID
jq '{status,summary,ran_at_epoch,detail}' "$HOME/.claude/health/clavain-shell.json"
jq '{status,summary,ran_at_epoch,detail}' "$HOME/.claude/health/clavain-structural.json"
```

Expected: timer enabled/active with a future elapse and daily cadence; fresh authoritative **per-check JSON passes** at the intended source tuple; raw detail reports skips separately. `systemctl start` can return nonzero and `Result=exit-code` can remain because of existing failures. Capture those results and continue reading both check JSONs; do not require aggregate service success or use `&&` to skip the evidence after a nonzero start. Also retain one subsequent **timer-triggered**, unattended invocation, not only the forced service start. Verify reader output with `cd "$HOME" && python3 "$HOME/.claude/hooks/report-rig-health.py" </dev/null`. A source checkout script run by hand is not this evidence.

After authorized Clavain push, identify the actual main-branch run rather than rerunning an old SHA:

```bash
cd "$CLAVAIN_SRC"
gh run list --repo mistakeknot/Clavain --workflow test.yml --branch main --limit 5 \
  --json databaseId,headSha,status,conclusion
gh run view "$ACTIONS_RUN_ID" --repo mistakeknot/Clavain --json headSha,jobs
gh run view "$ACTIONS_RUN_ID" --repo mistakeknot/Clavain --log
```

Expected: `headSha` includes Tasks 0–3; Tier 1 finishes with its reported no-ic deselection; `Tier 2 — Shell tests (bats)` starts and concludes success; direct bats exit is 0; complete TAP has at most 274 skips and no new/increased reason or case omissions relative to the verified historical baseline; summary shows counts and any delta; entire job completes below 900 seconds. A job blocked at the intervening Task attribution step does not meet acceptance and is an escalation, not permission to remove that step.

Complete the committed assertion and shortened timeout matrix through the checks-only systemd path using `RIG_CLAVAIN_DIR` and isolated output; retain named failure, timeout/nonzero status, no-survivor proof and unchanged source status. Already completed matrix legs need not be repeated absent a relevant change. Restore all task-owned scheduler configuration, remove the temporary LaunchAgent, and confirm the next normal scheduled result. Preserve drill evidence. Commit the runbook evidence update only after facts exist: `docs: record Clavain scheduled suite verification`.

## Acceptance Criteria

The numbered criteria below are the revision-2 acceptance contract to extract and seal once before the single clean independent re-review. Commands involving new files are evaluated after implementation. A fixture result cannot substitute for explicitly required host/scheduler evidence. For each check, `CLAVAIN_SNAPSHOT` is the absolute clean committed disposable Clavain clone with clean Intercore/interspect/interstat siblings, `DOTFILES_SNAPSHOT` is the absolute committed disposable dotfiles clone, and `ARTIFACTS`/`DRILL_ROOT` are private absolute evidence directories outside tested trees. Record these resolved paths, `pwd`, commits, raw exits and output; unset paths fail setup instead of falling back to the live checkout. Criteria judged from scheduler/status/reader artifacts identify their host, invocation and timestamps. No criterion can be satisfied by this document's promises alone.

1. **F1 — fixture repair is red-before-green on both hosts.** At the retained pre-fix SHA, the installer TAP names the six known failures; at the repaired SHA, every installer case passes. The missing-template negative test removes the shared template and proves refusal before consumer writes. Production installer and canary guards are unchanged.

   ```check
   cd "$CLAVAIN_SNAPSHOT"
   bats tests/shell/test_codex_installer.bats
   # exit 0 on Clavain and zklw; attach before/after SHA and TAP
   ```

2. **F1/F3 — the two substantive runtime canaries execute successfully from clean snapshots.** Neither is skipped for missing Go, missing Intercore source, or checkout dirt. Dirty live checkout files remain byte-identical before and after the run.

   ```check
   cd "$CLAVAIN_SNAPSHOT"
   git status --porcelain=v1 --untracked-files=all
   git -C ../../core/intercore status --porcelain=v1 --untracked-files=all
   bats tests/shell/test_runtime_evidence_canary.bats
   # both Git status outputs empty; bats exit 0
   # source and installed workload cases are ok without # skip
   ```

3. **F2 — dependency selection is honest.** Real ic present: 29 accounting cases pass. Real ic absent: one passes, 28 are deselected, the terminal states the number/reason/destination, and exit is 0. `--require-ic` with no ic fails; a present broken ic is not deselected. The expanded marker set contains exactly the 28 dependent cases.

   ```check
   cd "$CLAVAIN_SNAPSHOT/tests"
   uv run pytest structural/test_ic_selection.py -v
   uv run pytest structural/test_claude_usage.py -v --require-ic
   # exit 0 for both; second reports 29 passed, zero skipped/deselected
   ```

4. **F2 — the existing Actions lane actually reaches and completes Tier 2 within its coverage ceiling.** Retain the main-branch run ID/head SHA containing Tasks 0–3, successful Tier 1/Tier 2 conclusions, direct bats exit 0, complete TAP, exclusive counts/histogram and whole-job elapsed time below 900 seconds. **At most 274 shell cases may skip**, with no new skipped case identities, new reasons or increased per-reason counts against the retained historical run-34150176247 baseline (830 cases, 274 skips, 10 reasons). The historical baseline must first be verified from its full log; decreases remain visible with explanations. Reporter regression output proves unchanged baseline emits no coverage-change warning and any count/reason/identity change is surfaced. Workflow diff adds no action, checkout, dependency-installation step or trigger. A green badge alone is insufficient.

5. **F3 — committed-source isolation, build and identity work.** Dirty live sources produce clean detached snapshots without developer tree/index changes, including dirty Intercore. A fresh clone initially has no `bin/clavain-cli-go`; preparation output records a successful source build, executable hash and compose probe, and TAP shows all 7 compose plus 12 tool-surface cases passing without skips. Only that exact ignored build artifact is allowed inside the snapshot. Source metadata shows each SHA, commit date, local-main comparison and last-fetched origin/main comparison. Off-main, behind/diverged or unknown comparisons surface a warning. The installed ic's actual path, `ic version` output and SHA256 appear separately from source identities and canary-built binaries. Binary hash change during a run fails identity verification. A committed source advance is captured next run; advancement mid-run warns while retaining the captured suite outcome. Failed preparation never reuses an old tree. Retain real scheduled baseline/build records and controlled source/tool-drift transcripts, not just fixture output.

   ```check
   cd "$DOTFILES_SNAPSHOT"
   /bin/bash common/.claude/hooks/tests/test-rig-clavain-suites.sh
   # exit 0; retain actual scheduler clean-snapshot and source-advance evidence too
   ```

6. **F3 — designation cannot hide lost tools.** Actual launchd on Mac and systemd on zklw write fresh skips for an absent marker without invoking suites. Actual systemd runs with a present marker and each of bats, yq, gawk, and ic individually forced missing write named failures; ic absence fails both checks. No PATH fallback defeats an explicit override. Invalid/unreadable designation fails. These observations come from scheduler runs, not only shell fixtures.

7. **F3 — assertion failures and infrastructure failures remain red.** A systemd invocation against a committed throwaway failing bats test yields `clavain-shell=fail`, nonzero suite execution, and `psey forced assertion` at the start of the summary and in detail. A scheduled timeout yields fail with partial/incomplete output and no surviving child, proved by retained process-group/child checks. Missing reports, malformed results, empty collections, failed build, or fewer than the required accounting cases cannot pass; retain negative-case outputs and statuses.

8. **F3 — both suites fit without starving the harness, including timeout.** Retain two full zklw service invocations with no checks-only selector: healthy, and a committed shell sleeper held to the actual default 900-second timeout. Both complete under 2,400 seconds; the healthy run passes both new checks, the timeout run fails shell, and **every original name in the deployed `ALL_CHECKS` array** receives a fresh executed-check status in both runs. Reader-only `EXPECTED_BY_HOST` entries from other timers are not the denominator. A watchdog `not run` record does not count as execution. Preparation including build ≤120s, structural ≤300s, shell ≤900s, finalization ≤30s, plus separately recorded kill grace within the overall limit. Retain phase durations, start/end, the exact `ALL_CHECKS` list and a per-name timestamp/outcome table. Separate watchdog regression output names both new checks when not reached. Record serialization, peer/restore effects and restored timer/drop-in state. Failure blocks arming; the historical ~205s existing run is rationale, not acceptance evidence.

9. **F3 — daily ownership is demonstrated by per-check JSON.** Retain deployed server-only marker/link, unit definitions, enabled/active timer with a future elapse, forced production invocation and subsequent unattended timer-triggered invocation. In each, `clavain-shell.json` and `clavain-structural.json` have `status=pass`, authoritative scheduler provenance and timestamps within that invocation, with intended source/binary identities. Each structural report has 29 passing accounting cases and zero skipped/deselected cases. Judge these JSONs even if `systemctl start` returns nonzero or `Result=exit-code` persists from existing red checks; aggregate service success is not the criterion. No new Linux Actions scheduling or fleet registration is introduced.

   ```check
   cd "$HOME"  # zklw, after each identified production invocation
   jq -e '.status == "pass"' .claude/health/clavain-shell.json
   jq -e '.status == "pass"' .claude/health/clavain-structural.json
   jq '{check,status,summary,ran_at_epoch,detail}' .claude/health/clavain-shell.json
   jq '{check,status,summary,ran_at_epoch,detail}' .claude/health/clavain-structural.json
   # both predicates exit 0; retain complete raw records/provenance and match to invocation
   ```

10. **F4 — counts are exclusive, complete and measured in the target layout.** Valid TAP has `passed + failed + skipped == planned`; incomplete output is partial and failed. Histograms name every reason. The historical 872/862-ok/10-not-ok/57-skip sample yields **805 passed, 10 failed, 57 skipped**, with 41/10/5/1 reasons. An actual fresh-clone zklw run after the build must establish **at most six skips**, only five interphase path omissions and one explicit-candidate omission; this ceiling is a hypothesis until measured. No yq, gawk or missing-binary skips. Summary annotates that the five interphase cases cannot execute on the supported layouts despite an installed plugin, names an actual linked follow-up bead and expires its allowance at **2026-10-04T00:00:00Z**. At/after expiry those skips warn and block renewed acceptance. Extra/new omissions warn and block acceptance; limits cannot be raised without reviewed change. Structural accepts zero skips/deselections.

    ```check
    cd "$CLAVAIN_SNAPSHOT/tests"
    uv run pytest structural/test_suite_report.py -v
    # exit 0; covers counts, policy, malformed TAP/JUnit, and required accounting cohort
    ```

11. **F3/F4 — the real reader exposes the failure among existing red checks.** Both checks are in `EXPECTED`; deleted status produces `NEVER`, expired status produces `STALE`, and fresh undesignated skips alone stay quiet in isolated tests. On zklw, copy the contemporaneous real health inventory unchanged into the private reader-evidence directory and overlay only genuine scheduled assertion-drill records. The installed reader's stdout JSON `hookSpecificOutput.additionalContext` must contain a legible `FAIL` headline for `clavain-shell` with **psey forced assertion**, together with existing FAIL/STALE findings. Retain stdout, stderr and the exact input records; the name must survive the reader's 120-character line and 4,500-character total caps. Detail-only presence is insufficient. Normal production reader output is also retained after restoration. Authoritative scheduled results cannot be replaced by a manual fixture run, and full failure names/reasons remain in status detail after clone cleanup.

    ```check
    cd "$HOME"  # zklw; reader input prepared from real records as above
    RIG_HEALTH_DIR="$DRILL_ROOT/reader/health" python3 "$HOME/.claude/hooks/report-rig-health.py" \
      </dev/null > "$DRILL_ROOT/reader/stdout.json" 2> "$DRILL_ROOT/reader/stderr.txt"
    jq -er '.hookSpecificOutput.additionalContext' "$DRILL_ROOT/reader/stdout.json"
    # stdout includes FAIL clavain-shell + psey forced assertion alongside existing findings
    ```

12. **Scope and restoration hold.** Diffs and deployment inventories show only Clavain and dotfiles implementation commits. No production installer requirement, runtime dirty guard, production lock code, fleet recipe/hash/trigger, `tests/verification-pilot.json`, Sylveste source or unrelated dirty file changes. No Mac toolchain installation or repair/waiver of the two Mac calibration assertion failures; removing ambient candidate execution is the expressly scoped safety fix. Task-owned temporary services/drop-ins/overrides/designation are removed, prior timer state restored, and the normal scheduled path verified again. Retain before/after deployment and source-status inventories. Shell changes parse and applicable behavior tests pass under Mac `/bin/bash` 3.2, with any nested/platform omissions explicitly counted.

13. **F3 / Sylveste-we1q — scheduled tests preserve live locks and never execute an ambient temporary candidate.** Safety regression output fails on the old unsafe source without executing its deletions, then passes on the repaired source. The original 42 sprint case identities/assertions remain and pass without skips on zklw, supplemented by logged lock arguments/unlocks and acquisition-denied coverage. Diff removes both shared-lock deletions and retired global cleanup, while production lock code remains unchanged. In the repaired sprint run and real scheduled whole-shell run, a uniquely owned held `sprint-claim/psey-safety-<random>` sentinel retains its owner metadata/inode and rejects a competing acquisition before/after; raw transcripts show only that owned scope released. Candidate selection is unset-by-default and the dated `/tmp` fallback is absent; regression output shows unset yields the single named omission, invalid explicit candidate fails, explicit private selection never falls back, and the scheduled child clears inherited candidate selection. Keep Sylveste-we1q and arming blocked until these artifacts exist.

    ```check
    cd "$CLAVAIN_SNAPSHOT/tests"
    uv run pytest structural/test_shell_suite_safety.py -v
    cd "$CLAVAIN_SNAPSHOT"
    bats tests/shell/test_lib_sprint.bats --tap
    # exit 0 on equipped zklw; attach case list, call log and real scheduled sentinel proof
    ```

## Landing order, review, and handoff

1. Re-extract/seal revision 2 once and obtain the single clean independent re-review. Land reviewed Tasks 0–3 in **mistakeknot/Clavain**, immutable repository ID **1151593132**, including the lock/candidate fix before any full suite execution, and verify installer results on both hosts. Push only within execution authority; obtain the main-branch Actions evidence. Make that exact committed source available on zklw through the existing Git synchronization path.
2. Land Task 4 in **mistakeknot/dotfiles**, immutable repository ID **1137350173**, unarmed. Deploy only changed harness/reader paths through existing narrowly scoped links; do not run a broad agent installer. Prove the fresh-clone build/coverage, safe lock sentinel, and healthy plus timeout whole-run budget with temporary designation. Reuse/create the interphase follow-up in the existing workspace tracker and record its actual ID/expiry before arming. No new tracker or migration task.
3. Land Task 5 in dotfiles and deploy the server marker only after Sylveste-we1q and the baseline/budget gates pass. Perform Task 6's production and unattended proofs. Keep `Sylveste-psey` open until every criterion has surfaced evidence. No files land in the Sylveste repository itself.

Live read-only repository-ID and `zklw-ci status --repo ... --json` inspection during revision 2 confirmed Clavain remains `verification-pilot-passed-broader-migration-open`, `triggers: [manual]`, task **mk-ag2s.25**, with pinned verification recipe. Dotfiles remains `pending-inventory`, disabled, task **mk-ag2s.32**. Those campaigns remain outstanding; this plan neither claims completion nor claims/duplicates their migration tasks. Do not edit `scripts/ci-verification.sh`, its pinned `9a4a13c3…` verification-contract digest, the fleet recipe, or registration. Revision-1 tracker access failed on the workspace Dolt lock; revision-2 `bd prime` returned no text and repository-context `bd show` reported no database. The supplied Sylveste-we1q dependency is not claimed as independently refreshed; no tracker mutation or substitute tracker was created. Executor must resolve the actual workspace tracker before claiming/closing tasks or recording the interphase follow-up.

Preserve the supplied governed decision: selected package **0.6.318**, policy `/Users/sma/.claude/plugins/cache/interagency-marketplace/clavain/0.6.318/config/routing.yaml`, policy SHA256 **8148151129e30324c18147dec516223b5e672c82dd8cd0c99bd529bd3cc98fea**, profile **default**, role **planning**, profile **planning-astra**, model **gpt-6-astra**, effort **xhigh**, service tier **standard**, classification **difficult-verification**, frontier required, review requirement **existing-gates**. Revision 2 read the installed using-clavain skill and selected reasoning-routing canon; it preserves the supplied resolution. A separate temporary context-file write was rejected by workspace permissions, so the accountable revision and handoff JSON are embedded in this sole deliverable. No fresh role resolution or model/effort/usage receipt is asserted; the dispatch caller retains the actual author receipt. This does not waive any downstream routing or independence gate.

Accountable handoff context (embedded here to honor the one-file planning request):

```json
{
  "reasons": ["difficult-verification"],
  "rationale": "The design follows an existing harness, but acceptance requires real launchd/systemd execution, forced missing dependencies, clean committed source snapshots and measured whole-run timing. Fixtures and configuration cannot prove those outcomes.",
  "domain": "test infrastructure",
  "available_models": null,
  "investigation_active": false,
  "handoff": {
    "decisions": ["delete vestigial shared lock cleanup", "explicit candidate opt-in only", "whole structural suite", "fresh independent clones with clavain-cli-go build", "server-only designation", "15-minute existing Actions ceiling with 274-skip historical baseline", "six-skip zklw hypothesis with expiring interphase allowance", "early bounded checks in existing rig-health"],
    "constraints": ["revision 2 re-sealed once then one clean independent re-review before implementation", "F1 and Sylveste-we1q before F3 arming", "two repositories only", "no fleet change", "no new Linux Actions dependency", "Bash 3.2", "no weakened assertions or hidden skips"],
    "verification": ["safe red-before-green and live held-lock preservation", "installer on both hosts", "real no-ic execution", "main-branch Actions Tier 2 and coverage delta", "fresh-clone 19-case binary cohort", "actual scheduled fault matrix", "healthy and actual-timeout full-run ALL_CHECKS freshness", "per-check production and unattended timer proof", "real mixed-red reader stdout"],
    "escalation": ["baseline premise disproved", "unexpected failures or coverage omissions", "timing or source isolation cannot meet contract", "review or operational blocker", "two capability failures"]
  }
}
```

Execution resolves its role from this context and uses the packaged dispatcher with `CLAVAIN_ROUTING_POLICY` and `CLAVAIN_DECISION_CONTEXT`. Preserve the supplied independent **review-fable / claude-fable-5-1 / high / standard** seat and bind `--producer-identity` from the actual author receipt, not this document's model string. The revision-1 DO NOT SHIP verdict stands until revision 2 is re-sealed and receives its single clean re-review; neither is claimed performed here. Preserve existing review gates before implementation/landing; use the standing `claude-opus-5` fallback only upon a documented Fable quota limit, with the separate exception policy and both receipts. A permission/authentication failure is not that exception. Keep frontier involvement for deviations and scheduler acceptance.

## Non-claims and escalation

This document is a plan. It does not claim the installer or lock hazard is fixed, suites pass now, Actions is green, the lane is deployed, fleet migration is complete, installed ic matches cloned Intercore, tests cover uncommitted edits/latest remote main, the Mac executes all assertions, or skipped cases are passes. No implementation, suite remeasurement, scheduler start, deployment, publication, re-seal or independent re-review was performed during this revision. Read-only source, status and service inspection are identified above; the hosted histogram remains review-attributed because full re-count retrieval failed. The six-skip ceiling and cold-build budget are hypotheses with explicit execution gates. Unavailable version/tracker evidence stays unknown. A clean source clone isolates source dirt, not arbitrary global test effects.

Stop the affected execution and return with evidence if:

- The recorded installer cause no longer reproduces, the accounting cohort is no longer 29/28, or clean snapshots still trigger runtime-canary dirt failures. A disproved premise needs immediate frontier reassessment.
- The complete zklw suites have unexpected failures, missing helper/tool/source dependencies, extra skips, shared-state side effects, or source mutations. Do not quarantine cases, install new prerequisites without scope, or alter production guards to arm the lane.
- Task 0 cannot preserve the same sprint assertions while eliminating shared cleanup, its sentinel changes/disappears, or another suite touches live state. The confirmed sprint-claim collision is owned work under Sylveste-we1q, not a deferred question. Any further hazard blocks arming pending scoped review; a private clone/HOME is not filesystem isolation.
- Historical hosted TAP contradicts the 274/10 baseline, the fresh-clone skip ceiling is disproved, the required interphase follow-up ID cannot be recorded, or its allowance expires. Keep the coverage gap visible; do not silently rebaseline, extend expiry or hide cases.
- The structural suite exceeds 300 seconds, shell exceeds 900, full health execution starves existing checks/exceeds 2,400, or Actions still cannot complete below 15 minutes. Return measured phase times; do not silently raise global ceilings, reduce coverage, or add Actions dependencies.
- A new failure lies in the intervening Actions task-attribution step, Mac calibration, fleet automation, or unrelated dirty work. Identify it without expanding this plan or calling the blocked acceptance complete.
- Actual scheduler proof, deployment authority, required independent review, source/tool identity, or tracker access is unavailable. Preserve the open gate and continue only independent authorized work. A bare nonzero exit is not evidence of a quota or capability failure; two demonstrated capability failures require escalation.

If deployed behavior regresses, stop scheduling these new suites by restoring the previous reviewed harness/marker deployment within rollback authority, retain all status/log evidence, and explicitly record the resulting coverage gap. Never manufacture a passing record or relax skip limits as rollback. Restore temporary overrides and verify the ordinary scheduler path before ending execution.
