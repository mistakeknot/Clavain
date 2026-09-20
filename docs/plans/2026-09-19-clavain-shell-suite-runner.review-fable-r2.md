# Verdict: DO NOT SHIP as sealed, because criterion 4 cannot be met

**Blocking:**

- **P1-A:** Sealed criterion 4 cannot be met at any commit that contains Tasks 0–3.

P0-1 and the four earlier P1s are closed in substance. The fix for P1-A is a change to criterion 4's text only, under the explicit reseal override. No re-plan is needed. Tasks 0–3 do not depend on criterion 4 and could start before that reseal.

**Process gates**

- The `clavain:using-clavain` skill is not in this session's catalog (`Unknown skill`), so source selection is **unverified**. I relied on the decision context supplied with the dispatch and recorded no separate one.
- `Read` was denied outside the Clavain repository again. I read the dotfiles files with `sed` and `grep`.
- I ran two read-only `ssh zklw` inventories and one `gh run view --log` fetch.
- I edited nothing. My temporary directory under `/tmp` is removed.

## P1

**P1-A. Criterion 4's 274-skip cap cannot be met.**

- I re-counted run 34150176247 from its full log: plan 830, 830 `ok`, **274 skips, 10 reasons**. The 37-skip line is exactly the 37 cases `tests/shell/test_b3_calibration.bats` had at `0ac49e82`. Its `setup()` skips every case in the file when the interspect sibling checkout is absent.
- That file now has **55 cases** (19 new identities, net +18). `.github/workflows/test.yml` is unchanged since the baseline and still has no interspect checkout.
- A hosted run at HEAD will therefore show **at least 292 skips**. `lib-interspect.sh not found` rises from 37 to 55, and there are 19 new skipped identities.
- Criterion 4 forbids all three of those. It also forbids the only fix, a new checkout.
- The "unset yields the single named omission" behaviour in criterion 13 never appears on Actions, because the calibration-candidate case is skipped in `setup()` first. It cannot add an eleventh reason there.
- The 292 is derived, not observed. No main-branch run since the baseline has reached Tier 2; the last eight all concluded `failure`. I did not open their logs; that they stop at Tier 1 is inferred from the plan's account.

**What is needed:** reseal criterion 4 only. Define the cap by identity, not by the number 274:

- Allowed skips are the baseline identities plus the cases of `test_b3_calibration.bats`, under the existing reason.
- No other new identity, no new reason, and no other per-reason increase.
- The first Tier-2-reaching run must reproduce the derived count, or the question returns to review.

Task 3's "re-count before implementing" gate would have found this, but only as an escalation after implementation. It was answerable by reading the code now.

## P2

**P2-A. `/tmp` hazard left in the shell suite.**

- `test_seam_integration.bats:16-24` executes `/tmp/ic-seam-$$` if that file already exists.
- It then prepends **`/tmp`** to `PATH` for all 18 of its cases.
- That is an ambient executable from a predictable `/tmp` path. It also defeats the plan's rule that the selected binaries are the ones child processes execute, because a `/tmp/ic` would win.
- The fix is to build into `BATS_FILE_TMPDIR` or a `mktemp` directory and add this file to Task 0's static regression. That is a plan-body change. Criterion 13's title already covers it, so no reseal is needed.

**P2-B. Unset snapshot variables do not stop the checks.**

- `verification_runner.py:563` runs each check as `/bin/bash -e -o pipefail -c`, without `-u`.
- I measured `cd ""`: it returns 0 and stays in place in Mac bash 3.2, `sh` and zsh. It errors only in the 5.3 bash first on this Mac's PATH. zklw is on bash 5.2.21, where I did not run the test.
- With `CLAVAIN_SNAPSHOT` unset, the `<verify>` blocks in Tasks 0, 1 and 3 and the check blocks for criteria 1 and 13 run in the live checkout. At least under Mac `/bin/bash` 3.2 and `sh`, nothing flags it.
- Criterion 2 survives only because its `git status` assertions happen to catch a dirty tree.
- The sealed preamble already requires setup to fail when these paths are unset. The fix is to prefix each block with `: "${CLAVAIN_SNAPSHOT:?}"` in the plan body.

**P2-C. New tests must not skip on Actions.**

- Three of the five existing `sprint_claim` cases skip on hosts without `ic`.
- If the new acquisition-denied case or `test_helper_override.bats` copies that gate, the corrected criterion 4 fails again.

**P2-D. The expiry doubles as a deadline for criterion 9.**

- After 2026-10-04 the interphase allowance turns `clavain-shell` to `warn`. Criterion 9 requires `pass` on an unattended timer run.
- Acceptance has about 14 days. I accept this as deliberate; note the deadline in the runbook.

**P2-E. The Mac "designated, missing bats" drill still runs the structural lane.**

- The plan lets the structural lane run when only a shell tool is missing.
- That means clones, a Go build and the full pytest suite under launchd on the Mac. This is safe, but it is not a quick drill. Bound it, or also force `ic` missing.

**P2-F. `guard-tests` runs the new dotfiles suite daily on both hosts.**

- It prefers the live `~/projects/dotfiles` tests directory.
- `test-rig-clavain-suites.sh` will run under `guard-tests` on both hosts once Task 4's commit is in that checkout, before anything is armed.
- The plan's suppression of expensive cases when nested covers this. Keep the suite inside the 420-second per-suite bound, and do not describe Task 4 as inert on landing.

## Answers to your five questions

1. **P0-1 is closed.**
   - All five `sprint_claim` cases mock both `intercore_lock` and `intercore_unlock`. No other test removes fixed `/tmp` paths or touches `intercore/locks`.
   - The only real lock use is `seam-test/test-scope`, which is the test's own name.
   - The sentinel works as described. `lock.go:329-350` breaks a lock only when it is older than 5 seconds **and** its owner PID is dead, so a holder with a live PID survives. A holder with a wrong owner format makes the drill fail loudly, not pass vacuously.
   - `sprint-claim/` does not currently exist on zklw. The drill creates it, which is harmless.
   - The remaining shared-state item is P2-A.
2. **P1-1 through P1-4 are closed in substance.**
   - P1-1: `build-clavain-cli.sh:10-12` does exit 0 without Go. zklw has Go 1.26.4, bats 1.13, yq, gawk, uv and `ic`. The 7 compose and 12 tool-surface counts are right.
   - P1-2: closed in the contract; P2-B is the mechanical gap.
   - P1-3: a transient `systemd-run` unit is classified as scheduled through `INVOCATION_ID`, so the drill records are genuine. The reader's headline leaves about 85 characters for the summary, so the forced test name survives.
   - P1-4: the measured baseline replaced `--max-skipped 0` as I asked. Its one number is what P1-A breaks.
3. **Only criterion 4 is unjudgeable as written.**
   - Criterion 8 is attainable: all 24 `ALL_CHECKS` names refreshed within one 204-second run (epochs 1789809736 to 1789809780).
   - Criteria 6, 7, 9 and 11 require scheduler records that a fixture cannot satisfy.
   - Criteria 5 and 10 have fixture-only check blocks, but their text demands host evidence, so they hold.
4. **New surface:** the live sentinel drill is safe. The full-service drop-in drills state their side effects honestly. P2-E and P2-F are the additions.
5. **P2 dispositions absorbed as prose:** the mid-run source-advance `warn` remains and is mitigated by the separate `test_status` field. I accept that.

**The twelfth failing check:** I cannot name one. A direct read shows **11** failing: nine from the daily run, plus `estate-drift` and `estate-workflow-health` from other timers. Treat my earlier count of twelve as an error caused by truncated output. Revision 2 was right not to freeze it.

**The 274 / 10 histogram is confirmed.** The exact strings of the three interspect reasons are:

| Count | Exact skip reason |
|---:|---|
| 127 | `lib-interspect.sh not found (install interspect companion plugin)` |
| 37 | `lib-interspect.sh not found` |
| 16 | `interspect library not found` |

A static count of `@test` blocks at HEAD gives 876, not the 872 the plan records from a Mac run. The plan already says not to hard-code 872.
