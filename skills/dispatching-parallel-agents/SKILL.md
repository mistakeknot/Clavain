---
name: dispatching-parallel-agents
description: Use when facing 2+ independent tasks that can be worked on without shared state or sequential dependencies
---

<!-- compact: SKILL-compact.md — if it exists in this directory, load it instead of following the full instructions below. The compact version contains the same parallel dispatch pattern and orchestration patterns. -->

# Dispatching Parallel Agents

**Core principle:** One agent per independent problem domain. Let them work concurrently.

## When to Use / Not Use

**Use:** 3+ failures/tasks with different root causes, no shared state, each problem self-contained.
**Skip:** Failures are related (fix one might fix others), agents would edit same files, you don't know what's broken yet.

## The Pattern

### 1. Identify Independent Domains
Group by what's broken. E.g.: File A = tool approval flow, File B = batch completion, File C = abort. Each is independent.

### 2. Focused Agent Tasks
Each agent gets: specific scope, clear goal, constraints (don't touch other code), expected output format.

### 3. Dispatch in Parallel
```typescript
Task("Fix agent-tool-abort.test.ts failures")
Task("Fix batch-completion-behavior.test.ts failures")
Task("Fix tool-approval-race-conditions.test.ts failures")
// All three run concurrently
```

### 4. Review and Integrate
Read each summary → verify fixes don't conflict → run full test suite.

## Agent Prompt Structure

```markdown
Fix the 3 failing tests in src/agents/agent-tool-abort.test.ts:

1. "should abort tool with partial output capture" - expects 'interrupted at' in message
2. "should handle mixed completed and aborted tools" - fast tool aborted instead of completed
3. "should properly track pendingToolCount" - expects 3 results but gets 0

These are timing/race condition issues. Your task:
1. Read the test file and understand what each test verifies
2. Identify root cause - timing issues or actual bugs?
3. Fix (replace arbitrary timeouts with event-based waiting, fix bugs, adjust expectations)

Do NOT just increase timeouts.
Return: Summary of what you found and what you fixed.
```

## Prompt Mistakes

- **Too broad:** "Fix all the tests" → agent gets lost. Use: "Fix agent-tool-abort.test.ts"
- **No context:** "Fix the race condition" → agent doesn't know where. Paste error messages.
- **No constraints:** Agent might refactor everything. Add: "Do NOT change production code"
- **Vague output:** "Fix it" → you don't know what changed. Use: "Return summary of root cause and changes"

## Verification

After agents return: review each summary → check for same-file conflicts → run full suite → spot check for systematic errors.

## Cross-AI Variant: Codex Agents

**Use Codex (via `clavain:interserve`):** Well-scoped tasks with clear file lists, true parallel sandboxes, cost/context optimization.
**Keep Claude:** Deep cross-file understanding, exploratory investigation, architectural decisions.

## Orchestration Patterns

### Parallel Specialists
Independent tasks, distinct domains, no shared files. All dispatched in one message.
```
Task("Review authentication module")   ─┐
Task("Review database migrations")     ─┤── all in one message
Task("Review API error handling")      ─┘
```
Use when plan has 3+ independent modules.

### Pipeline
Sequential handoff — agent N's output feeds agent N+1.
```
Agent 1: Research & design    → design.md
Agent 2: Implement from design.md → code changes
Agent 3: Write tests for code changes → test files
```
Use when tasks have strict data dependencies.

### Fan-out / Fan-in
N agents, same question, different perspectives → synthesize.
```
Task("Review from security perspective")     ─┐
Task("Review from performance perspective")  ─┤── fan-out
Task("Review from UX perspective")           ─┘
                     │
              Synthesize findings              ── fan-in
```
Used by `/flux-drive` and `/quality-gates`.
