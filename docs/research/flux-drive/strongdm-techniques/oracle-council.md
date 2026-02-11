### Findings Index
- P0 | P0-1 | "Pyramid Mode" | False confidence failure — safety/security agents may miss critical issues when context is hidden
- P0 | P0-2 | "Shift-Work Boundary" | Autonomous batch=ALL without checkpointing, isolated branch, or pre-ship human gate is unsafe
- P1 | P1-1 | "Pyramid Mode" | Only implements one zoom level, not StrongDM's multi-resolution pyramid
- P1 | P1-2 | "Pyramid Mode" | Expansion is freeform prose annotation, not a structured contract/tool call
- P1 | P1-3 | "Pyramid Mode" | 70% token savings math is incorrect — overview repeated per agent not accounted for
- P1 | P1-4 | "Auto-Inject Learnings" | Design is institutional RAG, not Gene Transfusion (missing exemplar→synthesize→validate spine)
- P1 | P1-5 | "Auto-Inject Learnings" | Advisory-only mode too weak for hard constraints (safety/compat requirements need explicit ack)
- P1 | P1-6 | "Shift-Work Boundary" | Cites Attractor but doesn't adopt its key properties: graph execution, observability, resumability, determinism
- P1 | P1-7 | "Cross-Feature" | All three optimize prompting/workflow but StrongDM's core emphasis is validation + feedback loops — none of these strengthen the validation harness
- P1 | P1-8 | "Cross-Feature" | CXDB is directly relevant — branching state from all three features needs an explicit substrate
- P2 | P2-1 | "Pyramid Mode" | Keyword-based domain routing is brittle for cross-cutting sections
- P2 | P2-2 | "Pyramid Mode" | Pyramid scan output should be cached and content-addressed to avoid repeated overhead
- P2 | P2-3 | "Pyramid Mode" | Expansion loop policy is asymmetric — Stage 2 suppression may strand legitimate needs
- P2 | P2-4 | "Auto-Inject Learnings" | Placement after flux-drive conflicts with goal — exemplars shape architecture, not just implementation
- P2 | P2-5 | "Auto-Inject Learnings" | Missing Gene Transfusion "Propagate" step — new fixes don't auto-become future learnings
- P2 | P2-6 | "Auto-Inject Learnings" | Auto-injection needs stricter relevance controls (top-N cap, token budget, suppress affordance)
- P2 | P2-7 | "Shift-Work Boundary" | Filesystem-as-memory substrate only implicitly present — should be explicit and systematic
- IMP | IMP-1 | "Pyramid Mode" | Missing MapReduce "Cluster" step — cluster findings/sections to detect duplicates and focus expansions
- IMP | IMP-2 | "Shift-Work Boundary" | Practical Attractor midpoint: interactive steps 1-4 → non-interactive graph for execute/test/quality-gates → human gate before ship
- IMP | IMP-3 | "Cross-Feature" | Semport is unclaimed opportunity for keeping skills aligned with upstream agent SDKs
- IMP | IMP-4 | "Cross-Feature" | DTU-like record/replay for integrations would make autonomy safe
- IMP | IMP-5 | "Cross-Feature" | Three features should converge into two explicit interfaces: Context Policy + Execution Policy
- IMP | IMP-6 | "Cross-Feature" | If full CXDB too heavy, implement minimal "turn DAG + blob store + typed events" layer
Verdict: risky

### Summary (3-5 lines)

GPT-5.2 Pro reviewed all three design docs against StrongDM's published techniques and found significant gaps between the adaptations and their source material. The Pyramid Mode captures "compress then expand" but misses multi-zoom, collapsible, MapReduce+Cluster framing. Auto-Inject Learnings is useful institutional RAG but not Gene Transfusion (missing exemplar→synthesize→validate→propagate). Shift-Work captures the boundary concept but doesn't reflect "complete intent" (formal spec + validation suite) or Attractor's graph properties. The deepest cross-cutting concern: all three optimize prompting/workflow but none strengthen the validation harness — which is StrongDM's core principle.

### Issues Found

#### P0-1: Pyramid Mode can create false-confidence failure for safety/security review
If fd-safety doesn't see full context and doesn't realize it needs expansion, critical issues can be missed. StrongDM relies on validation harnesses rather than agents reading everything — but Clavain still depends on review quality, so hiding content is riskier. Requires: (a) force full expansion for high-risk sections (auth/crypto/secrets), (b) random spot-check excerpts per summarized section, (c) list key symbols + file paths + line ranges so agents can precisely expand.

#### P0-2: Autonomous batch=ALL is unsafe without strong checkpointing
If the agent runs far with a flawed assumption, you get a huge diff that's hard to unwind. Minimum safety bar: (a) run in isolated git worktree/branch, (b) commit after each task, (c) enforce stop conditions (test fail, lint fail, budget exceeded), (d) require human approval before any irreversible step.

#### P1-1: Only one zoom level, not multi-resolution pyramid
StrongDM's pyramids are explicitly multi-resolution ("2 words, 4, 8, 16…") where each level doubles detail. Clavain's design produces single 2-3 sentence summary + optional full text — "section outline + selective inclusion" not "pyramid zoom levels." Should store L1/L2/L3 summary levels per section.

#### P1-2: Expansion should be structured contract, not freeform prose
StrongDM frames pyramid summaries as collapsible detail where zoom is first-class. Clavain's expansion is a string in findings ("Request expansion: [section]") requiring agent awareness + orchestrator re-launch. Should be a structured tool call / contract event: expand(section_id, granularity).

#### P1-3: Token savings math still incorrect
200 overview + 250 per agent × 6 = 2700 (not 1700), because overview is included in every agent prompt. Need either tailored per-agent overviews, prompt caching, or honest math.

#### P1-4: Auto-Inject is institutional RAG, not Gene Transfusion
Gene Transfusion: exemplar → extract invariants → synthesize equivalent → validate → propagate. Clavain: retrieve → append advice. Missing the exemplar→synthesize→validate spine. Should return "transfusion packets" with exemplar code, invariants, edge cases, and validation hooks.

#### P1-5: Advisory-only too weak for hard constraints
Past learnings like "must do X to avoid data loss" need stronger enforcement. Tag learnings as {advisory, strongly_recommended, constraint}. Require explicit acknowledgement when constraints are violated.

#### P1-6: Cites Attractor but doesn't adopt its properties
Attractor: graph of phases, observable, resumable from checkpoints, deterministic. Clavain: mode toggle inside linear workflow. Should represent /lfg as explicit state machine with persisted checkpoints and "resume from node X."

#### P1-7: None of the three features strengthen the validation harness
StrongDM's core: Seed → Validation harness → Feedback loop. Correctness inferred from externally observable behavior. These adaptations reduce review context (Pyramid) and increase autonomy (Shift Work) without compensating validation upgrades. Each feature should be paired with: stronger test plans, scenario/holdout execution, "what proves this is correct?" artifacts.

#### P1-8: CXDB directly relevant — branching state needs explicit substrate
Pyramid Mode creates overview vs expanded sections plus expansion loops. Learnings creates injected artifacts + provenance. Shift Work creates checkpoints + resume-on-failure. All branching state. Should adopt CXDB or lighter "turn DAG + blob store + typed events."

### Improvements Suggested

1. **Multi-zoom pyramid**: Store L1/L2/L3 summaries per section, let agents request specific granularity levels
2. **MapReduce Cluster step**: Cluster section summaries and early findings to detect duplicates, surface conflicts, focus expansions
3. **Transfusion packets**: Learnings-researcher returns structured exemplar + invariants + validation hooks, not just text advice
4. **Context Policy + Execution Policy**: Converge three features into two explicit plugin interfaces
5. **CXDB-lite**: Append-only run log + content-addressed blobs + branch pointers for retries
6. **Semport**: Keep skills aligned with upstream agent SDKs via semantic porting
7. **Attractor midpoint**: Interactive steps 1-4 → non-interactive graph for execute/test/quality-gates → human gate before ship

### Overall Assessment

The three designs capture the spirit of StrongDM's techniques but adapt them as prompt/workflow optimizations rather than adopting the deeper architectural properties that make them work. The highest-leverage gap is the absence of validation harness upgrades to compensate for reduced context (Pyramid) and increased autonomy (Shift Work). GPT-5.2 Pro verdict is "risky" — not because the ideas are wrong, but because they remove safety margins without adding new ones.

---

### Cross-Validation: Second Oracle Run (tighter prompt)

A second Oracle run with a shorter prompt produced 17 findings that largely converge with the first run. Key additions and escalations:

**Escalation**: Gene Transfusion naming escalated to **P0** (was P1-4 above): "misnamed as Gene Transfusion — your design is mainly advisory retrieval with no equivalence validation." Both runs agree the exemplar→validate spine is missing; second run is firmer that the name is misleading without it.

**New finding — unknown-unknowns (P1)**: "Agents can't request expansion for unknown-unknowns — if the orchestrator summary omits the key detail, the agent may never know to ask." The first run implied this via P1-1 (single zoom level) but the second makes the failure mode explicit: StrongDM's ladder lets agents scan many low-res summaries themselves, reducing hidden information risk.

**New finding — Shift Work gate needs runnable specs (IMP)**: "StrongDM's canonical non-interactive inputs are spec + validation suite or existing working app as executable spec; your gate should require runnable scenarios/tests (not just 'test strategy mentioned')." Strengthens IMP-2 from the first run.

**New finding — CXDB Blob CAS for content dedup (IMP)**: "Blob CAS + dedup is a strong backend for pyramid levels, diff slices, tool outputs, and repeated doc blobs — store once, reference everywhere." More specific than IMP-6 from the first run.

**Convergent findings** (same conclusion, different framing): Pyramid is one zoom level not multi-resolution (P1), expansion loop approximates zooming but isn't bidirectional (P2), MapReduce Cluster missing (IMP), Attractor graph vs boolean toggle (IMP), CXDB turn DAG for debugging convergence (IMP), full CXDB may be heavy — start with primitives (P2).

Verdict: **Both runs agree the designs are directionally correct but architecturally shallow** — they capture the spirit of StrongDM techniques as prompt/workflow optimizations rather than adopting the deeper properties (multi-resolution, behavioral validation, graph execution, content-addressed storage) that make the techniques robust.

<!-- flux-drive:complete -->
