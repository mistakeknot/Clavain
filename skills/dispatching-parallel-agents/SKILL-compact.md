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
5. Relay work uses `"${CLAVAIN_SELECTED_ROOT:?}/scripts/dispatch.sh" --role coordination`. A new coordinator thread's own seat comes from `"${CLAVAIN_SELECTED_ROOT:?}/scripts/route-spawn.sh" --role coordinator-seat --project <slug>`. A running session cannot change its own model. Planning and review keep their roles.
6. Broad searches and log dumps run in a subagent, so your context carries only the conclusion.
7. Keep reports and messages terse: output costs five times input.
8. Resolve bb lanes first: `if read -r P M E < <("${CLAVAIN_SELECTED_ROOT:?}/scripts/route-spawn.sh" --role lane --lineage "$coordinator_id" --project "$project_slug"); then bb thread spawn --provider "$P" --model "$M" --reasoning-level "$E" …; else echo "Lane routing failed; no thread spawned" >&2; fi`. Frontier lanes use `--role frontier-planning`, or `plan-review` / `validation` with `--producer-identity` from the producer's receipt.
9. Until Quilan carry-forward ships, pinned self-handoffs use `bb handoff --provider "$current_provider" --model "$current_model" --reasoning-level "$current_effort" …`. Set those variables from the coordinator's own route-spawn receipt: `.spawn.provider`, `.spawn.model`, and `.spawn.reasoning_level`, respectively. Never type model literals on spawn or handoff lines.
10. Campaign sessions (`CLAVAIN_POLICY_PROFILE` nonempty and not `default`) must supply campaign-scoped context; `CLAVAIN_DECISION_CONTEXT` is inherited unless `--context-file` overrides it. Governed roles skip the pool probe and retain dispatch-time capacity handling. A stderr `fallback` line naming the head and chosen seat means the spawn used a fallback seat.

With Claude exhausted, lane, main-session and coordinator-seat fall back to gpt-6-astra medium, never gpt-5.6-sol (mk 2026-09-27); with no eligible seat, route-spawn exits 3: report it and do not spawn. A family counts as exhausted by bb's own rule (the pool `switchThreshold`) only when every up Claude account has an active family window.

Measure with `scripts/burn-report.py --since <ISO time>`: weighted burn by thread lineage, model, hour and context size, plus the 5-hour pace.

## Cross-AI Variant

For implementation-focused tasks (not exploratory), consider Codex agents via `clavain:interserve` — true parallel execution in separate sandboxes, preserves Claude's context for review.

---

*For real-world examples and detailed anti-patterns, read SKILL.md.*
