---
agent: spec-flow-analyzer
tier: workflow
issues:
  - id: P0-1
    severity: P0
    section: "Knowledge Conflict Resolution"
    title: "No defined precedence when project-local and Clavain-global knowledge contradict"
  - id: P0-2
    severity: P0
    section: "Compounding on False Positives"
    title: "No correction or retraction mechanism for compounded knowledge entries"
  - id: P0-3
    severity: P0
    section: "Ad-hoc Agent Lifecycle"
    title: "No deletion, deprecation, or quality-gate mechanism for ad-hoc agents"
  - id: P0-4
    severity: P0
    section: "Deep-Pass Correction Authority"
    title: "Deep-pass discovers stale or wrong entry but spec does not define whether it auto-corrects or flags for human"
  - id: P1-1
    severity: P1
    section: "First Run on New Project"
    title: "Spec does not describe what a first-run looks like — zero knowledge, zero ad-hoc agents, qmd empty"
  - id: P1-2
    severity: P1
    section: "Ad-hoc Agent Graduation"
    title: "Cross-project name collision for ad-hoc agents covering the same domain with conflicting prompts"
  - id: P1-3
    severity: P1
    section: "Oracle Unavailable"
    title: "Cross-AI delta is marked as origin type for knowledge entries but spec does not address entries originated from Oracle when Oracle is later permanently unavailable"
  - id: P1-4
    severity: P1
    section: "Phase 5 Compound"
    title: "Compounding agent has no explicit token budget, context cap, or circuit breaker"
  - id: P1-5
    severity: P1
    section: "Knowledge Layer"
    title: "Archival decay threshold N is undefined — no default, no override, no per-project tuning"
  - id: P1-6
    severity: P1
    section: "Ad-hoc Agent Lifecycle"
    title: "No versioning or update mechanism when triage generates a newer version of an existing ad-hoc agent"
  - id: P1-7
    severity: P1
    section: "Knowledge Retrieval"
    title: "Fallback behavior when qmd returns zero results is not specified"
  - id: P1-8
    severity: P1
    section: "Triage Changes"
    title: "Ad-hoc agent scoring criteria are undefined — how does triage score a saved ad-hoc agent vs core agent?"
  - id: P2-1
    severity: P2
    section: "Compounding System"
    title: "No concurrency guard when two flux-drive runs compound simultaneously on the same project"
  - id: P2-2
    severity: P2
    section: "Knowledge Format"
    title: "No schema validation for knowledge entries — malformed frontmatter silently enters the layer"
  - id: P2-3
    severity: P2
    section: "Phase Structure"
    title: "Phase 5 ordering relative to Phase 4 is ambiguous — does compounding wait for cross-AI delta?"
  - id: P2-4
    severity: P2
    section: "Agent Roster"
    title: "Merged agents lose specificity signals — triage cannot distinguish sub-domains within a merged agent"
  - id: P2-5
    severity: P2
    section: "Knowledge Layer"
    title: "No size cap or growth bound on knowledge directories"
improvements:
  - id: IMP-1
    title: "Define explicit first-run bootstrap sequence with graceful degradation to v1 behavior"
    section: "First Run on New Project"
  - id: IMP-2
    title: "Add a retraction mechanism to the compounding system for correcting false positives"
    section: "Compounding System"
  - id: IMP-3
    title: "Specify precedence rules for knowledge conflicts: project-local wins for codebase-specific patterns, global wins for universal safety rules"
    section: "Knowledge Layer"
  - id: IMP-4
    title: "Add ad-hoc agent quality scoring, user deletion, and namespace-collision resolution"
    section: "Ad-hoc Agent Lifecycle"
  - id: IMP-5
    title: "Define deep-pass correction authority explicitly: auto-archive low-confidence, flag high-confidence for human"
    section: "Deep-Pass Agent"
  - id: IMP-6
    title: "Specify Phase 5 runs after Phase 4 completes (or after Phase 3 if no Oracle)"
    section: "Phase Structure"
  - id: IMP-7
    title: "Add knowledge entry schema validation in the compounding agent before write"
    section: "Knowledge Format"
verdict: needs-changes
---

# Flux-Drive v2 Architecture: User Flow and Edge Case Analysis

Reviewed by spec-flow-analyzer on 2026-02-10.

**Document under review:** `/root/projects/Clavain/docs/research/flux-drive-v2-architecture.md`

**v1 implementation reference:** `/root/projects/Clavain/skills/flux-drive/SKILL.md` and its phase files under `/root/projects/Clavain/skills/flux-drive/phases/`

---

## User Flow Overview

The v2 architecture defines seven interconnected systems. Below is every distinct user/system journey mapped from start to finish.

### Flow 1: Standard Review Run (Happy Path)

```
User invokes /clavain:flux-drive <path>
  |
  v
Phase 1: Triage
  1.0 Understand project (read build files, check qmd)
  1.1 Profile document
  1.2 Score 5 core agents + check saved ad-hoc agents + check Oracle
       - If unmatched domain detected -> generate new ad-hoc agent (Flow 3)
       - Oracle always offered if available
       - Cap at 6 agents
  1.3 User confirmation (Approve / Edit / Cancel)
  |
  v
Phase 2: Launch
  2.0 Prepare output directory
  2.1 Inject knowledge context into each agent's prompt (qmd retrieval)
  2.2 Dispatch agents in parallel (background)
  2.3 Verify completion, retry failures, create stubs
  |
  v
Phase 3: Synthesize
  3.0-3.5 Validate, collect, deduplicate, write-back, report
  |
  v
Phase 4: Cross-AI (if Oracle participated)
  4.1-4.5 Validate Oracle, classify blind spots/conflicts, optionally chain to interpeer
  |
  v
Phase 5: Compound (NEW)
  5.1 Read synthesis summary + cross-AI delta
  5.2 Decide what to persist vs what is review-specific
  5.3 Extract knowledge entries (project-local and global)
  5.4 Update lastConfirmed on re-observed findings
  5.5 Check ad-hoc agent graduation criteria
```

### Flow 2: First Run on New Project (No Knowledge, No Ad-hoc Agents)

```
User invokes /clavain:flux-drive <path> on a project that has:
  - No .claude/flux-drive/knowledge/ directory
  - No .claude/flux-drive/agents/ directory
  - No entries in Clavain-global knowledge relevant to this project
  - qmd has no index for this project (or qmd is unavailable)
  |
  v
Phase 1: Triage
  1.0 qmd search returns nothing (or errors) -> ??? (UNSPECIFIED)
  1.1 Profile document normally
  1.2 Score 5 core agents only (no ad-hoc roster to check)
       - No knowledge injection possible -> agents run without context enrichment
  1.3 User confirmation
  |
  v
Phase 2: Launch
  2.1 Knowledge retrieval returns empty -> ??? (UNSPECIFIED: skip injection? inject empty context?)
  2.2 Dispatch agents with no knowledge context -> effectively v1 behavior
  |
  v
Phase 3-4: Normal synthesis and optional cross-AI
  |
  v
Phase 5: Compound
  5.1 First run, so no existing entries to update lastConfirmed on
  5.3 Creates initial knowledge entries -> creates .claude/flux-drive/knowledge/ directory
       - Who creates this directory? The compounding agent? The skill orchestrator?
  5.5 No ad-hoc agents to graduate
```

**CRITICAL GAP:** The spec never describes this flow. It is the most common initial experience for every new project.

### Flow 3: Ad-hoc Agent Generation

```
Phase 1.2 triage detects an unmatched domain
  (e.g., GraphQL schema design, accessibility, i18n)
  |
  v
Triage generates new ad-hoc agent prompt "on the fly"
  - What is the generation mechanism? (prompt engineering? template? LLM self-prompt?)
  - How long does generation take? Does it block triage?
  - What is the quality check on the generated prompt?
  |
  v
Agent is dispatched in Phase 2 alongside core agents
  |
  v
Agent produces output -> enters synthesis
  |
  v
Phase 5: Compounding agent checks if ad-hoc agent should be saved
  - Saved to .claude/flux-drive/agents/{agent-name}.md
  - What naming convention? What if name collides with a core agent?
  |
  v
Future runs: triage checks saved ad-hoc roster
  - Match criteria: ??? (name match? domain match? semantic similarity?)
  |
  v
After use in 2+ projects (or 2+ projects with high-confidence findings):
  - Agent graduates to config/flux-drive/agents/ in Clavain repo
  - Who performs the graduation? The compounding agent? The deep-pass agent? Manual?
  - What happens to the project-local copy?
```

### Flow 4: Ad-hoc Agent is Bad

```
Triage generates ad-hoc agent for "accessibility review"
  |
  v
Agent produces low-quality or irrelevant findings
  - Findings enter synthesis, potentially lowering quality
  |
  v
Phase 5: Compounding agent saves this ad-hoc agent
  (if it produced ANY findings, it may be saved)
  |
  v
Next run: triage finds saved "accessibility" ad-hoc agent
  - Scores it as relevant -> launches it again
  - Produces same low-quality output
  |
  v
FEEDBACK LOOP: Bad agent persists indefinitely
  - No quality gate on saved agents
  - No user mechanism to delete/disable an ad-hoc agent
  - No performance tracking (accuracy rate, usefulness score)
  - Deep-pass might notice pattern across runs, but spec says it looks at
    findings not agent quality
```

**CRITICAL GAP:** No corrective mechanism for bad ad-hoc agents.

### Flow 5: Knowledge Conflict Between Layers

```
Review run on Project A:
  Phase 2 knowledge injection retrieves:
    - Project-local entry: "Pattern X is fine in this codebase (established convention since 2024)"
    - Clavain-global entry: "Pattern X is dangerous (systematic blind spot, origin: cross-ai-delta)"
  |
  v
Agent receives BOTH entries in its context
  - Which takes precedence? UNSPECIFIED
  - Does the agent see metadata (project-local vs global)? UNSPECIFIED
  - Does the agent know one is codebase-specific and the other is universal? UNSPECIFIED
  |
  v
Agent must decide on its own how to weigh conflicting knowledge
  - May produce inconsistent results across runs depending on prompt ordering
  - May flag Pattern X as both "fine" and "dangerous" in the same review
```

**CRITICAL GAP:** No precedence rules. No conflict resolution strategy.

### Flow 6: Compounding a False Positive

```
Run 1: Agent incorrectly flags "auth middleware swallows errors" (it doesn't — the agent misread)
  |
  v
Phase 5: Compounding agent extracts this as knowledge entry
  - confidence: high (because another agent also flagged it, or convergence was high)
  - Entry written to .claude/flux-drive/knowledge/safety-auth-middleware.md
  |
  v
Run 2: Knowledge entry injected into Safety agent's context
  - Agent now has "prior knowledge" confirming the false positive
  - Agent re-flags the same non-issue with even higher confidence
  |
  v
Phase 5: Compounding agent updates lastConfirmed
  - Entry is now REINFORCED, not questioned
  |
  v
Run N: False positive is permanently baked into the knowledge layer
  - Self-reinforcing feedback loop
  - No mechanism to challenge or retract an entry
  - No user-facing way to view, edit, or delete knowledge entries
  - Deep-pass agent consolidates patterns but does not verify factual accuracy
```

**CRITICAL GAP:** No retraction mechanism. No user-facing knowledge management.

### Flow 7: Deep-Pass Discovers Incorrect Compounded Entry

```
Deep-pass agent scans docs/research/flux-drive/ across multiple reviews
  |
  v
Discovers pattern: "Knowledge entry K was always flagged but never actually fixed,
  suggesting it may be a false positive"
  |
  v
??? UNSPECIFIED: What authority does the deep-pass agent have?
  Option A: Auto-corrects (moves to archived/, lowers confidence)
    Risk: Deep-pass itself could be wrong — removes valid entry
  Option B: Flags for human review
    Mechanism: ??? (creates issue file? sends notification? prints warning in next run?)
  Option C: Compounds its own discovery back (writes "entry K may be false positive")
    Risk: Creates meta-knowledge about knowledge — complexity explosion
```

**CRITICAL GAP:** Spec says deep-pass "compounds its own discoveries back into the knowledge layer" but does not define correction authority or human-in-the-loop triggers.

### Flow 8: Oracle Unavailable

```
SessionStart hook reports oracle: unavailable
  OR: which oracle fails AND pgrep Xvfb finds nothing
  |
  v
Phase 1.2: Oracle not offered in triage
  - Cap remains at 6 (not 5+1)
  - No diversity bonus from cross-AI
  |
  v
Phases 2-3: Normal review with 5 core agents only
  |
  v
Phase 4: Skipped entirely
  - No cross-AI delta generated
  |
  v
Phase 5: Compounding agent reads synthesis summary
  - No cross-AI delta to analyze
  - Cannot create knowledge entries with origin: cross-ai-delta
  - Existing entries with origin: cross-ai-delta have no new confirmation
    -> They will decay faster (lastConfirmed not updated)
  |
  v
Over time: All cross-AI-originated knowledge entries age out
  - "Systematic blind spots" category slowly empties
  - No warning to user that knowledge quality is degrading
```

**P1 GAP:** Graceful degradation to "no Oracle" is implicit but the long-term consequence (knowledge decay of cross-AI entries) is not addressed.

### Flow 9: qmd Unavailable or Empty

```
Scenario A: qmd MCP server not running
  Phase 1.0: qmd search tool call fails/errors
    -> ??? UNSPECIFIED: Does triage abort? Continue without qmd?
    -> v1 behavior: Step 1.0 says "if qmd MCP tools are available" — so skip
  Phase 2.1: Knowledge retrieval via qmd also fails
    -> Agents receive no knowledge context
    -> Effectively v1 behavior

Scenario B: qmd running but index is empty (new project, first run)
  Phase 1.0: qmd search returns zero results
    -> Continue with file-based profiling (read CLAUDE.md, AGENTS.md, build files)
  Phase 2.1: Knowledge retrieval returns zero results
    -> Agents receive no knowledge context
    -> Effectively v1 behavior

Scenario C: qmd running but knowledge entries not indexed
  Phase 2.1: qmd search for knowledge entries returns nothing
    -> Same as empty: no knowledge injection
    -> But entries DO exist in .claude/flux-drive/knowledge/ — just not indexed
    -> Silent failure: user thinks knowledge is being used but it isn't
```

**P1 GAP:** Scenario C is a silent failure. The spec relies on qmd for retrieval but never specifies when/how knowledge entries get indexed by qmd.

---

## Flow Permutations Matrix

| Dimension | Variant | Impact on Flows |
|-----------|---------|-----------------|
| **Knowledge state** | Empty (first run) | No injection, no compounding updates, must bootstrap directories |
| | Populated (subsequent runs) | Full knowledge injection, lastConfirmed updates, graduation checks |
| | Conflicting (local vs global) | Undefined precedence, inconsistent agent behavior |
| | Stale (entries not re-confirmed) | Decay logic triggers, entries archived |
| | Corrupted (malformed frontmatter) | qmd may not index, compounding may fail silently |
| **Ad-hoc agent state** | None saved | Core agents only, may generate new ad-hoc |
| | Saved, good quality | Triage matches and launches, enriches review |
| | Saved, bad quality | Re-launched every run, degrades review quality |
| | Multiple saved, overlapping | Triage must deduplicate, cap enforcement harder |
| | Name collision with core agent | Undefined behavior |
| **Oracle state** | Available | Full 5-phase flow, cross-AI delta, diversity bonus |
| | Unavailable this run | Phase 4 skipped, no new cross-AI knowledge, cap at 6 core+adhoc |
| | Permanently gone | Cross-AI knowledge entries decay over time, blind spot detection lost |
| | Oracle fails mid-run | v1 error handling: stub file, continue without Phase 4 |
| **qmd state** | Healthy with index | Full knowledge retrieval, semantic search in triage |
| | Healthy, empty index | Returns nothing, effectively v1 behavior |
| | Unavailable | Tool calls fail, skip all qmd-dependent steps |
| | Index exists but stale | Returns outdated knowledge, may inject wrong context |
| **Dispatch mode** | Task (default) | Claude subagents, retry logic defined |
| | Clodex (autopilot) | Codex CLI dispatch, different retry and fallback chain |
| **Project docs** | Has CLAUDE.md + AGENTS.md | Core agents use codebase-aware mode, +1 scoring bonus |
| | No project docs | Agents fall back to generic mode, no bonus |
| **Concurrent runs** | Single run | Normal operation |
| | Two runs on same project | Knowledge write race condition, ad-hoc agent file collision |
| **User action at triage** | Approve | Normal flow |
| | Edit selection | Re-present triage, user can add/remove agents |
| | Cancel | Stop entirely |
| **Agent count** | Under cap (3-5 agents) | Normal operation, possibly too few for complex documents |
| | At cap (6 agents) | Oracle may displace lowest-scoring core agent |
| | Over cap (5 core + multiple ad-hoc + Oracle) | Displacement logic needed, undefined priority order |

---

## Missing Elements and Gaps

### Category: First-Run Bootstrap

**Gap Description:** The spec describes the system in its steady state (knowledge exists, ad-hoc agents exist, qmd has an index) but never describes the initial bootstrap experience. A user running flux-drive v2 for the first time on any project will encounter: no `.claude/flux-drive/` directory, no knowledge entries, no ad-hoc agents, empty qmd results.

**Impact:** Without explicit bootstrap behavior, implementation will either (a) fail on missing directories, (b) silently produce v1-equivalent results without telling the user, or (c) require manual setup that contradicts the "zero configuration" ethos.

**Current Ambiguity:** Who creates `.claude/flux-drive/knowledge/` and `.claude/flux-drive/agents/`? The compounding agent on first successful run? The orchestrator at Phase 1 start? A setup command?

### Category: Knowledge Conflict Resolution

**Gap Description:** The two-tier knowledge layer (project-local and Clavain-global) has no defined precedence rules. The spec says agents receive "relevant knowledge entries" via qmd but does not specify: (a) whether entries are labeled with their tier, (b) whether project-local entries override global ones on the same topic, (c) what happens when they directly contradict.

**Impact:** Agents will receive contradictory context and resolve it unpredictably. The same codebase could get different review results depending on the order qmd returns entries. This is especially dangerous for safety-critical findings where global says "dangerous" but local says "fine for this project."

**Current Ambiguity:** The v1 system has an analogous pattern: Project Agents (`.claude/agents/fd-*.md`) are preferred over Adaptive Reviewers when they cover the same domain (SKILL.md Step 3.3 rule 5). But the v2 knowledge layer has no equivalent deduplication or precedence rule.

### Category: Compounding Correctness

**Gap Description:** The compounding system has no retraction mechanism. Once a finding is compounded into a knowledge entry, there is no specified way to: (a) mark it as incorrect, (b) lower its confidence based on counter-evidence, (c) let a user review and delete it, (d) prevent it from being re-confirmed by the bias it introduces.

**Impact:** False positives become permanent. The self-reinforcing loop (false positive in knowledge -> agent re-flags -> compounding re-confirms) is the most dangerous failure mode of the entire system. It degrades review quality over time instead of improving it.

**Current Ambiguity:** The deep-pass agent is described as performing "decay" (archiving unconfirmed findings) but not "correction" (fixing wrong findings that ARE confirmed because the knowledge layer itself causes re-confirmation).

### Category: Ad-hoc Agent Lifecycle

**Gap Description:** The spec describes generation, saving, reuse, and graduation but omits: (a) quality evaluation before saving, (b) user ability to list, inspect, edit, or delete saved agents, (c) versioning when a newer generation of the same ad-hoc agent is created, (d) namespace collision with core agents or cross-project agents, (e) deprecation when a domain becomes covered by a new core agent.

**Impact:** The `.claude/flux-drive/agents/` directory becomes an append-only accumulator of agents with no pruning, no quality control, and no user management interface. Over time, triage becomes slower as it checks an ever-growing roster of potentially stale ad-hoc agents.

**Current Ambiguity:** The v1 system has Project Agents (`.claude/agents/fd-*.md`) with a hash-based staleness check. The v2 spec does not mention staleness detection for ad-hoc agents.

### Category: Phase 5 Ordering

**Gap Description:** The spec lists Phase 5 (Compound) after Phase 4 (Cross-AI) in the table but does not explicitly state the dependency. Does Phase 5 wait for Phase 4 to complete? Or can it run after Phase 3 if Oracle is unavailable?

**Impact:** If Phase 5 runs before Phase 4 completes, it misses the cross-AI delta. If it always waits for Phase 4 and Oracle is slow, compounding is delayed. If Oracle fails after Phase 5 already ran, the cross-AI delta knowledge is lost for this run.

**Current Ambiguity:** The immediate compounding agent description says it "reads the synthesis summary + cross-AI delta" — implying it runs after both Phase 3 and Phase 4. But the phase table does not have this dependency arrow.

### Category: Knowledge Indexing

**Gap Description:** The spec says qmd semantic search retrieves knowledge entries, and knowledge entries are markdown files with YAML frontmatter stored in `.claude/flux-drive/knowledge/` and `config/flux-drive/knowledge/`. But it never specifies how or when these files get indexed by qmd.

**Impact:** Knowledge entries could exist on disk but never be retrievable by qmd. This is a silent failure — the user thinks knowledge is accumulating and being used, but agents receive nothing because qmd's index is stale or missing.

**Current Ambiguity:** qmd is described as an MCP server elsewhere in the codebase. Does it auto-index markdown files in certain directories? Does it require explicit `qmd index` commands? Does the compounding agent need to trigger re-indexing after writing new entries?

### Category: Token Budget for Knowledge Injection

**Gap Description:** Open Question 1 in the spec mentions "cap at 10 entries per agent" but this is listed as an open question, not a decision. The actual token cost of knowledge injection is unspecified. If each entry is 200 tokens and 10 entries are injected per agent across 5 agents, that is 10,000 additional tokens per run.

**Impact:** Without a budget, knowledge injection could consume a significant fraction of the agent's context window, reducing the space available for the actual document being reviewed. This is especially problematic for large documents that already approach the trimming threshold (200+ lines).

**Current Ambiguity:** The v1 system has no knowledge injection and already does token-conscious trimming (Phase 2 Step 2.2). The v2 spec does not describe how knowledge injection interacts with the existing trimming budget.

### Category: Merged Agent Quality

**Gap Description:** Open Question 5 acknowledges the risk that 5 merged agents may produce shallower findings than 19 specialists. The mitigation ("knowledge injection means the merged agent has richer context") is circular — on first run, there is no knowledge to inject.

**Impact:** The v2 system on first run with a new project may produce lower-quality results than v1, since it has fewer agents (5 vs up to 8 from a roster of 19) and no knowledge context. The v2 advantage (compounding) only manifests after multiple runs.

**Current Ambiguity:** Is there a planned comparison or A/B test between v1 and v2 on the same document? The brainstorm mentions self-reviews but does not describe a migration validation plan.

### Category: Concurrency and Race Conditions

**Gap Description:** Two flux-drive runs on the same project (e.g., user launches one, then launches another on a different file before the first completes) will both attempt to: (a) read and write knowledge entries, (b) save ad-hoc agents to the same directory, (c) update lastConfirmed timestamps.

**Impact:** File corruption, lost writes, or duplicated knowledge entries. The compounding agent from run 1 and run 2 could both write to the same knowledge file.

**Current Ambiguity:** The v1 system has run isolation via OUTPUT_DIR cleaning but does not address concurrent runs modifying shared state (because v1 has no shared state).

### Category: Knowledge Entry Validation

**Gap Description:** The spec defines a knowledge entry format (YAML frontmatter with domain, source, confidence, convergence, origin, lastConfirmed) but does not specify validation. The compounding agent is an LLM — it could produce malformed frontmatter, missing fields, or invalid values.

**Impact:** Malformed entries may fail to parse during retrieval, fail to match qmd queries, or cause downstream errors in the deep-pass agent.

**Current Ambiguity:** The v1 system has explicit validation in Phase 3 (Step 3.1) for agent output frontmatter. The v2 spec defines no equivalent for knowledge entry frontmatter.

---

## Critical Questions Requiring Clarification

### Critical (Blocks Implementation or Creates Data Risks)

**Q1: What is the precedence rule when project-local and Clavain-global knowledge entries contradict?**

Why it matters: Without a rule, agents receive contradictory context and produce unpredictable results. A safety-critical finding could be suppressed or a project-specific convention could be flagged as dangerous.

Assumption if unanswered: Project-local wins for entries tagged with domain matching the project's tech stack. Clavain-global wins for entries with `origin: cross-ai-delta` (blind spot detection should override project conventions). Both are presented to the agent with tier labels so the agent can weigh them.

Example: Project-local says "error swallowing in `middleware/auth.go` is intentional — see design doc D-42." Clavain-global says "error swallowing in auth middleware is a systematic blind spot." Agent needs to know the first is project-specific context and the second is a cross-project heuristic.

**Q2: How does a user (or the system) retract a false-positive knowledge entry?**

Why it matters: Without retraction, the compounding system has a self-reinforcing false-positive loop. This is the single most dangerous failure mode of the knowledge layer.

Assumption if unanswered: Users can manually delete files from `.claude/flux-drive/knowledge/`. The compounding agent should check if a finding was NOT flagged in the current run despite being in the knowledge layer, and if this happens N times (e.g., 3 consecutive runs without re-confirmation), lower confidence to "low" and then archive.

Example: Run 1 compounds "N+1 query in user_service.go." Runs 2-4 do not review user_service.go (different files). Run 5 reviews user_service.go again and the agent does NOT flag the N+1 query. What happens? Currently: nothing (lastConfirmed stays at Run 1's date, entry eventually decays). Better: the compounding agent notices the non-confirmation and marks it.

**Q3: What authority does the deep-pass agent have over knowledge entries?**

Why it matters: The deep-pass agent is described as performing decay (archiving old entries) and consolidation (merging similar entries). But the spec also says it "compounds its own discoveries back." Can it delete entries? Lower confidence? Rewrite them? Create "meta-entries" about other entries?

Assumption if unanswered: Deep-pass can archive (move to `archived/`) and consolidate (merge two entries into one). It cannot delete entries permanently. It flags questionable entries by adding `status: review-needed` to their frontmatter. A future user-facing command (e.g., `/clavain:knowledge review`) presents flagged entries.

Example: Deep-pass notices that across 10 runs, the "Performance" agent always flags the same function but the finding is never acted on. It could mean: (a) the finding is valid but low-priority (user ignores it), or (b) the finding is wrong. Deep-pass cannot distinguish these cases without human input.

**Q4: What is the ad-hoc agent generation mechanism?**

Why it matters: "Generated by triage when it detects a domain none of the 5 core agents cover well" is the entire specification for ad-hoc agent creation. There is no prompt template, no quality gate, no output format, no maximum generation time.

Assumption if unanswered: Triage (which is the main orchestrator LLM, not a subagent) generates a system prompt for the ad-hoc agent inline, following the same format as existing agent `.md` files (frontmatter + role description + review approach + output format). The generation is synchronous and adds 5-10 seconds to triage. No quality gate — the agent's output quality is evaluated post-hoc in synthesis.

Example: Triage detects a GraphQL schema in the document. It generates an ad-hoc "graphql-schema-reviewer" agent with a prompt like "You are a GraphQL Schema Reviewer. Check for..." The quality of this prompt depends entirely on the orchestrator LLM's knowledge of GraphQL best practices — there is no external validation.

### Important (Significantly Affects UX or Maintainability)

**Q5: What does the first-run experience look like?**

Why it matters: Every project starts here. If the first run is noticeably worse than v1 (fewer agents, no knowledge, no ad-hoc agents), users will perceive v2 as a regression.

Assumption if unanswered: First run is effectively v1 behavior (5 core agents with no knowledge injection, no ad-hoc agents) plus Phase 5 bootstraps the knowledge layer for subsequent runs. The user should be told: "First run on this project -- building knowledge base for future reviews."

Example: User runs `/clavain:flux-drive plan.md` on a new Go project. v1 would select from 19 agents including `go-reviewer`, `security-sentinel`, `architecture-strategist` etc. v2 selects from 5 merged agents: "Quality & Style" (which subsumes go-reviewer), "Safety & Correctness" (security-sentinel), "Architecture & Design" (architecture-strategist). The user sees 3 agents instead of 6-8. Is this a problem?

**Q6: How does triage score saved ad-hoc agents?**

Why it matters: The scoring system for 5 core agents uses a 0-2 scale with bonuses. Ad-hoc agents need comparable scoring or they will either always be selected (no scoring, just domain match) or never be selected (scored too low).

Assumption if unanswered: Ad-hoc agents are scored on the same 0-2 scale based on domain overlap with the document profile. They get a +1 "project-specific" bonus (like v1 Project Agents). They are subject to the same cap (6 total).

Example: Project has a saved "graphql-schema-reviewer" ad-hoc agent. User reviews a plan that mentions GraphQL. Triage scores: Architecture 2, Safety 1, Quality 2, graphql-schema-reviewer ??? (no scoring criteria defined). Does it get a 2 for domain match? A 2+1 for project-specific?

**Q7: When and how are knowledge entries indexed by qmd?**

Why it matters: qmd semantic search is the SOLE retrieval mechanism for knowledge entries (the spec says "Agents don't use domain-tag matching"). If entries are not indexed, the entire knowledge layer is invisible.

Assumption if unanswered: The compounding agent (Phase 5) triggers qmd re-indexing after writing new entries. Or: knowledge directories are in qmd's auto-watch list.

Example: Compounding agent writes `safety-auth-middleware.md` to `.claude/flux-drive/knowledge/`. Next run, Phase 2 tries to retrieve it via qmd. If qmd has not re-indexed, the entry is invisible.

**Q8: What is the ad-hoc agent naming convention, and how are name collisions resolved?**

Why it matters: Two projects could independently generate ad-hoc agents with the same name (e.g., "accessibility-reviewer") but different prompts. When one graduates to Clavain-global, it overwrites or conflicts with the other.

Assumption if unanswered: Ad-hoc agents are named `{domain}-reviewer` (e.g., `graphql-schema-reviewer`, `accessibility-reviewer`). Project-local agents live in `.claude/flux-drive/agents/` namespaced by project. Global agents live in `config/flux-drive/agents/`. Graduation merges prompts or the deep-pass agent picks the better one based on finding quality.

Example: Project A generates "i18n-reviewer" focused on React i18n patterns. Project B generates "i18n-reviewer" focused on server-side gettext patterns. Project A's agent graduates to global. Project B's agent also meets graduation criteria. What happens?

**Q9: How does the cap interact with ad-hoc agents and Oracle?**

Why it matters: v2 drops the cap from 8 to 6. With 5 core agents + Oracle, the cap is already full. Any ad-hoc agent requires displacing a core agent or Oracle.

Assumption if unanswered: The cap of 6 means: most runs select 3-4 core agents + 0-2 ad-hoc agents + optional Oracle. Oracle displaces the lowest-scoring core agent (matching v1 behavior). Ad-hoc agents displace core agents with score 1 or lower.

Example: Document touches architecture, safety, quality, and has GraphQL content. Triage: Architecture 2, Safety 2, Quality 2, Performance 0, User 0 = 3 core agents. Saved graphql-schema-reviewer: 2+1=3. Oracle: available. Total 5 agents, under cap. But if ALL 5 core agents score 2+, plus an ad-hoc agent, plus Oracle = 7, one must be dropped. Which one?

### Nice-to-Have (Improves Clarity but Has Reasonable Defaults)

**Q10: What is the decay threshold N for knowledge entry archival?**

Why it matters: "Entries not confirmed in N reviews get moved to archived/" — N is undefined. Too low (2-3) and valid but infrequently-reviewed knowledge is lost. Too high (20+) and stale knowledge persists.

Assumption if unanswered: N = 10 reviews. This is approximately 2-3 weeks of regular use. Archived entries are not deleted, just moved, so they can be restored.

**Q11: Is there a maximum size for the knowledge directories?**

Why it matters: An active project with many reviews could accumulate hundreds of knowledge entries. qmd retrieval may slow down, and token injection budget becomes harder to manage.

Assumption if unanswered: No hard cap in v1. The deep-pass agent's consolidation role implicitly manages growth by merging similar entries. A soft warning at 100 entries per directory could be added.

**Q12: Does Phase 5 run in the foreground or background?**

Why it matters: If foreground, it adds time to every review. If background, the user may close the session before compounding completes.

Assumption if unanswered: Foreground, because it needs to read the synthesis output which is in the current session context. Duration should be short (30-60 seconds) since it reads a summary, not raw agent outputs.

**Q13: Should the compounding agent have access to the raw agent outputs, or only the synthesis summary?**

Why it matters: The spec says "reads the synthesis summary + cross-AI delta (not raw agent outputs)." But the synthesis may have deduplicated or discarded findings that were individually valuable as knowledge entries.

Assumption if unanswered: Summary + cross-AI delta is sufficient. Raw outputs are available in OUTPUT_DIR if needed, but the compounding agent should prefer the curated synthesis.

**Q14: What happens to v1 Project Agents (`.claude/agents/fd-*.md`) during migration?**

Why it matters: Projects using v1 with bootstrapped Project Agents will have files in `.claude/agents/fd-*.md`. v2 uses `.claude/flux-drive/agents/` for ad-hoc agents. The migration path is not described.

Assumption if unanswered: v1 Project Agents are ignored by v2 (different directory). Users are told to migrate manually if they had valuable project agents. Or: triage checks both directories during a transition period.

---

## Recommended Next Steps

1. **Define the first-run bootstrap sequence.** Add a section to the spec describing: directory creation, user messaging ("building knowledge base"), and explicit statement that first-run is v1-equivalent. This is the most common entry point and is completely unspecified.

2. **Add knowledge conflict resolution rules.** Define tier labels visible to agents, precedence rules (project-local for conventions, global for safety), and a deduplication strategy for contradictory entries on the same topic.

3. **Design a retraction mechanism.** Options: (a) non-confirmation decay (finding not re-flagged in N runs despite reviewing the same file -> lower confidence), (b) user command (`/clavain:knowledge retract <entry>`), (c) deep-pass correction authority with human approval for high-confidence retractions.

4. **Specify ad-hoc agent quality gates.** At minimum: (a) saving is conditional on producing at least one high-confidence finding, (b) a "strikes" counter tracks consecutive low-quality runs and auto-archives after 3 strikes, (c) users can list and delete ad-hoc agents.

5. **Define the qmd indexing contract.** Specify when knowledge entries get indexed (after compounding writes them? on a schedule? on next qmd startup?) and what happens when qmd is unavailable (graceful degradation to domain-tag fallback matching).

6. **Add Phase 5 ordering to the phase dependency graph.** Explicitly state: Phase 5 runs after Phase 4 if Oracle participated, or after Phase 3 if Oracle was unavailable. Phase 5 must not run concurrently with another flux-drive run's Phase 5 on the same project.

7. **Write the ad-hoc agent generation specification.** Define: prompt template, naming convention, collision resolution, quality gate, maximum generation time, and scoring criteria for triage.

8. **Plan a v1-to-v2 migration path.** Address: existing Project Agents, existing output directories, first-time use of new knowledge directories, and a comparison test on a known document to validate merged agent quality matches or exceeds v1 specialist quality.

---

## Overall Assessment

The flux-drive v2 architecture is an ambitious and well-motivated redesign that addresses real pain points (bloated roster, no learning, static agents). The core ideas -- 5 merged agents, two-tier knowledge, ad-hoc generation, compounding -- are sound. However, the spec describes the system in steady state and leaves the most common user journeys (first run, error correction, degraded mode) largely unspecified. The most dangerous gap is the compounding false-positive loop: without a retraction mechanism, the knowledge layer can degrade review quality over time instead of improving it. The eight critical and important questions above should be answered before implementation begins.

<!-- flux-drive:complete -->
