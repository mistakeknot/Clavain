---
agent: code-simplicity-reviewer
tier: 3
issues:
  - id: P1-1
    severity: P1
    section: "Agent Roster"
    title: "Tier 1 fd-* agents duplicate Tier 3 agents — same domains, different prompts, both maintained"
  - id: P1-2
    severity: P1
    section: "Commands"
    title: "review, quality-gates, plan-review, and flux-drive are four overlapping review entry points with duplicated agent dispatch logic"
  - id: P1-3
    severity: P1
    section: "Commands"
    title: "codex-first and clodex-toggle are two commands for the same toggle, plus clodex skill repeats the behavioral contract"
  - id: P1-4
    severity: P1
    section: "Skills"
    title: "dispatching-parallel-agents, subagent-driven-development, and clodex overlap substantially on 'how to fan out work'"
  - id: P2-1
    severity: P2
    section: "flux-drive SKILL.md"
    title: "745 lines with two complete dispatch paths (Task vs Codex) maintained in parallel"
  - id: P2-2
    severity: P2
    section: "Commands"
    title: "Three resolve-* commands share identical 4-step workflow structure, differing only in input source"
  - id: P2-3
    severity: P2
    section: "writing-skills SKILL.md"
    title: "520 lines — extensive anti-pattern examples, checklist redundancy with TDD skill, flowchart meta-guidance"
  - id: P2-4
    severity: P2
    section: "Skills"
    title: "Cross-AI peer review is four separate skills (interpeer, prompterpeer, winterpeer, splinterpeer) when it could be one skill with escalation modes"
  - id: P2-5
    severity: P2
    section: "Routing"
    title: "using-clavain routing table is 159 lines injected into every session — significant context window cost"
  - id: P2-6
    severity: P2
    section: "engineering-docs SKILL.md"
    title: "419 lines with 7-step decision-gated workflow and 7-option post-capture menu — over-specified for documentation capture"
  - id: P2-7
    severity: P2
    section: "Agent Roster"
    title: "concurrency-reviewer at 606 lines is the largest agent — more than 4x the median agent size"
  - id: P3-1
    severity: P3
    section: "Skills"
    title: "requesting-code-review and receiving-code-review are two skills for opposite sides of the same interaction"
  - id: P3-2
    severity: P3
    section: "Agents"
    title: "data-migration-expert and data-integrity-reviewer cover heavily overlapping data safety domains"
  - id: P3-3
    severity: P3
    section: "Skills"
    title: "agent-native-architecture (417 lines) serves a narrow niche — most projects will never trigger it"
improvements:
  - id: IMP-1
    title: "Merge Tier 1 fd-* agents and Tier 3 equivalents into a single configurable agent per domain"
    section: "Agent Roster"
  - id: IMP-2
    title: "Unify review, quality-gates, and plan-review into a single /review command with mode flags"
    section: "Commands"
  - id: IMP-3
    title: "Collapse three resolve-* commands into one /resolve command with source detection"
    section: "Commands"
  - id: IMP-4
    title: "Merge the four cross-AI skills into one interpeer skill with escalation tiers"
    section: "Skills"
  - id: IMP-5
    title: "Extract flux-drive Codex dispatch path into a shared dispatch utility instead of inlining it"
    section: "flux-drive SKILL.md"
  - id: IMP-6
    title: "Delete clodex-toggle command — codex-first already exists and clodex-toggle is a documented alias"
    section: "Commands"
  - id: IMP-7
    title: "Trim using-clavain routing table to top 15 most-used commands and a 'run /help for full list' pointer"
    section: "Routing"
  - id: IMP-8
    title: "Merge dispatching-parallel-agents into subagent-driven-development as a section"
    section: "Skills"
verdict: needs-changes
---

## Summary

Clavain is a thoughtfully designed agent rig with genuine value in its lifecycle orchestration, multi-agent review, and cross-AI integration. The `/lfg` pipeline, the flux-drive triage system, and the clodex dispatch pattern are all sound ideas that solve real problems. However, the implementation has accumulated significant redundancy across its 34 skills, 29 agents, and 27 commands. The most persistent pattern is **the same concept expressed at multiple abstraction levels without consolidation**: Tier 1 and Tier 3 agents covering the same domain, four review entry points dispatching overlapping agent sets, three resolve commands with identical workflows, four cross-AI skills that form a linear escalation chain, and two commands for the same toggle.

The total markdown footprint (excluding archives and research artifacts) is approximately 54,000 lines across 223 files. A conservative estimate suggests 20-30% of this content is duplicated reasoning, redundant examples, or over-specification that could be eliminated without losing any capability.

## Section-by-Section Review

### 1. Are Any of the 34 Skills Redundant?

**Yes. Several clusters of skills overlap substantially.**

**Cluster A: Parallel execution (3 skills, should be 1-2)**

- `dispatching-parallel-agents` (200 lines) teaches when/how to fan out work to parallel agents.
- `subagent-driven-development` (244 lines) teaches a serial loop with parallel-safe subagents and two-stage review.
- `clodex` (184 lines) teaches dispatching to Codex CLI agents, either single or parallel.

All three answer the question "how do I split work across agents?" They share the same decision criteria (independence, file overlap, clear scope). `dispatching-parallel-agents` is essentially the "when" section of the other two. It should be inlined into `subagent-driven-development` as a "Parallelization Criteria" section, and the Codex variant should remain in `clodex` with a cross-reference.

**Cluster B: Cross-AI review (4 skills, should be 1)**

- `interpeer` (232 lines) -- fast Claude-to-Codex review
- `prompterpeer` (312 lines) -- Oracle with prompt optimization
- `winterpeer` (422 lines) -- full LLM council
- `splinterpeer` (445 lines) -- post-processor for disagreements

These form a strict escalation chain: interpeer -> prompterpeer -> winterpeer -> splinterpeer. They share the same "comparison" table in three of the four files. Each references the others. A single `cross-ai-review` skill with escalation modes (quick / deep / council / mine-disagreements) would eliminate ~400 lines of duplicated context, comparison tables, and cross-references while preserving all functionality.

**Cluster C: Code review lifecycle (2 skills, could be 1)**

- `requesting-code-review` (106 lines) -- how to ask for review
- `receiving-code-review` (213 lines) -- how to handle feedback

These describe opposite sides of the same interaction. They could be a single `code-review` skill with "Requesting" and "Receiving" sections. The combined skill would be shorter than the current two because shared context (integration with workflows, red flags) would not be repeated.

**Cluster D: Niche skills with narrow trigger conditions**

- `agent-native-architecture` (417 lines) -- designing for agent-first applications
- `distinctive-design` -- anti-AI-slop visual aesthetic
- `beads-workflow` -- git-native issue tracking via `bd` CLI

These are legitimate skills but serve very narrow use cases. They are not redundant per se, but `agent-native-architecture` at 417 lines is over-invested for a skill most sessions will never trigger.

### 2. Is the 3-Layer Routing Over-Engineered?

**Partially. The concept is sound but the implementation is too heavy.**

The 3-layer routing (Stage -> Domain -> Language) is a solid mental model. The problem is the `using-clavain` SKILL.md is 159 lines and gets injected into every single session via the SessionStart hook. That is a substantial context window cost paid on every conversation, whether or not the user needs routing.

The routing table contains 27 commands, 34 skills, and 29 agents organized across 8 tables. Most users will use 5-10 of these regularly. The routing table could be reduced to a "top 10 most common workflows" quick reference (~40 lines) plus a "run `/clavain:help` for full catalog" fallback.

The three layers themselves are not over-engineered -- they map cleanly to how users think (what am I doing? what kind of thing? what language?). The over-engineering is in the verbosity of the table, not the taxonomy.

### 3. Is /lfg's 7-Step Pipeline Too Many Steps?

**No. The pipeline itself is well-designed, but two steps could be consolidated.**

The seven steps are:

1. `/brainstorm` -- explore
2. `/write-plan` -- plan (+ optional Codex execution)
3. `/work` -- execute (skipped in clodex mode)
4. `/flux-drive` -- review plan
5. `/review` -- review code
6. `/resolve-todo-parallel` -- fix issues
7. `/quality-gates` -- final check

Steps 5 and 7 (`/review` and `/quality-gates`) overlap significantly. Both launch reviewer agents against the current code. The difference: `/review` is a full multi-agent review (6+ agents), while `/quality-gates` is a lighter, risk-based selection (up to 5 agents). Running both back-to-back means many of the same agents run twice on the same code.

**Recommendation:** Merge steps 5 and 7 into a single "code review + quality gates" step. The risk-based triage from `/quality-gates` is the better approach; it should subsume `/review`'s exhaustive agent list. The `/review` command can remain as a standalone entry point for users who invoke it directly, but within `/lfg`, running both is redundant.

Step 4 (flux-drive on the plan) is also questionable after Step 5 (code review). If you review the plan *after* implementing it, plan-level feedback becomes less actionable. The natural order would be: brainstorm -> plan -> **review plan** -> execute -> **review code** -> resolve -> ship. This is essentially what `/lfg` does, but the naming makes it confusing -- `flux-drive` sounds like it should be a code review tool, not a plan review step.

### 4. Are There Simpler Alternatives to Clodex Branching?

**Yes. The clodex conditional branching adds complexity throughout the codebase.**

The clodex mode introduces conditional paths in at least 5 files:

- `commands/lfg.md` -- checks autopilot.flag to skip `/work`
- `skills/flux-drive/SKILL.md` -- entire Step 2.3 (140 lines) is clodex-only dispatch
- `skills/writing-plans/SKILL.md` -- auto-selects Codex Delegation when clodex active
- `commands/resolve-todo-parallel.md` -- special clodex handling for code-modifying resolutions
- `commands/codex-first.md` + `commands/clodex-toggle.md` -- two commands for the toggle

The autopilot hook (`hooks/autopilot.sh`) is 63 lines of well-written bash that blocks Edit/Write when a flag file exists. This is the right approach -- the enforcement is clean and centralized.

The problem is the **branching scattered across skills and commands**. Every skill that dispatches work needs to check "am I in clodex mode?" and maintain two code paths. This is the same problem as maintaining separate code paths for two deployment targets -- it doubles the surface area for bugs.

**Simpler alternative:** Instead of branching within each skill, make the dispatch mechanism itself mode-aware. A single `dispatch()` function that checks the flag and routes to either Task tool or Codex CLI would eliminate all the conditional checks in individual skills. `flux-drive` Step 2.3 (140 lines of Codex dispatch) would collapse to "call dispatch() with the same parameters as Step 2.2."

### 5. Do Any Skills Do Too Much?

**Yes. Three skills are significantly over-invested.**

**flux-drive (745 lines)** -- The largest skill. It contains:
- Phase 1: Analyze + Triage (~140 lines) -- appropriate
- Phase 2: Launch via Task (~120 lines) -- appropriate
- Phase 2.3: Launch via Codex (~140 lines) -- duplicates Phase 2 logic for clodex mode
- Phase 3: Synthesize (~130 lines) -- appropriate
- Phase 4: Cross-AI Escalation (~120 lines) -- could be a cross-reference to the interpeer skill stack

Approximately 260 lines (35%) are either duplicated dispatch logic or cross-AI escalation that already exists in dedicated skills. With dispatch unification and a skill cross-reference, flux-drive could be ~480 lines.

**writing-skills (520 lines)** -- This skill teaches TDD applied to documentation. It is well-written but over-specified:
- The TDD mapping table (lines 33-43) repeats concepts from the TDD skill it references
- Anti-pattern examples (lines 429-445) are verbose for their teaching value
- The 26-item checklist (lines 462-498) duplicates the inline guidance above it
- CSO (Claude Search Optimization) section (lines 140-267) is valuable but could be a separate reference file

A focused version at ~300 lines would teach the same concepts with less repetition.

**engineering-docs (419 lines)** -- This skill has a 7-step capture workflow with multiple decision gates, YAML schema validation, a 7-option post-capture menu, and error handling for every edge case. This is over-specified for what is essentially "write a structured markdown file after solving a problem." A simplified version with 3 steps (gather context, write doc, present options) and 3 post-capture options (continue, promote to critical, link related) would serve the same purpose in ~200 lines.

### 6. Are the 4 resolve-* Commands Justified or Redundant?

**Partially redundant. Three should be one.**

The four resolve-related commands are:

| Command | Source | Lines |
|---------|--------|-------|
| `resolve-parallel` | TODO comments in codebase (grep) | 29 |
| `resolve-todo-parallel` | todo files in `todos/*.md` | 36 |
| `resolve-pr-parallel` | PR comments via `gh` | 34 |

All three share an identical 4-step workflow:
1. **Analyze** -- gather items from source
2. **Plan** -- group by dependency, create TodoWrite
3. **Implement** -- spawn pr-comment-resolver per item in parallel
4. **Commit** -- commit changes

The only difference is Step 1 (where items come from: grep, files, or gh). This is a textbook case for a single `/resolve` command that auto-detects the source or takes a `--source` flag. The 4-step workflow would be written once instead of three times.

### 7. Is the 4-Tier Agent System Warranted?

**Yes, but the Tier 1/Tier 3 duplication needs resolution.**

The tier concept is sound:
- **Tier 1** (fd-*): Codebase-aware agents that read CLAUDE.md/AGENTS.md first
- **Tier 2** (.claude/agents/fd-*.md): Per-project custom agents
- **Tier 3** (generic): Domain specialists without project context
- **Tier 4** (Oracle): Cross-AI perspective from GPT-5.2 Pro

The problem is the **domain duplication between Tier 1 and Tier 3**:

| Domain | Tier 1 | Tier 3 |
|--------|--------|--------|
| Architecture | fd-architecture (48 lines) | architecture-strategist (53 lines) |
| Security | fd-security (59 lines) | security-sentinel (91 lines) |
| Performance | fd-performance (58 lines) | performance-oracle (110 lines) |

The Tier 1 agents are leaner and more focused ("read CLAUDE.md first, then review"). The Tier 3 agents are more verbose and generic ("OWASP Top 10 compliance", "Bundle size increases should remain under 5KB per feature"). The flux-drive triage already implements a deduplication rule: "If a Tier 1 agent covers the same domain as a Tier 3 agent, drop the Tier 3 one." This means the Tier 3 architecture/security/performance agents are only used when reviewing a project that lacks CLAUDE.md/AGENTS.md -- a progressively rarer case as Clavain users adopt project documentation.

**Recommendation:** Merge each Tier 1/3 pair into a single agent that conditionally reads project docs. The agent prompt starts with "If CLAUDE.md or AGENTS.md exists in the project root, read them first and ground your analysis in the project's actual patterns. Otherwise, apply general best practices." This eliminates 3 agents and ~250 lines of combined agent definitions.

The concurrency-reviewer at 606 lines deserves special mention. It is more than 4x the median agent size (roughly 100 lines). Much of its content is language-specific concurrency pattern catalogs that could be moved to reference files and loaded on demand by language.

## Issues Found

### P1 (High Impact)

**P1-1: Tier 1/Tier 3 agent domain duplication** (`/root/projects/Clavain/agents/review/`)

Three domain pairs (architecture, security, performance) are maintained as separate agents at two tiers. The deduplication rule in flux-drive already acknowledges only one should run. Maintaining both doubles the surface area and creates drift risk between the generic and codebase-aware versions.

**P1-2: Four overlapping review entry points** (`/root/projects/Clavain/commands/review.md`, `quality-gates.md`, `plan-review.md`, `flux-drive.md`)

`/review` launches 6+ agents against code. `/quality-gates` launches up to 5 agents against code. `/plan-review` launches 3 agents against plans. `/flux-drive` launches up to 8 agents against documents or repos. These share dispatching logic, synthesis logic, and agent selection logic. Within `/lfg`, both `/review` (step 5) and `/quality-gates` (step 7) run against the same code, producing overlapping findings.

**P1-3: Duplicate toggle commands** (`/root/projects/Clavain/commands/codex-first.md`, `clodex-toggle.md`)

`clodex-toggle.md` is explicitly documented as "an alias for `/codex-first`." It is 16 lines that say "follow the codex-first command." This is pure redundancy -- a command alias does not need to be a separate file. The behavioral contract is also repeated between `codex-first.md` (116 lines) and `clodex/SKILL.md` (184 lines).

**P1-4: Three skills for the same concept of parallel work dispatch** (`/root/projects/Clavain/skills/dispatching-parallel-agents/SKILL.md`, `subagent-driven-development/SKILL.md`, `clodex/SKILL.md`)

All three address "how to split work across multiple agents." The decision criteria are the same: independence, file overlap, clear scope. A user encountering a multi-task plan must choose between three skills that teach overlapping patterns with different execution mechanisms.

### P2 (Moderate Impact)

**P2-1: flux-drive dual dispatch paths** (`/root/projects/Clavain/skills/flux-drive/SKILL.md`)

Step 2.2 (Task dispatch, ~120 lines) and Step 2.3 (Codex dispatch, ~140 lines) are maintained in parallel with nearly identical prompt templates, agent selection logic, and error handling. Only the dispatch mechanism differs.

**P2-2: Three resolve commands with identical structure** (`/root/projects/Clavain/commands/resolve-parallel.md`, `resolve-todo-parallel.md`, `resolve-pr-parallel.md`)

All three implement Analyze -> Plan -> Implement(parallel) -> Commit. They differ only in input source (grep, files, gh).

**P2-3: writing-skills over-specification** (`/root/projects/Clavain/skills/writing-skills/SKILL.md`)

520 lines for a meta-skill about writing skills. Contains redundant TDD mapping, verbose anti-patterns, and a 26-item checklist that restates inline guidance.

**P2-4: Four cross-AI skills for a linear escalation chain** (`/root/projects/Clavain/skills/interpeer/SKILL.md`, `prompterpeer/SKILL.md`, `winterpeer/SKILL.md`, `splinterpeer/SKILL.md`)

Total: ~1,411 lines across four skills. Each contains a comparison table listing all four. A single skill with mode-based escalation would eliminate duplicated context.

**P2-5: Session context cost of using-clavain** (`/root/projects/Clavain/skills/using-clavain/SKILL.md`)

159 lines injected into every session. Contains 8 tables, 27 commands, a routing heuristic, priority rules, and plugin conflict warnings. Most sessions need 10-15 of these entries.

**P2-6: engineering-docs over-specification** (`/root/projects/Clavain/skills/engineering-docs/SKILL.md`)

419 lines with a 7-step workflow, YAML schema validation gate, and 7-option post-capture menu. Documentation capture should be lightweight, not a multi-gate pipeline.

**P2-7: concurrency-reviewer bloat** (`/root/projects/Clavain/agents/review/concurrency-reviewer.md`)

606 lines -- by far the largest agent. Contains language-specific concurrency pattern catalogs that could be externalized.

### P3 (Low Impact)

**P3-1: requesting/receiving-code-review split** -- Two skills for one interaction.

**P3-2: data-migration-expert / data-integrity-reviewer overlap** -- Both cover data safety with different lenses. Could be one agent with migration-specific guidance.

**P3-3: agent-native-architecture niche investment** -- 417 lines for a skill most projects never trigger.

## Improvements Suggested

### IMP-1: Merge Tier 1/3 Agent Pairs (HIGH IMPACT)

**Current:** 6 agents across 2 tiers for 3 domains (architecture, security, performance).
**Proposed:** 3 agents that conditionally read project docs when available.
**Impact:** -3 agents, -250 lines, eliminates drift risk. Simplifies flux-drive triage logic (no deduplication rule needed).

### IMP-2: Unify Review Entry Points (HIGH IMPACT)

**Current:** `/review`, `/quality-gates`, `/plan-review`, `/flux-drive` all dispatch agents with overlapping logic.
**Proposed:** `/review` becomes the single code review command (subsumes quality-gates). `/flux-drive` remains for document/repo review. `/plan-review` becomes a mode of `/flux-drive` (it already reviews documents). Within `/lfg`, steps 5 and 7 merge.
**Impact:** -2 commands, -1 `/lfg` step, eliminates duplicate agent runs within `/lfg`.

### IMP-3: Collapse resolve-* Commands (MODERATE IMPACT)

**Current:** 3 commands with identical workflow, different input sources.
**Proposed:** One `/resolve` command that auto-detects source (codebase TODOs, todo files, PR comments) or accepts `--source` flag.
**Impact:** -2 commands, -65 lines, eliminates workflow duplication.

### IMP-4: Merge Cross-AI Skills (MODERATE IMPACT)

**Current:** 4 skills totaling ~1,411 lines.
**Proposed:** One `cross-ai-review` skill with modes: `quick` (current interpeer), `deep` (prompterpeer), `council` (winterpeer), `mine` (splinterpeer).
**Impact:** -3 skills, estimated -400 lines from eliminated duplication (comparison tables, cross-references, overlapping context).

### IMP-5: Unify Dispatch Mechanism (HIGH IMPACT on flux-drive)

**Current:** flux-drive maintains separate Task and Codex dispatch paths (260 combined lines).
**Proposed:** A shared dispatch helper that checks clodex mode and routes to the appropriate mechanism. Called from flux-drive, resolve, and any future skill that dispatches agents.
**Impact:** flux-drive drops from 745 to ~480 lines. All clodex branching across skills reduces to one call site.

### IMP-6: Delete clodex-toggle (TRIVIAL)

**Current:** 16-line file that says "follow codex-first."
**Proposed:** Delete `commands/clodex-toggle.md`. Add `aliases: [clodex-toggle]` to `commands/codex-first.md` if command aliasing is supported, or mention the alternative name in codex-first's description.
**Impact:** -1 command, -16 lines, zero functionality loss.

### IMP-7: Trim using-clavain (MODERATE IMPACT on context window)

**Current:** 159 lines injected every session.
**Proposed:** Top 10 commands quick reference (~40 lines) + "invoke `/clavain:help` for full catalog." Move the full routing tables to a reference file loaded on demand.
**Impact:** -119 lines of per-session context. Frees ~4-5K tokens per session.

### IMP-8: Merge dispatching-parallel-agents into subagent-driven-development (LOW IMPACT)

**Current:** 200-line standalone skill for deciding when to parallelize.
**Proposed:** Inline the decision criteria as a "Parallelization Criteria" section (~30 lines) in subagent-driven-development.
**Impact:** -1 skill, -170 lines after inlining the useful content.

## Overall Assessment

Clavain's core architecture is sound. The lifecycle pipeline (`/lfg`), the tiered review system (flux-drive), and the cross-AI integration (interpeer stack) are genuinely useful and well-thought-out. The problem is not conceptual -- it is accretional. The plugin has grown through merging four upstream sources (superpowers, superpowers-lab, superpowers-dev, compound-engineering), and that merge history shows in the redundancy.

**What is justified:**
- The `/lfg` 7-step pipeline (though steps 5+7 should merge)
- The 4-tier agent system (though Tier 1/3 pairs should merge)
- The 3-layer routing concept (though the table is too verbose)
- The clodex dispatch pattern (though the branching should be centralized)
- Having 29 agents (each has a clear domain, even if some pairs overlap)
- Having 34 skills (each teaches a distinct discipline, even if clusters should merge)

**What is not justified:**
- Maintaining duplicate agents across tiers for the same domain
- Four separate review entry points with overlapping agent selection
- Three resolve commands with identical workflows
- Four cross-AI skills for a linear escalation chain
- Two commands for one toggle
- 745 lines in flux-drive when 260 are duplicated dispatch logic
- 159 lines injected into every session's context window

**Estimated simplification potential:**

| Category | Current | After Simplification | Reduction |
|----------|---------|---------------------|-----------|
| Skills | 34 | 28 (-6) | 18% |
| Agents | 29 | 25 (-4) | 14% |
| Commands | 27 | 23 (-4) | 15% |
| Total SKILL.md lines | 8,351 | ~6,200 | 26% |
| Total agent lines | 3,342 | ~2,900 | 13% |
| Total command lines | 2,532 | ~2,200 | 13% |
| Per-session context (using-clavain) | 159 lines | ~40 lines | 75% |

**Total potential LOC reduction:** ~20-25% across the plugin.

**Complexity score:** Medium-High. The individual components are well-written. The complexity comes from having too many of them covering overlapping ground.

**Recommended action:** Proceed with simplifications, prioritized as:
1. Delete `clodex-toggle` (trivial, zero risk)
2. Merge three `resolve-*` commands into one (low risk, clear benefit)
3. Merge Tier 1/3 agent pairs (moderate effort, high benefit)
4. Unify dispatch mechanism to eliminate clodex branching in flux-drive (moderate effort, high benefit for maintainability)
5. Trim `using-clavain` session injection (moderate effort, direct context window savings)
6. Merge cross-AI skills (higher effort, significant LOC reduction)
7. Consolidate review entry points (highest effort, biggest architectural simplification)
