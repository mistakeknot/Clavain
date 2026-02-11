## Flux Drive Enhancement Summary

Reviewed by 3 agents + Oracle (GPT-5.2 Pro) on 2026-02-11.

### Key Findings

1. **Two parallel content-assembly systems** — Pyramid mode and diff slicing solve the same problem (domain-specific content routing) with different mechanisms. Both need maintenance. Unify under a single abstraction. (3/3 agents)
2. **Autonomous mode needs guardrails** — Removing per-batch checkpoints without a pause mechanism, rollback path, or context ceiling is unsafe. Batch=ALL risks context exhaustion at 20+ tasks. (3/3 agents)
3. **Spec completeness grep is fragile** — Keyword search for "test", "acceptance", "done when" will false-positive on plans that mention criteria without satisfying them. (2/3 agents)
4. **lfg.md step-splicing conflict** — All three proposals insert between Steps 4 and 5 without acknowledging each other or coordinating numbering. (1/3 agents, but structural)
5. **Plan file mutation after review** — Appending learnings to a plan that flux-drive already reviewed creates a reviewed≠executed artifact mismatch. (2/3 agents)

### Issues to Address

- [ ] P1-1: Define Pyramid Content Contract in shared-contracts.md (fd-architecture)
- [ ] P1-2: Resolve expansion re-launch contradiction — piggyback vs separate invocation (fd-architecture, fd-performance, 2/3)
- [ ] P1-3: Add user progress signal for expansion requests (fd-user-product)
- [ ] P1-4: Address keyword extraction mismatch between plan files and docs/solutions/ frontmatter (fd-architecture)
- [ ] P1-5: Add pause escape hatch + mandatory incremental commits for autonomous mode (fd-user-product, fd-architecture, 2/3)
- [ ] P1-6: Replace keyword-grep with section-header matching or human-confirmed checklist (fd-user-product, fd-performance, 2/3)
- [ ] P1-7: Collapse autonomous toggle into clodex toggle to avoid 2x2 mode matrix (fd-architecture)
- [ ] P1-8: Add task-count ceiling (batch=min(ALL,10)) for context safety (fd-performance)
- [ ] P1-9: Define named insertion points in lfg.md instead of numbered step splicing (fd-architecture)
- [ ] P1-10: Add opt-out/override mechanisms for all three features (fd-user-product)
- [ ] P1-11: Account for orchestrator summarization cost in token budget (fd-performance)
- [ ] P1-12: Unify content-assembly systems before shipping pyramid mode (fd-performance, fd-architecture, 2/3)

### Improvements Suggested

1. **Unify content assembly** — Create a single `ContentSlice` abstraction for both diff slicing and pyramid mode (fd-performance, fd-architecture)
2. **Wire learnings into write-plan first** — Option B is architecturally cleaner; defer lfg insertion until the data path is validated (fd-architecture)
3. **Collapse autonomous into clodex** — Spec completeness gate should trigger clodex mode, not a new flag (fd-architecture)
4. **Named lfg phases** — Replace numbered steps with named phases: Explore, Plan, Review, Post-Review Gate, Execute, Verify, Ship (fd-architecture)
5. **Pause escape hatch** — Check for `.claude/pause-execution` sentinel between task groups (fd-user-product)
6. **Surface pyramid at confirmation** — Tell users about pyramid mode at Step 1.3 with override option (fd-user-product)
7. **Gate learnings on corpus size** — Skip when docs/solutions/ has <5 files (fd-user-product, fd-performance)
8. **Feature flags** — Ship each feature behind a flag for incremental rollout (fd-user-product)
9. **Batch ceiling** — batch=min(ALL, 10) with brief status reports between mega-batches (fd-performance)
10. **Instrument baseline** — Measure actual token usage per agent before implementing pyramid mode (fd-performance)

### Individual Agent Reports

- [fd-architecture](./fd-architecture.md) — needs-changes: 5 P1s, 3 P2s, strong cross-feature integration concerns
- [fd-user-product](./fd-user-product.md) — needs-changes: 4 P1s, 4 P2s, autonomous mode trust gap is primary concern
- [fd-performance](./fd-performance.md) — needs-changes: 4 P1s, 4 P2s, 70% savings claim overstated, context window risk
- [oracle-council](./oracle-council.md) — **risky**: 2 P0s, 8 P1s, 7 P2s, 6 IMPs. Deeper technique fidelity analysis. Key gap: designs remove safety margins without adding validation harness upgrades. Cross-validated by second Oracle run (17 findings, largely convergent; escalated Gene Transfusion naming to P0, added unknown-unknowns risk for Pyramid Mode).

### Cross-AI Comparison (Oracle vs Claude Agents)

**Where Oracle agreed with Claude agents:**
- Autonomous batch=ALL is unsafe (Oracle escalated to P0)
- Token savings math is wrong (all 4 agents)
- Expansion mechanism is fragile (all 4 agents)
- Spec completeness grep is brittle (3/4 agents)

**Where Oracle went deeper than Claude agents:**
- **P0: False confidence in safety review** — Claude agents didn't flag that hiding context from fd-safety could miss critical security issues. Oracle flagged this as P0 and proposed high-risk classifiers forcing full expansion for auth/crypto/secrets sections.
- **P1: Technique fidelity gap** — Claude agents evaluated the designs on their own merits. Oracle evaluated them *against StrongDM's actual technique definitions* and found significant mismatches:
  - Pyramid Mode is "one zoom level" not multi-resolution (StrongDM: 2→4→8→16 word summaries)
  - Auto-Inject is "institutional RAG" not Gene Transfusion (missing exemplar→synthesize→validate→propagate)
  - Shift Work is "mode toggle" not Attractor (missing graph execution, checkpoints, resume, determinism)
- **P1: Validation harness gap** — The deepest insight: all three features optimize prompting/workflow but none strengthen the validation harness. StrongDM's core principle is Seed→Validation→Feedback, and these designs reduce safety margins (less context, more autonomy) without compensating validation upgrades.
- **CXDB relevance** — Oracle connected all three features to CXDB's branching state management: pyramid creates overview/expanded branches, learnings creates provenance chains, shift-work creates checkpoint/resume points. All need an explicit substrate.

**Where Oracle uniquely contributed:**
- Transfusion packets: learnings-researcher should return structured exemplar + invariants + validation hooks, not just text advice
- Context Policy + Execution Policy: converge three features into two explicit plugin interfaces
- CXDB-lite: append-only run log + content-addressed blobs + branch pointers as stepping stone
- Semport: unclaimed opportunity for keeping skills aligned with upstream agent SDKs
- MapReduce Cluster step: cluster findings to detect duplicates and focus expansions

### Implementation Priority (All 4 Agents)

Claude agents recommended shipping order:
1. **Auto-inject learnings** — lowest risk, ship first (via write-plan, not lfg)
2. **Pyramid mode** — unify with diff slicing before shipping
3. **Shift-work boundary** — needs the most design iteration

Oracle's addendum: **before any of the three**, strengthen the validation harness. Each feature should be paired with a validation upgrade (stronger test plans, scenario/holdout execution, "what proves this is correct?" artifacts).

### Findings (findings.json)

Full machine-readable findings at `./findings.json`.
