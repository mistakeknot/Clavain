# OODARC(+S) — Adversarial Judgment

Read-only. Verified against the tree: `internal/tool/registry.go:43-72,116-121,199-259`, `internal/session/session.go:78-102`, `internal/agentloop/autocompact.go:55-64,135-187`, `internal/contextfiles/contextfiles.go:22,38-68`, `internal/agent/agent.go:227-254`, `internal/agent/phase.go:10-52`, `internal/agent/deps.go:60-96`, `internal/mutations/signal.go:17-45`, `internal/mutations/mutate.go:13-98`, `internal/mutations/inspire.go:20-85`, `internal/trust/trust.go:112-232`, `internal/hooks/executor.go:76-148`, `internal/hooks/types.go:9-12`, `internal/evidence/emitter.go:113`.

## 0. Two facts that reframe the whole field

Both were missed by all three prior runs and both cut against the divergence pass's advanced five.

**(a) Skaffen compounds no propositions.** The entire durable output of Compound is `mutations.Aggregate` → `WriteForType` (`agent.go:247-253`), producing a `QualitySignal`: four hard rates, three soft rates, an approval rate, an outcome string (`signal.go:17-45`). The only prose in the loop is `Suggestion.Approach`/`Rationale`, which is **mechanically generated from those rates** by `Suggest` (`mutate.go:46-95`) — templated strings like `"Break into smaller steps — previous sessions averaged %d turns"`. No model-authored claim, lesson, or assertion is persisted anywhere.

**(b) There is a general middleware seat, and it already ships.** `internal/hooks` gives external commands `SessionStart`, `PreToolUse` (with a real `deny > ask > allow` decision), `PostToolUse`, `Notification` (`types.go:9-12`, `executor.go:76-148`). The divergence pass never mentions this package, and it is the collapse target for most of its field.

`★ Insight ─────────────────────────────────────`
The divergence pass's strongest move was "a non-empty gate delta earns a capability, not a letter." Applied one level further with the hooks package in view, most of its own five earn *not even a capability* — they earn a hook script. The correct test is not "does any existing phase do this" but "does any existing **seat** do this," and Skaffen has five seats, not six phases: gate table, router entry, prompt injection, evidence trigger, and hook event.
`─────────────────────────────────────────────────`

## 1. Strict collapse test

| Candidate | Collapses into | Verdict |
|---|---|---|
| **Stash** | `PreToolUse` hook (`executor.go:79`) + `internal/git`. A 4-line shell hook matching `write\|edit` that content-addresses the prior bytes implements the contract *completely*, with no Go change and no new concept. | **Rejected as operation.** Real gap (headless has no reversibility — `runPrint` never constructs a Git), wrong remedy. Ship as a bundled hook, or make `AutoCommit` unconditional. Not a candidate. |
| **Spool** | Compaction-internal storage. It changes one `fmt.Sprintf` at `autocompact.go:157` plus a fetch tool. `microCompact` is already a lossy cache; giving it a spill file is ordinary storage engineering. | **Rejected.** A cache with a backing store is not a semantic operation. File as a bug: `autocompact.go:157` discards `block.Name` too, which is a strictly cheaper fix than a spool store. |
| **Sequester** | Policy in `contextfiles.Load`. But its input **does not exist**: no production code writes `*.md`, no Compound prompt injection exists (`session.go:78-102` covers Orient/Act/Reflect only), and `manifestGlobs` (`registry.go:44`) is a *permission*, not a behavior. | **Rejected — empty input.** f-050's "Compound's manifest-globbed write" describes a capability the model may never exercise. The hazard is real but hypothetical; the fix if it materializes is an authority tier in `Load`, i.e. loader policy. |
| **Sentinel** | Compound contract + a store. Its input — a compounded claim with lesson text and source artifacts — **does not exist** (fact (a)). See §2. | **Rejected as phase; see §2 for the operation question.** |
| **Shed** | `defaultGates` + `PreToolUse` hook. A run-scoped narrowing is a `map[Phase]map[string]*GateConstraint` mutation; a plan-declared narrowing is a hook reading `SKAFFEN_PHASE`. `SetPlanMode` (`registry.go:158`) is already a live capability-narrowing switch — the divergence pass's "nothing in Skaffen narrows capability" is **false**. | **Rejected.** Also fails the relief test (f-035): `defaultGates` gives Observe/Orient/Decide all-`nil` constraints — no incumbent is straining. |
| Sediment / Sift / Stratify | `session/scoring.go` weights. | Policy fix, not candidates (divergence agrees on Stratify). |
| Seal / Sidecar / Splice / Shore | Annotation, dominated, read tool, anti-subtractive. | Correctly rejected. |
| Satisfice / Stagger / Shear / Stamp / Stake | Prompt clause / bug fix / metric / schema field / other system's problem. | Correctly rejected. |
| Scout / Trace | Gate signature is Decide's verbatim (f-060). | Rejected; standing. |
| Sunset/Reprove/Melt/Retire | One composite act (f-030), whose *object* is `QualitySignal` rows — rates with timestamps. | Survives as **one** capability, radically cheaper than specified: see §4. |

**Score: 0 of 21 divergence candidates survive as a phase. 0 survive as a distinct semantic operation. 2 survive as capabilities (Stash-as-hook, subtraction).** Phase/operation inflation is the dominant failure mode of the entire three-run corpus.

## 2. Falsifying Sentinel

The divergence pass calls Sentinel "the only candidate in the whole corpus whose output is a *new kind of object*." Three independent falsifiers:

**F1 — the subject term is empty.** A defeasibility predicate needs a proposition to defease. Skaffen's compounded artifact is a metrics row (`signal.go:17-45`). "This claim holds while `hash(registry.go:49-69) == X`" cannot be authored because no claim is written. Sentinel is therefore **not one operation but two**: *first* invent claim-compounding (a genuinely new Compound output type), *then* add predicates to it. The divergence pass priced only the second and inherited the first for free. Its own pilot exposes this: "hand-author predicates over the *existing* compounded corpus" — the existing corpus is `quality-signals.jsonl`, and the predicate over a rates row is `now - timestamp > window`, which is age.

**F2 — on the object that does exist, the predicate space is degenerate.** For `QualitySignal`, mechanical defeasibility is: recency, `TaskType` match, and source-commit equality. Recency is already implemented (`ReadRecent(5)`, `session.go:179`). Source-commit equality *is* Reprove. So on today's data Sentinel is exactly the collapse its own reversal condition names — "if the predicate distribution is dominated by one kind, Sentinel collapses into Reprove." That condition is satisfiable **by inspection, before any pilot**.

**F3 — phasehood vs. contract, decided.** "Author your defeat condition when you write the claim" is a **stronger Compound contract**, not a distinct transformation. The transformation Compound performs is `evidence → durable record`. Sentinel changes the *schema of the record* (add `predicate_kind`, `predicate_arg`, `last_eval`) and the *read filter* (drop rows evaluating false). Schema + filter. Both are seats Compound already occupies. There is no new input, no new consumer, no new trigger — evaluation at session start is `SessionStart` (`types.go:9`), which ships.

**Verdict on Sentinel: valuable as a Compound *contract clause*, void as an operation, void as a phase.** The value is real and I want to name it precisely: *if* Skaffen ever compounds propositions, the write must carry its own defeat condition. That is a design rule for a feature that does not exist. It should be recorded as a constraint on any future claim-compounding work, not ranked as an S.

## 3. Twelve additional candidates from demonstrable contract gaps

Each names a gap verified above. I reject synonym-only names by construction — every entry states the seat it occupies and the contract that is absent.

### Semantic transformation

| # | Name | Contract | Gap it fills | Survives collapse? |
|---|---|---|---|---|
| 1 | **Substantiate** | Before a turn's `Outcome` becomes durable, bind it to a machine-checked result (exit status of a named command, test name, build). Rows lacking a binding are written `outcome: unsubstantiated`. | `emitter.go:113` infers `success` from `StopReason == "end_turn"` — i.e. **the model stopping talking is recorded as success**, and that string is what `HumanSignals.Outcome` carries into `ParetoFront` and back into Orient. The one field the whole feedback loop is ranked on is unverified by construction. | **Yes — strongest new candidate.** New input (a check result), new transformation (assertion → warranted assertion), material output (a schema value no code can currently produce), nonempty enforcement delta (Reflect's prompt asks for tests; nothing reads the answer). |
| 2 | **Situate** | At Compound, key the durable row by the *source domain* actually touched (file paths, package, subsystem) rather than by `inferTaskType`'s verb substring. | Write key ≠ read key (f-054/f-062) is a symptom; the disease is that `ClassifyTask` (`inspire.go:43-59`) buckets on `strings.Contains(lower, "fix")` over the *prompt string*. A session that refactored `internal/router` files under `TaskDocs` because the prompt said "document". | Partly — this is a keying fix, i.e. schema. **Reject as operation, keep as required fix.** Honest: it is Stratify's sibling. |
| 3 | **Sift** (recontracted) | A durable row may enter the Orient prompt only if its `TaskType` was derived from the same signal on both sides. | Same gap as 2, expressed as a read filter. | **Reject** — dominated by 2; one fix, two names. |

### Safety / governance

| # | Name | Contract | Gap it fills | Survives collapse? |
|---|---|---|---|---|
| 4 | **Sunder** | Split `trust.Evaluator`'s auto-promotion so that reaching `PromoteThreshold` produces a *proposal* requiring an operator act, not a `ScopeGlobal` override. | `Learn` at `trust.go:143-164`: five session-scoped calls silently mint a **global, unexpiring, unattributed** allow rule (`Scope: ScopeGlobal`), with no timestamp, no session ID, no rationale, and no rate ceiling. `Revoke` exists but nothing surfaces what to revoke. This is a live privilege-escalation path with a counter for a gate. | **Yes.** Nonempty enforcement delta (the promotion is unconditional today), material output (a proposal record), and unlike Shed it *passes the relief test*: the deflecting incumbent is `Evaluator.overrides`, which grows monotonically with no expiry. |
| 5 | **Screen** | Give `Registry.Register` (`registry.go:125-132`) a non-`nil` default constraint for dynamically registered tools. | `Register` writes `r.gates[PhaseAct][t.Name()] = nil` — **every MCP plugin tool lands in Act fully unconstrained**, while built-in `edit` in Reflect carries `{RateLimit:3, RequirePrompt:true}`. Untrusted third-party tools are gated *more loosely* than trusted built-ins. | **Reject as operation** — this is a one-line default change. But it is the sharpest unfiled safety bug in the tree; file it. |
| 6 | **Sever** (recontracted) | A `PreToolUse` deny reason enters the durable record. | `PreToolUse` returns a `Decision`; nothing writes why. `SoftSignals.ToolDenialRate` is one of the two objectives that is **constant zero on every row ever written** (f-068). | **Reject** — schema field. |

### Time / pace policy

| # | Name | Contract | Gap it fills | Survives collapse? |
|---|---|---|---|---|
| 7 | **Span** | Add a wall-clock or spend deadline to `LoopConfig`, evaluated alongside `turn < l.maxTurns`. | `loop.go:135` bounds the loop by turn count only; `maxTurns` defaults to 100 (`loop.go:92`), a crash guard. `time.Now()` is used only for duration *reporting* (`loop.go:205,220`). **Skaffen has no time policy of any kind** — the entire prior policy field (Fallow/Stint/Season/Slacken/Divert/Widen) argues about clocks in a runtime with zero clock. | **Yes, as policy — not as an operation.** This is the honest occupant of the pace lane the divergence pass admitted it left empty. It is a `LoopConfig` field, and it should be ranked *against* the five policy claimants, not alongside them. |
| 8 | **Stagger** (recontracted) | Declare one compaction clock authoritative per execution mode. | f-033 (still `raw`): two clocks with different discard laws, one TUI-only. Verified: `acCfg` is built per-turn from constants (`agent.go:227-229`). | **Reject as candidate; required pilot control.** Divergence pass agrees. |
| 9 | **Suspend** | A hook event at the compaction boundary, so external policy can act before evidence is destroyed. | `hooks/types.go:9-12` has four events and **no `PreCompact`, no `PhaseTransition`, no `SessionEnd`**. This is the *general* form of Spool: not a spool store, but the missing extension point that would let anyone build one. | **Yes, as capability.** Strictly dominates Spool: same gap, one event constant instead of a new store, and it serves Stash-at-compaction, Sequester, and Sentinel-evaluation from one seat. |

### Subtractive maintenance

| # | Name | Contract | Gap it fills | Survives collapse? |
|---|---|---|---|---|
| 10 | **Sunset** (= Reprove/Melt/Retire, minimally recontracted) | `QualitySignal` gains `status` + `retired_at`; `ReadRecent`/`BestApproach` skip retired rows; nothing is deleted. | Confirmed: `QualitySignal` (`signal.go:17-45`) has no TTL, status, or validity field; the only forgetting is `ReadRecent(n)` recency. The store is `O_APPEND` with no rotation or GC. | **Yes — the one uncontested gap, and far cheaper than three runs assumed.** Because the object is a *rates row*, not prose, "deface never delete" is trivial and Stash's whole reversibility argument evaporates: a status flag is inherently reversible. |
| 11 | **Sluice** | Bound the *volume* of the Orient injection, not just its recency: cap `formatQualityHistory` + `Inspire` + `cassSearch` output as one budgeted region. | `session.go:80-91` concatenates three unbounded sources into the system prompt, one of which is verbatim subprocess output (`cassSearch`, `inspire.go:74`) with no length cap. `ReadRecent(5)` bounds one of three. | **Reject as operation** — prompt-assembly policy. Real bug; file it. |
| 12 | **Scour** | Retention/rotation for `quality-signals.jsonl` and the evidence dir. | No GC anywhere in `internal/mutations`. | **Reject** — ordinary storage maintenance. |

**Net: 4 survive collapse** — Substantiate (semantic), Sunder (safety), Suspend (capability/pace seat), Sunset (subtractive). Span survives as policy. Eight are rejected as fixes, schema, or synonyms, as required.

## 4. Comparison

Best surviving new candidate is **Substantiate**. Criteria are qualitative; uncertainty stated per cell.

| Criterion | **Substantiate** | Sentinel | Sunset/Reprove | Scout/Trace | no-S |
|---|---|---|---|---|---|
| Distinct transformation | **Yes** — unwarranted assertion → warranted or explicitly unwarranted. No phase does this (moderate-high conf.) | No — Compound schema + read filter (high conf., §2) | No — status transition on an existing row (high conf.) | No — Decide's gate set verbatim (high conf., f-060) | n/a |
| Material output | **Yes** — a schema value (`unsubstantiated`) no code path can currently emit | Yes, but over an object that doesn't exist | Yes — a status flag | A report into a channel with no remover | none |
| Enforcement delta | **Nonempty** — `emitter.go:113` is the only writer and it cannot fail | Nonempty but = Compound's own seat | Nonempty — `ReadRecent`/`BestApproach` filter | **∅** | ∅ |
| Epistemic safety | **Strongly positive** — removes a false-warrant generator | Positive in principle, unexercisable now | Positive — adds the missing remover | **Negative** — adds a writer, no grade (f-021) | Neutral-negative (the false-success bug is the null's) |
| Pace fit | Per-turn (fast). The only survivor on the fast layer | Two clocks, both hypothetical | Operator cadence (slow) | Undefined | n/a |
| Implementable today | **Yes** — one field, one check, one honest default. No new store | **No** — requires inventing claim-compounding first | **Yes** — two fields + two filters | Yes, cheaply, and it shouldn't be | n/a |
| Architectural simplicity | **High** — no new store, no new concept, no letter | Low — new object class + new store + new evaluator | **Highest** — no new store at all | Moderate | Highest |
| Marginal value over no-S | **High** (moderate conf.) — the null's ranking signal is currently unverified | Unknown; unmeasurable now (low conf.) | Moderate-high (high conf.) | **Negative** (high conf.) | baseline |

Substantiate and Sunset are **not rivals** — they are the two halves of one discipline: don't let unwarranted rows in, and let warranted-but-stale rows out. Sentinel is a *contract clause on a future feature*. Scout/Trace remain net-negative. `no-S` wins the letter question against all of them.

## 5. Strongest pro-S argument, then the rebuttal

**Pro-S, at full strength.** OODARC has five writers and no auditor. Observe, Orient, Decide, Act and Compound all add material; Reflect judges the turn just taken and emits nothing durable. Every path from work to durable memory is unwarranted: `Outcome` is inferred from a stop reason (`emitter.go:113`), `TaskType` from a substring of the prompt, `Suggestion` prose from templated rates, trust from a bare counter (`trust.go:150`). A loop that writes to its own future context and never checks what it wrote will converge on its own artifacts regardless of the world — and the artifacts are already there: `optimization.jsonl` is provably unwritable, two of six `Scores()` objectives are constant zero, and the auto-promoted global trust rule has no expiry. A letter is how an architecture makes a duty non-optional. Skaffen has a phase-typed gate table, a phase-keyed router, phase-conditional prompt injection and a phase-gated evidence write — four seats a letter binds at once and no capability binds any of. **S = Substantiate**: nothing enters durable memory without a warrant.

**Rebuttal, and it wins.** The argument is a case for *a contract*, and it smuggles in *a phase*. Every duty it names is dischargeable at a seat that exists: the warrant check is one field on `Evidence` and one branch at `emitter.go:113`; the trust ceiling is a change to `Learn`; the plugin gate is a non-`nil` default at `registry.go:131`. Adding a seventh phase costs seven enumerations to keep in sync (`tool.go` constants, `phase.go:10-16`, `registry.go:49-72`, `router.go:20-27`, `shadow.go:26,37`, `main.go:216-221`, `main.go:160`) — and **two of those seven are already out of sync for the sixth member**: `main.go:160` and `main.go:216-221` enumerate five phases and reject `--phase observe` while `phaseOrder` holds six. The mortise is loose and nobody has re-driven the wedge. Adding an S there means every headless pilot silently runs without the phase it is piloting. Worse, the FSM is forward-only with one human caller, `phaseDefaults` routes all six phases to one model, and Observe and Decide have byte-identical gate maps — Decide differs from Observe at *zero* load-bearing layer. A runtime that cannot enforce its sixth phase cannot be trusted with a seventh, and charging a candidate with phasehood in that runtime is a promotion with no duties attached. Take the contract; refuse the letter.

## 6. Verdicts

### (a) Semantic S — **none**

Confidence: **moderate-high**, and higher than the divergence pass's, because the falsifier is structural rather than empirical. Sentinel's subject term is empty (fact (a)); Substantiate is a *stronger Compound/emit contract*, not a new transformation.

- **Evidence tier:** code-verified (`signal.go:17-45`, `mutate.go:13-98`, `emitter.go:113`) — no pilot needed, no measurement outstanding.
- **Pilot:** none. This verdict is settled by inspection; running a pilot would be theatre.
- **Kill criterion:** n/a (the verdict *is* the null).
- **Reversal condition:** if Compound ever writes a model-authored proposition — a lesson, a claim, a rule — re-ask immediately. At that moment Sentinel's contract clause becomes mandatory: *the write must carry its own defeat condition, in a separate store, or it must not ship.* Record that as a standing constraint now.

### (b) Runtime S — **none**

Confidence: **high**. Converging across three runs, and I add one fact that strengthens it: `SetPlanMode` (`registry.go:158`) is a shipped run-scoped capability narrowing, so the divergence pass's "nothing in Skaffen narrows capability" — Shed's core claim — is false.

- **Evidence tier:** code-verified across nine files.
- **Pilot:** none, and none should be run.
- **Kill criterion:** n/a.
- **Reversal condition:** re-ask only after all three hold — (1) `main.go:160` and `main.go:216-221` are reconciled with `phaseOrder` for Observe; (2) `defaultGates` gives Observe, Orient and Decide three *distinguishable* signatures; (3) `ResetRateCounts` has a production caller. Until then the runtime cannot express a sixth phase, let alone a seventh.

### (c) First implementation — **Substantiate**, then **Sunset**

Confidence: **moderate-high** on ordering, **high** on both being worth doing.

1. **Substantiate.** Change `emitter.go:113` so `Outcome` requires a verification binding, and add `outcome: "unsubstantiated"` as the honest default. Ship the field before the check if that's cheaper — the field alone reveals the rate.
2. **Sunset.** `status` + `retired_at` on `QualitySignal`; `ReadRecent`/`BestApproach`/`Suggest` skip retired rows; never `os.Remove`. This is the one uncontested gap and it is ~30 lines, not the substrate project three runs assumed — because the object is a rates row, reversibility is a flag, not a content-addressed store.

**Do not ship** Stash, Spool, Sequester, Sentinel, or Shed. Two file as bundled hooks or bug fixes (Stash, Spool); one has no input (Sequester); one has no subject (Sentinel); one fails the relief test and rests on a false premise (Shed).

**Also file as bugs, independent of the S decision** (each verified, none a candidate): `Register` gives MCP plugin tools `nil` constraints in Act while built-in `edit` is rate-limited in Reflect (`registry.go:131`); `trust.Learn` auto-promotes to unexpiring global scope on a bare count of five (`trust.go:150`); `hooks` has no `PreCompact`/`PhaseTransition`/`SessionEnd` event (`types.go:9-12`); `microCompact` discards `block.Name` along with the payload (`autocompact.go:157`); the Orient injection concatenates unbounded `cass` subprocess output into the system prompt (`session.go:86-91`, `inspire.go:74`).

- **Evidence tier for (c):** the *gaps* are code-verified; the *magnitudes* are unmeasured.
- **Pilot (Substantiate):** retrospective, zero new instrumentation. Replay existing evidence JSONL and count rows where `Outcome == "success"` with no test/build signal in the same session. That fraction is the false-warrant rate the whole feedback loop is ranked on.
- **Kill criterion:** false-warrant fraction near zero — i.e. `end_turn` already coincides with real verification — in which case the field is decoration and only the honest default is worth keeping.
- **Reversal condition:** if `HumanSignals.Outcome` is removed from the ranking path entirely (no `ParetoFront`, no `Suggest` reference), Substantiate has no consumer and should be deleted.

### Where the evidence cannot rank

Stated plainly rather than papered over:

1. **No candidate in any of the three runs has a single measured outcome.** f-021 is right: every value ordering above is a *reasoned* ordering over code facts, not a measured one. I rank Substantiate above Sunset on argument, not on data.
2. **The five policy claimants remain unranked and I do not rank them.** The reason is now sharper than f-017's dial finding: `loop.go:135` bounds the loop by turns alone and `time.Now()` is used only for reporting. **There is no clock to argue about.** Any pace policy must first add one (candidate 7, Span). Ranking five clock policies in a clockless runtime is not a hard problem, it is a malformed one.
3. **f-070 and f-033 are still `raw` and I did not adjudicate them.** They matter less than the divergence pass thought — both of its f-070-dependent candidates fail on independent grounds — but the compaction-clock question is live for any future pilot.
4. **My rejections of the allocation family are inherited, not independent** — the same caveat the divergence pass declared. No pro-S lens has ever run in any of the four passes, including this one.
