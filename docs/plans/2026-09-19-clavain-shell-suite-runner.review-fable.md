# Verdict: DO NOT SHIP as sealed

**Blocking:**

- **P0-1:** Arming the zklw lane has the shell suite delete live production lock state.
- **P1-1, P1-2:** Two sealed criteria cannot be met as written.

**Not blocking:** Tasks 1–3 (the Clavain-only work) are sound and can proceed once P1-2 and P1-4 are resolved. Tasks 4–6 need P0-1 fixed. The criteria must be re-extracted and re-sealed before anyone implements against them.

**Process gates**

- The `clavain:using-clavain` skill is not in this session's skill catalog, so source selection is **unverified**.
- I recorded no separate decision-context JSON and relied on the one supplied with this dispatch.
- `Read` was denied for files outside the Clavain repository, so I read the dotfiles files with read-only shell commands instead.
- I edited nothing.

## P0

**P0-1. The `/tmp` hazard is wider than the plan says.**

The hazard the plan misses is on the very next line of the file it cites:

- `tests/shell/test_lib_sprint.bats:25` and `:42` run `rm -rf /tmp/intercore/locks/sprint-claim` in every setup and teardown. That is 42 tests, so 84 deletions per run.
- That path is the production mutual-exclusion directory for sprint claims:
  - `hooks/lib-sprint.sh:849` calls `intercore_lock "sprint-claim"`.
  - `cmd/clavain-cli/claim.go:71-78` takes the same lock.
  - The path is hard-coded at `hooks/lib-intercore.sh:359` and `core/intercore/internal/lock/lock.go:16`, with no environment override.
- On zklw right now, `/tmp/intercore/locks/` holds `bead-claim`, `remontoire-cycle`, `runtime-evidence-adopt` and `seam-test`, and 33 claude/codex processes are running.
- The `/tmp/sprint-lock-*` globs the plan does name match no production code, so they are harmless legacy paths.

If the daily run deletes a lock directory while a session holds it, a second claimer acquires the lock and two sessions claim the same bead. The window is short, but the run is unattended, daily, and on the host where sessions run.

Deferring this to an escalation condition is wrong:

- "If those paths can collide" was answerable by reading the code, and the answer is yes.
- No task owns the question, and no sealed criterion covers it.
- The fix is small. The sprint tests already mock `intercore_lock` (`:430`, `:461`, `:496`), so the `rm` lines appear vestigial and can be removed or scoped to a test directory.

**What is needed:** a pre-arming task and a criterion, which means a new seal.

**Same class, lower severity:** `test_b3_calibration.bats:148` executes `/tmp/adaptive-routing-20260912/ic-calibration-candidate` if that file exists. Under a daily timer, that is a predictable executable path in world-writable `/tmp` on a multi-user host.

## P1

**P1-1. A fresh clone cannot reach the six-skip ceiling.**

- `.gitignore:45` ignores `bin/clavain-cli-go`.
- `test_compose.bats:11` (7 tests) and `test_tool_surface.bats:11` (12 tests) skip with "clavain-cli-go not built" when that binary is absent.
- The 57-skip, four-reason baseline was measured in a developer checkout where the binary was built.
- The isolated-clone proof at `512a5b7` ran only the two canary tests.
- The plan has no build step and forbids adding prerequisites without scope.

Detection works: a new skip reason becomes `warn`, which blocks arming. But Task 5's baseline gate and criterion 10 cannot pass as written. The plan should add an explicit `build-clavain-cli.sh` preparation step. It should also state that the ceiling of six is a hypothesis until a fresh-clone run on zklw measures it.

**P1-2. Sealed criterion 2's check depends on where it is run.**

- Run in this working directory, `bats tests/shell/test_runtime_evidence_canary.bats` fails.
- It fails because the canary refuses a dirty checkout, and this checkout has ` M .gitignore`.
- That is a check going red for a reason unrelated to what it measures, written into the acceptance contract.
- Task 1's `<verify>` block has the same defect.
- The check must name the clean-snapshot working directory.

**P1-3. The new checks land on a zklw harness that is already red.**

- Twelve zklw check status files currently read `fail`: `estate-drift`, `estate-workflow-health`, `guard-tests`, `finding-age`, `hook-integrity`, `ic-provenance`, `job-outcomes`, `marketplace-divergence`, `peer-agreement`, `publish-drift`, and two the truncated output did not show.
- `rig-health.service` ended with `exit-code` on both 2026-09-18 and 2026-09-19.
- A `clavain-shell` FAIL would be one more line in that list. That is the same burial mechanism as the Actions badge, moved to zklw.

The plan never mentions this. It should record the existing red baseline. Acceptance should then observe the real reader output on zklw, with the forced-assertion FAIL and its test name legible while the other FAILs are present.

One consequence for criterion 9: the forced service run will show `Result=exit-code` regardless of the new checks, so it has to be judged from the per-check status JSON.

**P1-4. Actions "green" would cover about two-thirds of the suite.**

Measured skips in run `34150176247`: 274 of 830, across 10 reasons.

| Count | Reason |
|---:|---|
| 127 + 37 + 16 | interspect library not found (three variants) |
| 39 | Go build failed |
| 19 | clavain-cli-go not built |
| 18 | intercore source not available |
| 10 | ic not available |
| 5 | interphase not installed |
| 2 | sibling Intercore checkout is required |
| 1 | jsonschema not installed |

- The 5 + 2 + 1 lines are not repeated in the consequences below.
- The plan carries the Mac's four-reason picture onto Actions (question 8).
- `--max-skipped 0` will therefore fire `::warning::` on every run, forever. A warning that fires every time cannot signal a change in coverage.
- Criterion 4 asks only for "separate skipped counts". A run with 800 skips would satisfy it.
- The plan should use the measured hosted skip count as a baseline so the warning fires only when that count changes.
- This sits in the plan body rather than the sealed criteria. Criterion 4 should still gain a skip ceiling.

## P2

**P2-1. Bounds arithmetic (question 4).**

- The arithmetic holds, but only because of a measurement the plan never cites.
- zklw's real run takes about 205 seconds (09:19:36 to 09:23:01 on 2026-09-19).
- The Mac's run lasted at least 709 seconds (spread of check write times; the full run is longer).
- Worst case on zklw is 1,350 + about 205 = about 1,555 seconds, which is inside 2,400.
- The stated rationale is wrong:
  - Existing nominal bounds sum to about 8,190 seconds, plus 44 × 420 seconds for the guard suites.
  - So "leaving 1,050 seconds for existing checks" guarantees nothing.
  - Placing the new block first also means a wedged new lane costs 24 established checks up to 1,350 seconds, as well as its own slot.
- Placing the block first is acceptable on the measured numbers. The plan should record the 205 seconds as the basis.
- Criterion 8 only exercises the healthy path.

**P2-2. The 15-minute Actions ceiling (question 5).**

- The ceiling is sound and within "repair".
- Tier 2 took 170 seconds of the 268-second job.
- The only new dependency is `python3`, and the job already installs it with `setup-python`.
- The intervening task-attribution step passed in both cited runs.

**P2-3. Source-freshness holes (question 6).**

- The `ic` binary under test is whatever is installed on PATH. It is not built from the cloned Intercore SHA, and zklw's `ic-provenance` check is currently FAIL. The detail should record the binary's path, version and hash.
- The captured HEAD is whatever the checkout happens to be on, including a detached HEAD or a feature branch. The lane should warn when HEAD differs from `refs/heads/main`.
- A local checkout that lags GitHub for weeks still yields a current-looking pass.
  - The plan's disclaimer about this is honest.
  - Even so, the summary should show the commit date.
  - It should also compare HEAD against the already-fetched `origin/main`.
- Downgrading a pass to `warn` when source advances mid-run is another warning with an unrelated cause, on a host where sessions commit often.

**P2-4. Skip policy (question 7).**

- Five "interphase not installed" skips are a certainty, not an allowance.
  - Those cases hard-code `/root/projects/interphase`, which is not the installing user's home path on either host.
  - The skip reason is false on both hosts, because interphase is installed.
- The allowance is honest only if it carries a tracked follow-up bead and an expiry.
- The summary should say those cases cannot run on any host.

**P2-5. Ambiguous or vacuous criterion text.**

- Criterion 8's "every original expected harness status" is ambiguous. It should name `ALL_CHECKS`, because `EXPECTED_BY_HOST` entries belong to other timers.
- A full harness re-run under `systemd-run` repeats the side effects of the existing checks, such as peer attestation and the restore drill. The plan does not assess that.
- Criterion 11's manual-cannot-overwrite clause tests behaviour `rig-health-write.py` already has, so it cannot fail. That is harmless.
- The `com.arouth.*` drill label does match the production agent on this Mac, `com.arouth.rig-health`.

**Confirmed as the plan claims:**

- There are 29 accounting cases, with `test_zaka_rejected_before_any_model_call` as the one case that needs no `ic`.
- `sync-agent-instructions.py:67` resolves its helper from `--source`.
- The negative test at `test_codex_installer.bats:128` removes the wrong file.
- Interspect resolves relative to the sibling checkout, so the snapshot layout works.
