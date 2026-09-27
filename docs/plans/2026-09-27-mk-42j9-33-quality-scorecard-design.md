---
artifact_type: design
bead: mk-42j9.33
stage: design
---

# Per-change quality scorecard (hard gates only)

**Design only, 2026-09-27, round 5 (final cut).** This proposes an offline reduction of existing evidence into a versioned JSON result carrying exactly two gates — attributed P0/P1 findings and attributed escaped defects — and a project-scoped rollback recommendation. It adds no receipt fields, database tables, daemon, or model-selection framework. Implementation and rollout are not authorized by this document. Independent other-frontier review remains a gate.

**Goal.** An efficiency change can be retained only after no attributable P0/P1 finding or escaped defect is found in an exposed project. A single confirmed regression blocks retention; there is no rate, threshold, or sample floor. Everything that was previously advisory (P2/P3 findings, rework, throughput, burn, TTL efficiency) and everything that depended on lineage-based statistical comparison is deferred to `mk-42j9.43`, not computed here.

**Consumers.** Lane A (`mk-42j9.25`, Sonnet-default rollout) and lane C (review-packet A/B) consume the same JSON contract. Quilan consumes a rollback recommendation through an integration adapter, preserving `routing-receipt.ts`. Clavain records the resulting exception through its existing routing policy. Those are proposed connections, not claims of deployed integration.

## Evidence and boundaries

Repository-relative citations below refer to Clavain at `cdaa9107de899d44854c3186e98d6019797d3416`. External sources have explicit roots and revisions. Line ranges are part of each source reference. Proposed behavior in later sections is deliberately separate from these observations.

| Ref | Verified source and implication |
|---|---|
| S1 | `scripts/lib-dispatch-audit.sh:25–38,41–100,103–157`: an attempt has `dispatch_id`, `attempt_id`, lifecycle state, parent/native session identities, checkout before/after, execution tuple, result, and optional task envelope. `primary_profile_ref`, `executed_profile_ref`, and `bead_source` are **context JSON fields**, not SQL columns. |
| S2 | `docs/canon/reasoning-routing-operations.md:248–268`: executed profile drives attribution; flag/env/session-file precedence supplies bead identity; unknown findings are not zero. `scripts/receipt-findings.py:12–20,60–96,99–122` implements counts and clean/unknown handling. It does not give finding identities or establish that a reviewer inspected a particular artifact. |
| S3 | `/home/mk/projects/Sylveste/core/intercore/internal/db/migrations/027_routing_decisions.sql:6–32` and `internal/routing/decision.go:127–168` at Intercore `d5b2f00ef3c804cce5ce20d8562875479b5be9a1`: SQL columns include project directory, bead/session/run/dispatch IDs, policy hash, context JSON and an insertion-time Unix-seconds timestamp. IDs, not seconds alone, order same-second inserts. |
| S8 | `scripts/task-delivery.py:2–15,181–239,377–429`: prospective enrollment, cohort/manifest hashes and usage bindings already use Intercore decisions; exports are evidence, not a task database. Reuse this path for direct bead-to-change attribution evidence where enrolled. |
| S9 | `/home/mk/projects/Sylveste/os/Quilan/routing-receipt.ts:31–52,83–123,126–142` at Quilan `64d2b10a8c3a42af66f20bde2f81e6f0e1da0454`: the governed consumer expects flat camelCase fields and checks the target model/effort catalog. Lines 104–109 explicitly state that real nested Intercore receipts fail this parser and there is no production caller. Preserve that public shape; an adapter and a real consumer canary are prerequisites, not completed work. |
| S10 | `config/routing-overrides.schema.json:3–5,31–45` and `scripts/lib-routing.sh:914–955`: Interspect overrides are agent triage/model recommendations, not general project rollback records. Intercore `internal/routing/reasoning.go:13–23,146–162` at S3's revision already supports named `{scope,roles}` policy profiles. Use that existing routing mechanism, not the Interspect file. |
| S11 | Clavain git object `e41c188:docs/research/2026-09-27-effort-per-role-validation.md:29–54,112–139` (read with `git show`, not present on this worktree's HEAD): mk-42j9.26 records unplanned mk-42j9.20 branch exposure, a model-plus-effort confound, same-seat fallback contamination and insufficient small-sample evidence. These observations require explicit exclusions here. |
| S12 | Clavain git object `0224f4b:docs/plans/2026-09-27-mk-42j9-25-sonnet-default.md:44–65,113–133,286–306,354–370`, also inspected at `/home/mk/projects/.clavain-laneA/docs/plans/2026-09-27-mk-42j9-25-sonnet-default.md`: this is a **draft with open review findings**, not deployed infrastructure. |
| S13 | `docs/research/claude-p/oodarcs-s4-deep-dive/2026-08-25-synthesis.md:36–56,135–148`: existing local prior art favors an evidence-bound scorecard artifact, explicit unknowns and existing enrollment/event paths. No second scorecard service is needed. |
| S14 | `docs/canon/reasoning-routing.md:7–23,33–51` and `docs/canon/reasoning-routing-operations.md:423–441`: classification, independent review, empirical evidence and authority floors remain binding; empty identity/hash prevents acceptance. `/home/mk/projects/Sylveste/PHILOSOPHY.md:102–110` calls for observable outcomes and feedback. |

The task brief is the source for mk-42j9.33's acceptance criteria. Live Beads evidence was unavailable: the required Clavain `~/.local/bin/bd-hub` adapter is absent, and `ssh -o BatchMode=yes zklw` failed DNS resolution. No legacy tracker was used as authoritative history. The GitHub repository-ID request and zklw CI-status request also failed connectivity; migration disposition is unknown. These operational failures do not prevent a design, but prevent live acceptance claims.

## 1. Data model and attribution

### Frozen change specification

One small JSON experiment specification accompanies the existing task/cohort evidence. It is input to a proposed `scripts/quality-scorecard.py`, not a new database or receipt version. Its SHA-256 is `change_revision`; changing a setting, cohort, rule or exclusion creates a new revision. It records:

- `schema_version: 2`, `change_id` (owning bead, e.g. `mk-42j9.25`), `kind` (`routing-default|effort|ttl|rotation-threshold|review-packet` — `kind` still names what changed for reporting/exclusion purposes; no kind gets different gate treatment), and the exact before/after setting values and units.
- Full landed commit OIDs, policy-file hashes, installed configuration hashes, affected roles, expected executed model/effort/tier tuples, and immutable project identities. A Git commit is evidence of a code change; it is not the activation timestamp.
- Project aliases, tracker namespace, default branch, bead enrollment, artifact/reviewer bindings, the frozen rule version and explicit exclusions. Each binding has an existing receipt/commit/export reference. An unsubstantiated manually typed binding is not gate evidence. There is no lineage or arm field: enrollment is by direct bead-to-change attribution (§3), not by session/lineage membership continuation.
- `t0` (evidenced activation for enrolled work, not merge time) and `evaluation_block_days` (default 14): the single window `[t0, t0+evaluation_block_days)` during which a bead can be attributed to this change (§3). `attribution_deadline_days` (default 3): the deadline (§4) counted from the moment a candidate's status becomes `triggered-pending-attribution`, never from the underlying finding's review-start or the escape's close. `declared_surface` (roles, deliverable kinds, file/path scope, or an explicit affected-component list; nullable — a null/absent surface means every candidate proceeds straight to attribution review, with no prefilter, §4).

For model and effort experiments, the actual executed tuple and profile must match the assigned exposure. TTL and rotation changes may leave policy hash/model unchanged: join their pre-recorded activation/configuration to the session, then to bead and receipt. **Time or a bead title alone is not proof of exposure.** If existing configuration evidence cannot supply this binding, those rows are `unattributed`; they cannot establish a treatment effect. This design does not add a TTL, rotation, or change field to governed receipts.

### Keys and cardinality

| Entity | Exact identity and selection |
|---|---|
| Project | Verified immutable GitHub repository ID, represented as `github:<decimal-id>`. A frozen map relates normalized `project_dir`/Git common directories to that ID. Worktrees of Clavain are one project; nested repositories are separate projects. Until identity is verified, use `unverified:<owner>/<repo>` and forbid promotion/action. |
| Bead | `(tracker_namespace,bead_id)`, then a verified project enrollment. A workspace-wide `mk-*` prefix or current assignee is not a project identifier. Multi-project beads need existing per-project deliverable/allocation evidence; otherwise mark ambiguous. |
| Attempt | `(source_store_id,dispatch_id,context.attempt_id)`. Consider only governed `rule_matched=dispatch-profile` lifecycle rows for attempt facts; task-enrollment rows in the same table are separate inputs. |
| Deliverable | One prospectively enrolled acceptance unit: `(project_key,tracker_namespace,bead_id,deliverable_key)`. Bind its **first reviewable revision** to a full Git tree/commit OID or committed artifact blob/digest, and to its required validation dispatch IDs. Revisions and re-reviews do not create extra deliverables. |
| Cell | `(change_id,change_revision,project_key)`. There is one evaluation block per change/project (§3); no arm, no stratum, no lineage. |

### Exact read/reduction path

1. **Snapshot.** Read consistent database snapshots/transactions, an authoritative Beads snapshot **and transition history**, and Git objects plus fresh remote default-branch ref evidence. Record capture time, watermarks and hashes. No `immutable=1` shortcut that silently drops SQLite WAL contents. Ref freshness must cover the entire outcome horizon; a failed fetch or missing history is unknown, not a failed landing or zero defects.
2. **Routing rows → attempts.** Project-map `project_dir`; validate context version 1; require SQL/context dispatch and bead IDs to agree when both are present. Collapse repeated lifecycle rows per attempt, ordered by `(decided_at,id)`. Retain all source IDs, earliest `started` and final terminal `completed|failed` row. Use `context.executed_profile_ref`, with only S2's documented `resolved_profile.profile_ref` fallback, plus `execution.{backend,model,reasoning_effort,service_tier}`. Never use the primary profile as actual exposure. Preserve failure class, exclusions and policy profile/hash.
3. **Attempts → direct bead attribution.** Match the namespaced bead and project, verify artifact/reviewer bindings, and confirm the bead's own anchor (first review-start for a finding, first acceptance-close for an escape, §2) falls inside the change's evaluation block `[t0, t0+evaluation_block_days)` (§3). There is no lineage/session-membership matching and no successor-work inheritance: a bead is attributed to a change only by its own direct evidence binding, never by belonging to the same coordinator lineage as an already-attributed bead. A dispatch spanning a configuration flip, conflicting bead IDs, or missing effective-setting evidence gets an explicit exclusion/reason (§3).
4. **Beads/Git → outcomes.** Normalize tracker history to `{event_id,namespace,bead_id,time,old_status,new_status,evidence_ref}` and snapshot metadata to `{namespace,bead_id,issue_type,priority,created_at,status,closed_at}`. These are reducer input records, not claimed native `bd` field names. Resolve the installed adapter's actual history/export interface before implementation; this session could not verify it. Git provides full-OID commit links, ancestry, revert bodies and fixed default-branch snapshots. Join these facts to attributed bead/deliverable keys, then reduce each signal below.

This separates two questions: was the bead actually exposed to this change, and did it produce a P0/P1 finding or an escape. Every output cell reports both. Legacy receipts with no bead/subject binding are useful inventory but cannot populate a gate.

## 2. Two signals and observable definitions

All windows are half-open UTC intervals. Event follow-up is `(anchor,anchor+604800 seconds]`; an event exactly at seven days counts. Block membership is explicit per signal: findings use the bead's first required review-start time; escapes use its first acceptance-close time. A required review that has not completed remains missing in its original position, not dropped or moved.

### Review findings, P0 and P1 only

For severity `s` in `{P0, P1}`, a bead's finding status is positive if its frozen first-review revision's required review slot(s), once scored, report a P0/P1 (§4's per-signal resolution). Use one preselected validation channel per artifact kind, with the same rubric, reviewer model/effort and stage. Counts are **reported findings**, not deduplicated unique defects; S2 has no finding IDs. Validate `source in {verdict,body}`, nonnegative integer counts; `unknown`, null, absent, inconsistent or non-review output leaves the bead's finding status `unknown` (§4) — it does not disable the gate.

**Lane C trap:** fewer findings by a weaker reviewer is not evidence of better quality. The review packet itself is lane C's deliverable. A fixed independent validator audits its omissions and false positives against the same subject and rubric, and that validator's findings are what this gate uses. The tested reviewer's raw counts are not a substitute.

P2 and P3 findings, and every other previously "advisory trend" metric (rework turns, beads-closed-per-hour throughput, weighted burn, TTL efficiency), are **not computed by this design**. They are deferred; see §8's Deferred list.

### Escaped defects within seven days

The headline is **distinct affected closed beads / attributed close-mature beads**, not a rate against baseline. Anchor to the bead's first acceptance close; never reset the clock on re-close. Include closed beads that remain open at maturity, as defects rather than exclusions. A multi-deliverable bead is counted once in the union.

| Signal | Falsifiable rule | Limits / unknown condition |
|---|---|---|
| Reopened bead | A historical `closed → any nonclosed status` transition within the follow-up interval. Count the bead once, retain every transition ID. | Missing ordered transition history makes the signal unknown. Administrative reopens still count in v1. |
| Revert | A commit reachable from the recorded default-branch tip has a canonical `This reverts commit <full-or-unambiguously-resolved-OID>.` body referencing a bead-linked accepted commit, and its committer time falls in the interval. | A title containing "revert" alone is insufficient. A revert of a shared commit affects each explicitly linked bead, once each. |
| Failed landing, observable v1 proxy | At first close, the bead has an explicit candidate commit set. At maturity, at least one required candidate is still not ancestor of the fresh recorded default-branch tip, and no explicit squash/cherry-pick replacement link proves delivery. | A missing commit link, object, fresh ref or replacement mapping is **unknown**, not failure. |

"At maturity" requires the default-ref state **at that bead's seven-day cutoff**, from timestamped Git ref/reflog evidence — this design designates **zklw's local `main` reflog** as that single source, retained at least 60 days (verified at implementation time, not assumed). Where the clone's history does not cover a bead's cutoff, that bead's failed-landing signal is `unknown`.

The union is positive if any known signal is positive. It is `clear` only if all three are observable and negative; otherwise it is `unknown` for verdict purposes (§4). Each mature bead's escape status classifies independently as `clear`, `triggered-pending-attribution`, `attributed`, or `unknown` (§4). A single `attributed` bead fires `regressed` outright once its attribution review resolves it; `unknown` and unresolved `triggered-pending-attribution` beads never count as `clear` and block `holds` until they resolve (§4's no-vacuous-holds rule).

**Escape candidate population (mk's 2026-09-27 final ruling, item 4, replacing the round-4 bounded-candidacy language).** An escape candidate is a bead directly attributed to the change (§1 step 3, §3) that closed within the change's evaluation block `[t0, t0+evaluation_block_days)`. There is no lineage and no successor-work inheritance: a bead enrolls only by its own attribution evidence, never by descending from an already-attributed bead's coordinator lineage. A bead still open at the end of the evaluation block is **out of scope** for this change's escape gate — not `unknown`, not carried forward — because it was never attributed to the change as a closed, evaluable outcome. This is a strict population boundary, not a resolution-timing rule: a bead that closes inside the block but has not yet reached its own close+7d follow-up by the report's `as_of` is `unknown` at that `as_of` under §4's ordinary stateless resolution, and may resolve normally at a later `as_of` once its follow-up elapses.

## 3. Change exposure and evaluation window

**Candidate: mk-42j9.25.** Its cited state is a reviewed draft with open findings, not a landed rollout (S12). The implementer must supply the actual landed commit and activation evidence before labeling this candidate "landed."

Freeze one experiment revision, one setting change, and project/bead enrollment rules before evaluation. The evaluation block is `[t0, t0+evaluation_block_days)` (default 14 days, §1); `t0` is the evidenced activation for enrolled work, not merge time. A bead is enrolled by direct attribution evidence (§1 step 3) confirming its own review-start or close anchor falls inside this block — never by lineage membership, session inheritance, or a neighboring timestamp. In-flight work crossing activation stays unattributed to this change and is reported separately.

Confound checks below are mandatory input predicates for `holds`; they exist to confirm a candidate bead was actually exposed to the declared change, not to support a rate comparison — there is no baseline/treatment/control comparison left in this design to protect with a comparison-specific tolerance.

- Exact actual profile/model/effort and policy hash; fallback/headroom substitution, provider outage and quota failures retained distinctly. Identical executed seats cannot demonstrate a treatment exposure (S11).
- Separate instrument epoch at mk-42j9.29; never compare previously unscored reviews as zeros. Historical output can be reparsed only with pinned parser/version and preserved body hashes.
- Model, effort, prompt packet, TTL, rotation, host/install, and reviewer fixed except the declared treatment. Combined changes get a bundle ID and cannot support a claim about one component.
- Exclude mk-42j9.20 exposure by actual policy/configuration evidence (S11). A branch name or presumed rollout date does not define exclusion.
- Same reviewer protocol and all required deliverables scored; same tracker and Git horizon; exact namespace/commit bindings.

Shadow is required to verify attribution and a dry-run rollback before any live evaluation. Shadow can reject a candidate or allow the bounded experiment to proceed through its existing approvals. It cannot clear fabricated outcomes on work never landed.

## 4. Exact v1 regression and keep rule

**Provenance (abbreviated).** Rounds 1–3 tried a bare threshold, then a pooled SPRT across seven metrics; the SPRT was found broken in ways no bounded delta could patch (collapsed hypotheses, wrong sampling model, undercounted error budget, a vacuous-holds bug). mk ruled option A: replace statistics with hard, single-event gates needing no sample floor, deferring real statistical gating to `mk-42j9.43`. Round 4 fixed the deadline anchor (P0-A), the `triggered`-vs-`attributed` conflation (P1-D), scoped usage completeness out of every gate (P1-E), and threaded a rollback-confirmation field (P1-G) — but round 4's delta review found the resulting design still contradictory or unimplementable in three places: `unknown` claimed to be permanently final while a fixture resolved it later and while the reducer has no stored state to make finality meaningful (P1-1); `Repin.rollback_confirmation_ref` could never be filled by the reducer, since a report is a closed, hashed, reproducible document (P1-2); and the escape-candidate population was undefined at the block boundary, letting `holds` become practically unreachable under lineage-based enrollment (P1-3). mk's final ruling (this round) resolves all three by cutting scope rather than patching further: the design keeps only the P0/P1-finding and escaped-defect gates, drops the rollback-confirmation field for an external check, and drops lineage-based enrollment entirely (§1–§3, above). This section applies the remaining two fixes (stateless resolution, escape population) directly to the state machine.

### Attribution: which change owns a finding or escape, and its window

A finding or escape is a **candidate** for attribution to change `change_id`/`change_revision` when both hold:

1. The underlying bead is directly attributed to that change under §1 step 3/§3 (own evidence binding, no lineage). A bead excluded for fallback or contamination (§3) is not silently dropped: it is reported as a distinct `Exclusion` and remains a `promotion_eligible` blocker even though it does not enter the candidate population.
2. The event's own timestamp falls inside that bead's own follow-up window as defined in §2: a finding's window is its bead's first required review-start time plus `(anchor,anchor+604800 seconds]`; an escape's window is its bead's first acceptance-close time plus the same interval. For escapes, the bead's close must additionally fall inside the change's evaluation block `[t0, t0+evaluation_block_days)` (§2's escape-candidate population rule) — a bead closing outside that block is out of scope for this change, not a candidate at all.

A finding or escape whose bead is not attributed to the change, or whose event falls outside the bead's own window (or, for escapes, outside the evaluation block), is not a candidate for this change — it is background noise reported elsewhere, never mixed into this change's gate.

**Declared-surface prefilter (applied first).** Where the frozen change specification (§1) declares an affected surface, a candidate whose deliverable or affected surface does not intersect the declared surface is excluded before attribution review — reported as background noise. A change with no declared surface skips the prefilter entirely.

A candidate that survives the eligibility/window test and the prefilter is **pending attribution** (below); it is not yet `regressed`.

### Hard gates: single-event triggers, no statistics

Two signals are **mandatory gates** and can never be reclassified as advisory, regardless of volume:

- Any **P0 or P1 finding** resolved `attributed` (below), on any deliverable.
- Any **escaped defect** resolved `attributed` (§2's reopened/reverted/failed-landing union), on any bead.

Each is a **single-event trigger**: one `attributed` occurrence is sufficient to fire it. There is no threshold, no rate comparison, no minimum count, and therefore no sample floor to reach before the gate can fire.

**Per-signal resolution point.** §2 defines two different anchors — first review-start for findings, first acceptance-close for escapes — and each signal resolves independently:

- **Finding status** resolves as soon as the bead's required first-revision review slot(s) are scored: `triggered` if any scored slot reports a P0/P1, `clear` if every required slot is scored with none, `unknown` if a required slot is unscored/invalid. This needs no seven-day wait and no bead close.
- **Escape status** resolves at the bead's first-close plus seven-day follow-up horizon, exactly as §2 defines it, for beads inside the evaluation block (§2's population rule). A bead still open at the block's end is out of scope, not a candidate at all — it never reaches this resolution step.

### Attribution review: `triggered-pending-attribution` before `regressed`

A `triggered` finding or escape status does not by itself produce `regressed`. It produces `triggered-pending-attribution`, which then requires an attribution review:

- The review's first pass may be performed by an agent, but the reviewer must not be the bead's own producer.
- The review records which surface of the change the finding or escape touches, as evidence (`Trigger.evidence_refs`, §5).
- The review resolves the candidate to exactly one of `attributed` (counts toward `regressed`) or `not-attributed` (treated as `clear`; the review records a `reason`).
- **Rollback needs mk's confirmation, and it is not a scorecard field (mk's 2026-09-27 final ruling, item 3, replacing round 4's `Repin.rollback_confirmation_ref`).** An `attributed` finding/escape makes the project `regressed` and sets `repin.required=true` (§4's Verdict aggregation), but the actual rollback action (§6) still requires mk's explicit confirmation, recorded as an external artifact — a bead note or decision record — bound to the report's action key (§6), and checked by Quilan's adapter independently of the report. The report itself carries only `repin.required`; there is no field in it for mk to fill in, because a report's stdout bytes are closed and hashed at emission time and nothing external can mutate them afterward (this is exactly why round 4's field-based mechanism could never be satisfied).
- **Deadline (P0-A).** Each `triggered-pending-attribution` candidate carries a frozen attribution deadline (`attribution_deadline_days`, §1, default 3 days), counted from **the moment this candidate's status became `triggered-pending-attribution`** — the per-signal resolution point above, never from the underlying finding's review-start anchor or the escape's close anchor. A candidate unresolved past that deadline is `unknown` for its signal **as of the report's `as_of`** — not `clear`, not `attributed` — which blocks `holds` under the no-vacuous-holds rule below.
- Until a candidate's attribution resolves (or its deadline expires), the bead/signal cannot contribute to `holds`.

### Per-bead resolution: stateless, recomputed from snapshot + spec + `as_of` (mk's 2026-09-27 final ruling, item 2, replacing round 4's "unknown is final")

Every report is a pure function of the snapshot, the frozen spec, and its own `as_of` cutoff. There is no stored scorecard state (§5): nothing a past report "decided" constrains a later report. For each candidate bead/signal, a report classifies it, **as of its own `as_of`**, as one of:

- `clear` — the signal is confirmed negative for this bead, or an attribution review recorded before `as_of` resolved a `triggered` candidate `not-attributed`.
- `triggered-pending-attribution` — the signal is confirmed positive, its attribution deadline has not yet passed as of `as_of`, and no attribution review is on record before `as_of`.
- `attributed` — an attribution review recorded before `as_of` confirmed the change caused it; this is what fires `regressed`.
- `unknown` — a required signal cannot be established (missing ordered transition history, absent cutoff-ref evidence, an unscored or invalid review), or the candidate's attribution deadline has passed as of `as_of` with no attribution review on record.

**This classification is a property of `as_of`, not a permanent designation.** A candidate that is `unknown` in a report run at `as_of=t1` because no review was on record by the deadline can be `attributed` or `not-attributed` (or remain `unknown`, if still nothing is on record) in a later report run at `as_of=t2 > t1`, if an attribution review was recorded between `t1` and `t2` — the later report simply sees more evidence than the earlier one and recomputes from scratch. A report never revises itself or another report's already-emitted verdict; each emitted report's stdout bytes are immutable once produced (§5). But nothing prevents re-running the reducer at a later `as_of` and getting a different, more-resolved classification for the same underlying bead/signal. A late attribution review is real evidence, usable by any report run after it is recorded — it is not merely "notes," and there is no separate finality rule to override that.

A single `attributed` bead/signal is sufficient to fire the gate: `regressed`. `triggered-pending-attribution` and `unknown` never fire the gate by themselves, but they also cannot be counted as `clear` — see "no vacuous holds" below.

### Mandatory gating set; no empty set, no vacuous holds

The gating set is always exactly `{P0/P1 finding, escaped-bead union}` — it is never empty, never shrunk to fit volume, and never reclassified as advisory for any project.

`holds` requires **all** of:

1. At least one attributed bead has a resolved finding status, and at least one attributed close-mature bead (inside the evaluation block, §2) has a resolved escape status, for the change in that project (i.e., there is actual evidence, not zero exposure). Report `Coverage.attributed_beads_scored` and `Coverage.mature_beads` (§5) as the counts.
2. Every candidate bead/signal, as of this report's `as_of`, is `clear` — zero `attributed`, zero `triggered-pending-attribution`, and zero `unknown`.

If neither `regressed` nor the full `holds` condition above is met, the verdict is `insufficient`. `insufficient` is not a default keep: lane A's own rollout stage gate governs whether a change stays exposed while evidence remains incomplete, per §6. Re-running the report at a later `as_of` can move an `insufficient` project to `holds` or `regressed` as more candidates resolve — this is expected, not a re-litigation of a past report.

### Verdict aggregation

For each project:

1. `regressed` if any bead/signal attributed to the change resolves to `attributed` (above), as of this report's `as_of`. Report the triggering bead, signal, and evidence in a `Trigger` record (§5).
2. `holds` only when the project satisfies the `holds` conditions above, and assignment/exposure evidence is complete per §3's confound checks (exact actual profile/model/effort/policy hash, instrument-epoch separation, fixed-except-treatment settings, and concurrent-change exclusion).
3. Otherwise `insufficient`, with the exact reason (`no_mature_beads`, `unresolved_bead_status` — covering both `triggered-pending-attribution` and deadline-expired `unknown`, or an existing confound exclusion reason).

Evaluate once per scheduled report (`--as-of`), not on a checkpoint/stopping-rule schedule. A regressed change/project remains reverted until an explicitly approved new experiment revision. Changing the rule version invalidates cached decisions.

## 5. Output contract

**Choose JSON on stdout.** Proposed command: `python3 scripts/quality-scorecard.py --spec <frozen-spec.json> --as-of <UTC>`. One UTF-8 JSON document, newline terminated; diagnostics only on stderr. Exit 0 means a valid report, including `regressed` or `insufficient`; exit 2 means malformed/unsupported input and no stdout document.

The caller may save the exact stdout bytes with its existing experiment artifacts and hash them for an action reference. No database migration, shared writable scorecard store or "latest" filename is part of the interface. Results are reproducible from snapshot/spec hashes and `as_of` — each `as_of` can produce a different result from the same underlying evidence as it accumulates, by design (§4). Publish the normative v1 field tables and metric definitions by extending `docs/canon/reasoning-routing-operations.md`, immediately after `### Receipt attribution fields`, as `### Quality scorecard contract` (S2). Do not put this object into the calibration reader's `agents` schema (S7).

`Comparison.worse`, `Metric.verdict`, `ProjectResult.verdict`, and `Report.overall` remain authoritative as emitted: a consumer must treat them as the decision, never recompute a verdict from `Cell.value`/`raw_value`. For the two hard-gate metrics (P0/P1, escaped-bead union), `Comparison.worse=true` means at least one bead/signal in that cell has resolved to `attributed` — a raw `triggered` or `triggered-pending-attribution` status alone is never sufficient. `Cell.adverse_beads` is the count of `attributed` beads; `Cell.diagnostics` carries a `pending_attribution_beads` entry alongside `unknown_beads`, so a consumer can see why a cell is `insufficient` rather than `holds`.

All fields below are required unless explicitly nullable. Unknown is JSON `null`, not zero/empty text. `Timestamp` is RFC3339 UTC ending in `Z`; `Hash` is 64 lowercase hex; `OID` is a full repository-format object ID; `ID` is a nonempty string. Objects are closed in v1; reject unknown fields, duplicate keys, nonfinite numbers, booleans used as counts. A compatible reader upgrade is required for new fields; bump `schema_version` for contract changes.

| Object | Fields and types |
|---|---|
| Report | `schema_version: 2`; `rule_version: "scorecard-hard-gate-v2"`; `generated_at: Timestamp`; `as_of: Timestamp`; `change: ID`; `change_revision: Hash`; `kind: enum from §1`; `landed_commits: CommitRef[]`; `sources: Source[]`; `projects: ProjectResult[]` (nonempty); `overall: Verdict`; `promotion_eligible: boolean`; `blockers: string[]`. |
| CommitRef | `project_key: ID`; `oid: OID`; `evidence_ref: ID`. |
| Source | `id: ID`; `kind: "routing-db"|"beads-history"|"git"|"assignment"`; `sha256: Hash|null`; `captured_at: Timestamp|null`; `watermark: ID|null`; `complete_through: Timestamp|null`; `status: "verified"|"missing"|"stale"|"inconsistent"`; `reason: string|null`. No credentials or prompt bodies. |
| ProjectResult | `project_key: ID`; `repo: ID` (owner/repo display); `change: ID`; `verdict: Verdict`; `promotion_eligible: boolean`; `metrics: Metrics`; `coverage: Coverage`; `confounds: string[]`; `triggers: Trigger[]`; `reason_codes: string[]`; `repin: Repin`; `blockers: string[]`. |
| Metrics | `review_findings: {P0: Metric,P1: Metric}`; `escaped_defects: Metric`. No optional gate metrics; no advisory-only entries. |
| Metric | `definition: ID`; `unit: ID`; `verdict: Verdict`; `comparisons: Comparison[]`; `reason_codes: string[]`; `evidence_refs: ID[]`. Definitions are exactly `reported-findings-v1` (severity-scoped to P0/P1), `escaped-bead-union-v1`; units are `findings/deliverable`, `affected-beads/bead`. |
| Comparison | `population: "attributed"`; `cell: Cell`; `worse: boolean`; `eligible: boolean`; `reason_codes: string[]`. There is no baseline/control comparison and no `tolerance` field: the hard-gate rule has nothing to compare against. |
| Cell | `numerator: number|null`; `denominator: number|null`; `value: number|null`; `raw_value: number|null`; `eligible_beads: integer`; `scored_deliverables: integer`; `mature_beads: integer`; `adverse_beads: integer`; `complete: boolean`; `diagnostics: Diagnostic[]`. |
| Trigger | `bead_ref: ID`; `signal: "P0"|"P1"|"escape"`; `status: "triggered_pending_attribution"|"attributed"|"not_attributed"|"unknown"`; `producer_ref: ID`; `event_ref: ID`; `evidence_refs: ID[]`; `reviewer_ref: ID|null` (null while `triggered_pending_attribution` or `unknown`); `reason: string|null` (required when `not_attributed` or `unknown` — for `unknown`, names the evidence gap or records that the deadline expired unresolved as of this report's `as_of`); `deadline: Timestamp`. A candidate's `status` here reflects this report's `as_of` only (§4); a later report on the same underlying bead/signal may carry a different `status` for the same `event_ref` if new evidence was recorded in between. One row per candidate bead/signal per report. |
| Stratum, TtlEfficiency | **Removed.** No stratification, no lineage/arm comparison, no TTL efficiency object in this design; see §8's Deferred list. |
| Diagnostic | `name: ID`; `value: number|null`; `unit: ID`. Required escape names: `reopened`, `reverted`, `closed_without_landing_7d`, `unknown_beads`, `pending_attribution_beads`, `out_of_block_beads` (beads excluded from escape candidacy for closing outside the evaluation block, §2 — reported for visibility, never a gate input). |
| Coverage | `attributed_beads: integer`; `attributed_beads_scored: integer` (attributed beads with a resolved finding status, §4); `mature_beads: integer` (close-mature attributed beads with a resolved escape status, §4); `eligible_deliverables: integer`; `scored_deliverables: integer`; `excluded_beads: integer`; `out_of_block_beads: integer`; `assignment_complete: boolean`; `history_complete: boolean`; `git_complete: boolean`; `exclusions: Exclusion[]`. |
| Exclusion | `entity_ref: ID`; `reason: ID`; `evidence_refs: ID[]`. Rows outside the declared population and invalid evidence remain auditable; no silent deletion. |
| Repin | `required: boolean`; `integration_ready: boolean`; `idempotency_key: Hash|null`; `expected_policy_hash: Hash|null`; `target_beads: ID[]`; `prior_profiles: PriorProfile[]`; `restore_settings: Setting[]`; `reason_metrics: ID[]`; `blockers: string[]`. This is a recommendation only; there is no `applied:true` in a scorecard, and no `rollback_confirmation_ref` field (mk's 2026-09-27 final ruling, item 3) — mk's confirmation is an external artifact, not a scorecard field (§4, §6). **`required=true` alone is never sufficient authorization to act.** |
| PriorProfile | `bead_ref: ID`; `role: ID`; `profile_ref: ID`; `policy_hash: Hash`; `backend: ID`; `model: ID`; `reasoning_effort: ID`; `service_tier: ID`; `receipt_ref: ID`. Values must come from the prior accepted execution/policy evidence. |
| Setting | `name: ID`; `value: string|number|boolean`; `unit: ID`; `configuration_ref: ID`. |
| Verdict | Exactly `"holds"|"regressed"|"insufficient"`. Overall is regressed if any project is regressed, holds only if every project holds, otherwise insufficient. |

`promotion_eligible` also requires ratified rule/proxy definitions, independent review, verified project identity, a prior rollback binding, passing runtime dry-run/canary and required existing rollout approvals. `holds` is a measurement result, not authority to publish or advance a stage. A consumer must reject a report for a different change revision, unsupported rule/schema, mismatching expected policy, absent target project, stale source watermarks or replayed decision.

## 6. Regression → Quilan action → Clavain record

For each regressed project, `repin.required=true` targets **all still-exposed beads attributed to that change in that project**, leaving unattributed work and unrelated projects alone.

**`repin.required=true` is a recommendation surfaced to mk; it is never by itself sufficient authorization for Quilan to execute a rollback (mk's 2026-09-27 final ruling, item 3).** The scorecard reports `repin.required` and carries no confirmation field (§5). mk's separate confirmation, once given, is recorded as an external artifact — a bead note or decision record on `change_id`, keyed to the report's action key below — through the existing approval channel. Quilan's adapter must independently look up that external artifact before acting: it checks for a recorded confirmation bound to the exact action key, not for any field inside the report. A missing confirmation blocks the action pending mk's separate approval, exactly like any other unmet pre-action check, regardless of `repin.required`.

The action key is SHA-256 of the canonical tuple `(change_revision,project_key,rule_version,evaluation_block_boundaries,report_as_of)`. Quilan persists that key through its existing operational journal/rollout state **when its owner implements the adapter**; this document does not claim a particular journal schema. mk's confirmation artifact must reference this exact action key, so a duplicate or later report with a different `as_of` cannot silently reuse an earlier confirmation. Before acting, the adapter checks current configuration/policy, role eligibility, project membership, manual pin state against the expected binding, **and the existence of a confirmation artifact matching the action key** — a missing match blocks the action pending mk's separate confirmation. A changed binding blocks the action for reconciliation; it does not restore a guessed default.

The proposed adapter restores each prior eligible execution profile and the setting that caused the regression, then resolves a fresh governed receipt through the selected policy with the original role and producer exclusions. It maps to S9's unchanged envelope: `policySha256`, `providerId`, `model`, `reasoningLevel`, optional `policyTier`, `producerExclusion`, `quotaFloor`, `role`, `reason`, `dispatchReceipt`. `dispatchReceipt` retains the full original nested resolver result. Backend→host provider mapping must use the installed adapter/catalog, never assume `claude` equals a BB provider name. The old receipt is rollback evidence, not a reusable dispatch authorization.

Existing manual pins win. No wake-up just to change idle threads, no shared `proj_personal` default write, and no role collapse from planning/validation/coordination to `lane`. These are necessary integration requirements in light of S12, not current behavior claims. The dry-run and live isolated canary must demonstrate restoration before live evaluation starts.

Clavain's policy record uses `config/routing.yaml`'s existing `reasoning.profiles` overlay: proposed name `scorecard-<project-slug>-<change-slug>`, scope `project:<slug>`, and only the affected `roles` mapped to the recorded prior profile refs (S10). Store the scorecard hash and reason beside the scoped change in the existing experiment evidence/commit; do not add unrecognized YAML fields and assume `ic` enforces them.

Runtime restore and policy commit are separate durable steps. A runtime failure leaves the action pending/failed and pauses new exposure; a policy-write failure does not undo a runtime restore. Never label both applied from an attempted command or a green scorecard. The consumer retains actual action evidence in its existing receipt/journal path, and retries idempotently. Existing verification, signing, branch protection and publication authority still govern the policy change. The design does not authorize this planning task to perform either step.

**Present integration gate:** S9's admitted mismatch and lack of production caller disprove the assumption that this path is ready. Escalate that premise to the task owner now. The implementing owners must fit a versioned adapter to real evidence and demonstrate runtime application plus scoped policy persistence and the external-confirmation-artifact lookup above. Preserve `routing-receipt.ts`'s contract; do not rewrite it to make synthetic fixtures pass.

## 7. Synthetic regression tests, written before implementation

Implement fixtures only in `tests/fixtures/quality-scorecard/` and focused behavior tests in `tests/structural/test_quality_scorecard.py`; use temporary SQLite copies, a temporary Git repository and authoritative-export-shaped bd history. No fixture is inserted into live Intercore or Beads.

**Base fixture.** Two verified synthetic projects, A and B, each with 40 distinct mature beads directly attributed to the same change within one evaluation block, 40 first-review deliverables with observed zero P0/P1, and 40 durable closes within the block. Give every attempt `started` and `completed` rows. Both projects mature at `as_of=t0+evaluation_block_days+7d`. Add prior tuples and complete assignment evidence; expected verdicts are `holds` in A and B, no repin.

**Inject a known escape regression.** In project A only, reopen ten of A's 40 beads two days after close and re-close three days after close, inside the evaluation block. Give each a linked corrective commit; keep the original closure and landing. Expected: A `regressed` on the escaped-bead union once the first `triggered` candidate's attribution review resolves it `attributed` (one attributed candidate is sufficient); repin required for A's attributed beads only; B holds; overall regressed. Re-run the same report at a later `as_of` with no new evidence: same decision key, no second runtime action.

Other first-class fixture assertions:

| Test | Mutation and required outcome |
|---|---|
| Only P0/P1/escape gate | Independently set one P0 or one P1 positive on a single distinct A bead, or reopen a single A bead (escape), and resolve its attribution review to `attributed`. Each single `attributed` event alone fires `regressed` — no count or rate threshold is checked. The same single event left at `triggered`/`triggered-pending-attribution` does not fire `regressed`; it holds the project at `insufficient` until attribution resolves. B remains unchanged throughout. |
| Single-event trigger, no sample floor | A project with exactly one mature bead whose P0 finding resolves `triggered` → `triggered-pending-attribution` → `attributed` reaches `regressed` immediately once attribution resolves — no 30-bead or 10-bead floor is checked. |
| Empty gating set is impossible | Attempt to construct a report where the gating set is empty: the implementation must reject this at the frozen-spec/validation level, not silently emit a report with zero gates. |
| No vacuous holds | A project with zero attributed mature beads (all in-flight or not yet matured) must report `insufficient` with `reason_codes` including `no_mature_beads`, never `holds`. A project with 39 of 40 attributed beads `clear` and one still `unknown` (unresolved ordered transition history) must report `insufficient` with `reason_codes` including `unresolved_bead_status`, never `holds`. |
| Escape candidate population (item 4) | A bead attributed to the change that closes inside the evaluation block but is still `triggered-pending-attribution` at `as_of=t0+evaluation_block_days+7d` blocks `holds` as `unknown`, per the ordinary deadline rule. A bead still open at the evaluation block's end (`t0+evaluation_block_days`) is reported in `Diagnostic.out_of_block_beads` and does **not** appear as an `unknown` escape candidate at all — it was never a candidate. A bead belonging to the same coordinator lineage as an attributed bead, but with no direct attribution evidence of its own, is not enrolled and does not appear in any escape-population count. |
| Stateless resolution across `as_of` (item 2) | A P1 candidate's attribution deadline expires with no review on record: a report at `as_of=t1` (past the deadline) classifies it `unknown` and reports `insufficient`. An attribution review is then recorded at `t1+1d`, resolving the candidate `attributed`. A report re-run at `as_of=t2 > t1+1d` classifies the same candidate `attributed` and reports `regressed` — this is not a revision of the `t1` report (whose stdout bytes are unchanged and immutable), it is a fresh computation over more evidence. A report at `as_of=t3` between `t1` and `t1+1d` still classifies the candidate `unknown`, since the review was not yet on record at `t3`. |
| Boundaries, including the P0-A deadline-anchor fix | An event exactly at +7d counts; at +7d+1s does not. A `triggered-pending-attribution` candidate exactly at its `attribution_deadline_days` boundary is still pending; one second past it becomes `unknown` (as of that `as_of`). An escape candidate whose bead closes at `t0+2d` resolves to `triggered-pending-attribution` at close+7d = `t0+9d`; its `attribution_deadline_days=3` deadline is `t0+12d` (three days after `t0+9d`, the status-assignment time), not `t0+5d` (three days after the close anchor). |
| Attribution review outcomes | A `triggered-pending-attribution` P1 resolved `attributed` by a reviewer other than the bead's producer fires `regressed`; the same candidate resolved `not-attributed` with a recorded reason is treated as `clear`; the same candidate left unresolved past `attribution_deadline_days` becomes `unknown` (as of that `as_of`) and blocks `holds` without firing `regressed`. In all three cases, `repin.required` for an `attributed` result still needs mk's separately recorded rollback confirmation artifact (§6) — never a field inside the report. |
| P0 fires without bead close | A bead's first required review scores a confirmed P0; the bead itself never closes before `as_of`. Finding status is `triggered` immediately, and once attributed, the project reaches `regressed` — even though the same bead's escape status remains out-of-scope for the escape gate (it never closed). |
| Declared-surface prefilter | A change with a declared surface excludes an out-of-surface P1 as background noise before attribution review. The same P1 under a change with no declared surface proceeds to attribution review normally. |
| Unknown ≠ clean | Replace a review with `source:unknown`, null findings, inconsistent total, missing slot or invalid terminal state: findings insufficient, never zero. |
| Lifecycle and joins | Duplicate started/completed rows; create two retries and three reviewers on the same bead. Deliverable denominator remains one. A conflicting terminal or ambiguous bead/session mapping invalidates the affected evidence. |
| Intended ≠ executed | Primary Sonnet with actual Opus fallback must appear as Opus exposure, invalidating the intended attribution. Same actual tuple as an unrelated project cannot prove exposure. Missing TTL/rotation activation proof is insufficient. |
| Histories and landing | Closed→open→closed must be detected even though the final snapshot says closed. Stale Git refs/missing object or commit binding are unknown, never failed landing. A genuine linked commit absent from the preserved default ref at +7d triggers the observable failed-landing proxy. Landing on day ten does not erase it. A local-only revert and a title-only "revert" do not count. |
| Project isolation | Two worktree aliases resolve to one project; the same bead token in two tracker namespaces stays distinct. A bad bead makes its project regressed despite otherwise clean evidence in the same project. |
| Review-packet trap | Treatment emits fewer raw findings but fixed independent validator finds ten omissions: quality worsens, not improves. |
| Confounds / parser | Wrong hash, unplanned branch exposure, reviewer change, absent project ID, unknown/fractional schema, duplicate JSON key or nonfinite number must never yield an eligible keep/action. |
| Runtime contract | Feed the emitted recommendation through the adapter into unchanged S9 schema; use a captured real nested receipt. Exercise unknown effort/provider, producer exclusion, manual pin changed after report, retry/replay, stale policy, and restart between restore and policy persistence. Exercise the external-confirmation-artifact lookup explicitly: a report with `repin.required=true` and no matching confirmation artifact must leave `integration_ready=false` and the adapter must refuse to act; a confirmation artifact bound to a different action key (e.g. an earlier `as_of`) must not satisfy a later report's action key. |

These fixtures prove reduction and action selection, not model quality in production. During implementation run the focused pytest suite, existing receipt-findings tests, the Quilan routing-receipt tests through its documented runner, and a real isolated restoration canary before treatment. Run the repository's required checks for each actual code change; do not replace independent review with fixtures.

## 8. Acceptance, open decisions and handoff

**Implementation acceptance evidence:** two actual projects (start with Clavain and a second project with complete history, such as Nartopo), immutable identity and source snapshot hashes, non-null computed values and denominators for both metric families, and coverage/exclusion lists. Supply an actual landed change's before/after evidence, not a simulated one. Supply the synthetic regression test result and an isolated runtime/policy-persistence canary. An insufficient real comparison is an honest view, but does not authorize retention.

**Decisions for mk (recommendations are explicit):**

1. Approve or replace `closed_without_landing_7d` for failed landings. Recommendation: use it alongside reopen/revert signals, stating that repaired push/CI failures and manual semantic undos are not measured.
2. Ratify the hard-gate rule as cut in this round: exactly two gates, `{P0/P1 finding, escaped-bead union}`; stateless per-`as_of` recomputation with no permanent-`unknown` rule (item 2); rollback confirmation as an external artifact keyed to the report's action key, never a scorecard field (item 3); escape candidacy bounded strictly to direct attribution within the evaluation block, with no lineage or successor-work inheritance and a still-open-at-block-end bead out of scope rather than `unknown` (item 4). This is a materially narrower design than round 4 — do not ratify against any prior description.
3. Confirm S9's real-receipt/runtime integration prerequisite with Quilan's owner, including the external-confirmation-artifact lookup (§6). Recommendation: an adapter preserving the hard interface plus the confirmation-artifact check, with no unrelated policy rewrite.
4. Confirm the second project's usable history and the real landed-change candidate once available. `bd-hub`/zklw access must provide verified transition history and repository identity; no legacy snapshot substitution.

**Deferred to `mk-42j9.43`** (mk's 2026-09-27 final ruling, item 1): the TTL efficiency check and its `TtlEfficiency` object; every previously "advisory trend" metric (P2/P3 findings, rework turns, beads-closed-per-hour throughput, weighted burn per closed bead); lineage-based enrollment, baseline/treatment/control block comparison, workload-stratum balance, and control-population drift diagnostics; and any future statistical (rate-based) gating design for the metrics above. None of this is computed, reported, or gated by this design. `mk-42j9.43` is seeded with the R1–R6 SPRT findings plus the three round-4 delta-review findings (P1-1, P1-2, P1-3) that this round resolved by scope cut rather than by further patching.

No new governed receipt field is required by this design. Missing lineage/exposure/subject bindings are explicit input/acceptance gaps. If existing evidence cannot resolve them, stop the affected gate and take the smallest requested schema/instrumentation expansion to mk as an open decision; do not fill them heuristically.

**Implementer handoff.** Add the small reducer/CLI and fixture tests, extend the existing receipt/calibration operations canon with §5's contract, then have the two lane consumers and Quilan adapter use that output. Preserve the cited store/receipt schemas. First verify the actual Beads history adapter; then implement reductions and the synthetic regression before evaluating real cohorts. The design is unsuitable for auto-rollout until independent other-frontier review, the open decisions and runtime canary are resolved. Escalate immediately if a source cannot establish subject/exposure/history or a prior tuple cannot be selected while preserving role/floor/exclusion rules.

### Round-5 revision checklist against §4's state machine

Every section below was checked against §4's revised state machine (stateless per-`as_of` resolution; external rollback confirmation; direct-attribution escape population with no lineage) and against mk's 2026-09-27 final ruling's five items (hard-gates-only cut, stateless fix, rollback fix, escape-population fix, matching §1/§5/§6/§7/§8):

| Section | Checked against | Outcome |
|---|---|---|
| §1 (frozen spec, keys/cardinality, read path) | Item 1 (hard gates only, no lineage), item 4 (direct attribution) | Rewritten: `ttl_price_table_ref` removed; `Lineage` entity removed; enrollment redefined as direct bead-to-change attribution; interstat/usage-reconciliation read-path steps removed. |
| §2 (two signals) | Item 1 (advisory trends removed), item 4 (escape population) | Rewritten: findings scoped to P0/P1 only, P2/P3 and rework/throughput/burn sections deleted; escape-candidate population redefined to direct attribution within the evaluation block, no lineage, still-open-at-block-end is out of scope not `unknown`. |
| §3 (renamed from baseline/treatment/confounds) | Item 1 (lineage/A-B removed) | Rewritten: baseline blocks, control lineages, stratification and control-drift diagnostics removed; kept the confound checks that establish actual exposure to the change. |
| §4 (state machine) | Item 2 (stateless), item 3 (rollback external), item 4 (escape population), item 1 (TTL/advisory removed) | Rewritten: "unknown is final" replaced with per-`as_of` stateless resolution and a worked cross-`as_of` example; `Repin.rollback_confirmation_ref` mechanism replaced with an external-artifact/action-key lookup; escape-candidate population section cross-referenced from §2; TTL section and "Everything else: advisory trend only" section deleted outright. |
| §5 (output contract) | Item 1, item 3 | Rewritten: `TtlEfficiency`, `Stratum`, `LineageResult`, `Repin.rollback_confirmation_ref` removed from schema; `Metrics` limited to `review_findings.{P0,P1}` and `escaped_defects`; `Trigger.status` documented as `as_of`-scoped, not final; new `Diagnostic.out_of_block_beads` name added. |
| §6 (rollback → Quilan → Clavain) | Item 3 | Rewritten: adapter now looks up an external confirmation artifact bound to the action key, never a report field; action key drops lineage/arm components. |
| §7 (fixtures) | Item 2, item 3, item 4, item 1 | Rewritten: TTL fixture, throughput/burn/rework/stratum fixture rows removed; new "Escape candidate population" and "Stateless resolution across `as_of`" fixture rows added; "Runtime contract" row updated to exercise the external-confirmation-artifact lookup instead of a null-field check. |
| §8 (decisions, handoff) | Item 1, item 5 (checklist) | Rewritten: decision 3's ratification paragraph replaced with the round-5 scope; new "Deferred to `mk-42j9.43`" list added naming every removed metric/mechanism; this checklist added. |

### Planning attribution and review gate

Accountable decision context, preserved from the task owner:

```json
{
  "reasons": ["difficult-verification", "broad-consequences"],
  "rationale": "Scorecard design gates lane A's Sonnet-default rollout and lane C's review-packet A/B; a wrong regression rule silently mis-calibrates routing across projects. Frontier-plan before implementation per task owner instruction.",
  "investigation_active": true
}
```

Selected policy: `/home/mk/projects/.clavain-laneB/config/routing.yaml`, SHA-256 `7209d67e29c4d9e668cb1ecd1d4d931600902cba4031fd35866b8b434b34f79b`, profile `default`. Local `ic --json route dispatch --role=planning` with that context resolved `planning-astra`, `gpt-6-astra`, `xhigh`, `standard`, matching the supplied dispatch. The observed started receipt is routing row 803, dispatch `be9d8c0d-2ccc-49e7-8f73-3808ac1cf41c`, attempt `3c0ae630-28ce-4942-ad96-e17cbd7cfb21`, actual execution `codex/gpt-6-astra/xhigh`; parent session `551543d1-0fcd-4856-93a2-5ecfab6a896b`. It is a started receipt, not terminal success or complete usage evidence.

Plan-review resolution with that actual producer identity selects `review-opus`, `claude-opus-5-5`, `high`, `standard`, excludes `review-astra` for `producer_model_conflict`, and has no remaining fallback. Preserve this other-frontier requirement; local self-check is not its substitute. The author dispatch's terminal receipt and usage are owned by the enclosing dispatcher and must be retained on handoff.

The packaged read-only plan-review dispatch was attempted with the selected policy/context and that producer identity. It exited 1 before review execution: `Error: cannot verify bb host enrollment for pooled claude dispatch`; the wrapper classified it `terminal_configuration` and suppressed fallback. This is an operational prerequisite failure, not quota or a capability strike. No provider/model bypass was attempted. Independent review is **outstanding**, and this design is not approved for implementation or rollout. The configured model-service standing authorization was sufficient; the failure was host enrollment verification, not a request for renewed repository consent.
