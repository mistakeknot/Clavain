# OODARCS Mac rollout — September 5, 2026

The Mac now uses the Clavain-generated OODARCS contract for substantive Codex
work, with a complete 112-entry runtime catalog at `skills.max_context_tokens =
8500`. The final matched matrix passed all 15 cases; a second documentation
boundary probe also passed. These are diagnostic results with **zero Astra canary
task-completion credit**, not a model-promotion or general performance result.

Tracking: `Sylveste-x7va`, with `Sylveste-l04p` (Clavain), `Sylveste-rrg8`
(dotfiles), and `Sylveste-7oe8` (philosophy/evidence). Remaining companion work is
`Sylveste-7wn0`; `Sylveste-8nov` still blocks broad installation and refresh.

## Published and installed configuration

- Clavain implementation: [762a635](https://github.com/mistakeknot/Clavain/commit/762a635d8d9f7aed81a249b0fa75562a2881fe74).
- Final proportional documentation route: [10fda1d](https://github.com/mistakeknot/Clavain/commit/10fda1d9ddca2cb5cabbb00d2c5b2a4afd6343df).
- Dotfiles producer: [f9da1c2](https://github.com/mistakeknot/dotfiles/commit/f9da1c2bc6b53fd38073d13557e89c352b705fa6).
- Sylveste philosophy: [e8f0c36](https://github.com/mistakeknot/Sylveste/commit/e8f0c3644aaecc565c1b3efcff0b11a1fcbb9b54).

Producers were reviewed and pushed before their installed consumers changed.
The global instruction symlink survives; its contents match the dotfiles producer.
The narrow dry-run was empty after the explicit dotfiles cleanup, and apply was
idempotent. The live dotfiles checkout has pre-existing divergent history, so a
local consumer receipt (`b596f26`) records the already-published file without
publishing unrelated commits. Sylveste's unrelated `estate-checks-falsifiable`
checkout and its dirty work were preserved. Clavain was fast-forwarded on `main`.

Read-only pre-push checks found no registered Codex source-refresh hook or producer
autosync marker on this Mac or zklw. No zklw checkout/config update was initiated.
The protected Sylveste push required a real GitHub Actions result: a temporary
`ci/` tag let that exact commit run its required check, then the commit landed on
`main` and the temporary tag was removed. Protection was not changed.

Twenty-one companion links now target byte-identical skill trees verified against
published producer trees. Twelve divergent trees and eight supporting-script
compatibility reviews remain deferred; the pre-existing disabled `troubleshoot`
link retains its resolved path. All 13 duplicate-path overrides remain intact.
The fresh inventory still has 102 unique enabled entries and zero loader errors
or duplicate names. Its full metadata measure is 30,536 Unicode characters,
versus 30,377 before: 303 characters saved in descriptions were offset by 462
additional characters in canonical source paths. This is distinct from prompt
rendering and token usage. All 84 Clavain skill/support files survive.

## Runtime evidence and budget

The invoked binary was Codex CLI 0.153.3 (SHA-256
`0e1f892695844ad0798dab8895955846450a9e7663476ebf24615814dd377216`), using
Astra/xhigh, Standard service, read-only sandbox and `never` approval policy.
Both variants used `CLAVAIN_SESSION_REFRESH=0`. TUI sessions launched without a
prompt, waited for plugin startup, and then received the prompts in
[oodarcs-fixtures.json](oodarcs-fixtures.json). Each case began a fresh first turn;
resumption cases actually closed and reopened the same session ID.

The baseline used Clavain `e53ca59` and the unset budget. The final candidate used
`10fda1d` and 8500. All 15 final turns share identical instruction, router and
configuration hashes. The [machine-readable evidence](oodarcs-mac-2026-09-05.json)
records source/binary identities, session/turn IDs, tools, skill reads, input
usage, elapsed time, acceptance and the budget sweep. Raw tool arguments and TUI
captures remain locally in `~/projects/oodarcs-x7va-review/runtime/`.

| Allowance | Shortened descriptions per 112-entry catalog |
|---|---:|
| Default (2% of the 272,000-token model context) | 77 |
| 5500 | 77 |
| 6000 | 64 |
| 6500 | 45 |
| 7000 | 35 |
| 7500 | 23 |
| 8000 | 9 |
| 8500 | 0 |

Each sweep row has four fresh sessions across both directory contexts. Repetition
produced eight complete-catalog passes at 8500 and eight failures at 8000. The
sweep stopped at the lowest repeatedly passing allowance, below the 10,000 cap.
Only the 8500 setting was persisted; removing that exact addition in memory
reproduces the baseline config hash. No model-context, routing, MCP, approval,
release or Astra-promotion setting changed.

Warning absence was insufficient: candidate TUI sessions sometimes showed no
warning while their descriptions still ended mid-sentence. Acceptance compares
rendered text against source descriptions. The warning-only pilot was invalidated.
An earlier harness pilot also collected a stale turn after a stray update-dialog
keystroke; those records were excluded and rerun with exact prompt/turn matching.

## Behavior and overhead

The baseline and final candidate produced evidence-backed outcomes. The measured
routing change was **0/11 → 11/11** fresh substantive router reads. Debugging,
planning and review selected their relevant skills; release assessments loaded
verification guidance. Bounded research and response-only explanatory writing
used proportional guidance. Trivial requests remained direct, with no tools.

A documentation mismatch was reproduced before final acceptance: the old router
sent all documentation toward `interscribe`, whose actual scope is repository
health. The corrected router supplies concise explanatory-writing guidance and
reserves `interscribe` for audit/refactor/consolidation. Independent Fable review
confirmed this scope correction, and the entire final matrix was rerun afterward.

| Case | Directory | Model tool calls, baseline → final | Final acceptance |
|---|---|---:|---|
| documentation | outside | 3 → 2 | pass |
| missing-companion-1 | outside | 1 → 1 | pass |
| planning | outside | 4 → 4 | pass |
| research | outside | 1 → 1 | pass |
| restricted-review-1 | outside | 1 → 2 | pass |
| trivial-1 | outside | 0 → 0 | pass |
| trivial-2 | outside | 0 → 0 | pass |
| contradiction-resume-1 | inside | 0 → 0 | pass |
| contradiction-resume-2 | inside | 0 → 0 | pass |
| debug | inside | 3 → 3 | pass |
| missing-companion-2 | inside | 1 → 2 | pass |
| release-preparation-1 | inside | 1 → 2 | pass |
| release-preparation-2 | inside | 1 → 2 | pass |
| restricted-review-2 | inside | 2 → 2 | pass |
| review | inside | 4 → 4 | pass |

Both resumption cases explicitly replaced pending remote checks with a failed
tenant-isolation result, retained the independent-review gate, and revised the
readiness requirements without starting new work. Missing companions caused no
installation or substitute validator. Policy-restricted review caused no provider
switch or transmission. All four synthetic fixture files remained unchanged;
no extra fixture files, memory writes, tracker writes, releases or configuration
changes were performed by the fixture agents.

Median fresh first-model input rose from **29,352 to 31,820 tokens** (+2,468,
8.4%). Model tool calls across the matched matrix rose from 22 to 25. Summed case
duration rose from 451.857 to 535.921 seconds; sessions ran concurrently, so these
are not wall-clock rollout durations. This is an observed instruction/discovery
cost, not a claim of token savings or statistically established task improvement.

## Verification and remaining limits

Local checks passed: 913 structural (one skipped), 18 audit/process, 10 instruction
sync, and seven installer fixtures. Fable independently reviewed the implementation
and follow-ups with CLEAN landing verdicts. Its review was static: command replay
was denied, so the test runs and live checks are integrator evidence.

Broader Clavain CI is still red: the [baseline](https://github.com/mistakeknot/Clavain/actions/runs/33985569636)
had ten shell failures; the [final router revision](https://github.com/mistakeknot/Clavain/actions/runs/33997586920)
has five, all present in the baseline. They concern a Linux `md5` dependency and
four routing/authorization gate fixtures. The five installer fixture failures
were repaired. No new CI failure was introduced, and no unrelated gate logic was
changed. Sylveste's required [Generator and parity checkers](https://github.com/mistakeknot/Sylveste/actions/runs/33996837313)
passed on the landed philosophy commit.

Re-audit after skill/plugin changes, using both fresh inventory and real first
turns. Roll back only this change's managed instruction block, selected links and
budget setting; the dotfiles cleanup has a scoped Git diff. Preserve unrelated
current configuration. Do not use broad install/uninstall or automatic refresh as
rollback while `Sylveste-8nov` remains unresolved.
