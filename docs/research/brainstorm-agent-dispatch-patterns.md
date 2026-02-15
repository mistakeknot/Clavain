# Brainstorm: Reducing Context Cost of Mass Agent Dispatch

**Date:** 2026-02-14
**Status:** Brainstorm
**Problem:** Parent session context bloat when dispatching 10-26 subagents via the Task tool

---

## Table of Contents

1. [Problem Analysis](#problem-analysis)
2. [Context Budget Breakdown](#context-budget-breakdown)
3. [Approach 1: Prompt Compression via File Indirection](#approach-1-prompt-compression-via-file-indirection)
4. [Approach 2: Batch Dispatch via Meta-Agent](#approach-2-batch-dispatch-via-meta-agent)
5. [Approach 3: Staged Chunking with Context Pruning](#approach-3-staged-chunking-with-context-pruning)
6. [Approach 4: CLI Session Spawning via claude -p](#approach-4-cli-session-spawning-via-claude--p)
7. [Approach 5: Codex CLI for Research/Analysis Tasks](#approach-5-codex-cli-for-researchanalysis-tasks)
8. [Approach 6: Dispatcher Session Pattern (Sidecar)](#approach-6-dispatcher-session-pattern-sidecar)
9. [Approach 7: Notification Suppression and Batching](#approach-7-notification-suppression-and-batching)
10. [Approach 8: File-Based Job Queue](#approach-8-file-based-job-queue)
11. [Approach 9: Prompt Template Pre-Registration](#approach-9-prompt-template-pre-registration)
12. [Approach 10: Hierarchical Dispatch (Dispatcher Subagent)](#approach-10-hierarchical-dispatch-dispatcher-subagent)
13. [Approach 11: Hybrid Codex + Task Split](#approach-11-hybrid-codex--task-split)
14. [Approach 12: Progressive Delegation with Early Termination](#approach-12-progressive-delegation-with-early-termination)
15. [Approach 13: Tmux Orchestrator Pattern](#approach-13-tmux-orchestrator-pattern)
16. [Approach 14: Compact Dispatch Protocol](#approach-14-compact-dispatch-protocol)
17. [Approach 15: Result File Polling Instead of Task Notifications](#approach-15-result-file-polling-instead-of-task-notifications)
18. [Comparative Analysis](#comparative-analysis)
19. [Recommended Combinations](#recommended-combinations)
20. [Implementation Priority](#implementation-priority)

---

## Problem Analysis

### The Context Arithmetic

When the parent session dispatches N agents, the following context entries accumulate:

| Source | Per-Agent Size | For 13 Agents | For 26 Agents |
|--------|---------------|---------------|---------------|
| Task tool call (prompt) | ~3,000 chars | ~39,000 chars | ~78,000 chars |
| Tool result ("launched") | ~400 chars | ~5,200 chars | ~10,400 chars |
| Progress notifications | ~150 chars x 3-4 | ~6,500 chars | ~13,000 chars |
| Completion notifications | ~500 chars | ~6,500 chars | ~13,000 chars |
| Orchestration reasoning | ~2,000 chars | ~2,000 chars | ~2,000 chars |
| **Total** | | **~59,200 chars** | **~116,400 chars** |

Claude Code's context window is ~200K tokens (~800K chars). A 26-agent dispatch consumes ~15% of the context window purely on dispatch overhead, before any actual work.

The problem compounds: after dispatch, the parent still needs context for synthesis, user interaction, follow-up actions, and the original conversation history. Effective usable context drops to 50-60% of the window.

### What Actually Enters Context

From examining the existing patterns (review.md, quality-gates.md, flux-drive, flux-research):

1. **Task tool call**: The full prompt text is serialized into context as a tool_use block. This is the largest contributor. A well-structured review prompt with document path, output format, domain context, and knowledge context can easily reach 3-5K chars per agent.

2. **Tool result**: Confirmation that the task launched. Small (~400 chars) but adds up.

3. **System-reminder notifications**: Claude Code injects progress updates as system messages. These are NOT controllable by the plugin. They appear as `task-notification` blocks with status updates.

4. **Completion notifications**: When a background task finishes, a system message delivers a summary of the agent's output. This is typically 300-500 chars but can be longer if the agent produced substantial output.

5. **Orchestration turns**: The parent's own reasoning about what to dispatch, how to triage, staging decisions. This is typically 1-3 turns of ~1K chars each.

### Root Causes

The core issue is that Claude Code's Task tool was designed for modest parallelism (2-5 agents), not mass dispatch (10-26). The protocol treats each agent as a first-class conversation participant, with full prompt text in context and individual lifecycle notifications.

Three independent cost centers:
- **Prompt duplication**: Each agent gets a full prompt inlined in context, even when prompts share 60-80% boilerplate.
- **Notification overhead**: Progress and completion events are per-agent, with no batching or suppression.
- **Tool call overhead**: Each Task invocation requires a tool_use/tool_result pair in context.

---

## Context Budget Breakdown

### Current State: Flux-Drive with 7 Review Agents

Using the flux-drive orchestration as a concrete example:

```
Phase 1 (triage):
  - Read document: ~2K chars in context
  - Triage reasoning: ~3K chars
  - User confirmation: ~1K chars
  Subtotal: ~6K chars

Phase 2 (dispatch):
  Stage 1 (3 agents):
  - 3x Task prompts: ~9K chars (3K each)
  - 3x Tool results: ~1.2K chars
  - 3x Progress notifications: ~1.5K chars
  - 3x Completion notifications: ~1.5K chars
  Subtotal: ~13.2K chars

  Expansion decision: ~2K chars

  Stage 2 (4 agents):
  - 4x Task prompts: ~12K chars
  - 4x Tool results: ~1.6K chars
  - 4x Progress notifications: ~2K chars
  - 4x Completion notifications: ~2K chars
  Subtotal: ~17.6K chars

Phase 3 (synthesis):
  - Read 7 output files: ~14K chars (referenced, not inlined)
  - Synthesis reasoning: ~5K chars
  Subtotal: ~19K chars

TOTAL: ~57.8K chars (~14.5K tokens)
```

This is manageable for 7 agents. But scaling to 26 agents (full roster with generated agents + research escalation + Oracle):

```
Phase 2 at 26 agents:
  - 26x Task prompts: ~78K chars
  - 26x Tool results: ~10.4K chars
  - 26x Progress: ~13K chars
  - 26x Completion: ~13K chars
  Subtotal: ~114.4K chars (~28.6K tokens)

FULL PIPELINE: ~139K chars (~35K tokens)
```

That's 35K tokens of dispatch overhead alone, nearly 18% of a 200K context window.

---

## Approach 1: Prompt Compression via File Indirection

### Mechanism

Instead of inlining the full prompt in each Task call, write the prompt to a temp file and have the Task prompt say only: "Read /tmp/flux-drive-task-{agent}.md and execute."

The current flux-drive already does this partially (Step 2.1c writes the document to a temp file). This approach extends it to the ENTIRE agent prompt, not just the review document.

### Implementation

```
# Before dispatch:
Write /tmp/flux-drive-prompt-fd-architecture-{ts}.md with:
  - Output format contract
  - Knowledge context
  - Domain context
  - Document reference
  - Focus area

# Task call becomes:
Task(fd-architecture):
  "Read and execute the review task at /tmp/flux-drive-prompt-fd-architecture-{ts}.md.
   Write output to {OUTPUT_DIR}/fd-architecture.md.partial, rename to .md when complete."
```

### Context Savings

| Component | Before | After | Savings |
|-----------|--------|-------|---------|
| Per-agent prompt | ~3,000 chars | ~200 chars | ~2,800 chars |
| Per-agent total | ~4,000 chars | ~1,200 chars | ~2,800 chars |
| 7 agents | ~28K chars | ~8.4K chars | ~19.6K chars |
| 26 agents | ~104K chars | ~31.2K chars | ~72.8K chars |

**Savings: ~70% reduction in dispatch context.**

### Feasibility

**Works**: Subagents have full file system access. They can Read any file the parent can. This is the single highest-impact change with the lowest risk.

**Doesn't work**: Tool results and notifications still accumulate. Can't eliminate those.

**Prerequisites**:
- Write all prompt files before dispatching (already the pattern in clodex dispatch).
- Unique temp file names per run (already done with timestamps).
- Cleanup of temp files after synthesis.

**Risk**: If a subagent fails to read the file (permission issue, file doesn't exist), it runs with minimal context. Mitigation: write file, verify it exists, then dispatch.

### Verdict: HIGH IMPACT, LOW EFFORT. Implement immediately.

---

## Approach 2: Batch Dispatch via Meta-Agent

### Mechanism

Instead of N individual Task calls, dispatch a single "meta-dispatcher" subagent whose job is to launch all N agents. The parent's context sees only 1 Task call, 1 tool result, and 1 completion notification.

```
Task(dispatch-orchestrator):
  "You are a dispatch coordinator. Read /tmp/dispatch-manifest-{ts}.json.
   It contains a list of agent tasks. For each entry, launch it as a
   background Task with the specified subagent_type and prompt file.
   When all agents complete, write a summary to /tmp/dispatch-results-{ts}.json."
```

The manifest file:
```json
{
  "output_dir": "/path/to/output",
  "agents": [
    {
      "name": "fd-architecture",
      "subagent_type": "interflux:review:fd-architecture",
      "prompt_file": "/tmp/flux-drive-prompt-fd-architecture.md"
    },
    {
      "name": "fd-safety",
      "subagent_type": "interflux:review:fd-safety",
      "prompt_file": "/tmp/flux-drive-prompt-fd-safety.md"
    }
  ]
}
```

### Context Savings

| Component | Before (26 agents) | After (1 meta-agent) | Savings |
|-----------|-------------------|---------------------|---------|
| Task calls | 26 x ~200 chars | 1 x ~300 chars | ~4,900 chars |
| Tool results | 26 x ~400 chars | 1 x ~400 chars | ~10,000 chars |
| Progress notifications | 26 x ~500 chars | 1 x ~500 chars | ~12,500 chars |
| Completion notifications | 26 x ~500 chars | 1 x ~500 chars | ~12,500 chars |
| **Total context** | ~41.6K chars | ~1.7K chars | **~39.9K chars** |

Combined with Approach 1 (file indirection): total dispatch overhead drops from ~116K to ~1.7K chars. That's a **98.5% reduction**.

### Feasibility

**Works**: Subagents CAN launch their own subagents. The meta-agent reads a manifest and calls Task N times.

**Critical concern**: Do progress/completion notifications from grandchild agents bubble up to the grandparent (original session)? Based on Claude Code's architecture:
- Progress notifications are scoped to the DIRECT parent. Grandchildren notify the meta-agent, not the root.
- The root session only sees the meta-agent's lifecycle events.

**If notifications DON'T bubble**: This is the ideal pattern. The root session sees exactly 1 dispatch.

**If notifications DO bubble**: The savings are reduced but still significant because the prompt text (the largest contributor) is eliminated from the root's context.

**Doesn't work well**:
- The meta-agent itself has a context window. It accumulates 26 dispatches internally. But since it's a single-purpose agent, this is fine -- it doesn't need context for anything else.
- If the meta-agent crashes mid-dispatch, some agents launch, some don't. Need crash recovery.
- Staging (launch 3, analyze, launch 4 more) is harder because the meta-agent doesn't have the triage intelligence.

**Prerequisites**:
- A reusable dispatch-orchestrator agent definition
- Manifest file format
- The meta-agent needs to handle subagent_type correctly
- Crash recovery (manifest tracks which agents launched)

### Variant 2a: Two-Tier Dispatch

For staged dispatch (flux-drive's Stage 1 + Stage 2 pattern):

```
Task(stage-1-dispatcher):
  "Launch these 3 agents from manifest. Wait for completion.
   Read their outputs. Write summary to /tmp/stage-1-results.json."

# Parent reads results, makes expansion decision

Task(stage-2-dispatcher):
  "Launch these 4 agents from manifest. Wait for completion.
   Write summary to /tmp/stage-2-results.json."
```

This preserves the staged intelligence while reducing context from 7 individual dispatches to 2.

### Verdict: VERY HIGH IMPACT, MEDIUM EFFORT. Best combined with Approach 1.

---

## Approach 3: Staged Chunking with Context Pruning

### Mechanism

Dispatch agents in batches of 3-5. After each batch completes and results are synthesized, request that Claude Code prune the dispatch-related context from earlier batches. The key insight: once an agent has completed and its output file is written, the Task call that launched it is dead context.

### Implementation

```
Batch 1: Dispatch agents 1-5
         Wait for completion
         Read output files
         Summarize findings to /tmp/batch-1-summary.md
         [Context pruning opportunity]

Batch 2: Dispatch agents 6-10
         Wait for completion
         Read output files
         Summarize findings to /tmp/batch-2-summary.md
         [Context pruning opportunity]

Batch 3: Dispatch agents 11-13
         ...

Final: Read all batch summaries, synthesize
```

### Context Savings

At any given time, only 1 batch worth of dispatch context is "live":

| Scenario | Peak Context | Without Batching |
|----------|-------------|-----------------|
| 13 agents, batches of 5 | ~22K chars peak | ~59K chars |
| 26 agents, batches of 5 | ~22K chars peak | ~116K chars |

### Feasibility

**Works partially**: Claude Code does not have an explicit "prune context" API. However, context naturally cycles:
- Older tool calls scroll out of the context window as new content pushes in
- The conversation model gives less weight to older tool interactions
- Some Claude Code implementations may truncate middle context

**Doesn't really work**: In practice, Claude Code keeps ALL tool interactions in context until the window is full. There's no way to explicitly remove old Task calls. The "pruning" here is aspirational, not mechanical.

**What actually works**: The batching part. Even without pruning, batching creates natural breakpoints where the parent can write intermediate summaries to files. If the context window fills up, the parent has file-based checkpoints to recover from.

**Prerequisites**:
- Batch assignment during triage (which agents go in which batch)
- Inter-batch summary format
- Tolerance for longer wall-clock time (sequential batches vs. all-parallel)

### Verdict: MODERATE IMPACT, LOW EFFORT. Useful as a fallback, not a primary strategy.

---

## Approach 4: CLI Session Spawning via `claude -p`

### Mechanism

Instead of using the Task tool, spawn entirely separate Claude Code sessions using `claude -p "prompt"` via the Bash tool. Each session is independent -- no notifications flow back, no context shared.

```bash
claude -p "Read /tmp/flux-drive-prompt-fd-architecture.md and execute the review task." \
  --output-file /tmp/fd-architecture-result.md &

claude -p "Read /tmp/flux-drive-prompt-fd-safety.md and execute the review task." \
  --output-file /tmp/fd-safety-result.md &

wait
```

### Context Savings

| Component | Task Tool (26 agents) | CLI Spawn (26 agents) | Savings |
|-----------|----------------------|----------------------|---------|
| Per-agent in parent | ~4,000 chars | ~200 chars (bash cmd) | ~3,800 chars |
| Notifications | ~25K chars | 0 | ~25K chars |
| Total | ~116K chars | ~5.2K chars | ~110.8K chars |

**Savings: ~95% reduction.**

### Feasibility

**Works**: `claude -p` is a real CLI command. It can be run from Bash. Multiple instances can run in parallel via `&` and `wait`.

**Major issues**:
1. **No MCP access**: CLI sessions don't inherit the parent's MCP server connections. Agents that need qmd, exa, or other MCP tools won't work.
2. **No plugin context**: CLI sessions don't load plugin skills/commands unless `--plugin-dir` is specified. And even then, they're fresh sessions without the parent's conversation state.
3. **No subagent_type**: Can't specify that a CLI session should use a particular agent personality. It's always a generic Claude instance.
4. **Model routing**: CLI sessions use whatever model is configured globally, not necessarily the same model the parent is using.
5. **Cost**: Each CLI session is a separate API call chain. No token sharing.
6. **Authentication/permissions**: Works on this server because `cc` handles permissions, but may not generalize.

**Partial mitigation**: Include the agent personality in the prompt file itself. The CLI session reads the file which contains both the agent's system prompt AND the task prompt. This approximates subagent_type behavior, though without the Claude Code platform's built-in agent routing.

**Where this shines**: For tasks that DON'T need MCP, DON'T need specific agent types, and are primarily file I/O (read files, analyze, write output). Research agents and some review agents fit this profile.

### Verdict: HIGH IMPACT for suitable tasks, but NOT a general replacement. Best for research/analysis agents that only need file access.

---

## Approach 5: Codex CLI for Research/Analysis Tasks

### Mechanism

Route read-only, file-analysis tasks through Codex CLI (`dispatch.sh`) instead of Claude Code subagents. Codex agents run in separate sandboxes, produce output files, and don't affect the parent's context at all.

The existing clodex infrastructure already supports this:
- `dispatch.sh` wraps `codex exec` with sensible defaults
- `--prompt-file` reads task from file
- `-o` writes output to file
- `--tier fast|deep` selects model
- Parallel dispatch via multiple Bash calls

### Implementation

```bash
# Dispatch review agents through Codex
DISPATCH=$(find ~/.claude/plugins/cache -path '*/clavain/*/scripts/dispatch.sh' 2>/dev/null | head -1)

bash "$DISPATCH" --prompt-file /tmp/review-fd-arch.md \
  -C "$PROJECT_ROOT" --name fd-arch \
  -o /tmp/codex-{name}.md --tier deep &

bash "$DISPATCH" --prompt-file /tmp/review-fd-safety.md \
  -C "$PROJECT_ROOT" --name fd-safety \
  -o /tmp/codex-{name}.md --tier deep &

wait
```

### Context Savings

Same as CLI session spawning: ~95% reduction. The Codex dispatch appears as Bash tool calls in context (~200 chars each), not full Task invocations.

### Feasibility

**Works well for**:
- Review tasks where the agent reads files and writes findings
- Research tasks that search the codebase
- Any task with clear input/output contract

**Doesn't work for**:
- Tasks needing Claude Code-specific features (MCP servers, specific subagent_types, conversation continuity)
- Tasks needing the review agent's full personality/training (Codex models differ from Claude models)
- Tasks where the Claude-specific reasoning quality matters (safety reviews, architectural reviews)

**Key tradeoff**: Codex uses GPT models (gpt-5.3-codex-spark/deep), not Claude. The review quality may differ. For some agents (fd-safety, fd-correctness), the Claude-specific training matters. For others (fd-quality, repo-research-analyst), the model difference is less critical.

**Already supported**: dispatch.sh has `--tier deep` and `--prompt-file` and all the plumbing needed. This approach requires only routing decisions, not new infrastructure.

### Verdict: HIGH IMPACT for research/utility agents. Use selectively, not universally.

---

## Approach 6: Dispatcher Session Pattern (Sidecar)

### Mechanism

Run a persistent "dispatcher" Claude Code session in a separate tmux pane. The parent session writes dispatch requests to a file-based queue. The dispatcher reads requests, launches agents via Task tool, and writes results to files. The parent polls for results.

```
Parent Session (tmux pane 1):
  1. Write /tmp/dispatch-queue/request-001.json
  2. Write /tmp/dispatch-queue/request-002.json
  ...
  3. Poll /tmp/dispatch-results/ for completions

Dispatcher Session (tmux pane 2):
  Running: claude -p "You are a dispatch coordinator. Watch /tmp/dispatch-queue/
  for new .json files. For each, launch the specified agent via Task tool..."
```

### Context Savings

Parent sees only file writes and polls: ~200 chars per agent. No Task calls, no notifications.

### Feasibility

**Major issues**:
1. **Session lifecycle**: The dispatcher session needs to stay alive across multiple dispatch cycles. `claude -p` exits after one response. Would need an interactive session or a loop.
2. **No persistent file watching**: Claude Code sessions can't run infinite loops watching for files. They execute, produce output, and exit.
3. **Coordination complexity**: Two independent Claude sessions coordinating via filesystem is fragile. Race conditions, stale requests, partial writes.
4. **Resource usage**: Two active Claude sessions means double the API costs for the dispatcher overhead.

**Variant 6a: Script-based dispatcher**

Instead of a Claude session, use a bash script that watches for requests and dispatches Codex agents:

```bash
#!/bin/bash
# dispatcher-daemon.sh
inotifywait -m /tmp/dispatch-queue/ -e create |
while read dir action file; do
  prompt_file=$(jq -r '.prompt_file' "/tmp/dispatch-queue/$file")
  output=$(jq -r '.output_file' "/tmp/dispatch-queue/$file")
  bash dispatch.sh --prompt-file "$prompt_file" -C "$project" -o "$output" &
done
```

This is simpler but limited to Codex dispatch (no Claude Task tool).

### Verdict: LOW FEASIBILITY for Claude sessions. MODERATE for Codex-based variant. Overly complex for the benefit.

---

## Approach 7: Notification Suppression and Batching

### Mechanism

If Claude Code provided configuration to suppress or batch subagent notifications, the context cost would drop significantly. This is a platform feature request, not something we can implement.

### What Would Help

1. **Suppress progress notifications**: `run_in_background: true, suppress_progress: true` -- agent runs silently, only completion is reported.
2. **Batch completion notifications**: Instead of N individual completion messages, one message: "5 agents completed: [names]. Read their output files."
3. **Compact notification format**: Replace verbose notification text with a one-line summary.

### Context Savings (if available)

| Feature | Savings per Agent | 26 Agents |
|---------|-----------------|-----------|
| Suppress progress | ~500 chars | ~13K chars |
| Batch completions | ~400 chars | ~10K chars |
| Compact format | ~200 chars | ~5K chars |
| **All three** | ~1,100 chars | ~28K chars |

### Feasibility

**Not currently possible.** Claude Code's notification system is not configurable by plugins or users. This requires a platform change.

**Advocacy path**: File a feature request for `suppress_notifications` or `notification_level: none|summary|full` on the Task tool.

### Verdict: NOT ACTIONABLE NOW. Worth requesting as a platform feature.

---

## Approach 8: File-Based Job Queue

### Mechanism

Inspired by distributed systems job queues. The parent writes job specifications to files. A coordinator (could be a single subagent or a bash process) picks up jobs and executes them. Results are written to a known output directory.

```
/tmp/flux-dispatch-{run-id}/
  queue/
    fd-architecture.json    # Job spec
    fd-safety.json
    fd-quality.json
  running/                  # Jobs being processed (moved from queue/)
  done/                     # Completed jobs (moved from running/)
  results/                  # Output files
    fd-architecture.md
    fd-safety.md
```

### Implementation with Codex

```bash
# Parent writes all job specs
for agent in fd-architecture fd-safety fd-quality; do
  Write /tmp/flux-dispatch-{id}/queue/${agent}.json
done

# Single bash command dispatches all
for spec in /tmp/flux-dispatch-{id}/queue/*.json; do
  agent=$(basename "$spec" .json)
  prompt_file=$(jq -r '.prompt_file' "$spec")
  mv "$spec" /tmp/flux-dispatch-{id}/running/
  bash "$DISPATCH" --prompt-file "$prompt_file" -C "$PROJECT" \
    --name "$agent" -o "/tmp/flux-dispatch-{id}/results/{name}.md" &
done
wait

# Move all to done
mv /tmp/flux-dispatch-{id}/running/*.json /tmp/flux-dispatch-{id}/done/
```

### Context Savings

Parent context sees: N Write tool calls (small, ~200 chars each for JSON specs) + 1 Bash command + 1 Bash result. Total: ~N*200 + 500 = ~5.7K for 26 agents.

Compare to ~116K with direct Task dispatch. **~95% savings.**

### Feasibility

**Works**: This is essentially the Codex dispatch pattern (Approach 5) with more structure. The job queue semantics add robustness (retry, partial completion tracking) at the cost of complexity.

**Limitations**: Same as Approach 5 -- limited to Codex-compatible tasks. No MCP, no Claude subagent personalities.

**When it adds value over raw Codex dispatch**: When you need crash recovery, retry logic, or monitoring across many agents. For 5-7 agents, raw dispatch is fine. For 20+, the queue structure helps.

### Verdict: MODERATE IMPACT. Useful for very large dispatches (20+). Overkill for typical flux-drive (5-7).

---

## Approach 9: Prompt Template Pre-Registration

### Mechanism

Define reusable prompt templates that agents understand by reference, not by full text. Instead of inlining the output format contract, knowledge context, and domain context in every prompt, register them as named templates:

```
Task(fd-architecture):
  "Execute review template 'flux-drive-v1' with:
   - document: /tmp/flux-drive-doc.md
   - output_dir: /path/to/output
   - focus: architecture
   - domain_context: /tmp/domain-ctx-arch.md"
```

The agent knows what "flux-drive-v1" means because its agent definition (the .md file) already contains the full output format contract and review methodology.

### Context Savings

| Component | Before | After | Savings |
|-----------|--------|-------|---------|
| Output format (~800 chars) | Inlined per agent | In agent definition | ~800/agent |
| Knowledge context (~500 chars) | Inlined per agent | File reference | ~400/agent |
| Domain context (~400 chars) | Inlined per agent | File reference | ~300/agent |
| Focus area (~200 chars) | Inlined | Inlined (unique) | 0 |
| **Per-agent savings** | | | ~1,500 chars |
| **26 agents** | | | ~39K chars |

### Feasibility

**Works partially**: Agent definitions (.md files) already contain methodology and output format. If the Task prompt says "follow your standard flux-drive review protocol," the agent should understand.

**Risk**: Without explicit instructions in the prompt, agents may deviate from expected output format. The inline contract acts as a reinforcement.

**Compromise**: Include a minimal output format reminder (3 lines instead of 20) and reference the file for full details:

```
"Output format: Findings Index → Summary → Issues → Improvements.
 Full contract at /tmp/flux-drive-contracts.md.
 Document at /tmp/flux-drive-doc.md.
 Output to {OUTPUT_DIR}/fd-architecture.md.partial."
```

### Verdict: MODERATE IMPACT. Works best combined with Approach 1 (file indirection).

---

## Approach 10: Hierarchical Dispatch (Dispatcher Subagent)

### Mechanism

This is the detailed version of Approach 2. A single "dispatcher" subagent receives the full dispatch manifest and handles all agent launching internally.

### Architecture

```
Parent Session
  └── Task(dispatch-coordinator)           # 1 Task call in parent context
       ├── Task(fd-architecture)           # These are in the dispatcher's context
       ├── Task(fd-safety)                 # NOT the parent's
       ├── Task(fd-quality)
       ├── Task(fd-correctness)
       └── Task(fd-performance)

       Writes: /tmp/dispatch-results-{id}.json
       Writes: {OUTPUT_DIR}/fd-*.md (individual agent outputs)
```

### Dispatcher Agent Prompt

```markdown
# Dispatch Coordinator

You are a dispatch coordinator for flux-drive reviews. Your ONLY job is to:

1. Read the dispatch manifest at {MANIFEST_FILE}
2. For each agent entry, launch a Task with:
   - subagent_type from the manifest
   - Prompt: "Read and execute {prompt_file}. Write output to {output_file}."
   - run_in_background: true
3. Wait for all agents to complete (poll {OUTPUT_DIR} for .md files)
4. Write a completion summary to {RESULTS_FILE}

DO NOT analyze, synthesize, or modify agent outputs.
DO NOT add your own review findings.
You are a dispatcher, not a reviewer.
```

### Critical Question: Notification Bubbling

The entire approach hinges on whether grandchild notifications bubble to the grandparent:

**Scenario A: Notifications DON'T bubble (ideal)**
- Parent sees: 1 Task launch + 1 completion = ~1.5K chars
- Dispatcher sees: N Task launches + N completions (its own context, irrelevant to parent)
- **Result**: ~98% context savings in parent

**Scenario B: Notifications DO bubble**
- Parent sees: 1 Task launch + N progress notifications + 1 completion
- Notifications are smaller (status only, no prompt text) = ~N*150 chars
- **Result**: ~80% context savings (prompts eliminated, notifications remain)

**Scenario C: Notifications bubble AND include grandchild prompts**
- Parent sees everything: worst case, no improvement
- **Result**: No savings

Based on Claude Code's architecture, Scenario A is most likely. Background tasks report to their direct parent only. But this MUST be empirically tested.

### Testing Protocol

```
1. Launch a meta-agent (Task A) with run_in_background: true
2. Meta-agent launches a sub-agent (Task B) with run_in_background: true
3. Observe: does the parent session receive notifications about Task B?
4. Check context length before and after
```

### Feasibility

**High confidence this works** if notification bubbling doesn't occur. The implementation is straightforward:
- Write a reusable dispatch-coordinator agent definition
- Write manifest file format
- The dispatcher is simple enough that even a minimal prompt works

**Edge cases**:
- If the dispatcher crashes mid-dispatch, some agents are launched, some aren't. The manifest should track launch status.
- If an individual agent crashes, the dispatcher needs retry logic.
- The dispatcher's own context window is limited. For 26 agents, it accumulates ~30K chars of dispatch overhead. This is fine -- it has no other context needs.

### Verdict: HIGHEST IMPACT. Must test notification bubbling first.

---

## Approach 11: Hybrid Codex + Task Split

### Mechanism

Split agents into two categories and dispatch each through the optimal channel:

| Agent Type | Channel | Why |
|-----------|---------|-----|
| Research agents (5) | Codex CLI | Read-only, file I/O, model-agnostic |
| Review agents needing Claude reasoning | Task tool | Need Claude's specific capabilities |
| Review agents with standard analysis | Codex CLI | Good enough quality, lower cost |
| Oracle (cross-AI) | Bash (oracle CLI) | Already uses Bash |

### Routing Heuristic

```
For each agent in roster:
  if agent.type == "research":
    dispatch via Codex (--tier fast)
  elif agent.type == "review" AND agent.name in [fd-quality, fd-architecture]:
    dispatch via Codex (--tier deep)  # These are more formulaic
  elif agent.type == "review" AND agent.name in [fd-safety, fd-correctness]:
    dispatch via Task tool  # These need Claude's nuanced reasoning
  elif agent.type == "cross-ai":
    dispatch via Bash (oracle CLI)
```

### Context Savings

For a 12-agent dispatch (7 review + 5 research):
- 5 research via Codex: 5 Bash calls = ~1K chars
- 2 review via Codex: 2 Bash calls = ~400 chars
- 3 review via Task: 3 Task calls = ~4K chars (with file indirection)
- 1 Oracle via Bash: 1 Bash call = ~200 chars

Total: ~5.6K chars vs. ~50K chars with all-Task dispatch. **~89% savings.**

### Feasibility

**Works**: All the infrastructure exists. dispatch.sh handles Codex, Task tool handles Claude agents, Bash handles Oracle. The routing logic is the only new code.

**Quality concern**: Codex review agents may miss nuances that Claude catches. Mitigation: route only the most formulaic agents (fd-quality for style checks, research agents for lookups) through Codex. Keep safety-critical agents on Claude.

**Already partially implemented**: flux-drive's `launch-codex.md` phase file already handles clodex-mode dispatch. This approach generalizes it to selective routing.

### Verdict: HIGH IMPACT, LOW-MEDIUM EFFORT. Natural evolution of existing patterns.

---

## Approach 12: Progressive Delegation with Early Termination

### Mechanism

Instead of dispatching all agents upfront, dispatch progressively and terminate early when enough signal is gathered:

```
Round 1: Dispatch 2 most relevant agents (2 Task calls)
         Wait for completion
         If findings are P0/P1: stop, no need for more agents
         If findings are thin: continue to Round 2

Round 2: Dispatch next 2-3 agents (targeting gaps from Round 1)
         Wait for completion
         If coverage is sufficient: stop
         If specific concerns remain: continue

Round 3: Dispatch targeted agents for remaining concerns
```

### Context Savings

Best case (P0 found in Round 1): 2 Task calls = ~2.5K chars (vs. ~50K for all agents)
Average case (3 rounds of 2-3): 7-8 Task calls = ~10K chars
Worst case (all rounds exhaust roster): Same as current approach

### Feasibility

**Works**: This is essentially flux-drive's staged dispatch (Stage 1 + optional Stage 2) taken further. The expansion scoring algorithm already does this with 2 stages.

**Concern**: More rounds = more wall-clock time. Each round includes launch overhead (~30s) + agent execution (~2-3min) + completion polling. Three rounds could take 10+ minutes vs. 5 minutes for all-parallel.

**Optimization**: Pipeline rounds. Start Round 2 before Round 1 fully completes if Round 1 agents show early signals (partial output files).

### Verdict: MODERATE IMPACT. Already partially implemented in flux-drive's staging. Could be pushed further with faster early-termination criteria.

---

## Approach 13: Tmux Orchestrator Pattern

### Mechanism

Use tmux to run agent dispatch in a separate terminal context. A bash script in a tmux pane handles all the Codex dispatch, file coordination, and status reporting. The parent session only needs to:
1. Write the manifest
2. Launch the tmux script
3. Poll for completion

```bash
# Parent session
tmux new-session -d -s flux-dispatch \
  "bash /path/to/flux-orchestrator.sh /tmp/dispatch-manifest.json"

# flux-orchestrator.sh handles:
# - Reading manifest
# - Launching N codex agents in parallel
# - Monitoring progress
# - Writing status to /tmp/dispatch-status.json
# - Writing results when complete
```

### Context Savings

Parent sees: 1 Write (manifest) + 1 Bash (tmux launch) + periodic Bash (status check). ~2K chars total for any number of agents.

### Feasibility

**Works well for Codex dispatch**: The orchestrator script can manage any number of Codex agents with minimal parent interaction.

**Doesn't work for Task tool dispatch**: Can't call the Task tool from bash/tmux. Only for external CLI-based agents (Codex, Oracle).

**Already implemented**: dispatch.sh + JSONL parser + statusline integration already provide the orchestrator functionality. The tmux aspect just isolates it from the parent.

### Verdict: MODERATE IMPACT. Good for Codex-heavy dispatch. Doesn't help with Task-based dispatch.

---

## Approach 14: Compact Dispatch Protocol

### Mechanism

Design a minimal dispatch protocol that reduces per-agent context to the absolute minimum. Key insight: most of the prompt is boilerplate that every agent shares. Factor it out.

### Protocol Design

**Step 1: Write shared context once**
```
Write /tmp/flux-dispatch/shared-context.md:
  - Output format contract
  - Project context
  - Document reference
  - Domain context
```

**Step 2: Write per-agent delta only**
```
Write /tmp/flux-dispatch/fd-architecture.md:
  "Focus: architecture boundaries and coupling
   Score: 5 (core)
   Reason: document describes new service architecture"

Write /tmp/flux-dispatch/fd-safety.md:
  "Focus: security of credential handling
   Score: 3 (tangential)
   Reason: mentions secret management briefly"
```

**Step 3: Dispatch with minimal prompts**
```
Task(fd-architecture):
  "Read /tmp/flux-dispatch/shared-context.md then /tmp/flux-dispatch/fd-architecture.md. Execute."

Task(fd-safety):
  "Read /tmp/flux-dispatch/shared-context.md then /tmp/flux-dispatch/fd-safety.md. Execute."
```

### Context Savings

Per-agent Task prompt drops to ~120 chars. With 26 agents: 26 * 120 = ~3.1K chars for prompts.
Total dispatch overhead: ~3.1K (prompts) + ~10K (tool results) + ~25K (notifications) = ~38K chars.

Without notification reduction: saves ~78K chars from prompt compression alone (~67% savings).
With meta-agent (Approach 10): saves ~115K chars (~99% savings).

### Feasibility

**Works**: The two-file pattern (shared + delta) is clean and agents can read both files. The shared file is written once and reused.

**Risk**: Agents might not correctly merge the two files' instructions. The shared context needs to be self-contained enough that the delta only adds focus directives.

**Enhancement**: The shared context file can include the complete output format contract, making each agent's behavior more predictable even with minimal per-agent prompts.

### Verdict: HIGH IMPACT when combined with Approach 1 or 10. The "shared + delta" pattern is reusable across all dispatch scenarios.

---

## Approach 15: Result File Polling Instead of Task Notifications

### Mechanism

Instead of relying on Claude Code's notification system for agent completion, use file-based signaling. Agents write output to files. The parent polls the output directory.

This is ALREADY implemented in flux-drive (Step 2.3: polling loop). But the key insight is: if we can suppress notifications entirely and rely solely on file polling, we eliminate the notification context cost.

### Current Implementation (flux-drive)

```
# Already exists in launch.md Step 2.3:
Poll {OUTPUT_DIR}/ every 30 seconds:
  Check for .md files (not .md.partial)
  Report completion
```

### Enhancement: Explicit Notification Suppression

If Claude Code adds a `suppress_notifications: true` option to the Task tool:

```
Task(fd-architecture):
  prompt: "..."
  run_in_background: true
  suppress_notifications: true  # Don't send progress/completion to parent
```

The parent then relies entirely on file polling:

```bash
# Check completion
count=$(ls {OUTPUT_DIR}/*.md 2>/dev/null | wc -l)
echo "Completed: $count / $expected"
```

### Context Savings

Eliminating notifications saves ~25K chars for 26 agents.

### Feasibility

**Partially available**: The file polling already works. The notification suppression requires a platform feature.

**Workaround**: If using the meta-agent pattern (Approach 10), the parent never receives notifications from grandchild agents anyway. The meta-agent's single completion notification is the only one that appears.

### Verdict: Already partially implemented. Full impact requires platform support or meta-agent pattern.

---

## Comparative Analysis

| Approach | Context Savings | Effort | Works Today | Needs Platform Changes |
|----------|---------------|--------|-------------|----------------------|
| 1. File indirection | ~70% | Low | Yes | No |
| 2. Meta-agent (basic) | ~98% | Medium | Probably | Need to test notification bubbling |
| 3. Staged chunking | ~40% | Low | Partially | No |
| 4. CLI session spawn | ~95% | Medium | Yes (limited) | No |
| 5. Codex CLI routing | ~95% | Low | Yes (limited) | No |
| 6. Dispatcher sidecar | ~95% | High | Partially | No |
| 7. Notification suppression | ~25% | None | No | Yes |
| 8. File-based job queue | ~95% | Medium | Yes (Codex only) | No |
| 9. Template pre-registration | ~35% | Low | Partially | No |
| 10. Hierarchical dispatch | ~98% | Medium | Probably | Need to test |
| 11. Hybrid Codex + Task | ~89% | Low-Medium | Yes | No |
| 12. Progressive delegation | ~50% avg | Low | Yes | No |
| 13. Tmux orchestrator | ~95% | Low | Yes (Codex only) | No |
| 14. Compact protocol | ~67-99% | Low | Yes | No |
| 15. File polling only | ~25% | None | Partially | Yes (for full benefit) |

---

## Recommended Combinations

### Combination A: Immediate Wins (implement today)

**Approach 1 (File Indirection) + Approach 14 (Compact Protocol) + Approach 9 (Template Pre-Registration)**

- Write shared context to one file, per-agent delta to individual files
- Task prompt becomes: "Read /tmp/shared.md then /tmp/delta-{agent}.md. Execute."
- ~70% context savings, zero platform dependencies
- **Effort: 1-2 hours of refactoring flux-drive's launch.md and review.md**

### Combination B: Maximum Savings (requires testing)

**Approach 10 (Hierarchical Dispatch) + Approach 1 (File Indirection) + Approach 14 (Compact Protocol)**

- Parent dispatches 1 meta-agent
- Meta-agent reads manifest, dispatches N agents from file-based prompts
- Parent's context: ~1.7K chars regardless of agent count
- **~98% savings**
- **Prerequisite: Test notification bubbling behavior**
- **Effort: 4-6 hours (dispatcher agent definition, manifest format, testing)**

### Combination C: Selective Channel Routing

**Approach 11 (Hybrid Codex + Task) + Approach 1 (File Indirection)**

- Research agents and formulaic review agents → Codex CLI
- Nuanced review agents → Task tool with file indirection
- Oracle → Bash (already working)
- **~89% savings**
- **Effort: 2-3 hours (routing logic, Codex prompt adaptation)**

### Combination D: Full Optimization Stack

All of A + B + C:
- File indirection for all prompts (foundational)
- Hierarchical dispatch for Task-based agents (if bubbling test passes)
- Codex routing for research + formulaic review agents
- Progressive delegation for early termination

**~99% savings on dispatch context.**

---

## Implementation Priority

### Phase 1: Foundation (Day 1)

1. **File indirection for all Task prompts** (Approach 1)
   - Refactor flux-drive `phases/launch.md` to write full prompts to files
   - Refactor `commands/review.md` to use file-based prompts
   - Refactor `commands/quality-gates.md` similarly
   - Test: verify agents correctly read and execute from files

2. **Shared + delta file pattern** (Approach 14)
   - Define `/tmp/flux-dispatch-{run-id}/shared-context.md` format
   - Define per-agent delta format
   - Update launch.md prompt template

### Phase 2: Multiplier (Day 2-3)

3. **Test notification bubbling** (prerequisite for Approach 10)
   - Write a minimal test: parent → meta-agent → grandchild
   - Measure parent context before/after
   - Document findings

4. **If bubbling doesn't occur: Implement hierarchical dispatch** (Approach 10)
   - Write `agents/workflow/dispatch-coordinator.md`
   - Define manifest JSON format
   - Integrate with flux-drive, review.md, quality-gates.md

5. **If bubbling does occur: Implement hybrid routing** (Approach 11)
   - Define routing heuristic (which agents → Codex, which → Task)
   - Adapt Codex prompts for review agents
   - Quality validation: compare Codex vs. Task output quality

### Phase 3: Optimization (Day 4+)

6. **Progressive delegation refinement** (Approach 12)
   - Earlier termination criteria
   - Round pipelining

7. **Platform advocacy** (Approach 7)
   - File feature request for notification suppression
   - File feature request for compact notification format

---

## Open Questions

1. **Notification bubbling behavior**: Do grandchild agent notifications appear in the grandparent's context? This is the single most important unknown. Must be tested empirically.

2. **Codex review quality**: How do Codex-dispatched review agents compare to Claude Task-dispatched ones? A side-by-side comparison on 3-5 real reviews would quantify the quality tradeoff.

3. **Context window management internals**: Does Claude Code ever prune old tool interactions from context? Understanding the actual context management strategy would inform whether Approach 3 (staged chunking) has any value.

4. **Subagent_type in CLI sessions**: If `claude -p --agent-type fd-architecture` were supported, Approach 4 would become much more viable. Worth checking the latest Claude Code CLI docs.

5. **Token cost model**: Each approach has different API cost implications. Hierarchical dispatch adds one extra agent (the dispatcher). Codex routing uses cheaper Codex models. File indirection adds Read tool calls in agents. Need cost modeling.

6. **Wall-clock time tradeoffs**: Some approaches (progressive delegation, staged chunking) trade context savings for longer execution time. Need to quantify: is context or time the binding constraint?

---

## Conclusion

The single highest-impact change is **file indirection** (Approach 1): write prompts to files, reduce Task calls to one-liners. This is safe, backwards-compatible, and saves ~70% of dispatch context.

The game-changer is **hierarchical dispatch** (Approach 10): a dispatcher subagent that handles all N dispatches internally. If notification bubbling doesn't occur (likely), this reduces parent context to a constant ~1.7K regardless of agent count. Combined with file indirection, the total savings approach 99%.

For immediate practical use, **hybrid Codex + Task routing** (Approach 11) is the most pragmatic approach. It requires no platform changes, uses existing infrastructure, and achieves ~89% savings by routing read-only agents through Codex.

The recommended path: implement file indirection now, test hierarchical dispatch this week, and implement hybrid routing as the production-ready fallback.
