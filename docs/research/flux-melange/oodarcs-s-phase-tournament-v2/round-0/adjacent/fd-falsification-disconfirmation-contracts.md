# fd-falsification-disconfirmation-contracts — round 0

Seed position 2 (falsification advocate). Contracts centred on disconfirmation, anomaly, and
retirement, plus the adjudication of generativity versus error correction. Every runtime claim
below is verified against committed code.

## Findings Index

- [P0] contract-retire-subtractive — Retire: a candidate whose only output is removal; nothing in Skaffen expires or demotes anything, so this is the null's one provable gap (§Candidate-generation requirement)
- [P0] contract-stress-test-vs-reflect — Stress-test survives the Reflect overlap test on a real trace: Reflect is confirmatory repair of this turn's diff, not severe testing of a claim (§Mandatory disagreement and fusion work)
- [P1] contract-anomaly-ledger-reuses-experiment-record — negative-result retention is already implemented once in `internal/experiment`; the anomaly candidate should reuse that schema, not invent a store (§Per-candidate contract)
- [P1] no-obligated-reader-for-retirement — every candidate, including no-S, has a losing condition but no one obliged to look for it after the pilot ends (§Pilot contract)
- [P2] generativity-vs-error-correction-flip-unpredeclared — the mandated comparison is unanswerable unless the corpus records which bucket each task is in and the flip condition is pre-registered (§Pilot contract)

## Findings

### contract-retire-subtractive

- **Severity:** P0
- **Where:** §Candidate-generation requirement (target line 70, "at least one candidate that primarily subtracts, retires, or prunes"); runtime anchors `internal/mutations/store.go:26-52,99-131`, `internal/mutations/signal.go:17-46`, `internal/agent/deps.go:61-96`, `internal/tool/quality_history.go:44-60`
- **What:** Contract for **Retire** — the subtractive candidate.
  1. *Input:* any durable record that carries an expiry or a replication expectation — a speculative report past its review date, a compounded lesson whose predicted effect has not recurred in N subsequent sessions.
  2. *Transformation:* demote or expire. Not deletion: a status transition from `active` to `expired`/`demoted`, with the reason recorded.
  3. *Output/consumer:* a retirement record; consumers are every read path that currently treats stored material as current.
  4. *Authority/storage/retention:* retirement records are themselves durable evidence about base rates — an expired transfer from source domain X is data about X's transfer yield.
  5. *Trigger/pace:* slow layer — a scheduled sweep, not a per-turn operation.
  6. *Re-entry:* Retire feeds Orient by *removing* material, so it needs no promotion path — which is precisely why it is the epistemically safest S candidate on the board.
  7. *Runtime delta:* a status field plus a read filter; both stores are currently append-only JSONL with no status concept.
  8. *Overlap:* none. Compound only adds.
  9. *Failure/Goodhart:* over-pruning driven by a recency window; retire on failed replication, never on age alone.
  10. *Losing condition:* on the corpus, Retire loses if suppressing expired material does not reduce false-transfer cost.
  11. *Classification:* capability at minimum; phasehood only if a scheduled trigger is enforced.
- **Evidence, verified:** nothing in Skaffen retires anything. `mutations.Store.Write` opens with `O_APPEND` and never rewrites (`store.go:26-52`); `WriteForType` appends a second copy to a per-type file (`store.go:99-131`); `QualitySignal` has no TTL, status, or validity field (`signal.go:17-46`); `agent.Evidence`'s 25 fields include no expiry (`deps.go:61-96`). The only thing resembling forgetting is `ReadRecent(n)`, a *recency window* used by `quality_history` (`quality_history.go:44-60`) — which is not retirement: a stale record stays eligible forever and reappears whenever traffic is quiet.
- **Failure scenario:** a speculative transfer written once is read back into Orient months later with the same standing as a validated one, because the only filter is "is it in the last n lines". Nobody is notified; the material simply never dies.
- **Suggestion:** promote Retire from a checklist item to a named shortlist candidate, and require every other candidate's contract field 4 to name *which* retirement operation removes its output — a candidate that cannot name one has no expiry, only a claim of one.

### contract-stress-test-vs-reflect

- **Severity:** P0
- **Where:** §Mandatory disagreement and fusion work (target line 126, generative candidates vs Stress-test) and §Tournament gates (line 96); runtime anchors `internal/tool/registry.go:63-66`, `internal/session/session.go:99-101` and the `reflectPhaseGuidance` block at `session.go:149-167`
- **What:** The charter's lesson 8 says apply the same distinctness criteria to incumbents; the live question for this lens is whether Stress-test is "Reflect with a wider aperture". Tested against the actual Reflect contract, it is not. Reflect's runtime contract is: read/glob/grep/ls/bash plus `edit` constrained to `RateLimit: 3, RequirePrompt: true` (`registry.go:63-66`), with prompt guidance that says verify the changes made in Act, do not modify test files, up to 3 edit attempts (`session.go:149-167`). That is **confirmatory repair of the current diff**, scoped to one session's Act output.
  Stress-test's contract by contrast: *input* is a claim or model, not a diff; *transformation* is designing an observation that would kill the claim; *output* is a severe test plus its result; *consumer* is whoever holds the claim, possibly in a later session; and it needs the one capability Reflect is explicitly forbidden — authoring new tests. So it passes semantic distinctness on input, consumer, and licence, and it has a real, enforceable gate delta (a write gate for test paths that Reflect denies).
- **Failure scenario if this is not adjudicated:** the tournament eliminates Stress-test as "already Reflect", and the loop keeps a phase that can only repair the diff it just produced while nothing can ever attack a claim it already believes.
- **Suggestion:** record this as a settled disagreement outcome with its evidence, and require the Stress-test contract to state its gate delta as test-path write access — the discriminator that survives the elimination round.

### contract-anomaly-ledger-reuses-experiment-record

- **Severity:** P1
- **Where:** §Per-candidate contract field 4 (target line 82, retention of failed probes); runtime anchors `internal/experiment/store.go:15-19,33-52`, `internal/experiment/analyze.go:130-145`, `internal/experiment/gitops.go:132-146`
- **What:** Contract for **Anomaly-capture**, and a reuse verdict. Charter lesson 5 ("do not erase failed probes") already has a working implementation in this repo, in a subsystem neither charter cites. `ExperimentRecord` carries `Hypothesis`, `Status`, `MetricBefore/After`, `Delta`, `AgentDecision`, effective `Decision` (keep/discard), `OverrideReason`, and `GitSHA` (`experiment/store.go:33-52`); records are typed (`RecordTypeSegment|Experiment|Summary`, `store.go:15-19`); and `analyze.go:130-145` counts kept versus discarded, so **discard rate per mutation type is already a computed base rate**. Note the precise separation: `DiscardChanges` destroys the failed probe's *code* (`gitops.go:132-146`) while the record of the failure survives — exactly the behaviour the charter demands.
  The anomaly contract is therefore: same JSONL-with-record-type pattern, one added field (`source_domain` or `claim_id`), `Decision: "disconfirmed"`, and a read path that reports disconfirmation base rates per source.
- **Failure scenario if ignored:** the tournament invents a third store for negative results, and Skaffen ends with three parallel append-only ledgers (`~/.skaffen/evidence`, `~/.skaffen/mutations`, `~/.skaffen/experiments`) plus a fourth, none of which can be queried together.
- **Suggestion:** add a contract field requirement: name the *existing* store the candidate extends, or justify a new one. For every disconfirmation candidate the answer should be `internal/experiment`'s record schema.

### no-obligated-reader-for-retirement

- **Severity:** P1
- **Where:** §Pilot contract (target lines 148-157) and §Required output item 10 (line 170)
- **What:** The pilot names six blind-scored measures and says thresholds are predeclared, and the required output names reversal conditions. Neither names **who is obliged to look, and when**. A losing condition that nobody is scheduled to evaluate is ceremonial: after the pilot ends, the winning candidate has no standing retirement check, and the no-S null has none either.
- **Failure scenario:** the pilot is scored once, S ships, and eighteen months of evidence that it produces no validated discoveries accumulates in an append-only file that only `ReadRecent(5)` ever touches. The reversal condition in output item 10 is never evaluated because no one owns it.
- **Suggestion:** add a twelfth per-candidate field: *standing review* — who evaluates the losing condition, on what cadence, against which query. For the no-S null, the same obligation applies symmetrically: name the recurring check that would retire the null.

### generativity-vs-error-correction-flip-unpredeclared

- **Severity:** P2
- **Where:** §Pilot contract (target lines 142-147) and §Mandatory disagreement (line 126)
- **What:** The charter demands an adjudication of exploration versus disconfirmation but designs a corpus with four mixed buckets (hidden mechanisms, tempting false analogies, unresolved contradictions, no-benefit cases) and scores them in aggregate. Aggregated, the two candidate families cancel: generative candidates win the hidden-mechanism bucket, disconfirmation candidates win the contradiction and false-analogy buckets, and the aggregate reports no difference.
- **Suggestion:** require per-bucket reporting and pre-register the flip hypothesis — for example: "error correction dominates when the contradiction bucket exceeds X% of tasks; generation dominates when hidden-mechanism density exceeds Y%". That is a risky prediction the corpus can actually break, and it is more informative than a single aggregate ranking.

## Verdict

Retire is the strongest candidate this lens can put on the board, and the reason is empirical
rather than philosophical: Skaffen's three durable stores are all append-only with no status,
expiry, or demotion anywhere, so retirement is the one operation the no-S null demonstrably
does not carry. Stress-test survives the Reflect overlap test on a real trace — Reflect is
rate-limited repair of the current diff, not severe testing of a claim — and it has a genuine
gate delta in test-path write access. Negative-result retention needs no new design: the
`ExperimentRecord` keep/discard ledger already does it, and every disconfirmation contract
should extend that schema rather than open a fourth JSONL file.
