# Dispatching Parallel Agents (compact)

Dispatch one agent per independent problem domain. Let them work concurrently.

## When to Use

2+ independent failures/tasks with no shared state. Don't use for related failures, exploratory debugging, or shared-file editing.

## Pattern

### 1. Identify Independent Domains

Group by what's broken — each domain must be independent (fixing one doesn't affect others).

### 2. Create Focused Agent Tasks

Each agent gets: specific scope (one file/subsystem), clear goal, constraints ("don't change other code"), expected output format.

### 3. Dispatch in Parallel

Launch all Task calls in a single message:
```
Task("Fix agent-tool-abort.test.ts failures")
Task("Fix batch-completion-behavior.test.ts failures")
```

### 4. Review and Integrate

Read each summary → verify no conflicts → run full test suite → integrate.

## Agent Prompt Rules

- **Focused:** One test file or subsystem, not "fix all tests"
- **Context:** Include error messages and test names
- **Constrained:** Specify what NOT to change
- **Output:** Request summary of root cause and changes

## Orchestration Patterns

| Pattern | When | How |
|---------|------|-----|
| **Parallel Specialists** | 3+ independent modules | One Task per domain, all in one message |
| **Pipeline** | Strict data dependencies | Agent N output feeds agent N+1 |
| **Fan-out/Fan-in** | Diverse analysis needed | N agents same question, different perspectives, then synthesize |

## Cross-AI Variant

For implementation-focused tasks (not exploratory), consider Codex agents via `clavain:interserve` — true parallel execution in separate sandboxes, preserves Claude's context for review.

---

*For real-world examples and detailed anti-patterns, read SKILL.md.*
