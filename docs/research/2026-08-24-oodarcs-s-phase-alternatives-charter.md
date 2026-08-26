---
title: "OODARCS S-phase alternatives — Flux Melange charter"
artifact_type: review-charter
stage: research
status: proposed
---

# OODARCS S-Phase Alternatives: Review Charter

## Decision question

What, if anything, should the optional **S** in OODARC(+S) mean?

Generate strong alternatives and adversarially determine whether any deserves to be a distinct operation rather than behavior already contained in Observe, Orient, Reflect, or Compound. Preserve the letter **S** only when doing so improves the architecture; include **no S phase** and **S as a capability/side-loop rather than a phase** as live null hypotheses.

## Existing model

OODARC currently means:

1. **Observe** — gather current evidence and actual state.
2. **Orient** — interpret evidence in the current context and choose a useful frame.
3. **Decide** — commit to an action under explicit authority and uncertainty.
4. **Act** — execute within bounds and emit receipts.
5. **Reflect** — compare outcomes with expectations and identify supported lessons.
6. **Compound** — promote validated lessons into durable knowledge or reusable capability.

The broader architecture treats these as coupled loops at multiple pace layers rather than one mandatory linear turn sequence. Agent orchestration is an orthogonal topology over those loops. Any additional S operation should therefore be sparse, pace-aware, and explicit about authority.

## Current leading candidate: Scout

**Scout** searches related, lateral, and orthogonal domains for transferable mechanisms. It accepts a validated mechanism, unresolved contradiction, or detected shear and emits a bounded scout report:

- source domain and mechanism;
- correspondence mapping;
- where the analogy breaks;
- falsifiable prediction;
- reversible probe;
- `authority: speculative`;
- expiration or review condition.

Scout reports cannot become evidence directly. They must re-enter Observe → Orient → Decide → Act → Reflect, and only successful probes may later be Compounded. The proposed topology is:

```text
Reflect → Compound → Scout ⇢ Observe
```

Scout is conditional, not mandatory each cycle.

## Previously considered alternatives

These are seeds, not a closed candidate set:

- **Synthesize** — transfer supported mechanisms into other contexts and generate new frames or hypotheses.
- **Speculate** — explicitly generate lower-authority hypotheses and probes.
- **Stress-test** — attack the current model and search for disconfirmation.
- **Sensemake** — build a broader frame from accumulated evidence.
- **Search** — explore beyond the current task for relevant mechanisms.
- **Simulate** — run counterfactual or model-based trials before real action.
- **Share** — propagate compounded knowledge across agents, projects, or pace layers.
- **Select** — choose what deserves promotion, transfer, or further investigation.
- **No S** — retain OODARC and model cross-domain exploration as a conditional capability invoked by Orient or Compound.

## Required adversarial review

Do not merely produce synonyms or endorse Scout. Generate additional alternatives from adjacent, lateral, and orthogonal domains. Include at least one candidate inspired by each of:

- scientific discovery and falsification;
- control theory or cybernetics;
- intelligence analysis or reconnaissance;
- organizational learning or knowledge transfer;
- ecology/evolution or exploration-exploitation;
- rhetoric/linguistics/naming and mnemonic quality.

For every serious candidate, specify:

1. Distinct input and output contract.
2. Authority grade and storage boundary.
3. Trigger and natural pace layer.
4. Re-entry path into OODARC.
5. What existing phase it overlaps with and why it is not redundant.
6. Characteristic failure mode and Goodhart/gaming risk.
7. A falsifiable pilot or counterexample.
8. Whether it is truly a phase, an optional side-loop, a tool/capability, or merely an artifact type.

## Tournament criteria

Rank candidates using explicit criteria rather than rhetorical appeal:

- **Semantic distinctness:** minimal overlap with O/O/R/C.
- **Operational crispness:** enforceable input/output and state transition.
- **Epistemic safety:** speculative output cannot silently become durable truth.
- **Pace/shear fit:** natural cadence and cross-layer behavior are coherent.
- **Generativity:** finds useful alternatives beyond local optimization.
- **Falsifiability:** produces probes whose failure can retire the hypothesis.
- **Mnemonic/taste:** concise, verb-shaped, pronounceable, and durable.
- **Complexity cost:** earns a new letter rather than adding taxonomy.

## Required disagreement probes and fusions

The prior OODARC+S Melange run over-steered wide and performed no actual fusions. This review must explicitly probe disagreement and attempt fused reasoning before selecting a winner:

- **Scout vs Speculate:** outward search behavior versus explicit epistemic status.
- **Scout/Speculate vs Stress-test:** generativity versus falsification.
- **Any S vs No S:** distinct operation versus unnecessary phase inflation.
- **Phase vs side-loop:** mandatory lifecycle stage versus sparse escalation.
- **Synthesis vs Compound/Orient:** test conceptual duplication directly.
- Fuse at least two productive lens pairs and report whether the fusion yields a genuinely new candidate or contract.

## Required output

Return:

1. A diverse longlist, then a justified shortlist.
2. A scored comparison matrix with uncertainty, not false precision.
3. Strongest steelman and strongest attack for each shortlisted option.
4. Pairwise disagreement outcomes and fusion-emergent findings.
5. A recommendation with confidence and explicit conditions under which it changes.
6. Residual disagreements requiring human judgment.
7. A minimal read-only pilot for the top two choices plus the no-S null.

The goal is not to force an S. The goal is to find the smallest coherent operation that improves agent learning and cross-domain transfer without creating a competing truth channel or an ornamental seventh step.
