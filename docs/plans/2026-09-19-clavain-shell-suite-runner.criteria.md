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

4. **F2 — the existing Actions lane actually reaches and completes Tier 2 within its coverage ceiling.** Retain the main-branch run ID/head SHA containing Tasks 0–3, successful Tier 1/Tier 2 conclusions, direct bats exit 0, complete TAP, exclusive counts/histogram and whole-job elapsed time below 900 seconds. **The allowed skip set is defined by identity, not by a count.** It is the retained historical run-34150176247 baseline identities (830 cases, 274 skips, 10 reasons), plus the cases of `tests/shell/test_b3_calibration.bats` under its existing `lib-interspect.sh not found` reason — that file's `setup()` skips every case because the workflow checks out no interspect sibling, and the file grew from 37 cases at `0ac49e82` to 55 at HEAD, so the historical 274 is unmeetable at any commit containing Tasks 0–3. No other new skipped case identity, no new reason, and no other per-reason increase. The historical baseline must first be verified from its full log; decreases remain visible with explanations. The first Tier-2-reaching run must reproduce the derived count, or the question returns to review rather than the baseline being silently reset. Reporter regression output proves unchanged baseline emits no coverage-change warning and any count/reason/identity change is surfaced. Workflow diff adds no action, checkout, dependency-installation step or trigger. A green badge alone is insufficient.

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

