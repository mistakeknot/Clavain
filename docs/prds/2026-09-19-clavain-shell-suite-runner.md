---
artifact_type: prd
bead: Sylveste-psey
stage: design
prior_implementations:
  - bead: Sylveste-ytm
    title: "interverse test-baseline restoration — green the rotted suites (interphase 71/91 bats, Clavain 165 shell, interline 2 structural, interflux backpressure Sylveste-9cs)"
    status: closed
    matched_keywords: [bats, test-baseline]
    verdict: orthogonal
    rationale: "ytm's scope was a one-time repair pass across five plugins and it shipped clean on both platforms. This PRD's scope is scheduled execution, which ytm explicitly did not deliver. The recurrence eight weeks later is the evidence that these are different scopes, not the same one — but the repair half of F1 is a literal repeat of ytm's work, which is a warning this PRD acts on rather than a reason to subsume it."
  - bead: sylveste-wdf2
    title: "Doc monitoring automation (replaces interscout shape)"
    status: open
    matched_keywords: [rig, scheduled]
    verdict: orthogonal
    rationale: "Keyword coincidence. wdf2 is document/context auto-refresh inside interwatch; it shares no surface with shell-suite execution."
---

# PRD: Give Clavain's shell suite a runner that outlives the session that fixes it

## Problem

Clavain's GitHub Actions job has not reached its bats tier since 2026-09-08, so 872 shell assertions have had no automated execution for eleven days — and during that window a real, still-unfixed regression was reported correctly and then buried under an unrelated red badge.

## Solution

Repair the eight real failures, restore the Actions gate by marking the 28 tests that require the `ic` binary, and install a scheduled rig self-check on zklw so the suite has an owner that survives the session that fixed it.

## Prior Implementations (Shipped-State Reconciliation)

Two in-tree epics matched two keywords each; both are `orthogonal`, and one of them is the reason this PRD exists.

`Sylveste-ytm` (closed 2026-07-21) greened these same suites on both platforms — *"Clavain 782 structural + 654 bats FAILCOUNT=0 … zklw: same suites all 0 failures … Zero quarantines needed"* — and installed nothing that would run them again. Eight weeks later the suite is at 10 failures of 872. The repair half of F1 is therefore a repeat of shipped work, and F3 is the part that makes it the last repeat. `sylveste-wdf2` is document auto-refresh inside interwatch and shares no surface.

## Features

### F1: Repair the eight real cross-platform bats failures

**What:** Fix the six `test_codex_installer` failures and the two `test_runtime_evidence_canary` failures, both of which reproduce on zklw's Linux checkout and are therefore not environment artefacts.

**Acceptance criteria:**
- [ ] `bats tests/shell/test_codex_installer.bats` exits 0 on both Clavain and zklw
- [ ] `bats tests/shell/test_runtime_evidence_canary.bats` exits 0 on both Clavain and zklw
- [ ] The installer fix is in the fixture's contract with `install-codex.sh:1067`, not a relaxation of the production requirement added by `bc5e2f5`
- [ ] Each fix is demonstrated red-before-green at the pre-fix commit

### F2: Restore the Actions gate so Tier 2 is reached again

**What:** Mark the 28 tests in `tests/structural/test_claude_usage.py` that require the `ic` binary and deselect them when it is absent, so Tier 1 stops failing for a reason that has nothing to do with the structural suite.

**Acceptance criteria:**
- [ ] With `ic` on PATH, all 29 tests run and pass — the marker changes nothing where the binary exists
- [ ] With `ic` hidden from PATH, the 28 deselect and the suite exits 0 rather than reporting 28 failures
- [ ] The deselection is *reported*, not silent: the run states how many tests were held back and why
- [ ] A Plugin Tests run on main reaches and completes `Tier 2 — Shell tests (bats)`

### F3: Install the scheduled rig self-checks

**What:** Add `clavain-shell` and `clavain-structural` checks to `rig-health-check.sh`, modelled on `intercore-tests`, gated on a designated-host marker, so the suite and the 28 relocated tests both run daily on zklw where every dependency exists.

**Acceptance criteria:**
- [ ] Both checks appear in `ALL_CHECKS` so the watchdog can name them when a run does not reach them
- [ ] On an undesignated host the checks write `skip`; on the designated host with `bats`, `yq` or `gawk` missing they write `fail` — proven by forcing each path against an override, not by reading the code
- [ ] `clavain-structural` runs the 28 `ic`-dependent tests and fails if `ic` is absent on the designated host
- [ ] A failing assertion in the suite turns the check red and names the failing tests in its detail file
- [ ] Both checks are reachable inside the run's existing ceiling; the suite takes 8m41s on the Mac and is bounded accordingly

### F4: Make the silent skips visible

**What:** Report the suite's skip count separately from its pass count, so a Mac run that silently withholds 51 assertions cannot be read as a full run.

**Acceptance criteria:**
- [ ] The check summary states passed, failed and skipped separately, as `guard-tests` already does
- [ ] A run whose skip count exceeds a declared floor is visible in the summary rather than folded into the pass count
- [ ] The four current skip reasons — `yq`, `gawk`, `interphase`, Intercore calibration candidate — are recorded with their counts so the next reader knows what was not looked at

## Non-goals

The zklw fleet CI lane. `mistakeknot/Clavain` is registered under `mk-ag2s.25` with `triggers: ["manual"]`, pinned `recipe_sha`/`recipe_sha256`, and a hard-pinned SHA256 of `tests/verification-pilot.json` inside `scripts/ci-verification.sh`. Adding a bats check there requires two protected fresh guests at identical inputs. Out of scope, and no duplicate migration task is to be created.

Installing `yq` and `gawk` on the Mac. F4 makes the shortfall visible; closing it is a separate call about what this machine should carry.

Retiring `.github/workflows/test.yml`. The fleet drift report already flags it as `linux-actions-present`; that retirement belongs to the campaign, not here.

The two Mac-only `test_b3_calibration` failures. They pass on zklw at the same code, so they do not block the designated-host lane. Recorded, not repaired.

## Dependencies

`rig-health-check.sh` lives in `~/projects/dotfiles`, so F3 lands in a second repository and must be deployed to zklw before its acceptance criteria can be checked there.

F3's acceptance depends on F1: arming a lane against a known-red baseline recreates the exact condition this bead names.

## Open Questions

Whether `clavain-structural` should run the whole structural suite on zklw or only the 28 relocated tests. The narrow version is honest about what moved; the wide version is cheap and catches more.

Whether the Actions job's `timeout-minutes: 5` still holds. The last green run finished in 4m28s with 830 tests; there are 872 now.
