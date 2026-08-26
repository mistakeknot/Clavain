# fd-timberframe-load-path — round 2

Hand on the frame first. Before judging anything proposed, I established what the six
existing OODARC phases actually carry in this runtime, at every layer where a phase is
a load path rather than a word.

## Findings Index

- [P0] incumbent-phases-carry-nothing-distinctness-graded-on-the-acronym — criterion 1 measures candidates against a six-name vocabulary the runtime implements as a four-way gate partition, a one-way router, and a three-way prompt split; two incumbents differ at zero load-bearing layer and one is unreachable (§Comparison criteria, :56)
- [P0] no-relief-test-anywhere-over-constraint-is-unrankable — the only load-related obligation asks about duplication, whose passing answer is precisely the trigger for the relief question that is never asked (§Adversarial obligations, :77 with :52-65)
- [P0] champion-per-class-ranks-different-kinds-of-force — the four classes seat at four incommensurable structural layers, and requirement 5 mandates one winner across them with no common load named (§Required completion work, :37)
- [P1] admission-cut-never-located-cost-priced-as-new-member-size — seven enumerations must be cut to seat a phase claimant, two of them already out of sync with `phaseOrder` for the sixth member, and no required output records where the mortise lands (§Required output, :91 and :95)

## Findings

### incumbent-phases-carry-nothing-distinctness-graded-on-the-acronym

- **Severity:** P0
- **Where:** `docs/research/2026-08-24-oodarcs-s-phase-ranking-charter.md:56` (criterion 1,
  "semantic distinctness from O/O/D/A/R/C"), consumed by the ranking at :36-:37 and by the
  runtime-phase verdict at :47/:95.
- **What:** Criterion 1 is the charter's only structural admission test for a phase seat,
  and it grades the candidate against a *name list*. In the standing runtime the six names
  are not six members. At every layer where a phase carries load, the frame is coarser than
  the acronym — so a candidate can be genuinely distinct from all six words while being
  structurally identical to an incumbent, and criterion 1 will pass it. The tournament is
  defending inherited proportion and reporting it as load.
- **Evidence:**
  - `internal/tool/registry.go:49-58` — `PhaseObserve`, `PhaseOrient`, `PhaseDecide` have
    byte-identical gate maps (`read`, `glob`, `grep`, `ls`, every constraint `nil`). The
    gate table is a **four-way** partition of six names.
  - `internal/router/router.go:20-27` — `phaseDefaults` maps all six phases to `ModelOpus`.
    At the router, phase is **one-way**: it differentiates nothing by default.
  - `internal/session/session.go:78-102` — phase-specific prompt text exists for `Orient`
    (quality history + inspiration), `Act` (fault localization), `Reflect` (reflect
    guidance) only. `Observe`, `Decide`, `Compound` receive the bare prompt.
  - `internal/agent/agent.go:245-253` — the only other phase-conditional behaviour: evidence
    aggregation fires at `PhaseCompound`.
  - Net: **`Decide` differs from `Observe`/`Orient` at zero load-bearing layer.**
  - `cmd/skaffen/main.go:216-221` rejects `--phase observe`; `cmd/skaffen/main.go:160`
    enumerates five phases when applying `--model`; `internal/agent/phase.go:38-45` advances
    forward only; `internal/agent/agent.go:88` defaults the FSM to `PhaseAct`. **`Observe`
    is never entered.** It is trim that has been counted as structure for the whole
    tournament — and it holds an `Opus` routing default and a gate map anyway.
- **Failure scenario:** A candidate (say Assay or Trace) is admitted to the shortlist on a
  strong criterion-1 rating, wins the runtime-phase verdict at :47, and is implemented. Its
  actual runtime footprint is a seventh row in `phaseOrder`, a seventh gate map identical to
  the Observe/Orient/Decide one, a seventh `Opus` router entry, and no prompt injection —
  i.e. a second `Decide`. Nothing deflects less. Every future re-cut of the gate table and
  the sequence must now be made around it. Nothing in the ten criteria would have caught
  this, because all ten score the candidate and none inspects the frame.
- **Suggestion:** One clause added to :56 — the distinctness claim must be stated against
  the runtime's four actual differentiators (gate set, router entry, prompt injection,
  evidence trigger), naming which of the four the candidate would differ on and how. Plus
  one line added to the required output at :88-98: an incumbent census recording which
  existing phases differ from their neighbours at zero layers. This is a paragraph, not a
  redesign, and it makes the acronym-versus-structure question answerable instead of
  presumed.

### no-relief-test-anywhere-over-constraint-is-unrankable

- **Severity:** P0
- **Where:** `docs/research/2026-08-24-oodarcs-s-phase-ranking-charter.md:77` (adversarial
  obligation 5) with the criteria at :52-65.
- **What:** The nearest thing the charter has to a relief test is :77, "whether another
  existing phase or candidate carries the same load." That is a *duplication* test, and
  duplication and relief are opposite findings. "No existing member carries this" is the
  passing answer to :77 — and it is exactly the answer that should trigger the question the
  charter never asks: *then which existing member is currently deflecting under this load,
  and can that deflection be pointed at in the running system?* Nothing in the ten criteria
  (:54-65) or the five obligations (:71-77) requires a candidate to name a straining
  incumbent. Consequently over-constraint — support added where nothing is failing — is
  literally unrankable: it scores identically to relief.
- **Evidence:**
  - The charter's own only relief-shaped statement, ":26 subtraction/retirement is the
    clearest capability gap", is filed as a claim to verify, never converted into a
    criterion or an obligation, so it cannot influence :36, :37 or :48.
  - A policy claimant seated the way policy is seatable here is a `GateConstraint`
    (`internal/tool/registry.go:13-25`: `AllowedGlobs`, `RateLimit`, `RequirePrompt`) added
    to a phase's map. The three phases most likely to receive an exploration or spend policy
    — `Observe`, `Orient`, `Decide` — today have **no constraints at all**
    (`internal/tool/registry.go:49-58`, every value `nil`). There is no measured strain at
    that point in the frame for a brace to relieve.
  - The one wear point that does exist, `edit: {RateLimit: 3, RequirePrompt: true}` on
    `PhaseReflect` (`internal/tool/registry.go:65`), is enforced at
    `internal/tool/registry.go:243-256` against a counter whose documented reset —
    `ResetRateCounts`, `internal/tool/registry.go:116-121`, commented "call on phase
    transition" — has **no non-test caller anywhere in the tree**. The runtime's single
    existing constraint is not maintained; adding a second class of them is being ranked as
    if maintenance were free.
- **Failure scenario:** The first-implementation verdict (:48, :95) names a policy candidate
  — Fallow, Stint or Slacken. It is implemented as a new `GateConstraint` on a phase whose
  constraint map is presently empty. No operator complaint is resolved and no existing member
  deflects less; what changes is that every subsequent tool registration
  (`internal/tool/registry.go:121-133`) and every subsequent re-cut of the phase contract must
  now be made compatible with a restraint nobody asked for. The frame is heavier and no
  deflection anywhere has been reduced.
- **Suggestion:** Add one obligation under :69, alongside the existing five: "Name the
  existing phase, gate, store or loop that is currently deflecting under this load; point at
  it in the runtime; state what deflects less after admission. If no such member can be
  named, record the candidate as over-constraint and rank it below the no-S null." One
  bullet, and it is the bullet that separates a post from a decoration.

### champion-per-class-ranks-different-kinds-of-force

- **Severity:** P0
- **Where:** `docs/research/2026-08-24-oodarcs-s-phase-ranking-charter.md:37` ("Compare the
  strongest survivor from each class"), feeding :48 and :95.
- **What:** The four classes are not four competitors. In this runtime they are four
  different structural layers, and they take load in incommensurable ways. :37 mandates a
  single cross-class comparison with no common load named and no escape hatch permitting the
  answer "these are not comparable", so a category error is guaranteed to be reported as a
  comparative result.
- **Evidence:** Where each class actually seats:
  - **phase claimant → post.** A member of `phaseOrder` (`internal/agent/phase.go:10-16`);
    it carries the sequence, and the sequence is advanced only by a human typing `/advance`
    (`internal/tui/commands.go:196-213`).
  - **policy claimant → brace.** A `GateConstraint` field (`internal/tool/registry.go:13-25`)
    checked per tool call at `internal/tool/registry.go:243-256`. It resists a sideways load
    (spend, edit churn) and carries no sequence whatsoever.
  - **capability claimant → joint/fastening.** A `Registry.Register` /
    `RegisterForPhases` entry (`internal/tool/registry.go:121-133`); it exists only where a
    phase already stands and cannot stand alone.
  - **artifact claimant → finish.** An evidence/JSONL emission
    (`internal/agent/agent.go:245-253`); nothing in the runtime reads it back into a
    decision path.
  Now read the criteria against those: "semantic distinctness from O/O/D/A/R/C" (:56) is not
  a property a `RateLimit` integer can have; "enforceability in an agent harness" (:63) is
  not a property a mnemonic or a JSONL record can have; "generativity and validated
  discovery" (:58) is not a property a fastening can have. Each class champion is therefore
  scored on the rows its own kind can occupy and marked neutral on the rest.
- **Failure scenario:** Melt (subtractive), Assay (capability), Fallow (policy) and Frontier
  (artifact) are laid on the same ten rows. Fallow wins: policy rates well on epistemic
  safety and cost and cannot be marked down on the artifact and distinctness rows it never
  claimed. :48 reports "implement Fallow first". The runtime gains an exploration-quota dial
  while the one deflection the prior round actually identified (:26 — subtraction/retirement
  as the clearest capability gap) goes untouched, and the tournament's own strongest finding
  has been outvoted by a scoring artifact rather than refuted.
- **Suggestion:** Amend :37 to require a kind-of-force sort *before* the comparison, ranking
  only within a kind; cross-kind statements are permitted only in the forms "these are not
  competitors — both may be admitted" or "neither". If a cross-kind ranking is kept for
  decision convenience, require the single common load it is ranked on to be written in one
  sentence at the head of the table. Either version is a two-line edit to requirement 5.

### admission-cut-never-located-cost-priced-as-new-member-size

- **Severity:** P1
- **Where:** `docs/research/2026-08-24-oodarcs-s-phase-ranking-charter.md:91` and :95
  (required outputs: shortlist grouping, verdicts).
- **What:** Nothing in the required output (:88-98) asks where the mortise lands. Admission
  of a runtime-phase claimant is not the cost of making the new member; it is the set of cuts
  into the members currently doing the most work, and those cuts are spread across at least
  seven enumerations that must stay mutually consistent.
- **Evidence:** The seven cut sites for a seventh phase:
  1. `internal/tool/tool.go:47-54` — `Phase` constants (note the deprecated aliases already
     living there: `PhaseBrainstorm`, `PhasePlan`, `PhaseBuild`).
  2. `internal/agent/phase.go:10-16` — `phaseOrder`, i.e. the forward-only sequence itself.
  3. `internal/tool/registry.go:49-69` — `defaultGates`, the table **every** tool call is
     filtered through at `internal/tool/registry.go:243-256`. This is the most heavily
     loaded member in the frame; the mortise lands directly in it.
  4. `internal/router/router.go:20-27` — `phaseDefaults`.
  5. `internal/router/shadow.go:26,37` — the shadow routing ladders.
  6. `cmd/skaffen/main.go:216-221` — the `--phase` validator.
  7. `cmd/skaffen/main.go:160` — the `--model` override phase list.
  Sites 6 and 7 are **already out of sync** with site 2 for the sixth member: both enumerate
  five phases and omit `observe`, while `phaseOrder` enumerates six. This joint has already
  come loose once, without anybody re-driving the wedge.
- **Failure scenario:** An S phase is admitted and added to `phaseOrder` and `defaultGates`
  but not to `cmd/skaffen/main.go:216-221`. `--phase s` is then rejected in print mode while
  `/advance` reaches it in the TUI. Every headless pilot run required by :40 — the identical
  task buckets, stores, budgets and compaction treatment comparing the top two designs
  against the null — silently executes without the phase being piloted, and the pilot reports
  no difference from no-S. That is exactly the shape of the discrepancy already present for
  `observe`, so it is not a hypothetical failure mode; it is the observed one.
- **Suggestion:** Two additions. (a) At :91, require one "admission cut" line per shortlist
  member: which enumerations it must be entered into, and which of those is the most loaded
  at the point of the cut. (b) Add a **rebuild row** to the shortlist grouping — re-cutting an
  existing phase's contract (for instance giving `Decide` a gate set or prompt injection that
  differs from `Orient`'s, `internal/tool/registry.go:53-58` and
  `internal/session/session.go:78-102`) — so that "re-cut what stands" is a ranked entry that
  can win, rather than collapsing into the no-S null where it cannot.

## Verdict

The charter finishes a tournament about additions without ever putting a hand on the frame:
its one structural admission test grades candidates against the acronym, while in the running
system `Decide` differs from its neighbours at zero load-bearing layer and `Observe` cannot be
entered at all. Because no criterion or obligation asks which incumbent is deflecting, relief
and over-constraint score the same, and because requirement 5 forces a champion across posts,
braces, joints and finish, the first-implementation verdict can be decided by a scoring
artifact rather than by load. Four small edits — a structural distinctness clause, a relief
obligation, a within-kind ranking rule, and an admission-cut line with a rebuild row — leave
the tournament intact and make its result about what the frame carries.
