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

Every spawn names a model — execution `model: sonnet`, validation `model: opus`, frontier-in-the-loop `model: inherit` (routing doctrine, commands/model-routing.md). Unpinned spawns inherit the session model.

Launch all Task calls in a single message:
```
Task("Fix agent-tool-abort.test.ts failures", model="sonnet")
Task("Fix batch-completion-behavior.test.ts failures", model="sonnet")
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

## Coordinator Burn Discipline

Applies while you coordinate threads or workers (mk ruling 2026-09-25, mk-42j9.5). Cost scales with context size times calls: over half of measured Claude burn was cache reads, and most of it came from calls carrying more than 100k context.

1. Hand off or compact at 80-100k context, for yourself and for workers. Do not run to the ~165k limit.
2. Workers report only DONE or BLOCKED. Wait on a thread instead of checking in; answer batched reports in one reply.
3. Waits and wakeups stay under 270s or go to 1200s or more. A ~300s wait expires the 5-minute cache and rewrites it in full.
4. Run at most 2-3 concurrent workers per coordinator; stagger the rest.
5. Relaying, waiting and status turns use the `coordination` role (Sonnet); planning and review keep their roles.
6. Broad searches and log dumps run in a subagent, so your context carries only the conclusion.
7. Keep reports and messages terse: output costs five times input.

Measure with `scripts/burn-report.py --since <ISO time>`: weighted burn by thread lineage, model, hour and context size, plus the 5-hour pace.

## Cross-AI Variant

For implementation-focused tasks (not exploratory), consider Codex agents via `clavain:interserve` — true parallel execution in separate sandboxes, preserves Claude's context for review.

---

*For real-world examples and detailed anti-patterns, read SKILL.md.*
