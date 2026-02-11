### Findings Index
- P1 | P1-1 | "Pyramid Mode" | Pyramid scan creates an unversioned orchestrator-only phase with no shared contract
- P1 | P1-2 | "Pyramid Mode" | Expansion request loop introduces a re-launch path with no completion-signal update to synthesize.md
- P1 | P1-3 | "Auto-Inject Learnings" | learnings-researcher runs on the plan file but searches docs/solutions/ — mismatch between plan keywords and solution frontmatter
- P1 | P1-4 | "Shift-Work Boundary" | Autonomous batch mode toggle in executing-plans creates a second dispatch-mode axis orthogonal to clodex mode
- P1 | P1-5 | "Cross-Feature" | All three proposals add steps to lfg.md independently without coordinating step numbering or error-recovery sequencing
- P2 | P2-1 | "Pyramid Mode" | Section-to-agent mapping duplicates diff-routing keyword logic without reusing it
- P2 | P2-2 | "Auto-Inject Learnings" | Gene Transfusion scope expansion (codebase exemplar search, upstream repos) has no design and risks turning learnings-researcher into a god-agent
- P2 | P2-3 | "Shift-Work Boundary" | Spec completeness checklist overlaps with flux-drive Phase 1 document profiling — dual gating without shared criteria
- IMP | IMP-1 | "Pyramid Mode" | Reuse diff-routing.md's domain keyword structure for section-to-agent mapping
- IMP | IMP-2 | "Auto-Inject Learnings" | Wire learnings-researcher into write-plan (Option B) first, deferring lfg insertion until the data path is validated
- IMP | IMP-3 | "Shift-Work Boundary" | Collapse autonomous mode into clodex toggle rather than adding a new flag
- IMP | IMP-4 | "Cross-Feature" | Define a single lfg.md extension protocol — named insertion points rather than numbered step splicing
Verdict: needs-changes

### Summary (3-5 lines)

Three design documents propose extensions to the flux-drive and lfg orchestration pipeline, each inspired by a distinct StrongDM Software Factory technique. Individually, each proposal is modest and well-motivated. The primary architectural risk is not any single proposal but the compound effect: all three splice new steps into `lfg.md` and touch `executing-plans/SKILL.md` or `shared-contracts.md` without a shared insertion protocol, creating step-numbering fragility and an expanding orchestrator surface. The Pyramid Mode proposal introduces the most structural novelty (a new phase between Analysis and Launch) but under-specifies its contract integration. The Shift-Work proposal's autonomous mode toggle creates a second modal axis that intersects with the existing clodex toggle in ways that need resolution.

### Issues Found

#### P1-1: Pyramid scan creates an unversioned orchestrator-only phase with no shared contract
**Severity: P1** | **Section: Pyramid Mode** | **File: `skills/flux-drive/SKILL.md`, `phases/shared-contracts.md`**

The proposal adds "Phase 1.5: Pyramid Scan" as a new step between Analysis (Phase 1) and Launch (Phase 2). Currently, flux-drive has a clean phase progression: Phase 1 (Analyze + Triage) produces a Document Profile and agent selection; Phase 2 (Launch) uses those outputs via the prompt template in `phases/launch.md` Step 2.2; Phase 3 (Synthesize) consumes agent output files via the Findings Index contract in `phases/shared-contracts.md`.

The Pyramid Scan sits between Phase 1 and Phase 2 but has no corresponding contract in `shared-contracts.md`. Its output — "overview + domain-relevant sections + thin sections + expansion request instruction" — is a new data shape consumed by `launch.md`'s prompt template. Without a formalized contract:

1. The orchestrator's prompt template in `launch.md` would need conditional logic: "if pyramid mode active, use pyramid content; else use full document." This branches the prompt assembly path.
2. The per-agent content assembly (overview + domain-relevant sections) is orchestrator logic that lives nowhere in the current phase-file structure. It would need to be either in `SKILL.md` (bloating Phase 1) or in a new `phases/pyramid.md` file (adding a sixth phase file).
3. The expansion request annotation is mentioned as an addition to `shared-contracts.md` but the contract is not specified — what does an expansion request look like in the Findings Index? How does synthesis count it?

**Recommendation:** Define a `Pyramid Content Contract` section in `shared-contracts.md` specifying: (a) the shape of per-agent pyramid content, (b) how expansion requests are annotated in agent output, (c) how synthesis adjusts convergence when agents reviewed different content subsets. The existing Diff Slicing Contract in `shared-contracts.md` (lines 57-88) is the exact template to follow — it already handles the problem of agents seeing different content and adjusts synthesis accordingly.

#### P1-2: Expansion request loop introduces a re-launch path with no completion-signal update
**Severity: P1** | **Section: Pyramid Mode** | **File: `phases/launch.md`, `phases/synthesize.md`**

The design specifies "Max 1 expansion per agent per run. Stage 1 expansion batched with Stage 2. Stage 2 expansion noted but NOT re-launched." This creates a re-launch scenario: an agent in Stage 1 completes, requests expansion, and is re-launched with expanded content alongside Stage 2 agents.

The current monitoring contract in `shared-contracts.md` (lines 90-97) and `launch.md` Step 2.3 expects exactly one `.md` file per launched agent. A re-launched agent would produce a second output. The completion signal (`.md.partial` renamed to `.md`) does not account for a re-run of the same agent. Specifically:

- Step 2.3 checks for `.md` files and considers an agent "done" when `{agent-name}.md` exists. A re-launched agent would need its first output removed or renamed before re-launch.
- The retry logic in Step 2.3 (item 2c) has a "Pre-retry guard" that skips agents with existing `.md` files — this would conflict with intentional re-launch for expansion.
- `synthesize.md` Step 3.3 deduplication assumes one output per agent. Two outputs from the same agent (pre-expansion and post-expansion) would need merging or replacement logic.

**Recommendation:** If expansion re-launch is kept, the simplest path is: delete the first output before re-launching (the expanded content subsumes it). Update `shared-contracts.md` to distinguish "retry on failure" from "re-launch for expansion" — the pre-retry guard must not block expansion re-launches.

#### P1-3: learnings-researcher searches docs/solutions/ but receives a plan file — keyword extraction mismatch
**Severity: P1** | **Section: Auto-Inject Learnings** | **File: `agents/research/learnings-researcher.md`, `commands/lfg.md`**

The proposal says: "Launch learnings-researcher with plan file + keywords." But the learnings-researcher agent (at `/root/projects/Clavain/agents/research/learnings-researcher.md`) is designed to search `docs/solutions/` directories using YAML frontmatter fields (`module`, `problem_type`, `component`, `symptoms`, `root_cause`, `tags`). Its grep-first filtering strategy works on frontmatter like `tags:.*(payment|billing|stripe)`.

A plan file written by `writing-plans/SKILL.md` is structured as numbered Tasks with Files/Steps — it does not contain frontmatter, `module` fields, or `tags`. The learnings-researcher's keyword extraction (Step 1) expects "Module names", "Technical terms", "Problem indicators", "Component types" — these are reasonable to extract from a plan, but the matching target (`docs/solutions/` with YAML frontmatter) may not exist in many projects. The Clavain project itself has a `docs/solutions/` directory with only 4 subdirectories (`best-practices`, `integration-issues`, `test-failures`, `workflow-issues`).

More critically, the proposal says learnings should be "Append to plan file" — modifying the plan file that was just reviewed by flux-drive in Step 4. This creates a temporal dependency: the plan reviewed in Step 4 is not the plan executed in Step 5, because Step 4.5 mutated it.

**Recommendation:** (1) Do not append to the plan file. Instead, output learnings as a separate advisory file (e.g., `docs/plans/YYYY-MM-DD-<name>-learnings.md`) and reference it in the execution context. (2) Consider wiring into `write-plan` (Option B) first, where the learnings inform plan creation rather than post-hoc annotation. This avoids the plan-mutation problem entirely. (3) Document the assumption that `docs/solutions/` exists and is populated — the feature degrades to a no-op without it, which is fine, but should be explicit.

#### P1-4: Autonomous batch mode toggle creates a second dispatch-mode axis orthogonal to clodex mode
**Severity: P1** | **Section: Shift-Work Boundary** | **File: `skills/executing-plans/SKILL.md`**

The proposal says: "Changes to executing-plans: Add autonomous batch mode toggle." Currently, `executing-plans/SKILL.md` already has a modal dispatch axis at Step 2: it checks for `.claude/clodex-toggle.flag` and branches into either "Step 2A: Codex Dispatch" or "Step 2B: Direct Execution." The clodex toggle controls parallel vs serial dispatch.

The Shift-Work proposal adds a second axis: interactive (per-batch approval) vs autonomous (batch size = ALL, no per-batch approval). This creates a 2x2 matrix:

| | Interactive | Autonomous |
|---|---|---|
| **Direct (Claude)** | Current default | New: all tasks, no checkpoints |
| **Clodex (Codex)** | Current clodex | New: all tasks via Codex, no checkpoints |

The "autonomous + clodex" quadrant is particularly concerning because it means dispatching ALL plan tasks to parallel Codex agents with no human checkpoint between batches. The existing clodex mode already has a max-5-agents-per-batch guard (Step 2A, item 2). Autonomous mode would override this.

The proposal partially addresses this: "still stops on blockers." But the mechanism for blocker detection in autonomous mode is unspecified. In interactive mode, the user sees batch results and can intervene. In autonomous mode, who detects the blocker? The orchestrator? Based on what signal?

**Recommendation:** Collapse the autonomous toggle into the clodex toggle rather than adding a new flag. The insight from StrongDM's Shift Work is about spec completeness enabling non-interactive execution — this is already what clodex mode provides. Instead of a new toggle, add the spec-completeness checklist as a gate before clodex activation. The `lfg.md` Step 4a proposal is sound; it just should gate clodex rather than introducing a new mode.

#### P1-5: All three proposals add steps to lfg.md independently without coordinating step numbering
**Severity: P1** | **Section: Cross-Feature** | **File: `commands/lfg.md`**

The current `lfg.md` has 9 steps: brainstorm (1), strategize (2), write-plan (3), flux-drive (4), execute (5), test (6), quality-gates (7), resolve (8), ship (9). The error recovery section references step numbers explicitly.

The three proposals each splice into this sequence:
- Pyramid Mode: No direct lfg.md change, but changes flux-drive behavior called in Step 4.
- Auto-Inject Learnings: Adds Step 4.5 between flux-drive (4) and execute (5).
- Shift-Work Boundary: Adds Step 4a between flux-drive (4) and execute (5).

Both Step 4.5 and Step 4a occupy the same slot. The proposals do not acknowledge each other. If both are implemented:

- Is the order: flux-drive (4) -> learnings check (4.5) -> shift boundary (4a) -> execute (5)? Or the reverse?
- The error recovery section says "resume from a specific step" — fractional step numbers break this.
- The "Note" on Step 3 says clodex mode auto-executes during write-plan, skipping Step 5. How does this interact with Step 4.5 (learnings) and Step 4a (shift boundary)?

**Recommendation:** Define named insertion points in `lfg.md` rather than numbered steps. For example: `## Post-Review Gate` (after flux-drive, before execute) with sub-steps that can be composed. This is a one-time structural change that prevents future step-numbering conflicts as more techniques are added.

### P2-1: Section-to-agent mapping duplicates diff-routing keyword logic
**Severity: P2** | **Section: Pyramid Mode** | **File: `config/flux-drive/diff-routing.md`**

The Pyramid Mode design says "Map sections to agent domains using diff-routing keywords." This is the right instinct — diff-routing already has per-agent domain keywords and file patterns. But the proposal does not specify how this reuse works. Section-to-agent mapping operates on prose section headings and content, not file paths and diff hunks. The existing diff-routing keywords (`password`, `secret`, `token` for fd-safety) would need adaptation to work on document sections rather than code hunks.

Without explicit reuse, implementers will likely create a parallel keyword-to-agent mapping, duplicating the domain model.

#### P2-2: Gene Transfusion scope expansion risks a god-agent
**Severity: P2** | **Section: Auto-Inject Learnings**

The proposal mentions future expansion: "Could extend to: config/flux-drive/knowledge/, project's own codebase (exemplar search), upstream repos." The learnings-researcher is already a focused agent with a clear data contract (grep YAML frontmatter in `docs/solutions/`). Expanding it to search flux-drive knowledge entries, arbitrary codebase files, and upstream repos would make it responsible for three different data formats and search strategies.

The flux-drive knowledge layer already has its own retrieval mechanism — `launch.md` Step 2.1 uses qmd semantic search against `config/flux-drive/knowledge/`. Adding learnings-researcher as a second retrieval path for the same data creates ownership ambiguity: who is responsible for knowledge retrieval, the orchestrator or the learnings agent?

#### P2-3: Spec completeness checklist overlaps with flux-drive document profiling
**Severity: P2** | **Section: Shift-Work Boundary**

The Shift-Work proposal defines a "Spec Completeness Signal" checklist: plan approved, acceptance criteria defined, test strategy specified, dependencies identified, scope bounded. Flux-drive Phase 1 (Step 1.1) already extracts a document profile with `Section analysis` (thin/adequate/deep) and `Estimated complexity`. These two assessments overlap — both evaluate whether the plan is sufficiently specified.

If flux-drive runs on the plan (lfg Step 4) and finds all sections adequate/deep, that is already a signal of spec completeness. The Shift-Work checklist would be a second, independent evaluation of the same property.

### Improvements Suggested

#### IMP-1: Reuse diff-routing.md's domain keyword structure for section-to-agent mapping

The Pyramid Mode proposal needs to map document sections to agent domains. Rather than inventing a new mapping, extend `config/flux-drive/diff-routing.md` with a `Section Keywords` subsection per agent (parallel to the existing `Priority hunk keywords`). This keeps the domain model in one authoritative location. The orchestrator would match section content against section keywords the same way it matches hunk content against hunk keywords.

This also makes the pyramid mode's domain mapping testable: a structural test can verify that every agent in the roster has both hunk keywords and section keywords defined.

#### IMP-2: Wire learnings-researcher into write-plan first, deferring lfg insertion

Option B (inject during plan drafting) is architecturally cleaner than Option A (inject between review and execute) because:
1. It avoids mutating a reviewed plan.
2. Plan-time injection lets the planner incorporate learnings into task design, not just append them as afterthoughts.
3. `write-plan` already has an execution handoff section that analyzes the plan — adding a learnings step before that analysis is a natural fit.
4. It validates the data path (keywords from spec -> grep -> frontmatter match -> useful results) before committing to an lfg integration.

Defer lfg integration (Option A) until after Option B proves the value. If the learnings step consistently returns empty results or irrelevant matches, the lfg insertion adds latency for no benefit.

#### IMP-3: Collapse autonomous mode into clodex toggle rather than adding a new flag

The Shift-Work insight — "when intent is complete, agents run end-to-end" — maps directly onto the existing clodex toggle. Instead of a new autonomous flag in `executing-plans`, add the spec-completeness gate as a precondition for clodex activation in `lfg.md`. The flow becomes:

1. Flux-drive reviews the plan (existing Step 4).
2. Check spec completeness (new Step 4a from the proposal).
3. If complete AND codex available: activate clodex mode (set the flag file).
4. Execute via clodex (existing Step 5 with clodex path).

This avoids the 2x2 mode matrix and reuses existing infrastructure. The "autonomous" behavior is an emergent property of clodex + complete spec, not a separate toggle.

#### IMP-4: Define a single lfg.md extension protocol with named insertion points

Replace numbered step splicing with named phases in `lfg.md`:

```
## Phase: Explore (Steps 1-2)
## Phase: Plan (Step 3)
## Phase: Review (Step 4)
## Phase: Post-Review Gate (new — insertion point for learnings, shift-work, future techniques)
## Phase: Execute (Step 5)
## Phase: Verify (Steps 6-7)
## Phase: Ship (Steps 8-9)
```

Each phase is a named boundary. New techniques insert into the appropriate phase without renumbering. Error recovery references phase names instead of step numbers. This is a small structural change to `lfg.md` that pays for itself as more StrongDM-inspired techniques are added.

### Overall Assessment

The three proposals are individually well-scoped and correctly motivated by StrongDM's patterns. The primary risk is compositional: they converge on the same orchestration files (`lfg.md`, `shared-contracts.md`, `executing-plans/SKILL.md`) without a shared integration protocol. Addressing P1-5 (named insertion points) first would make all three proposals safer to implement independently. The Pyramid Mode proposal (Document 1) needs the most contract work before implementation; the Learnings injection (Document 2) should start with Option B; the Shift-Work boundary (Document 3) should collapse into the existing clodex toggle rather than adding a new mode.

<!-- flux-drive:complete -->
