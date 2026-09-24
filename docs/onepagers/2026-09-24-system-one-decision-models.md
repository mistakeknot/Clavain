---
artifact_type: onepager
distills: docs/brainstorms/2026-09-24-system-one-decision-models-brainstorm.md
bead: none
stage: discover
---

# System One decision models — one-pager

**Thesis.** Clavain's token bill comes from the main thread re-sending context,
not from the decisions it makes. The main thread still does many of those
decisions: which agents to run, whether to delegate, whether to stop. Moving
them onto a cheap, calibrated System One layer (CLM by default, Jev optional)
shrinks the expensive thread. It also turns fixed-depth reviews into early exits
based on confidence.

**How it works.**
- **One decision layer.** `clavain-cli decide` takes a typed question plus
  state and returns `{choice, probs, confidence}`. It calls models served by
  interfer (CLM) or hosted Jev, and logs through `ic` with a JSONL fallback.
  It moves to `ic decide` once the contract is stable. The backend (CLM, Jev or a heuristic) is
  chosen per decision in `routing.yaml` under `decision_models:`, with
  off/shadow/enforce modes.
- **Deterministic fallback on every call.** If confidence falls below the B5
  bands (accept ≥0.8, escalate <0.6), the existing heuristic or haiku path
  runs instead.
- **Four parallel tracks:**
  1. main-thread offload: flux triage, the delegate decision, per-agent
     document slicing;
  2. replacing the haiku classifiers in `/route`, staleness checks and the
     lane gate;
  3. calibrated early exit for reviews and gates;
  4. the B6 learned router.
- **Shadow evidence.** Both answers and the outcome are logged, then scored by
  galiana. Savings are measured with the Pattern F meter and interstat.

**Lineage / prior art.**
- From the B5 local-models cascade it takes the confidence bands and the
  endpoint.
- From B6 it takes the reserved shadow log, but not B6's deferral.
- From the 2026-02-16 synthesis it takes "heuristic first", but refuses
  "LLM when ambiguous" in favour of a calibrated model.
- From Pattern F it takes the diagnosis that the main thread is the cost.

**The refusals.**
- The layer never blocks a sprint. There is always a fallback.
- No enforce without shadow evidence. Tracks 1 and 3 need no increase in
  missed P0/P1 findings.
- We don't replace zero-token heuristics (complexity, model routing) unless
  outcomes improve.
- Jev is not used on decisions whose state may not leave the machine.

**Open.**
1. Whether CLM is good enough zero-shot, or who owns fine-tuning on interspect
   evidence.
2. Per-agent slicing requires coordinated contract changes in interflux.
3. The egress policy: which decisions may send state to hosted Jev.

(Full list: brainstorm § Open Questions.)

**Status.** Discover. Gated on strategy's prior-art verdict against B6,
iv-jdow, iv-4xqu and iv-jgdct. First slice: the layer plus track 2 in shadow
(`/route` 4b), with CLM on interfer.
