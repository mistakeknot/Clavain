# Clavain Roadmap

**Version at regeneration:** 0.6.332

**Last updated:** 2026-11-08 (PST)

**Sources:** milestone epic `mk-47vtm`, its scope comments, all beads labelled
`clavain-0.7`, and outstanding beads labelled `clavain` in the hub tracker.

This is a snapshot of recorded work, not a release schedule. Priorities and
statuses below are tracker values; table order does not assign execution order.
An open or in-progress bead is not evidence that its change has shipped. Closed
beads are reported as closed, with superseding work called out separately.

## Where we are

Clavain is on the 0.6 patch series. The beads describe existing packaged dispatch,
role routing, review receipts, hooks, and review-history storage, together with
gaps in their correctness and enforcement. The 0.7 milestone targets those gaps;
it does not claim they are already solved.

The tracker records the startup instruction-contract drift check as closed
(`mk-4xzwm.2`). The older lock tasks `mk-bxfvc`, `mk-htpmr`, and `mk-8gaoq`
are also closed, but `mk-aban2` records failed combined reviews and replaces the
cleaner-takeover approach with a simpler shared lock design. Their closure does
not establish that cross-client locking is correct.

## Milestone 0.7: trustworthy gates, routing, and skill quality

The epic description initially proposed trustworthy gates. Its scope comment
records the selected expansion to include routing and skill quality. Membership
is tracked with `clavain-0.7`, rather than relying only on epic child links.
The labelled set also includes review-sandbox isolation and the lock redesign.

The recorded exit criteria are: close the milestone work, observe two weeks
without a false BLOCK receipt, and obtain maintainer approval to publish 0.7.0.
No observation-window start or release date is recorded in the sources used here.
This document does not authorize publication.

### Review receipts and sandbox isolation

The receipt cluster addresses inconsistent parsers, verdict spelling, and
same-head reruns (`mk-0qjva`, `mk-8m912`, `mk-0ud4q`, `mk-4c909`,
`mk-n37ml`). Unknown verdict words must not silently become BLOCK receipts;
recovery must preserve history and must not turn a genuine blocking review into
a passing receipt. The beads contain different proposed parser/recovery shapes;
they do not establish a completed unified implementation.

`mk-z770` covers role verdict instructions, advisory REVIEW vocabulary, and a
fresh repair dispatch; it records sequencing after `mk-yjki`. `mk-vsqgd`
requires checking saved review output and resolving the mismatch between prompt
and parser handling of code fences/comments. Its choice of fix remains open.
`mk-1w54d` calls for an allowlisted review environment without inherited secrets;
`mk-nkprr` calls for a private temporary root outside any ancestor Git tree.

### Review history

Four in-progress beads add fields needed to connect a review, producing work,
merge, and later correction: PR head and normalized producer identity
(`mk-6i8ex`), links and classifications for forward fixes (`mk-8wgql`), verdict
and blocking-finding count in review events (`mk-629bo`), and bead attribution
on dispatch rows (`mk-0o5wm`).

### Locks and deterministic enforcement

`mk-aban2` requires Bash callers to acquire the cross-client lock through
Intercore's `ic`, with no separate Bash protocol and no cleaner takeover. The
choice between a kernel lock and an atomic owner record with fencing is still
open. A plan and independent packaged plan review precede implementation.
`mk-u3bu2` separately tracks generation-fenced claim/sprint leases.

`mk-4xzwm.1` adds transcript/tool-call checks for phase evidence, beginning
advisory before gating. `mk-4ma3` remains blocked: bead-first enforcement is off
while awaiting the broader task-first plan; its bounded follow-up evidence is
unconfirmed. It is not an active enforcement capability.

### Routing and skill quality

`mk-ji9m` reviews execution/review routing under Claude quota pressure while
preserving reviewer independence. `mk-1rbg` records the chosen direction for
Kimi validation: shell access with the same snapshot guard, edits refused, and
a live exact-plan demonstration. The bead remains in progress.

The skill-quality epic `mk-2i46` measures held-out outcome lift and loaded
context cost. Clavain owns cases, the paired runner, and the cross-lab judge;
Interlab owns the campaign loop. Hygiene (`mk-2i46.1`), a paired runner and
judge-noise spike (`mk-2i46.2`), and advisory record-only/same-run baselines
(`mk-2i46.3`) remain outstanding. Gates stay advisory until the noise spike
reports. The epic is a recorded blocker of `mk-47vtm`; the runner has a related,
not blocking, link to the Interlab baseline task.

Regenerating this roadmap is itself milestone work (`mk-48dhw`).

## Milestone bead inventory

| Bead | Recorded work | Priority | Status |
|---|---|---|---|
| `mk-aban2` | Shared cross-client lock redesign | P1 | open |
| `mk-1w54d` | Remove inherited secrets from review sandboxes | P1 | open |
| `mk-0qjva` | Unknown verdicts and safe same-head recovery | P1 | in_progress |
| `mk-nkprr` | Review temporary roots outside Git trees | P2 | in_progress |
| `mk-8gaoq` | Exclusive Intercore owner-record creation; redesign follows | P2 | closed |
| `mk-48dhw` | Regenerate the roadmap from beads | P2 | in_progress |
| `mk-htpmr` | Collector mutex exclusivity; redesign follows | P2 | closed |
| `mk-bxfvc` | Bash/Intercore lock compatibility; redesign follows | P2 | closed |
| `mk-4xzwm.1` | Deterministic phase-evidence checks | P2 | in_progress |
| `mk-4xzwm.2` | Startup instruction-contract drift check | P2 | closed |
| `mk-8m912` | Reconcile dispatch and receipt verdict parsers | P2 | in_progress |
| `mk-0ud4q` | Unknown verdict errors and append-only receipt history | P2 | in_progress |
| `mk-4c909` | PASS-WITH-NOTES parsing and receipt reruns | P2 | in_progress |
| `mk-n37ml` | Verdict warnings and append-only supersession | P2 | in_progress |
| `mk-u3bu2` | Generation-fenced claim/sprint leases | P2 | open |
| `mk-0o5wm` | Bead IDs on dispatch rows | P2 | in_progress |
| `mk-629bo` | Verdict and blocking-finding count in review events | P2 | in_progress |
| `mk-6i8ex` | Merge head and normalized producer identity | P2 | in_progress |
| `mk-8wgql` | Forward-fix provenance and classification | P2 | in_progress |
| `mk-ji9m` | Quota-aware execution/review routing | P2 | in_progress |
| `mk-4ma3` | Bead-first enforcement; activation held | P2 | blocked |
| `mk-2i46.1` | Skill hygiene and structural coverage | P2 | in_progress |
| `mk-2i46.2` | Paired skill evaluation and judge-noise spike | P2 | open |
| `mk-2i46.3` | Interlab advisory mode and same-run baseline | P2 | open |
| `mk-2i46` | Skill-quality evaluation epic | P2 | open |
| `mk-z770` | Role verdict contract and repair dispatch | P2 | in_progress |
| `mk-1rbg` | Executable, snapshot-guarded Kimi validation | P2 | in_progress |
| `mk-vsqgd` | Review code-fence/comment parsing contract | P3 | open |

## Other outstanding Clavain work

These beads carry `clavain` but are not in the milestone-labelled set. Inclusion
here does not add them to 0.7. The milestone epic itself is in progress at P2.

| Bead | Recorded work | Priority | Status |
|---|---|---|---|
| `mk-4xzwm` | Deterministic phases and orchestration-tool evaluation epic | P2 | open |
| `mk-4xzwm.3` | Survey orchestration/decision tools and assess project fit | P2 | open |
| `mk-g74wu` | Flag instruction rewrites and detect gate retries | P2 | open |
| `mk-j25yy` | Reserved continuation slot and daemon observe mode; fit unverified | P2 | open |
| `mk-83d3w` | Advisory receipt/head relation using patch identity | P2 | open |
| `mk-jcbzm` | Premise checks and structural fixes for recurring findings | P2 | open |
| `mk-54hzc` | Run public-repository hygiene checks in CI | P2 | open |
| `mk-lyscb` | Durable asynchronous ask journal and reply wake | P2 | open |
| `mk-muqr4` | Rerun invariant checkers before a base-failure waiver | P2 | open |
| `mk-km4a` | Incorporate recorded upstream deltas | P2 | open |
| `mk-km4a.7` | Longitudinal PR watch; residual follow-up wording remains | P2 | in_progress |
| `mk-wxlk` | Terminate stalled tmux executor process groups before resume | P2 | open |
| `mk-cmcrf` | Verification evidence and certainty levels | P3 | open |
| `mk-9ahvl` | Choose and prove an enforcer after repeated mistakes | P3 | open |
| `mk-80zm3` | Derive producer identity from producing evidence | P3 | open |
| `mk-6ghz4` | Audit startup tests and adopt property/model-based coverage | P3 | open |
| `mk-nwphk` | Opt-in friction records and metadata-only usage digest | P3 | open |
| `mk-xxem2` | Default-off capabilities and separate release evidence states | P3 | open |
| `mk-yda6d` | Metadata-only quarantine for unreadable hook/dispatch inputs | P3 | open |
| `mk-taovl` | Traceable attention decisions for inter-thread messages | P3 | open |
| `mk-42j9.23` | Pilot durable workflows for repeated dispatch/review loops | P3 | open |
| `mk-mlvc` | Carry the shipped-surface sweep through a publish wave | P3 | open |
| `mk-idxl` | Generic copy lint; deferred until a second project needs it | P3 | open |

## Research and decisions still open

- The lock primitive is unresolved in `mk-aban2`; the shared implementation and
  removal of cleaner takeover are already specified.
- The receipt/parser cluster still contains alternative fix proposals. In
  `mk-83d3w`, whether a same-patch relation may carry a verdict is a separate
  maintainer decision; the proposed check is advisory only.
- The placement of the waiver seam check (merge checklist or landing check)
  remains undecided in `mk-muqr4`.
- The orchestration survey `mk-4xzwm.3` evaluates adopt/reference/skip outcomes;
  it is not an adoption decision. Hosted use of a new service requires approval.
- Skill-evaluation gating awaits noise measurements (`mk-2i46.2`). The workflow
  pilot `mk-42j9.23` requires per-run opt-in and comparison with the task-tracking
  trial before broader adoption. Neither records a rollout date.
- Copy lint and a possible review-lens extension remain deferred in `mk-idxl`.

## Keeping current

Regenerate with Interpath's roadmap artifact workflow, using hub label-scoped
queries for `clavain` and `clavain-0.7` (including closed milestone members),
and reread `mk-47vtm` comments for scope changes. Verify referenced bead IDs,
priorities, statuses, and dependency types against that snapshot. Paraphrase
internal operational details before committing to this public repository.
Keep this document at `docs/clavain-roadmap.md`; this task regenerates only the
human-readable roadmap, not a machine-readable roll-up or a new release plan.
