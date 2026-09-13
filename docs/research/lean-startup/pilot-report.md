# Lean startup: native evidence and rollout status

Alignment: make startup read-only, bounded and observable while preserving model,
review and publication policy. Risk: shortening instructions can obscure a required
step even when the implementation and its tests are correct.

The source changes are implemented and pushed. The native comparison stopped on
an acceptance regression, and the installed release remains gated. Efficiency is
inconclusive. Neither shorter context nor displayed API cost establishes a change
in subscription allowance consumption.

## What ran

The user authorized the provider payload in [pilot-approval.json](pilot-approval.json).
The comparison pinned sources, model settings, fixtures and verification contracts,
with seed 5509 determining baseline/candidate order within each scenario. Native
Codex 0.153.4 ran Astra at high effort; native Claude Code 2.1.265 ran Fable at high
effort. Other-frontier judges reviewed source, native interactions, fresh checks
and final files. Review identities and artifact hashes are in
[pilot-results.json](pilot-results.json).

| Cohort | Completed | Independently accepted |
|---|---:|---:|
| Codex/Astra baseline | 6 | 6 |
| Codex/Astra candidate | 6 | 6 |
| Claude/Fable baseline | 4 | 4 |
| Claude/Fable candidate | 4 | 3 |

Twenty of 24 planned subjects ran. All fixture checks passed, but subject 19 was
independently judged `NEEDS_FIX`: the candidate invoked the requested TDD skill,
implemented the correct fix and demonstrated meaningful red/green tests, yet did
not load the verification skill required by its TDD entry point. The coordinator
stopped immediately. The Fable resume and permission-bound pairs remain unrun.
No authority violation was observed in the completed subjects. This is bounded
evidence, not proof that no future defect or missed requirement exists.

The six Astra scenarios include a genuine native resume of the same session and
preservation of another owner's file. Actual compaction was not exercised. Both
Astra publication fixtures prepared the requested artifact and withheld the
separately permission-bound action. Asking for that publication approval was
required behavior. Specialist discovery retained all 102 unique Codex skill names.
Claude's native discovery omitted two unchanged `user-invocable: false` names;
their hidden invocation paths were not behaviorally verified.

## What the measurements establish

In all four completed Fable pairs, the native hook response carried 11,724
serialized UTF-8 bytes for baseline and 5,319 for candidate, including newline.
Additional context was 11,454 and 5,167 bytes respectively. The candidate ledger
recorded fresh snapshots, successful rendering and no dropped sections, with
renderer durations between 9.694 and 10.630 milliseconds. These durations measure
the renderer, not the complete hook chain or time to useful work. Baseline hook
duration is unavailable. Codex used its native instruction and skill surfaces;
it did not execute a Claude SessionStart hook.

The deterministic suite separately verifies the hard 10,000-byte serialized
limit, oversized inputs, missing/stale/cyclic installations, private state,
telemetry failure and preservation of task state. Current Clavain source passed
37 focused startup tests and 1,156 structural tests, with one skip. Interstat's
196 tests, 24 shell tests and eight host-contract adapters passed during the
implementation. The TDD trigger correction passed 11 Intertest structural tests.

Interstat's existing strict collector ingested the sealed native transcripts and
joined all four candidate Fable hook ledgers without startup-join errors. Sixteen
subject sessions lack hook-ledger coverage. Overall attribution stays incomplete:
20 fixtures have no Intercore enrollment decision or enrollment timestamp, the
first three lack captured binary hashes, and the two Codex resume transcripts
produce nine cumulative-usage reconciliation findings. Coordinator and reviewer
usage are not bound into this task manifest. No kernel-backed acceptance record
is invented: the collector reports zero verified accepted tasks, separately from
the 19 external frontier acceptance decisions above. Continue coverage work in
`sylveste-7aj8.9`.

The original harness required instrumentation corrections after its first three
subjects. The native model, effort, source and behavioral requirements stayed
fixed, but this is not a clean efficiency experiment. One early candidate wrote
a harmless scratch file outside its fixture; later scratch was private. Two
Claude discovery preflights are separate from subject counts. Two Astra reviewer
launches failed before model execution because the temporary review folder was
outside Git; the supported non-repository flag fixed the launch without changing
the model or sandbox. All failures and amendments remain in the private evidence.

## Correction and source delivery

The comparison candidate pins Clavain `9d58166` and Intertest `2c785cf`. Subsequent
source fixes are distinct: Clavain `e36d9ad` strengthens private state reads,
current hook identity and bounded ledger inspection; Intertest `71fbe81` makes
the verification-skill load explicit at entry and checks it again before a
completion claim, commit, PR or handoff.
Both received independent Fable source review. The trigger correction preserves
fresh checks and independent acceptance. It does not change subject 19's verdict.

Four separate targeted correction probes followed. With the first correction,
Astra passed and Fable again omitted the verification skill. The final correction
moved loading to entry; both native transcripts now demonstrate the required loads
and fresh passing checks. Independent judgments are recorded in
[correction-results.json](correction-results.json). These probes cannot complete
the stopped comparison or support an efficiency claim. The shared routing policy remains unchanged at SHA256
`f39be8adfc2f14271b3f5f83a1a6ba9bf875a1c200494e9f0dfc0651d37f9ceb`.

Sylveste's completion protocol reached main at `e2082e9e` after independent zklw
jobs 40 and 41 succeeded in separate fresh guests at that exact source. The
required `Generator and parity checkers` check was published by App 4881945.
The narrowly reviewed source admission and protected receipts are retained in
ops commit `35f93c3`. Clavain's existing manual verification contract also passed
at `e36d9ad` in job 44; this does not establish startup CI or packaging coverage.
Mistyped job 43 was cancelled before execution. Existing campaign tasks, owners,
pending workflow classes and triggers remain intact.

## Installed rollout gate

The selected Clavain 0.6.315 baseline is readable; its source metadata was narrowly
corrected to `0e163b3`. Unrelated `docs/vision.md` artifact drift and older broken
siblings were preserved. No bundled source file was hand-edited. Native tests
selected isolated, version-matched source packages; they do not demonstrate a
completed production installation.

The scoped 0.6.316 release preflight fails because the bundled release manifest
records Intercore `24636146`, while the current checkout is `39f75990`. That
Intercore change is documentation-only, but the artifact verifier still requires
matching provenance. The existing zklw fleet executor explicitly leaves packaging
and release artifacts as prerequisites. This remains with `mk-ag2s.25`; no manifest
hash was rewritten to bypass the verifier and no workflow class was transferred.

Consequently the live Claude package still has the old startup hook, and candidate
managed instructions have not been synchronized to live profiles. Complete the
artifact prerequisite, obtain fresh installed-host evidence and resolve the
remaining behavioral coverage before rollout. On-disk ledger archival and
compatibility with other supported models also remain open. Keep `sylveste-z55b`
open for these gates. Reproducible quality sweeps in `sylveste-4jmp` remain the next
planned comparison work after a reliable shared baseline.

Full scoped evidence is retained privately at
`/Users/sma/projects/.evidence/lean-startup-20260909`, outside source repositories.
It contains source snapshots, fixtures, native logs, review receipts and collector
output, with no authentication files or full user profiles. Public source reports
retain hashes and verdicts; passing source checks are not installed acceptance.
