# Plan: every Clavain hook reads the session it is in, and the deployed hook is the one in HEAD (mk-rd9f + mk-f0mz)

**Goal:** intercore 49d193d1 (project `/Users/sma/projects`). **Beads:** mk-rd9f (session registers), mk-f0mz (deployed clavain-cli and plugin cache vs HEAD). **Date:** 2026-09-02. **Author:** session 45f5fb3c (Claude Fable 5.1).

**Branches:** Clavain `fix/mk-rd9f-session-registers` stacked on PR #31 (`fix/mk-hxgi-next-goal-audit`, d90e6df). interphase `fix/mk-rd9f-session-registers` from `origin/main` (83f7cfe). dotfiles `fix/mk-f0mz-clavain-deployed` stacked on PR #3 (`fix/mk-rd1x-standing-vs-new`, 6284fd9), edited on zklw.

## Why (one paragraph)

mk-hxgi found that the two next-goal receipt writers keyed on `CLAUDE_SESSION_ID`, a variable that exists only after `hooks/session-start.sh` has written it into `CLAUDE_ENV_FILE`. Claude Code 2.1.259 itself exports `CLAUDE_CODE_SESSION_ID` into the Bash tool environment (the binary carries it in its managed-env list) and hands every hook its `session_id` on stdin. Thirty-five more lines in twenty-three Clavain files, and seven lines in five interphase hooks, still read `CLAUDE_SESSION_ID` alone. In any session whose start hook did not fire (the plugin-cache loop of mk-i3u8, a hook timeout, `claude -p`, a runtime that never ran the hook) every one of them collapses to `unknown` or `default`: interphase's auto-claim writes `claimed_by=unknown`, treats `unknown` as unclaimed, and its session-end hook releases whichever session's claim it finds; the catalog-reminder sentinel and the AGENTS.md refresh throttle become one shared key for all sessions; interspect evidence rows and sprint claims lose their session. The second half of the defect is that the hook a session runs is the plugin cache copy, not the checkout. On Clavain the cache for 0.6.303 matches main today, but `installed_plugins.json` records `gitCommitSha` 2472a15 from 2026-08-08, twenty-nine commits behind: the record is not evidence. `publish-drift` asks whether committed source moved since the version commit, `marketplace-divergence` asks whether the clones agree, `ic-provenance` asks whether the deployed `ic` matches its source. Nobody asks whether the cache on this machine contains what is published, or whether the `clavain-cli` on PATH behaves like HEAD, which is how the Mac ran a five-week-old permissive CLI (mk-f0mz) and how a repaired audit could ship and stay dead.

## Register facts the design rests on

| register | who sets it | where it is visible | verified how |
|---|---|---|---|
| hook stdin `session_id` | Claude Code, per hook invocation | the hook process only | every hook here already parses stdin JSON |
| `CLAUDE_CODE_SESSION_ID` | Claude Code 2.1.259 | Bash tool environment; hook environment unverified | present in this session's Bash tool; name found in the 2.1.259 binary's env list |
| `CLAUDE_SESSION_ID` | `hooks/session-start.sh` via `CLAUDE_ENV_FILE` | Bash tool environment after the start hook ran | absent in sessions whose start hook did not fire (mk-hxgi) |
| `CODEX_SESSION_ID` | Codex runtime | peer telemetry hooks already chain it | unchanged |

Whether hook processes inherit `CLAUDE_CODE_SESSION_ID` is not established and the design does not depend on it: hooks read stdin first.

## Assumptions

- **A1.** When `CLAUDE_SESSION_ID` and `CLAUDE_CODE_SESSION_ID` are both set they name the same session. Precedence stays `CLAUDE_SESSION_ID` first, matching what mk-hxgi shipped on the base branch and what the mk-rd9f bead asked for, so a runtime that sets `CLAUDE_SESSION_ID` by hand keeps working. Reversible in one line of the helper.
- **A2.** "interphase statusline state" in the goal's DONE WHEN is two things, and the plan as first written saw only one. The bead-claim state (`claimed_by`, `claimed_at`, the `/tmp/interphase-bead-<session>` marker) that `bead-autoclaim.sh` writes and that heartbeat, session-end-release and interline's lane resolver key on is the first. The second is the interband bead envelope `~/.interband/interphase/bead/<session>.json` that interline's statusline actually renders, written by `writeBeadSideband` in `cmd/clavain-cli/sideband.go` — the kernel-authored successor to the retired `_gate_update_statusline` that `session-start.sh` still names (melange f-024, f-018). `sideband.go` already chained both registers; the seven other Go sites did not, and the fold below covers them.
- **A3.** "Published HEAD" for the rig check is `origin/main` of `mistakeknot/Clavain`, which is what the marketplace entry's source URL resolves to and what `ic publish` copies into the cache. A version tag is not used because the repo has none.

## Constraints the executor must respect

- Test first per work item: the failing test lands in the same commit as the fix or the one before it.
- No hook gains a new external dependency. `jq` is already required by every hook touched.
- Hooks stay fail-open. The helper never exits non-zero and never prints to stderr.
- Commit form: `git commit -F <file> -- <paths>`; trailers `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01RcpTgt7BZrKuMtAZWkLg5a`.
- No merges. The three PRs are mk's to land, in the order #30, #29, #31, then this Clavain PR; interphase PR; dotfiles #3 then this dotfiles PR.
- dotfiles edits happen on zklw in a worktree; the pre-commit `config-invariants` check fails from any worktree by construction, so commit with `SKIP_CONFIG_INVARIANTS=1` after a `readlink` check that the live units still point at the main checkout.

## Work items

### W1 — one helper, three registers (Clavain `hooks/lib.sh`)

Add `clavain_session_id [hook_input_json] [fallback]` to `hooks/lib.sh`: if `$1` is non-empty and parses, print its `.session_id`; else print `CLAUDE_SESSION_ID`, else `CLAUDE_CODE_SESSION_ID`, else `$fallback` (default `unknown`). Exit 0 always. The library's own companion-cache key (`# session=${CLAUDE_SESSION_ID:-$$}`, two sites) moves to the helper with `$$` as the fallback so a session-less process still gets a per-process cache rather than a shared one.

Tests (`tests/shell/session_registers.bats`, new): stdin wins over both env registers; `CLAUDE_SESSION_ID` wins over `CLAUDE_CODE_SESSION_ID`; `CLAUDE_CODE_SESSION_ID` alone resolves; nothing set gives the fallback; malformed stdin falls through to env; the helper is silent on stderr.

### W2 — every Clavain reader goes through the helper or the canonical chain

Hooks with stdin in hand pass it: `catalog-reminder.sh` (sentinel key), `agents-md-refresh.sh` (throttle file), `peer-telemetry.sh` and `peer-routing-telemetry.sh` (keep `CODEX_SESSION_ID` last in the chain), `session-start.sh` line 471 (uses the `_session_id` it already parsed). Library functions without stdin use the env chain: `lib-sprint.sh` (six sites), `lib.sh` (two, W1). Commands, skills and agents run inside the Bash tool, so they use the inline canonical chain `${CLAUDE_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-unknown}}`: `work.md`, `quality-gates.md` (two, one of them the jq form `env.CLAUDE_SESSION_ID // env.CLAUDE_CODE_SESSION_ID // "unknown"`), `execute-plan.md`, `sprint.md` (two), `resolve.md` (two), `reflect.md`, `strategy.md`, `route.md` (two, including the bare `"$CLAUDE_SESSION_ID"` argument to `sprint-claim`), `codex-delegate/SKILL.md`, `agents/workflow/codex-delegate.md`, `scripts/dispatch.sh`, `scripts/lib-routing.sh`. Prose in `next-goal.md` and `handoff.md` stops naming one register as the key.

Tests: `session_registers.bats` runs `catalog-reminder.sh` and `agents-md-refresh.sh` with `CLAUDE_SESSION_ID` unset and a stdin `session_id`, and asserts the sentinel and the throttle file are keyed by the stdin id, not `unknown` or `default`. The bead-claim path in `lib-sprint.sh` is exercised with `CLAUDE_CODE_SESSION_ID` only.

### W3 — the structural test that keeps it fixed

`tests/structural/test_session_registers.py` walks `hooks/`, `scripts/`, `commands/`, `skills/`, `agents/` and, for every line that reads the variable (`$CLAUDE_SESSION_ID`, `${CLAUDE_SESSION_ID`, `env.CLAUDE_SESSION_ID`), requires one of: the canonical chain (`${CLAUDE_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-`), the jq chain (`env.CLAUDE_SESSION_ID // env.CLAUDE_CODE_SESSION_ID`), an assignment or export (`CLAUDE_SESSION_ID=`), or the helper's own definition in `hooks/lib.sh`. The failure message names the file, line and the accepted forms. A second test asserts the helper exists and is exported by `lib.sh`. Comments and prose that name the variable without `$` are not reads.

### W4 — interphase reads the session it is in

Add `_interphase_session_id [hook_input_json] [fallback]` to `hooks/lib-phase.sh` (same contract as W1; interphase cannot source Clavain's library). Convert `bead-autoclaim.sh` (passes `$INPUT`), `heartbeat.sh` and `session-end-release.sh` (read stdin once, pass it), `lib-gates.sh` line 283 and `lib-discovery.sh` line 413 (env chain). The marker and heartbeat file names keep their `/tmp/interphase-bead-<id>` and `/tmp/clavain-heartbeat-<bead>-<id>` shapes.

Test (`tests/shell/session.bats`, new): with `CLAUDE_SESSION_ID` unset and a stubbed `bd` that records its arguments, `bead-autoclaim.sh` fed `{"session_id":"s-real",…}` writes `claimed_by=s-real` and the marker `/tmp/interphase-bead-s-real`; `session-end-release.sh` fed the same session releases it and fed another session does not; `heartbeat.sh` keys its throttle file on the stdin id. This is the DONE WHEN proof that interphase state is written in a session whose start hook did not fire.

### W5 — rig check `clavain-deployed` (dotfiles, zklw)

New `common/.local/bin/rig-clavain-deployed.py`, same shape and exit contract as `rig-dotfiles-deployed.py` (0 no findings, 1 findings, 2 could not assess; first stdout line is the summary). Steps:

1. Read `installed_plugins.json` for `clavain@interagency-marketplace` (installPath, version, gitCommitSha). Missing or unreadable: exit 2.
2. Resolve the source checkout: the directory `~/.local/bin/clavain-cli` resolves into (readlink -f, strip `bin/clavain-cli`), else `~/projects/Sylveste/os/Clavain`, else `~/projects/Clavain`. None is a git repo: exit 2.
3. `git fetch origin main` bounded at 60 s. On failure keep the existing `origin/main` and carry its last-fetch age into the summary as a caveat; a verdict against a stale ref is still a verdict, and the caveat says which.
4. Content: `git ls-tree -r origin/main -- hooks scripts bin commands agents skills config .claude-plugin` gives blob ids; hash each cache file the git way (`blob <len>\0<bytes>`, SHA-1) without invoking git per file. Findings: `STALE <path>` (differs), `MISSING <path>` (in tree, not in cache), `EXTRA <path>` (in cache under those roots, not in tree).
5. CLI: `~/.local/bin/clavain-cli` must exist and resolve into a git checkout (`CLI-ABSENT`, `CLI-NOT-A-CHECKOUT`); that checkout must be on `main` (`CLI-OFF-MAIN <branch>`) and not behind `origin/main` (`CLI-BEHIND <n>`); the resolved file must equal the `origin/main` blob (`CLI-STALE`); and `clavain-cli policy audit --zzz` bounded at 20 s must exit 1 (`CLI-PERMISSIVE rc=<n>`), which is the behavioral probe mk-f0mz asked for.
6. Detail records the recorded `gitCommitSha` beside the `origin/main` sha. It is reported, not judged: on Clavain it is stale today while the content is current.

Environment overrides for the test suite, each optional: `RIG_CLAVAIN_INSTALLED_FILE`, `RIG_CLAVAIN_CLI`, `RIG_CLAVAIN_CHECKOUT`, `RIG_CLAVAIN_NO_FETCH=1`, `RIG_CLAVAIN_CLI_PROBE` (command to run instead of `policy audit --zzz`).

Wiring in `rig-health-check.sh`: status name `clavain-deployed`, added to `ALL_CHECKS`; exit 0 pass; exit 1 **fail** with `--signature` = the sorted finding kinds and paths so an unchanged drift becomes warn + STANDING under mk-rd1x and a grown one fails again; exit 2 fail "could not assess"; bound 300 s. Fail, not warn, on drift, deliberately inverted from `dotfiles-deployed`: drift here is exactly the condition the goal exists to surface, and a daily run that sees it means the auto-publish hook did not close it.

Deployment: `link` lines in `install-server.sh` and `install-macos.sh`, so `rig-dotfiles-deployed.py` does not report the helper as UNDECLARED.

Test (`common/.claude/hooks/tests/test-rig-clavain-deployed.sh`, house `ck` harness with the NORESULT branch): builds a bare origin and a clone with a `bin/clavain-cli` stub that exits 1 on `policy audit --zzz`, a fake installed record and cache copied from the clone, then asserts in order: fresh cache and CLI on main exit 0; a hook edited in origin gives 1 with `STALE hooks/<name>`; a deleted cache file gives `MISSING`; the CLI symlink into a checkout parked on a branch gives `CLI-OFF-MAIN`; a checkout one commit behind gives `CLI-BEHIND 1`; a stub that exits 0 on the probe gives `CLI-PERMISSIVE`; a missing installed record gives exit 2. Then the real `rig-health-check.sh` is driven once with HOME in the sandbox to confirm the status file carries `clavain-deployed` with a signature.

### W6 — prose follows code

`CHANGELOG.md` entries in Clavain and interphase; `hooks/session-start.sh` comment names the real consumers; `docs/guide-goal-shape.md` untouched. The dotfiles commit message explains the fail-on-drift choice.

## Sequencing

W1 → W2 → W3 on the Clavain branch (three commits, structural test last so it fails before W2 lands and passes after). W4 on interphase in parallel. W5 on zklw after the melange fold, since it carries the design choices. W6 last on each branch.

## Verification matrix

| claim | command | expected |
|---|---|---|
| helper contract | `bats tests/shell/session_registers.bats` | all pass |
| no bare reader | `cd tests && uv run pytest structural/test_session_registers.py` | pass; fails on any new bare read |
| nothing else broke | `bats tests/shell` on the branch | exit 0 |
| interphase proof | `bats tests/shell/session.bats` | claim and marker keyed by stdin id |
| rig check | `bash common/.claude/hooks/tests/test-rig-clavain-deployed.sh` | all pass, 0 unevaluated |
| live | `rig-clavain-deployed.py` on zklw and Clavain | zklw exit 0; Clavain reports the stale `gitCommitSha` in detail only |

## Out of scope

- interline's own `CLAUDE_SESSION_ID` reads: its statusline already passes the JSON `session_id` through the environment.
- Other plugins' readers (interspect, interflux) — filed as follow-ups if the structural test's pattern is worth copying.
- Whether `os/Clavain-pub` should exist. The check judges only the checkout the CLI symlink resolves into; the worktree question is mk's.
- Rebuilding the cache. The check reports; `ic publish` repairs.

## Questions for review

1. Precedence when both env registers are set and differ (A1). Is there a resume or compaction path where `CLAUDE_SESSION_ID` from the env file is the old id and `CLAUDE_CODE_SESSION_ID` is the new one, and which should key state then?
2. Is fail-on-drift right for `clavain-deployed`, given the window between a main push and the publish wave, or does the mk-rd1x standing logic make fail safe enough?
3. Is comparing eight roots the right surface, or should the check compare the whole tracked tree and accept a longer finding list?
4. Should a failed fetch in step 3 downgrade the verdict to warn rather than carry a caveat?
5. Is A2 the right reading of "interphase statusline state", or is there a sideband writer this plan did not find?
6. What in this plan would let the register defect return silently in a new hook?

## Melange fold (2026-09-02, run wf_7d06d476-cda: 3 rounds, DRY halt, 28 findings / 15 upheld / 0 refuted; the synthesis authored f-029 to f-031 with the repos in hand)

Ledger and synthesis under `docs/research/flux-melange/session-registers-deployed-head/`. The synthesis ran against code that had already landed (W1 to W4 and the first cut of W5), so the register findings are defect reports against merged commits and were folded as follow-up commits on the same branches.

| finding | disposition | what changed |
|---|---|---|
| f-013, f-008, f-025, f-026, f-024, f-003, f-018 — seven bare `os.Getenv("CLAUDE_SESSION_ID")` sites in `cmd/clavain-cli`, outside W3's walk; `sideband.go` is the statusline writer that matters | folded | `sessionRegisterID()` in `sideband.go`, the seven sites converted (`claim.go` ×3, `phase.go`, `budget.go`, `evidence.go`, `init.go`), `session_test.go`, `phase_attribution_test.go` scrubs the app register; the structural test walks `cmd/**/*.go` and flags any direct read of either register outside the helper, plus the Python idioms (f-005, f-015). Proven red on a bare Go read. A2 corrected. |
| f-031 (synthesis) — `origin/main` is the wrong baseline: 42% of the last 26 days main was ahead of the published cache | folded | Measured: 9 version bumps and 21 root-touching non-bump commits in 30 days. The cache is now compared against the published commit (marketplace clone's `origin/main` version, resolved to the commit that set `plugin.json`); `VERSION-BEHIND` names a publish the machine never took; main's lead is printed, not judged — that is `publish-drift`'s question, and the pair together is the OUTCOME's "the fix reached the running plugin". The CLI stays against `origin/main` because it runs from the checkout. One test case pins the choice: a hook changed on main without a publish is clean here. |
| f-009 — STANDING converts fail to warn with no re-escalation | folded | `RIG_CLAVAIN_STANDING_MAX_DAYS` (7): past it the wiring withholds the signature and the check fails again daily until the drift clears or grows. Tested by backdating `first_failed_at_epoch`. |
| f-010 — a persistent fetch failure degrades silently | folded | `FETCH-STALE` after `RIG_CLAVAIN_STALE_FETCH_DAYS` (7); the age is the ref file's, not `FETCH_HEAD`'s, because a failed fetch still touches `FETCH_HEAD`. |
| f-027 — the resolved checkout's origin is never verified | folded | `CLI-WRONG-REPO` (`RIG_CLAVAIN_ORIGIN_MATCH`, default `mistakeknot/Clavain`). |
| f-014, f-011 — seven vs eight roots; a green run reads as complete | folded | Eight roots stated; the summary prints bytes hashed, seconds, and how many top-level entries were not compared (37 of 45 live). `cmd/` stays out: the shipped artefact is `bin/`, source is not executed by a session. |
| f-006, f-007 — dotfiles' own bare readers, including the writer's run-kind classification | folded | `rig-health-write.py`, `lib-hook-log.sh` and its two callers, `log-tool-invocation.sh` chain `CLAUDE_CODE_SESSION_ID`; every harness `env -u` scrub includes it (the writer test had been misclassifying runs on a machine where Claude Code sets it). |
| f-012 — 55 MB of binaries hashed per run with no ceiling | refuted by measurement | 54 MiB in 0.06 s; the figure is now printed each run. |
| f-016 — both registers set and different | folded | A bats case documents that `CLAUDE_SESSION_ID` wins (A1). |
| f-019 — the fail-open helper has no telemetry for its own collapse | follow-up | Bead filed for a periodic sentinel-rate rig check; per-invocation noise on the hot path is the wrong altitude. |
| f-001, f-002, f-020, f-021, f-023 — the session id changes across compact/resume, so claim and release disagree | declined, with evidence | The cluster rests on one comment in `session-start.sh`. This session's own id (45f5fb3c) survived two compactions on 2026-09-02: the SessionStart:compact hook printed the same id both times. No round observed a change. If one is ever observed, the repair belongs in the claim protocol, not the register chain. |
| f-022 — key claims on `BD_ACTOR` instead | declined | `BD_ACTOR` is written by the same start hook and is absent in exactly the sessions this plan exists for. |
| f-017, f-028 — no magnitude term in the signature | not needed | The signature is `kind:path` (and `CLI-BEHIND:<n>`), so growth by path or by count re-fails by construction; tested. |
| f-004 — the cache key passes an empty stdin argument | accepted as-is | Documented pattern; the fallback is `$$` on purpose. |
| f-029 (synthesis) — subagents see `CLAUDE_SESSION_ID` absent and `CLAUDE_CODE_SESSION_ID` = the spawning session | recorded | The chain already resolves it; noted in the register facts. |

Open measurement the review named and nobody has taken: whether hook processes inherit `CLAUDE_CODE_SESSION_ID`. Hooks read stdin first, so the exposure is the library callers without stdin (`lib-sprint.sh`'s six sites) when sourced inside a hook rather than the Bash tool. One `env` line inside a hook settles it.

## Answers to the review questions

1. Precedence: `CLAUDE_SESSION_ID` first, kept. Both registers name the same session in every case observed, including across compaction; the bats case documents the choice.
2. Fail-on-drift was right for the wrong baseline. Against `origin/main` it would have been red two days in five; against the published commit it is red only when this machine did not take a publish, and the 7-day STANDING ceiling stops the downgrade from becoming permanent.
3. Eight roots, stated as such, with what was left out printed. The whole tree would add `docs/` and `tests/` churn a session never executes.
4. A failed fetch stays a caveat for a week and becomes `FETCH-STALE` after; the verdict is never skipped.
5. A2 was half right. The claim state is proven under the real session; the statusline envelope writer in `sideband.go` is now covered by the Go helper and its test.
6. The Go binary. Two directories outside the structural walk, seven bare reads, and a structural test that passed 11/11 while they sat there. The walk now includes `cmd/` and any direct read of either register outside the helper is a failure.
