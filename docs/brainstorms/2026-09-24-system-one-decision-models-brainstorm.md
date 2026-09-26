---
artifact_type: brainstorm
bead: none
stage: discover
---

# System One Decision Models for Token Efficiency (Jev / CLM)

**Question:** How can Clavain/intercore cut token spend, especially when paired
with "System One" decision models — TypeSafe's **Jev** (hosted, typed outputs with
calibrated probabilities, 70–500 ms, ~$0.04/MTok input, output unmetered) and
**CLM** (Contrastive-LM, Apache-2.0, dual-encoder state/action ranker on a frozen
Qwen3-8B, 20M-param heads, ~58 ms cold / <1 ms cached, `/v1/systemone` + `/v1/rank`)?

Sources: <https://typesafe.ai/blog/introducing-system-one-models-and-jev>,
<https://github.com/Contrastive-LM/CLM>. Both were read as untrusted. All
benchmark claims are the vendors' own. Jev is early access (waitlist).

## What We're Building

A **shared decision layer** ("the layer"). It takes a typed question plus some
state and returns a calibrated distribution over typed options. Four tracks run
on top of it **in parallel**:

1. **Main-thread offload (largest lever).** Pattern F measured the main thread
   at ~85% of spend, most of it context re-sent every turn
   (`2026-09-03-main-thread-offload-pattern-f.md`). Take in-context decisions
   off the main thread:
   - flux-drive agent triage, which is 3–6K tokens scored in the main thread
     today;
   - the CC→Codex delegate yes/no, where the main model reads injected policy
     text;
   - per-agent document slicing: CLM ranks sections × agent, attacking the
     31–125K-token re-send that `audit-flux-drive-token-flow.md` P0 flags.
2. **Replace LLM-as-classifier calls.** These are haiku subagents today:
   - `/route` 4b fallback (`commands/route.md:139`);
   - bead staleness checks (`route.md:62,80`);
   - the lane-contradiction gate (`sprint.md:329`);
   - verdict-level synthesis triage.

   All already have typed outputs (`{command, confidence}`,
   `{implemented, evidence}`, `{contradicts, reason}`), so a System One call
   drops in.
3. **Calibrated early exit.**
   - Feed a learned score into the B2 `reasoning_depth` slot, which is
     hardcoded today (`REVIEW_DEPTH=2`).
   - Upgrade the `review-calibration` skip/lighten/full decision from P0/P1
     rates to a per-diff probability.
   - Stop remaining review agents once confidence of "no P0/P1" clears a
     threshold.
4. **Learned router (B6 microrouter).** Revive the deferred B6 using CLM
   `rank` over the model and executor candidates for each dispatch. It logs to
   the already-reserved `.clavain/interspect/microrouter-shadow.jsonl`.
   `ic route` / `routing.yaml` remain the fallback.

## Why This Approach

Chosen: **A + C**. Build the layer first, run all four tracks in shadow in
parallel, then promote each track independently with a bar set by its risk.

- Every track asks the same thing: state → typed options → probabilities. One
  interface means one integration, one shadow log and one eval harness
  (`galiana/`). It also means we can compare Jev and CLM on the same traffic.
- It reuses what exists rather than adding new machinery:
  - `routing.yaml` off/shadow/enforce modes;
  - the B5 `local_models` endpoint (interfer, `:8421`) and its confidence
    cascade (≥0.8 accept, <0.6 escalate);
  - the `ic route record` decision log;
  - interstat and budget.go for measuring tokens saved.
- Rejected: **B (independent tracks)**, because it produces duplicated plumbing
  and evidence that can't be compared. Rejected: **A with one common bar**,
  because tracks 1 and 3 change what the main thread sees or skips, which is a
  different risk from changing a haiku verdict.

## Key Decisions

- **Backend:** both. **CLM-8B, self-hosted behind interfer, is the default.**
  Jev sits behind the same interface once early access lands. Per-decision
  backend choice is config, not code.
- **Contract:** typed question in, then `{choice, probs, confidence, backend,
  latency_ms}` out. Every call has a **deterministic fallback**: the current
  heuristic or haiku path. The layer never blocks a sprint.
- **Where the layer lives (ruled 2026-09-24).** The layer is split into
  three jobs:
  - **Serving** stays in interfer, the warm B5 daemon at `:8421`. CLM's
    speed depends on a long-lived embedding cache, so the layer is a client
    and never hosts a model.
  - **Policy** is a new `clavain-cli decide` command, alongside the
    `classify-complexity` and `review-calibration` contracts. It reads
    `decision_models:`, chooses the backend, applies the confidence bands and
    falls back to today's path.
  - **Logging** goes through `ic` when it is installed. Otherwise it appends
    to `.clavain/interspect/microrouter-shadow.jsonl`, the stream reserved for
    B6.

  Once the contract is stable across 2–3 tracks, the policy moves into
  `ic decide` in intercore (the same path `ic route model` took) and
  `clavain-cli decide` calls through to it. Not starting in intercore avoids
  changes across two repos while the contract is still changing.
- **Rollout per track:** off → shadow → enforce, set in `decision_models:` in
  `routing.yaml`. Shadow logs both answers plus the downstream outcome.
- **Promotion bars (the C part):**
  - Tracks 2 and 4 change only a decision value. They promote on agreement
    with today's decisions (target ≥90%) and no regression in the outcome.
  - Tracks 1 and 3 change what gets reviewed or seen. They promote only with
    **no increase in missed P0/P1 findings**, measured by galiana golden sets
    and shadow-review.
- **Confidence semantics:** use the same accept/escalate bands as B5. Below the
  band, call the existing LLM path. Calibration drift is monitored like gate
  calibration.
- **Success metric:** main-thread tokens per sprint (Pattern F meter) and total
  sprint tokens (interstat), not per-call savings. Track 2 alone is expected to
  save only low-thousands of tokens per sprint. Its value is latency and the
  proof that the layer works.
- **Scope honesty:** complexity classification and model routing are already
  heuristic and cost zero tokens. We do not replace them unless shadow shows
  better outcomes.

## Open Questions

1. **Is CLM zero-shot good enough on Clavain states?** If not, the recipe is
   fine-tuning the heads on interspect evidence and verdict history. Who owns
   that data pipeline?
2. **Serving footprint.** CLM needs an 8B backbone for embeddings. Is it
   acceptable on dev machines and cloud sessions, or does it need a shared
   interfer host?
3. **Track 1 slicing is structural.** Per-agent document slicing changes the
   contracts of interflux, a separate repo. It needs a coordinated bead there.
4. **Privacy and egress for Jev.** Hosted calls send state (plans, diffs)
   off-box. We need a policy for which decisions may use a hosted backend.
5. **Relation to open beads.** This may subsume or refine iv-jdow, iv-4xqu,
   iv-jgdct, iv-sym06 and B6 (sylveste-s3z6.19.10). `/clavain:strategy` Phase
   0.5 should rule subsume, supersede or orthogonal. The bead corpus was not
   available in this session.

## Prior Art Consulted

The 2026-02-16 token-efficiency synthesis and trio brainstorms (they chose a
heuristic-first classifier, with an LLM only when ambiguous), the flux-drive
token audit, the research survey §9.4 (cheap screening and early exit, 30–50%
savings), Pattern F, codex-first routing (Layer 4 classifier not shipped), the
static routing table, and B5/B6 in `routing.yaml` / `lib-routing.sh`. No prior
assess doc covers Jev or CLM.

**Review:** `/interflux:flux-drive` was not available in this session, so this
doc has not been reviewed yet. Run it before `/clavain:write-plan`.
