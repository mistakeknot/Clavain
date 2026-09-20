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

