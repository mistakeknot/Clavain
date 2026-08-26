# OODARC Optional-S Research Corpus

**Date:** 2026-08-25
**Source repository:** Skaffen at `26e2d38c679a53922f02085919f61c7ce9662040`
**Method:** adaptive Flux Melange tournaments, focused Claude Code Opus 5 reviews, and parent source verification.
**Status:** research decision record; no Skaffen source implementation is included.

**Alignment:** Supports Clavain's orchestration and gate-reliability priorities by separating semantic duties from runtime phase inflation and by grounding recommendations in observable, reversible contracts.
**Conflict/Risk:** The code findings are a snapshot of Skaffen at the source commit above. The final Flux ranking synthesis failed operationally, no live Skaffen evidence stores were present for the retrospective census, and raw ledger claims must not be treated as adjudicated conclusions.

## Canonical conclusion

- **Semantic operation:** `Stipulate` is the strongest provisional S only when understood as the complete warrant lifecycle: pre-register criteria before Act, bind evidence after Act, and redeem into a material scorecard. A write-only stipulation should not ship.
- **Runtime phase:** no seventh phase. Use the existing Decide→Act and Reflect→Compound edges; reconsider only if mid-run replanning creates a back-edge and phase enforcement is repaired.
- **First implementation:** repair evidence adapters and phase-aware tool enforcement, then ship process substantiation, then pilot Stipulate plus claim substantiation and a scorecard.
- **Score:** useful as a scorecard artifact, but not one semantic operation. Per-run scoring is adjudication/reduction; cross-run scoring is the existing `QualitySignal.Scores`/Pareto path and needs typed unknown handling and calibration.
- **Sunset:** retain as a slow-loop capability. Skaffen may invalidate derived cache locally; retirement of authority-bearing claims should be proposed by Skaffen and recorded by Intercore.
- **Scout/Trace:** does not earn phasehood; its effective gate delta against existing exploration seats remains insufficient.

## Start here

1. [Deep-dive synthesis: Stipulate, Substantiate, Score, Sunset](claude-p/oodarcs-s4-deep-dive/2026-08-25-synthesis.md)
2. [Focused contract anatomy — Opus 5](claude-p/oodarcs-s4-deep-dive/contract-anatomy-opus.md)
3. [Focused adversarial judgment — Opus 5](claude-p/oodarcs-s4-deep-dive/adversarial-judge-opus.md)
4. [Balanced Flux tournament synthesis](flux-melange/oodarcs-s-phase-tournament-v2/2026-08-24-synthesis.md)
5. [Initial Flux alternatives synthesis](flux-melange/oodarcs-s-phase-alternatives/2026-08-24-synthesis.md)
6. [Final ranking heat ledger](flux-melange/oodarcs-s-phase-ranking/heat-ledger.jsonl)

## Charters

- [Initial alternatives charter](2026-08-24-oodarcs-s-phase-alternatives-charter.md)
- [Balanced tournament charter](2026-08-24-oodarcs-s-phase-tournament-v2.md)
- [Final ranking charter](2026-08-24-oodarcs-s-phase-ranking-charter.md)
- [Stipulate–Substantiate–Score–Sunset charter](2026-08-25-oodarcs-stipulate-substantiate-score-sunset-charter.md)

## Corpus layout

### Flux Melange

- `flux-melange/oodarcs-s-phase-alternatives/` — first three-round adversarial review; 33 findings, 28 upheld, 5 refuted. Methodological caveat: all initial lenses were anti-S and no candidate tournament ran.
- `flux-melange/oodarcs-s-phase-tournament-v2/` — balanced generation and contract tournament; 73 findings, 47 upheld, 12 refuted, 14 raw, with six attempted fusions.
- `flux-melange/oodarcs-s-phase-ranking/` — final ranking rounds and 37-finding ledger. Its workflow failed before producing a synthesis; use the ledger with its `upheld`, `raw`, and `refuted` status fields intact.

### Claude Code Opus 5

- `claude-p/oodarcs-s-alternatives/` — divergent, skeptical, and pro-S passes that generated and tested Spool, Sequester, Stash, Sentinel, Shed, Substantiate, Sunder, Suspend, Span, Sunset, Stipulate, Spread, Strand, and related candidates.
- `claude-p/oodarcs-s4-deep-dive/` — focused comparison of Stipulate, Substantiate, Score, Sunset, and no-S, including source-grounded dataflow, state-machine, authority, and pilot analysis.

Raw JSON outputs are retained beside rendered Markdown to preserve model identity, session metadata, and provenance. Claude Code reported `claude-opus-5` for the retained focused runs.

## Important source findings

The focused review found prerequisites that supersede the phase-naming question:

1. Normal terminal turns are recorded as success without verification.
2. Computed failure classification is dropped at the agent-loop adapter.
3. File/model provenance is dropped during mutation aggregation.
4. Several quality axes have no production writer or test an unreachable value; the effective frontier is primarily token efficiency versus turn count.
5. Tests/build fields are inert in cross-session scoring.
6. Aggregate uses the final turn instead of reducing observations across the run.
7. Phase membership is enforced, but the flat `toolBridge` path bypasses gate constraints, sandbox path validation, and phase-aware execution.
8. `RequirePrompt` lacks production enforcement and rate counters lack a production reset.
9. Compound-only persistence excludes aborted/error sessions and creates selection bias.
10. The experiment record/event path contains useful warrant-like fields but is disconnected across adapters.

These are research findings, not fixes in this corpus. Verify against current Skaffen before creating implementation work.

## Evidence boundaries

- Durable Flux ledgers distinguish `upheld`, `raw`, and `refuted`; preserve those statuses.
- The final ranking workflow timed out and its resume journal duplicated unfinished verifier launches. Do not represent it as a completed Flux synthesis.
- Two salvage reviewers also timed out after producing partial analysis; the parent synthesis relied on durable artifacts and fresh Opus 5 reviews instead.
- No `~/.skaffen/evidence`, `mutations`, or `experiments` stores existed on the research machine, so value ordering remains reasoned over code facts rather than measured runtime outcomes.
- A focused Go validation run was not clean: the local Masaq replacement was absent, a mutation test hung in external `cass`, and experiment worktree tests failed. The research corpus makes no passing-test claim.
