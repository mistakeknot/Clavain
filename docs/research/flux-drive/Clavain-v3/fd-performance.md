---
agent: fd-performance
tier: 1
issues:
  - id: P0-1
    severity: P0
    section: "Session Start Context Injection"
    title: "using-clavain SKILL.md (8.6KB / ~2,160 tokens) injected into every session via additionalContext, including on resume/compact events"
  - id: P0-2
    severity: P0
    section: "/lfg Pipeline Serial Token Cost"
    title: "7-step /lfg pipeline loads ~74KB of instruction content serially with zero parallelization, accumulating ~18,600 tokens of prompt overhead"
  - id: P1-1
    severity: P1
    section: "Flux-Drive Agent Prompt Token Cost"
    title: "Flux-drive SKILL.md is 32KB (~8,000 tokens) — the largest skill in the plugin — loaded in full even when orchestrator only needs Phase 1+2"
  - id: P1-2
    severity: P1
    section: "Agent Model Hints"
    title: "28 of 29 agents use model: inherit, running Opus-class models for tasks that could use Sonnet or Haiku — only learnings-researcher uses haiku"
  - id: P1-3
    severity: P1
    section: "/review Command Agent Count"
    title: "/review launches 6 core agents + language reviewers + risk reviewers (potentially 12+) with no run_in_background directive in the command itself"
  - id: P1-4
    severity: P1
    section: "Bloated Skill Files"
    title: "8 skills exceed 200 lines; concurrency-reviewer agent is 606 lines (20KB) of code examples that inflate every dispatch"
  - id: P2-1
    severity: P2
    section: "Session Start Hook"
    title: "session-start.sh uses find, curl, pgrep as serial probes during hook execution, adding latency to every session start"
  - id: P2-2
    severity: P2
    section: "Flux-Drive Document Inclusion"
    title: "Token trimming guidance for agent prompts says ~50% but enforcement is purely instructional — no structural mechanism prevents full document injection"
  - id: P2-3
    severity: P2
    section: "/lfg Pipeline"
    title: "Steps 4 (/flux-drive) and 5 (/review) both launch overlapping sets of review agents against the same codebase"
improvements:
  - id: IMP-1
    title: "Tiered model assignment: Sonnet for fd-* agents, Haiku for pattern-recognition and learnings-researcher"
    section: "Agent Model Hints"
  - id: IMP-2
    title: "Split using-clavain into routing-table-only injection (~3KB) and full reference loaded on-demand via Skill tool"
    section: "Session Start Context Injection"
  - id: IMP-3
    title: "Split flux-drive SKILL.md into phase-specific files loaded progressively"
    section: "Flux-Drive Agent Prompt Token Cost"
  - id: IMP-4
    title: "Extract concurrency-reviewer code examples to references/ directory, shrinking prompt by ~14KB"
    section: "Bloated Skill Files"
  - id: IMP-5
    title: "Merge /lfg steps 4+5 into a single review phase to eliminate duplicate agent launches"
    section: "/lfg Pipeline"
  - id: IMP-6
    title: "Add explicit run_in_background: true to /review command agent dispatch instructions"
    section: "/review Command Agent Count"
  - id: IMP-7
    title: "Parallelize /lfg steps 4+5 (plan review) and 6 (resolve issues) where outputs are independent"
    section: "/lfg Pipeline"
  - id: IMP-8
    title: "Cache companion detection results in session-start.sh to avoid re-probing on compact/resume"
    section: "Session Start Hook"
verdict: needs-changes
---

### Summary

Clavain v0.4.6 is a 34-skill, 29-agent Claude Code plugin with significant token overhead at three critical points: (1) the session-start hook injects 8.6KB of routing content into every session as non-evictable `additionalContext`, (2) the `/lfg` pipeline serially loads ~74KB of instruction text across 7 steps with no parallelization opportunities exploited, and (3) the flux-drive orchestrator loads a 32KB monolithic skill file even when only triage and launch phases are needed. Additionally, 28 of 29 agents inherit the parent model (typically Opus-class), wasting high-cost inference on tasks like grep-based research, pattern matching, and checklist validation that Sonnet or Haiku would handle equally well. The `/review` command can launch 12+ agents without explicit background dispatch guidance, and 8 skill files exceed the 200-line threshold with the concurrency-reviewer agent alone contributing 20KB of inline code examples.

### Section-by-Section Review

#### 1. Session Start Context Injection

**Files analyzed:**
- `/root/projects/Clavain/hooks/session-start.sh` (70 lines)
- `/root/projects/Clavain/hooks/hooks.json` (44 lines)
- `/root/projects/Clavain/skills/using-clavain/SKILL.md` (159 lines, 8,639 bytes)
- `/root/projects/Clavain/hooks/lib.sh` (15 lines)

**Current behavior:** The SessionStart hook fires on `startup|resume|clear|compact` events. It reads the entire `using-clavain/SKILL.md` (8,639 bytes, ~2,160 tokens), escapes it for JSON, and injects it as `additionalContext`. This content becomes part of the system prompt and is present in every API call for the session's lifetime. It is not evictable by context compaction.

**Token cost analysis:**
- Raw SKILL.md: 8,639 bytes -> ~2,160 tokens per session
- With JSON escaping overhead: ~2,300 tokens
- With `<EXTREMELY_IMPORTANT>` wrapper and companion detection output: ~2,400 tokens
- Over a 10-turn conversation at 200K context: this represents 1.2% of context permanently occupied
- Over a 50-turn conversation that compacts 3 times: the hook re-fires on each compact event, re-injecting the content

**Specific concerns:**
1. The hook fires on `compact` events. When context window pressure triggers compaction, the system re-injects the full 2.4K tokens immediately, partially counteracting the compaction benefit.
2. The `find` command on line 22 searches for `dispatch.sh` at every session start. The `curl` on line 33 probes the agent-mail server with a 1-second timeout. The `pgrep` on line 38 checks for Xvfb. These serial probes add 1-3 seconds of latency to session start.
3. The content includes extensive markdown tables, code examples, and the full command quick reference (lines 128-159) -- routing information that is only consulted when the user invokes a specific command, not on every turn.

**Content breakdown of using-clavain (8,639 bytes):**
- EXTREMELY-IMPORTANT directive + rule statement: ~800 bytes (essential -- keep)
- 3-layer routing tables (Layers 1-3): ~3,200 bytes (routing -- keep compact version)
- Cross-AI review stack table: ~600 bytes (rarely needed at session start)
- Routing heuristic + skill priority + skill types: ~1,200 bytes (essential -- keep)
- Plugin conflicts: ~400 bytes (rarely needed)
- Key commands quick reference table: ~2,400 bytes (reference only -- load on demand)

**Projection at scale:** If Claude Code adds support for more plugins, each injecting similar-sized context, the non-evictable context budget grows linearly. At 5 plugins each injecting 2.4K tokens, that is 12K tokens of permanent overhead.

#### 2. Flux-Drive Agent Prompt Token Cost

**Files analyzed:**
- `/root/projects/Clavain/skills/flux-drive/SKILL.md` (744 lines, 32,058 bytes)
- `/root/projects/Clavain/agents/review/fd-architecture.md` (47 lines, 2,361 bytes)
- `/root/projects/Clavain/agents/review/fd-performance.md` (58 lines, 2,837 bytes)
- `/root/projects/Clavain/agents/review/fd-security.md` (58 lines, 2,776 bytes)
- `/root/projects/Clavain/agents/review/fd-code-quality.md` (54 lines, 2,850 bytes)
- `/root/projects/Clavain/agents/review/fd-user-experience.md` (51 lines, 2,626 bytes)

**Current behavior:** When `/flux-drive` is invoked, the Skill tool loads the entire 32KB SKILL.md into the conversation context. The orchestrator (main session) processes all 4 phases from this single file. Each launched agent receives its own agent `.md` file (2.3-2.8KB each) plus a prompt template that includes the trimmed document, project context, focus area, and output requirements.

**Token cost per flux-drive invocation:**

| Component | Bytes | ~Tokens | Loaded By |
|-----------|-------|---------|-----------|
| flux-drive SKILL.md (full) | 32,058 | 8,015 | Orchestrator (main session) |
| fd-architecture.md | 2,361 | 590 | Subagent |
| fd-performance.md | 2,837 | 709 | Subagent |
| fd-security.md | 2,776 | 694 | Subagent |
| fd-code-quality.md | 2,850 | 713 | Subagent |
| fd-user-experience.md | 2,626 | 657 | Subagent |
| Prompt template per agent (~1.5KB trimmed doc) | ~1,500 | ~375 each | Subagent |
| **Orchestrator total** | **32,058** | **~8,015** | |
| **Per-agent total (5 Tier 1)** | **~4,300 avg** | **~1,075 avg** | |
| **All agents combined (5)** | **~21,500** | **~5,375** | |
| **Grand total** | **~53,500** | **~13,390** | |

**Structural observation:** The 32KB SKILL.md contains 4 phases plus the agent roster, Codex dispatch instructions (Step 2.3), and cross-AI escalation (Phase 4). When the orchestrator is in Phase 1 (triage), it has already loaded Phase 4 (cross-AI escalation, lines 629-743) which it may never need. When it is synthesizing results in Phase 3, the Phase 2 launch instructions (lines 230-498) are dead weight.

**The Codex dispatch section** (Step 2.3, lines 386-498) accounts for 112 lines (~4,500 bytes, ~1,125 tokens) and is only relevant when `CLODEX_MODE=true`. In the default Task dispatch path, this is pure overhead.

**Agent prompt trimming:** The skill instructs the orchestrator to trim documents to ~50% before including them in agent prompts (lines 306-313). This is a good optimization but is purely instructional -- the orchestrator must interpret and apply it each time. There is no mechanism to verify the trimming actually happened, and the instruction itself consumes prompt space in every agent dispatch.

#### 3. /lfg Pipeline Serial Token Cost

**Files analyzed:**
- `/root/projects/Clavain/commands/lfg.md` (46 lines, 1,648 bytes)
- `/root/projects/Clavain/commands/brainstorm.md` (115 lines, 3,942 bytes)
- `/root/projects/Clavain/commands/work.md` (264 lines, 8,606 bytes)
- `/root/projects/Clavain/commands/review.md` (98 lines, 3,065 bytes)
- `/root/projects/Clavain/commands/quality-gates.md` (94 lines, 3,133 bytes)
- `/root/projects/Clavain/commands/resolve-todo-parallel.md` (36 lines, 1,512 bytes)
- `/root/projects/Clavain/skills/brainstorming/SKILL.md` (53 lines, 2,488 bytes)
- `/root/projects/Clavain/skills/writing-plans/SKILL.md` (190 lines, 6,665 bytes)
- `/root/projects/Clavain/skills/flux-drive/SKILL.md` (744 lines, 32,058 bytes)

**Pipeline flow and cumulative token load:**

| Step | Command/Skill | Bytes Loaded | ~Tokens | Cumulative |
|------|---------------|-------------|---------|------------|
| 0 | using-clavain (session start) | 8,639 | 2,160 | 2,160 |
| 1 | /brainstorm -> brainstorming skill | 3,942 + 2,488 | 1,608 | 3,768 |
| 2 | /write-plan -> writing-plans skill | 6,665 | 1,666 | 5,434 |
| 3 | /work (non-clodex) | 8,606 | 2,152 | 7,586 |
| 4 | /flux-drive -> flux-drive skill | 32,058 | 8,015 | 15,601 |
| 5 | /review | 3,065 | 766 | 16,367 |
| 6 | /resolve-todo-parallel | 1,512 | 378 | 16,745 |
| 7 | /quality-gates | 3,133 | 783 | 17,528 |

**Total prompt instruction overhead across /lfg pipeline: ~74,000 bytes / ~18,500 tokens.**

This does not include the actual document content, agent outputs, user messages, or tool call results that accumulate during the pipeline. By step 4 (flux-drive), the context window already contains the brainstorm output, the plan document, and the /work execution history.

**Serial bottleneck analysis:**

Steps 1 through 3 are necessarily serial -- you cannot plan before brainstorming, and you cannot execute before planning. However:

- **Steps 4 and 5 overlap significantly.** Step 4 (`/flux-drive` on the plan) launches up to 8 review agents examining the plan document. Step 5 (`/review`) launches 6+ review agents examining the code changes. These are reviewing different artifacts (plan vs code diff) and could run concurrently. Instead, the pipeline waits for flux-drive's full 4-phase lifecycle before starting code review.

- **Step 6 depends on steps 4+5** (it resolves issues found by reviewers), so it cannot be parallelized.

- **Step 7 depends on step 6** (quality gates verify the resolved state).

**Realistic parallelization opportunity:** Steps 4 and 5 could be launched concurrently. Step 4 reviews the plan document while step 5 reviews the code diff. Their outputs feed independently into step 6. This would reduce wall-clock time by the duration of the slower of the two (~3-5 minutes for flux-drive with codebase-aware agents).

**Redundancy between steps 4 and 5:** The `/flux-drive` step (step 4) launches agents like `fd-architecture`, `fd-security`, `fd-performance` to review the plan. The `/review` step (step 5) launches `architecture-strategist`, `security-sentinel`, `performance-oracle` to review the code. These are partially overlapping agents examining the same codebase. The Tier 1 agents in flux-drive (`fd-architecture`, etc.) read CLAUDE.md/AGENTS.md -- the same files the Tier 3 agents in `/review` analyze. This creates duplicated codebase analysis.

#### 4. Bloated Skill Files (>200 lines)

**Threshold: 200 lines.** Skills above this threshold inject more prompt context than necessary. The following 8 skills exceed the threshold:

| Skill | Lines | Bytes | ~Tokens | Assessment |
|-------|-------|-------|---------|-----------|
| flux-drive | 744 | 32,058 | 8,015 | Monolithic -- contains 4 phases, 4 agent tiers, Codex dispatch, cross-AI escalation |
| writing-skills | 520 | 18,646 | 4,662 | Meta-skill for authoring other skills -- extensive but specialized |
| splinterpeer | 445 | 14,365 | 3,591 | Cross-AI disagreement processor -- could separate templates |
| winterpeer | 422 | 12,337 | 3,084 | Multi-model consensus -- large Oracle invocation section |
| engineering-docs | 419 | 11,968 | 2,992 | Documentation system -- extensive schema and templates |
| agent-native-architecture | 417 | 22,895 | 5,724 | Architecture review -- includes inline reference material |
| mcp-cli | 375 | 9,237 | 2,309 | MCP CLI usage -- includes protocol examples |
| test-driven-development | 371 | 9,867 | 2,467 | TDD workflow -- includes code examples |

**Agent files exceeding 200 lines:**

| Agent | Lines | Bytes | ~Tokens | Assessment |
|-------|-------|-------|---------|-----------|
| concurrency-reviewer | 606 | 20,313 | 5,078 | Inline code examples in Go, Python, TypeScript, Shell, JS across 11 sections |
| agent-native-reviewer | 246 | 8,571 | 2,143 | SwiftUI/React/Flutter examples inline |
| learnings-researcher | 243 | 11,364 | 2,841 | Extensive search strategy documentation |

The concurrency-reviewer is the most significant offender. Its 606 lines include Go mutex patterns, Python asyncio examples, TypeScript Promise patterns, Shell trap examples, DOM event listener patterns, and more. These code examples are valuable reference material but inflate every dispatch by ~5,000 tokens. When this agent is launched as a subagent, the entire 20KB prompt must be processed before it can begin its actual review work.

#### 5. Agent Dispatch: run_in_background Consistency

**Findings across all commands and skills:**

| Location | Mentions run_in_background | Explicit Directive |
|----------|---------------------------|-------------------|
| flux-drive SKILL.md | 7 mentions | YES -- "Every agent MUST use run_in_background: true" |
| quality-gates.md | 1 mention | YES -- "Launch selected agents using the Task tool with run_in_background: true" |
| review.md | 0 mentions | NO -- says "Launch these core agents in parallel" but never specifies background mode |
| work.md | 0 mentions | NO -- Phase 3 mentions Task tool but no background directive |
| resolve-todo-parallel.md | 0 mentions | NO -- says "Spawn in parallel" but no background directive |
| brainstorm.md | 0 mentions | N/A -- uses single repo-research-analyst task |

**Impact:** The `/review` command launches 6+ agents in Phase 2 without specifying `run_in_background: true`. If the model interprets "in parallel" as foreground Task calls, each agent's full output streams into the conversation context, consuming tokens and potentially hitting context limits before synthesis can begin. The flux-drive skill explicitly calls this out as a problem (line 261: "This prevents agent output from flooding the main conversation context"), but the same discipline is not applied to `/review`.

#### 6. Agent Model Hints

**Current state:** 28 of 29 agents use `model: inherit`. Only `learnings-researcher` uses `model: haiku` with the comment "Grep-based filtering + frontmatter scanning -- no heavy reasoning needed."

**Analysis of agent task complexity vs model requirements:**

| Agent | Current Model | Task Complexity | Recommended Model | Rationale |
|-------|---------------|-----------------|-------------------|-----------|
| fd-architecture | inherit (Opus) | High -- architectural reasoning | inherit | Needs deep reasoning |
| fd-security | inherit (Opus) | High -- threat modeling | inherit | Security needs precision |
| fd-performance | inherit (Opus) | Medium-High -- perf analysis | sonnet | Pattern-based, less creative reasoning |
| fd-code-quality | inherit (Opus) | Medium -- convention checking | sonnet | Checklist-driven |
| fd-user-experience | inherit (Opus) | Medium -- UX evaluation | sonnet | Heuristic-based |
| pattern-recognition-specialist | inherit (Opus) | Medium -- pattern matching | sonnet | Pattern matching is well-suited to smaller models |
| shell-reviewer | inherit (Opus) | Medium -- script review | sonnet | Quoting/portability checks are mechanical |
| code-simplicity-reviewer | inherit (Opus) | Medium -- YAGNI checks | sonnet | Checklist-driven |
| deployment-verification-agent | inherit (Opus) | Low-Medium -- checklist | sonnet | Pre/post-deploy checklists |
| learnings-researcher | haiku | Low -- grep + filter | haiku | Already correct |
| git-history-analyzer | inherit (Opus) | Low -- log parsing | haiku | Git log analysis is mechanical |

**Cost projection:** If a typical flux-drive run launches 5 agents, each processing ~4,300 bytes of input and generating ~2,000 tokens of output:
- At Opus pricing (~$15/M input, ~$75/M output): ~$0.22 per run for 5 agents
- At Sonnet pricing (~$3/M input, ~$15/M output): ~$0.044 per run for 5 agents
- Switching 3 of 5 fd-* agents to Sonnet saves ~60% per flux-drive invocation

For `/review` launching 8+ agents: the savings compound further.

### Issues Found

**P0-1: Session start context injection is oversized and non-evictable**
The using-clavain SKILL.md (8,639 bytes, ~2,160 tokens) is injected via `additionalContext` on every session start, resume, clear, and compact event. This content cannot be evicted by context compaction. The key commands quick reference table alone accounts for ~2,400 bytes of this content and is only consulted when users invoke a specific command. On compact events, the re-injection partially counteracts the memory freed by compaction.

**P0-2: /lfg pipeline accumulates ~18,500 tokens of serial instruction overhead**
The 7-step /lfg pipeline loads ~74KB of instruction content (commands + skills) serially, with each step adding its full instruction set to the context. Steps 4 (flux-drive plan review) and 5 (code review) both launch overlapping sets of review agents against the same codebase, creating redundant codebase analysis. These two steps could be parallelized, and their agent selection could be deduplicated.

**P1-1: Flux-drive SKILL.md is a 32KB monolith**
At 744 lines, flux-drive is the largest skill file, nearly 3x the size of the next largest skill actually invoked during the /lfg pipeline (writing-plans at 190 lines). It contains 4 phases, 4 agent tiers, full Codex dispatch instructions, and cross-AI escalation -- all loaded regardless of which phases are actually executed. The Codex dispatch section (Step 2.3, 112 lines, ~4,500 bytes) is dead weight in the default Task dispatch path.

**P1-2: Missed model tiering across 28 agents**
All agents except learnings-researcher use `model: inherit`, meaning they run at Opus-class cost. Several agents perform checklist-driven, pattern-matching, or mechanical tasks (fd-code-quality, fd-user-experience, pattern-recognition-specialist, shell-reviewer, deployment-verification-agent, git-history-analyzer) that Sonnet or Haiku would handle effectively at 1/5th to 1/20th the cost.

**P1-3: /review command lacks run_in_background directive**
The /review command specifies "Launch these core agents in parallel" but never includes `run_in_background: true`. This risks agent output flooding the main conversation context, which flux-drive explicitly identifies as a problem and guards against.

**P1-4: concurrency-reviewer agent is 606 lines (20KB) of inline code examples**
The concurrency-reviewer contains Go, Python, TypeScript, Shell, and JavaScript code examples across 11 sections. Every dispatch of this agent includes ~5,000 tokens of reference code that could be extracted to a `references/` directory and loaded only when the agent determines it needs a specific pattern.

**P2-1: Session start hook performs serial I/O probes**
The session-start.sh hook runs `find`, `curl` (with 1s timeout), and `pgrep` sequentially to detect companions. On a cold start with agent-mail unavailable, this adds 1-2 seconds of latency. On compact events, these probes re-run unnecessarily since companions do not change mid-session.

**P2-2: Agent prompt trimming is instructional only**
The flux-drive skill instructs the orchestrator to trim documents to ~50% for agent prompts (lines 306-313) but provides no structural mechanism to enforce this. The trimming instruction itself appears in the prompt, consuming tokens to describe how to save tokens.

**P2-3: Steps 4 and 5 of /lfg launch overlapping review agents**
Step 4 (flux-drive) may launch fd-architecture, fd-security, fd-performance against the plan. Step 5 (/review) launches architecture-strategist, security-sentinel, performance-oracle against the code. Both sets of agents read the same CLAUDE.md/AGENTS.md and analyze the same codebase structure, creating duplicated analysis work.

### Improvements Suggested

**IMP-1: Tiered model assignment (High impact, Low effort)**
Assign `model: sonnet` to: fd-code-quality, fd-user-experience, pattern-recognition-specialist, shell-reviewer, code-simplicity-reviewer, deployment-verification-agent. Assign `model: haiku` to: git-history-analyzer. Keep `model: inherit` for: fd-architecture, fd-security, concurrency-reviewer, data-integrity-reviewer, and language-specific reviewers that need deep reasoning. Expected savings: ~50-60% cost reduction on multi-agent reviews.

**IMP-2: Split using-clavain into core + reference (High impact, Medium effort)**
Create two files:
- `using-clavain/SKILL.md` (core, ~3.5KB): Keep the EXTREMELY-IMPORTANT directive, 3-layer routing tables (compact form), routing heuristic, and skill priority. This is the minimum needed for the session-start injection.
- `using-clavain/references/commands.md` (~2.5KB): Move the key commands quick reference table here. Load on demand when a user asks "what commands are available?"
- `using-clavain/references/cross-ai.md` (~600 bytes): Move the cross-AI review stack table here.

This reduces the per-session injection from ~2,400 tokens to ~1,000 tokens -- a 58% reduction in permanent context overhead.

**IMP-3: Split flux-drive into progressive phases (High impact, High effort)**
Break `flux-drive/SKILL.md` into:
- `flux-drive/SKILL.md` (entry point, ~2KB): Phase 1 triage + agent roster reference
- `flux-drive/phases/launch.md` (~4KB): Phase 2 Task dispatch + prompt template
- `flux-drive/phases/launch-codex.md` (~4.5KB): Phase 2 Codex dispatch (loaded only in clodex mode)
- `flux-drive/phases/synthesize.md` (~3KB): Phase 3 synthesis
- `flux-drive/phases/cross-ai.md` (~3KB): Phase 4 cross-AI escalation (loaded only when Oracle participated)

The orchestrator would load each phase file as needed via the Read tool. This reduces the initial context load from 32KB to ~2KB, with subsequent phases adding only what is needed.

**IMP-4: Extract concurrency-reviewer code examples (Medium impact, Low effort)**
Move the inline code examples from sections 1-8 of `concurrency-reviewer.md` to `agents/review/references/concurrency-patterns.md`. The agent's main file would contain the review principles, approach, and output format (~150 lines), with a directive to "Read `references/concurrency-patterns.md` for code examples relevant to the specific language being reviewed." This reduces the per-dispatch cost from ~5,000 tokens to ~1,500 tokens.

**IMP-5: Merge /lfg steps 4+5 into a unified review phase (Medium impact, Medium effort)**
Replace the separate `/flux-drive` (plan review) and `/review` (code review) steps with a single review phase that:
1. Triages agents against both the plan and the code diff
2. Deduplicates overlapping domains (e.g., do not launch both fd-architecture and architecture-strategist)
3. Launches all agents in a single parallel batch
This eliminates the redundant codebase analysis and reduces the number of agent launches by approximately 30%.

**IMP-6: Add explicit run_in_background to /review command (Low impact, Low effort)**
Add `run_in_background: true` to the agent dispatch instructions in `/review` Phase 2, matching the discipline already established in `flux-drive` and `quality-gates`.

**IMP-7: Parallelize /lfg review steps (Medium impact, Low effort)**
If steps 4 and 5 remain separate, launch them concurrently. Step 4 reviews the plan document, step 5 reviews the code diff. Their outputs are independent -- both feed into step 6 (resolve issues). This reduces wall-clock time by 3-5 minutes without changing any agent behavior.

**IMP-8: Cache companion detection in session-start hook (Low impact, Low effort)**
Write companion detection results to a temp file (e.g., `/tmp/clavain-companions-$SESSION_ID`) and reuse on compact/resume events. Only re-probe on `startup` events. This eliminates the serial I/O overhead on context compactions.

### Overall Assessment

Clavain's performance profile is characterized by a "pay-for-everything-upfront" pattern: the session start injects the full routing table, skill invocations load monolithic instruction files, and nearly all agents run at Opus-class pricing. The plugin's design is sound architecturally -- the 3-layer routing, agent tiers, and background dispatch patterns in flux-drive show performance awareness -- but the implementation has not followed through on the principles it establishes. The flux-drive skill explicitly warns about context flooding yet the /review command lacks the same safeguards. The model tiering that learnings-researcher demonstrates (haiku for mechanical tasks) has not been extended to other suitable agents.

The most impactful changes, in priority order:
1. **IMP-1** (model tiering) -- immediate cost savings with near-zero behavioral risk
2. **IMP-2** (split using-clavain) -- reduces permanent per-session overhead by 58%
3. **IMP-5** (merge /lfg review steps) -- eliminates redundant agent launches
4. **IMP-3** (progressive flux-drive loading) -- reduces per-invocation cost by 75% at entry
5. **IMP-4** (extract concurrency-reviewer examples) -- reduces per-dispatch cost by 70%

Together, these changes would reduce the per-session token overhead by approximately 40% and the per-/lfg-run cost by approximately 50%, with no loss of review quality for the use cases where Sonnet-class models are sufficient.
