---
agent: architecture-strategist
tier: 3
issues:
  - id: P1-1
    severity: P1
    section: "Tier 2 Bootstrap Agent Pattern"
    title: "Blocking bootstrap dispatch creates a synchronous dependency inside an otherwise async launch phase"
  - id: P1-2
    severity: P1
    section: "Staleness Detection"
    title: "Git-diff staleness heuristic is unreliable and placed in the wrong architectural layer"
  - id: P1-3
    severity: P1
    section: "Template Section Key Mismatch"
    title: "review-agent.md template uses mixed-case placeholders incompatible with dispatch.sh uppercase-only parser"
  - id: P1-4
    severity: P1
    section: "Error Propagation"
    title: "No defined contract for detecting or recovering from Codex agent failures during review dispatch"
  - id: P2-1
    severity: P2
    section: "Clodex 'When NOT to Use' Contradiction"
    title: "Plan routes code review through clodex, but clodex SKILL.md explicitly excludes code review"
  - id: P2-2
    severity: P2
    section: "Component Coupling"
    title: "Flux-drive directly references clodex template internals and dispatch.sh flags, creating tight cross-skill coupling"
improvements:
  - id: IMP-1
    title: "Introduce a review-dispatch abstraction that flux-drive calls instead of directly invoking dispatch.sh"
    section: "Component Boundaries"
  - id: IMP-2
    title: "Move staleness detection into a standalone script or shared hook, not inline in SKILL.md"
    section: "Staleness Detection"
  - id: IMP-3
    title: "Define an explicit failure contract for Codex review agents with structured exit codes and fallback"
    section: "Error Propagation"
  - id: IMP-4
    title: "Add a --review-mode flag to dispatch.sh rather than creating a separate template resolution path in flux-drive"
    section: "dispatch.sh Interface"
  - id: IMP-5
    title: "Make Tier 2 bootstrap a separate skill or command rather than embedding it in flux-drive's Phase 2"
    section: "Tier 2 Bootstrap"
verdict: needs-changes
---

### Summary

The plan introduces Codex CLI dispatch as an alternative execution backend for flux-drive review agents when clodex mode is active. Architecturally, the concept is sound: flux-drive remains the orchestrator, clodex provides the dispatch mechanism, and dispatch.sh handles execution. However, the plan as written creates several boundary violations: flux-drive reaches into clodex template internals, the staleness detection logic is embedded in the wrong layer, the Tier 2 bootstrap pattern introduces a synchronous blocking step inside an async phase, and there is no error propagation contract for when Codex agents fail. The plan also contradicts clodex's own documented exclusion of code review from its scope.

### Section-by-Section Review

#### Component Boundaries: flux-drive, clodex, dispatch.sh

The plan's three-component separation is conceptually correct. Flux-drive owns orchestration (which agents, what prompts, when to synthesize). Clodex owns Codex dispatch patterns (templates, behavioral contracts). dispatch.sh owns the mechanical execution (argument parsing, template assembly, `codex exec` invocation).

**Where boundaries blur.** In the plan's Step 2.1-codex, flux-drive directly resolves the path to `skills/clodex/templates/review-agent.md`, constructs task description files with section headers matching `dispatch.sh`'s `^[A-Z_]+:$` parser format, and passes flags like `--template`, `--prompt-file`, `--inject-docs` that are dispatch.sh implementation details. This means flux-drive has intimate knowledge of:
1. The clodex template directory structure (`skills/clodex/templates/`)
2. The dispatch.sh section parser's `^[A-Z_]+:$` regex contract
3. The dispatch.sh flag interface (`--template`, `--inject-docs`, `-s workspace-write`)

If any of these change -- a template gets renamed, the parser format evolves, a flag is deprecated -- flux-drive's SKILL.md must be updated in lockstep. This is **inappropriate intimacy** between skills.

**Current state for comparison.** The existing clodex SKILL.md already demonstrates this same pattern (Step 0: Resolve Paths, Step 2: Dispatch), so the plan is consistent with precedent. But the precedent itself has the coupling problem. Adding a second consumer (flux-drive) of dispatch.sh's internal contract amplifies the risk.

#### Clodex "When NOT to Use" Contradiction

Clodex's SKILL.md at line 21 explicitly states: "Code review (use interpeer instead)" under the "When NOT to Use" section. The plan routes review work through clodex's dispatch infrastructure. While the plan's review agents are read-only analysts (not implementation agents), the category conflict is real. This creates architectural ambiguity: is clodex a general-purpose Codex dispatch layer, or is it specifically for implementation work?

The plan should either:
- Amend clodex's scope documentation to acknowledge "read-only analysis dispatch" as a valid use case distinct from interactive code review, or
- Route through a separate dispatch mechanism that does not carry clodex's implementation-oriented assumptions (sandbox defaults, verdict format, retry logic).

The former is cleaner. Clodex is fundamentally a dispatch wrapper, and artificially limiting it to implementation creates unnecessary friction.

#### Tier 2 Bootstrap Agent Pattern

The plan proposes: when no `.claude/agents/fd-*.md` files exist and clodex mode is active, dispatch a **blocking** Codex agent to create them before launching the actual review agents.

**Architectural concerns:**

1. **Synchronous dependency in an async phase.** Phase 2 is "Launch" -- it dispatches all agents in parallel with `run_in_background: true`. The bootstrap step breaks this by requiring a synchronous, blocking `codex exec` call that must complete before any Tier 2 agents can be dispatched. This turns Phase 2 into a two-sub-phase process (2a: bootstrap, 2b: launch) but the plan does not make this phasing explicit.

2. **Codex creating agents that Codex later consumes.** This is a bootstrap paradox: the quality of the review depends on the quality of the generated agent definitions, which are themselves unreviewed. If the bootstrap agent generates poor fd-*.md files (wrong domains, vague instructions, misidentified architecture), every subsequent flux-drive run on that project will produce poor Tier 2 reviews -- and there is no feedback loop to detect this.

3. **Side effects in a review workflow.** Flux-drive is documented as a review/analysis tool. The bootstrap step writes new files to `.claude/agents/`, which is a persistent project mutation. This violates the principle that review workflows should be side-effect-free (they observe and report, they do not change project state). While the agents directory is not source code, it is project configuration that persists across sessions.

4. **Staleness regeneration compounds the problem.** If the staleness check triggers regeneration, the bootstrap agent overwrites existing fd-*.md files. A team member who customized their project agents could have their work silently replaced.

**Recommendation:** The bootstrap pattern should be a separate, explicit skill or command (`clavain:init-review-agents` or similar) that the user invokes intentionally. Flux-drive's SKILL.md would document: "If no Tier 2 agents exist, suggest the user run init-review-agents." This preserves the side-effect-free nature of review workflows and gives the user explicit control over when project agents are generated or regenerated.

#### Staleness Detection

The plan proposes two heuristics for determining whether Tier 2 agents are stale:
1. File modification timestamps compared to the oldest `fd-*.md`
2. Git commit hash comparison (`git diff --stat` between creation commit and HEAD)

**Placement problem.** This detection logic is described inline in flux-drive's SKILL.md, embedded in a code block within a prose section about Tier 2 bootstrap. Staleness detection is a utility concern that should live either in a shared script (e.g., `scripts/check-agent-staleness.sh`) or as a hook, not inline in a skill's instructional text.

**Heuristic reliability.** The git-diff approach (`git diff --stat abc123..HEAD -- CLAUDE.md AGENTS.md docs/ARCHITECTURE.md`) is the better of the two, but it has false positives: any whitespace change, typo fix, or comment update to CLAUDE.md would trigger regeneration. The plan acknowledges this ("If the diff is non-empty, regenerate") but provides no filter for significance. A 200-commit diff between creation and HEAD that only touches README formatting should not trigger a full regeneration.

**The sidecar file pattern (.fd-agents-commit) is sound** but needs a defined owner. Who reads it? Who writes it? Who deletes it? The plan has the bootstrap agent write it, but does not specify what happens when a human creates fd-*.md files manually (no sidecar file exists, so staleness detection falls back to... what?).

#### Template Section Key Mismatch

The proposed `review-agent.md` template uses these placeholders:

    {{PROJECT}}, {{AGENT_IDENTITY}}, {{REVIEW_PROMPT}}, {{OUTPUT_FILE}},
    {{AGENT_NAME}}, {{TIER}}

The dispatch.sh template assembly parser at lines 199-219 matches section headers with the regex `^([A-Z_]+):$`. This means the task description file must use headers like:

    PROJECT:
    AGENT_IDENTITY:
    REVIEW_PROMPT:
    OUTPUT_FILE:
    AGENT_NAME:
    TIER:

The plan's task description example (lines 112-131) uses these exact headers, which is correct. However, the template also contains `{{AGENT_NAME}}` and `{{TIER}}` inside the YAML frontmatter block:

    ---
    agent: {{AGENT_NAME}}
    tier: {{TIER}}
    ---

The dispatch.sh parser uses `perl -0777` for multi-line replacement, which should handle this correctly. But `{{TIER}}` will be replaced with the string "1", "2", or "3" -- and the YAML frontmatter expects an integer. The assembled YAML will contain `tier: 1` (unquoted string that YAML parses as integer), which is fine. This is not a bug, but it is fragile: if anyone adds a tier value like "1a", the YAML would break silently.

More critically, the template contains the literal text `issues: [...]` as a placeholder. The dispatch.sh parser will NOT replace this because `[...]` is not a `{{KEY}}` placeholder -- it is literal template content that the Codex agent is expected to fill in at runtime. This is architecturally correct (the agent generates the issues list), but the mixing of dispatch-time placeholders (`{{AGENT_NAME}}`) and agent-runtime placeholders (`[...]`) in the same file creates confusion about which substitutions happen when.

#### Error Propagation

The plan does not address what happens when a Codex review agent fails. Possible failure modes:

1. **codex exec exits non-zero.** dispatch.sh uses `exec "${CMD[@]}"` (line 359), so the exit code propagates to the Bash call. But flux-drive launches these with `run_in_background: true`, which means the orchestrator must poll for completion and check exit status. The plan says nothing about this.

2. **Agent produces no output file.** The Codex agent might run but fail to write to `{OUTPUT_DIR}/{agent-name}.md` (permissions, wrong path, agent confusion). Flux-drive's existing Phase 3 Step 3.0 handles this ("poll every 30 seconds, after 5 minutes proceed with what you have"), but this was designed for Task-based agents. Codex agents that fail silently (exit 0 but no output) are harder to detect.

3. **Agent writes malformed output.** Existing Step 3.1 handles this via frontmatter validation with prose fallback. This works regardless of whether the agent was Task-based or Codex-based. No change needed here.

4. **Partial dispatch failure.** If 3 of 6 Codex agents fail (e.g., Codex CLI is rate-limited), flux-drive has no retry mechanism for the Codex path. The existing Task path also lacks retries, so this is consistent -- but Codex agents are more likely to fail due to external dependencies (Codex CLI availability, API quotas, sandbox issues).

**Recommendation:** Define an explicit failure contract. At minimum:
- Check exit status of each background Bash call before reading output
- If exit non-zero and no output file exists, log the failure and continue (matching existing "no findings" behavior)
- If 50%+ of agents fail, warn the user and offer to retry with Task dispatch as fallback

### Issues Found

**P1-1: Blocking bootstrap creates synchronous dependency in async phase.**
The Tier 2 bootstrap step requires a blocking `codex exec` before Tier 2 agents can launch. This makes Phase 2 implicitly sequential for first-time runs on any project with clodex mode active. The plan should make this phasing explicit (Step 2.0a: Bootstrap if needed, Step 2.0b: Launch all) and document the expected latency impact (bootstrap adds 60-120 seconds before review agents start).

**P1-2: Staleness heuristic is unreliable and misplaced.**
The `git diff --stat` heuristic triggers on any change to CLAUDE.md/AGENTS.md, including insignificant edits. The detection logic is embedded inline in SKILL.md rather than in a reusable utility. Moving it to a script with a configurable significance threshold (e.g., `--min-lines 10`) would make it testable and reusable.

**P1-3: Template placeholder format assumptions are undocumented.**
The review-agent.md template relies on dispatch.sh's `^([A-Z_]+):$` parser format and `{{KEY}}` replacement, but this contract is not documented in either the template or the plan. A new contributor adding a lowercase or hyphenated key (e.g., `agent-name:`) would break silently. The template should include a comment block documenting the parser contract.

**P1-4: No error propagation contract for Codex dispatch failures.**
The plan does not specify how flux-drive detects or recovers from failed Codex agents. Background Bash calls with `codex exec` can fail silently (exit 0, no output) or loudly (exit non-zero). Phase 3's existing polling logic partially covers this, but the gap between "Task agent that returned no findings" and "Codex agent that crashed" is architecturally significant and should be handled explicitly.

**P2-1: Clodex scope contradiction.**
Routing review work through clodex contradicts clodex's documented "When NOT to Use: Code review" exclusion. The plan should update clodex's scope documentation to distinguish between "code review" (interpeer, interactive) and "review dispatch" (read-only analysis via Codex agents).

**P2-2: Tight cross-skill coupling.**
Flux-drive directly resolves clodex template paths, constructs dispatch.sh-format task files, and passes dispatch.sh flags. This creates a maintenance coupling where changes to dispatch.sh or clodex templates require coordinated updates in flux-drive's SKILL.md.

### Improvements Suggested

**IMP-1: Introduce a review-dispatch abstraction.**
Rather than having flux-drive directly invoke `dispatch.sh --template review-agent.md`, create a thin wrapper (e.g., `scripts/dispatch-review.sh`) that encapsulates the review-specific defaults: template selection, sandbox mode (`workspace-write`), output path conventions, and `--inject-docs`. Flux-drive would call `dispatch-review.sh --agent fd-architecture --output-dir /path --prompt-file /tmp/prompt.md` without knowing about templates or dispatch.sh flags. This preserves the separation: flux-drive knows what to review, the wrapper knows how to dispatch reviews, dispatch.sh knows how to invoke Codex.

**IMP-2: Extract staleness detection into a standalone script.**
Create `scripts/check-agent-staleness.sh` that takes a directory of agent files and a project root, performs the git-diff check with configurable significance filtering, and exits 0 (fresh) or 1 (stale). This is testable, reusable by other skills, and keeps SKILL.md focused on orchestration logic rather than utility code.

**IMP-3: Define an explicit Codex failure contract.**
Add a section to the plan specifying: (a) how flux-drive checks whether each background Codex agent succeeded, (b) what constitutes a retriable vs. permanent failure, (c) whether to fall back to Task dispatch for individual failed agents, and (d) what threshold of failures triggers a user-facing warning. The contract should be documented in the review-agent.md template's constraints section as well, so the Codex agent knows it must produce the output file or exit non-zero.

**IMP-4: Add --review-mode to dispatch.sh.**
Instead of creating a parallel template-resolution path in flux-drive, extend dispatch.sh with a `--review-mode` flag that automatically selects the review template, sets sandbox to `workspace-write`, and adjusts any review-specific defaults. This keeps the dispatch interface stable and avoids flux-drive needing to know template file paths.

**IMP-5: Make Tier 2 bootstrap a separate skill or command.**
Extract the bootstrap logic into a dedicated command (`clavain:init-review-agents` or similar) that the user invokes intentionally. Flux-drive's SKILL.md would document: "If no Tier 2 agents exist, suggest the user run init-review-agents." This preserves the side-effect-free nature of review workflows and gives the user explicit control over when project agents are generated or regenerated.

### Overall Assessment

The plan addresses a real need -- leveraging Codex CLI for parallel review dispatch keeps Claude's context window clean during flux-drive runs. The high-level architecture (flux-drive orchestrates, clodex dispatches, dispatch.sh executes) is correct. However, the implementation as written introduces four P1 issues: a synchronous blocking step in an async phase, an unreliable staleness heuristic in the wrong layer, undocumented template format contracts, and missing error propagation. Addressing these issues before implementation -- particularly extracting the bootstrap into a separate command and adding a failure contract -- would produce a cleaner, more maintainable integration. The plan needs changes but not a fundamental redesign.
