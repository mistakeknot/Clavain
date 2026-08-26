# fd-falsification-disconfirmation-contracts — round 1

## Findings Index

- [P1] policy-slot-survives-clustering-but-free-three-is-untyped — REFUTED as stated: the policy slot is contract-distinct and cannot cluster into Scout; the real construction bias is the three untyped slots at line 69 anchoring report-shaped against five report-shaped named seeds (§Candidate-generation requirement 60-73)
- [P0] hard-gates-are-non-severe-for-the-two-mandated-non-artifact-classes — the subtractive (70) and policy (71) candidates the charter mandates pass 3 of 5 hard gates with probability 1, so the gate battery supplies zero evidence about exactly the classes it was extended to admit (§Candidate-generation requirement 70-71, §Hard gates 95-101)
- [P1] subtractive-quota-satisfiable-by-a-field-of-scout — line 70 does not say what gets subtracted, so "expire stale speculations" fills the quota while duplicating a contract field every candidate already owes (82) and Scout already carries (29); the real gap is retirement of *validated* material (§Candidate-generation requirement 70)
- [P1] letter-s-is-an-undeclared-elimination-gate — orthography is absent from the hard gates but live as a comparative criterion (115), and the field this tournament actually produced is entirely non-S, so contract-superior survivors lose on spelling after passing every declared gate (§Candidate-generation requirement 60-71) [t]

## Findings

### policy-slot-survives-clustering-but-free-three-is-untyped

- **Severity:** P1
- **Where:** `docs/research/2026-08-24-oodarcs-s-phase-tournament-v2.md:60-73` (esp. 69, 71)
- **What:** The prior claim — "ten artifact/report-shaped slots against exactly one policy-class slot, so contract-equivalence clustering will fold the single policy candidate into Scout and the tournament will conclude S is a document by construction" — is **REFUTED on both the count and the mechanism**, but a weaker sibling of it survives and needs a fix.

  *Count.* The mandated field is twelve slot-lines, not eleven-of-which-ten-are-artifacts: five artifact-shaped named seeds (Scout, Speculate, Stress-test, Simulate, Synthesize), two null slots (61-67), three untyped free slots (69), one subtractive slot (70), one policy slot (71). Only **5 of 12** are report-shaped by name; the ratio against the policy slot is 5:1, not 10:1.

  *Mechanism.* Clustering cannot fold the policy candidate into Scout under the charter's own clustering rule (Lesson 6, line 42: cluster synonyms "unless their contracts, triggers, outputs, or authority differ"). Divert differs on three of the four axes at once — output (none vs. a speculative report), consumer (the router, not Orient), and authority (allocation budget, not an epistemic grade). Divert's mechanism has an existing, named home in code that Scout's does not touch: `complexityTracker.shouldEscalate()` at `internal/costrouter/complexity.go:99-125`, which already returns typed reallocation reasons (`cheap-turn-limit`, `file-scope-escalation`, `consecutive-failures`) against configured thresholds. A candidate that changes those thresholds shares no contract field with a candidate that writes a document. The clustering step is not where the policy class dies.

  *What actually survives.* The three untyped slots at line 69 are the field's only free capacity, and they carry a *novelty* quota ("not named in either charter") with **no class quota**. Every named exemplar preceding them is a report-emitter, so the free three are anchored report-shaped by example, while the subtractive and policy classes stay capped at one apiece — a floor, never a portfolio. The imbalance is real; it is anchoring in generation, not collapse in clustering.
- **Evidence:** target 42, 60-71; `internal/costrouter/complexity.go:99-125`; `internal/tool/registry.go` phase-gated registration (report-shaped candidates all land as tools/artifacts, Divert lands as routing config).
- **Suggestion:** Retype the line-69 quota by class rather than by novelty: "at least three candidates not named in either charter, of which at least one is non-artifact-emitting (policy, allocation, or authority-removing)." One clause, and the anchoring is broken without touching the clustering rule.

### hard-gates-are-non-severe-for-the-two-mandated-non-artifact-classes

- **Severity:** P0
- **Where:** `docs/research/2026-08-24-oodarcs-s-phase-tournament-v2.md:70-71` consumed by `:95-101` (Hard gates) and `:107-116` (Comparative criteria)
- **What:** The charter mandates two candidate classes that emit nothing (subtractive at 70, policy at 71), then routes them through a gate battery whose questions only bite on emitters. Against a policy or subtractive candidate:
  - "epistemic separation of speculative and validated material" — passed with probability 1 (there is no speculative material; this is already a settled fact for Divert);
  - "an explicit re-entry path" — passed vacuously (re-entry is the absence of a row, or a changed threshold on the next turn);
  - "a falsifiable output" — no output exists, so the disjunct silently degrades to "or losing condition," which every candidate asserts on paper.

  Under severe testing, a test a hypothesis passes with probability 1 confers no evidence. So the gate battery discriminates among report-shaped candidates and is **inert** for exactly the two classes the charter added to widen the field. Discrimination then falls entirely to the comparative criteria at 107-116, where the same candidates read N/A on "generativity beyond local optimization," "falsification and calibration," and "resistance to authority laundering" — three of eight. Net: the two non-artifact classes are gated by nothing and scored on the residue (implementation cost, mnemonic/taste).
- **Failure scenario:** Divert and Reprove both clear all five hard gates without producing a single piece of evidence, then arrive at the matrix with half their score cells empty. The adjudicator ranks them on cost and mnemonic — i.e., picks by taste — and either (a) a non-artifact candidate wins for reasons unrelated to epistemics, or (b) both are dropped as "thin" because their cells are blank, and the tournament re-converges on a document. Both outcomes are decided by the schema, not by the tournament. The verdict is corrupt either way, and nobody downstream can tell which happened because the gate log will read "passed" in both cases.
- **Evidence:** target 70-71, 95-101, 107-116; settled fact that Divert "emits no document and therefore satisfies epistemic separation trivially"; `internal/costrouter/complexity.go:99-125` (a policy delta is observable only as a threshold change, never as an artifact); `internal/mutations/store.go:26,56,99,134` (the store's whole surface is write/read of signals — a subtractive candidate has no write path to be gated on).
- **Suggestion:** Add a class-conditional gate row: a candidate that emits no artifact must instead name (i) the observable state variable it changes, (ii) the pre-registered magnitude of change that counts as the operation having fired, and (iii) the null-behavior baseline it is measured against. For Divert that is a measured shift in the escalation-reason mix from `complexityTracker.shouldEscalate()`; for Reprove it is a count of authority-grade demotions per corpus run. Passing must require a *number*, not the absence of an artifact.

### subtractive-quota-satisfiable-by-a-field-of-scout

- **Severity:** P1
- **Where:** `docs/research/2026-08-24-oodarcs-s-phase-tournament-v2.md:70`
- **What:** Line 70 requires "at least one candidate that primarily subtracts, retires, or prunes" but never says *what material* it acts on. Three very different operations satisfy that wording — expiring speculations, pruning non-replicating compounded knowledge, and demoting authority grades — and the cheapest of them is already owned by other parts of the charter. Contract field 4 (line 82) obliges **every** candidate to state "expiry, and retention of failed probes," and the Scout baseline at line 29 already carries "authority grade, and expiry." So a candidate whose entire job is expiring speculations is a mandatory field of every rival, promoted to a slot — the quota is satisfiable without generating a distinct operation, which is exactly the failure Lesson 6 (42) exists to prevent.

  The repo says which of the three is the real gap. Speculation expiry has an implemented analogue: TTL eviction in the web-search cache at `internal/tool/web_search.go:306-335` (`delete(c.entries, key)`). Retirement of *validated* material has none: the `Store` surface is `Write`, `ReadRecent`, `WriteForType`, `ReadRecentForType`, `Inspire`, `Suggest`, `BestApproach`, `BestSummary` (`internal/mutations/store.go:26,56,99,134`; `inspire.go:20`; `mutate.go:15`; `best.go:8,20`) — append and read, no delete, no demote, no staleness field on `QualitySignal` (`internal/mutations/signal.go:17-25` carries only `Timestamp`, never a validity horizon). `Store.Inspire` (`inspire.go:20-40`) reads `BestSummary`/`Suggest` over the whole history unconditionally, so a signal that stopped replicating a year ago still enters Orient's prompt today with full authority.
- **Failure scenario:** A lens fills the line-70 quota with "Sunset: expire speculative transfer reports after N days." It passes every gate, wins the additive-vs-subtractive disagreement at line 129 as the token subtractive entrant, and the tournament reports the subtractive class as adequately represented. The single capability the affirmative null identifies as carried by *no* named code — retirement of compounded, validated knowledge — is never contracted, and `Store.Inspire` keeps laundering stale `BestSummary` output into Orient forever.
- **Evidence:** target 29, 70, 82, 129; `internal/mutations/store.go:26,56,99,134`; `internal/mutations/inspire.go:20-40`; `internal/mutations/signal.go:17-25`; contrast `internal/tool/web_search.go:306-335`.
- **Suggestion:** Tighten line 70 to name the material: "at least one candidate whose primary output is the removal or demotion of *previously validated or compounded* material, not the expiry of its own speculative output (which every contract already owes under field 4)."

### letter-s-is-an-undeclared-elimination-gate

- **Severity:** P1
- **Where:** `docs/research/2026-08-24-oodarcs-s-phase-tournament-v2.md:13, 60-71`, scored at `:115`
- **What:** Every named exemplar in the mandated field starts with S (Scout, Speculate, Stress-test, Simulate, Synthesize), and the Decision framing at line 13 scopes the tournament to "an optional **S** operation." Orthography is therefore a live constraint on generation — but it appears nowhere in the hard gates (95-101), and it re-enters at scoring time as "mnemonic/taste" (115). That is an undeclared gate applied after the declared ones, which is precisely the pre-registration violation this charter enforces elsewhere ("Predeclare thresholds and losing conditions," 157).

  It is not hypothetical: the field this tournament has actually produced — Trace, Assay, Reprove, Frontier, Divert — contains **zero** S-names. Under line 115 all five are penalized against "Scout" for a property unrelated to their contracts, and the charter's own closing warning about "an ornamental seventh step" (172) supplies the rhetorical cover.
- **Evidence:** target 13, 60-71, 115, 157, 172; the round's contracted candidates (Trace, Assay, Reprove, Frontier, Divert) are all non-S.
- **Suggestion:** State in §Candidate-generation requirement that names are placeholders and that mnemonic scoring is applied **after** contract ranking, by renaming the winner if needed (Reprove→Sunset, Assay→Screen, Trace→Sound, Frontier→Salient, Divert→Shunt all exist). No candidate may be eliminated or down-ranked on its initial letter.

## Verdict

The prior finding is refuted as stated — the count is 5:1, not 10:1, and the policy candidate is contract-distinct on outputs, consumer, and authority simultaneously, so the charter's own clustering rule cannot fold it into Scout. What actually biases the field toward documents sits one step later: the three untyped free slots anchor report-shaped, and the hard-gate battery is inert against the two non-artifact classes the charter mandates, so those candidates pass with probability 1 and are then adjudicated on cost and spelling. Fix the class quota at line 69, add a class-conditional gate requiring a measured state delta from non-emitting candidates, name the material the subtractive slot must act on, and demote the letter S to a post-ranking rename.
