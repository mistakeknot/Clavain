---
name: dispatching-parallel-agents
description: Use for 2+ independent tasks with no shared state or sequential dependency.
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

Every spawn names a model — execution `model: sonnet`, validation `model: opus`, frontier-in-the-loop `model: inherit` (routing doctrine, commands/model-routing.md). Unpinned spawns inherit the session model.

```typescript
Task("Fix agent-tool-abort.test.ts failures", model="sonnet")
Task("Fix batch-completion-behavior.test.ts failures", model="sonnet")
Task("Fix tool-approval-race-conditions.test.ts failures", model="sonnet")
// All three run concurrently
```

Multiple dispatch calls in one response run in parallel; one per response runs sequentially. Give each agent precisely the context it needs, never your session history.

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

## Coordinator Burn Discipline

Applies while you coordinate threads or workers (mk ruling 2026-09-25, mk-42j9.5). Cost scales with context size times calls: over half of measured Claude burn was cache reads, and most of it came from calls carrying more than 100k context.

1. Hand off or compact at 80-100k context, for yourself and for workers. Do not run to the ~165k limit.
2. Workers report only DONE or BLOCKED. Wait on a thread instead of checking in; answer batched reports in one reply.
3. Waits and wakeups stay under 270s or go to 1200s or more. A ~300s wait expires the 5-minute cache and rewrites it in full.
4. Run at most 2-3 concurrent workers per coordinator; stagger the rest.
5. Relaying, waiting and status work runs on Sonnet: dispatch it with `"${CLAVAIN_SELECTED_ROOT:?}/scripts/dispatch.sh" --role coordination`, or hand the relay stage to a Sonnet thread. Spawn a new coordinator thread on its own seat and pass the seat in its spawn prompt: `seat="$(mktemp)"; if read -r P M E < <("${CLAVAIN_SELECTED_ROOT:?}/scripts/route-spawn.sh" --role coordinator-seat --project "$project_slug" --seat-out "$seat"); then bb thread spawn --provider "$P" --model "$M" --reasoning-level "$E" … (include "Seat: $(cat "$seat")" in the spawn prompt); else echo "Coordinator routing failed; no thread spawned" >&2; fi`. A running session cannot change its own model. Planning and review keep their roles.
6. Broad searches and log dumps run in a subagent, so your context carries only the conclusion.
7. Keep reports and messages terse: output costs five times input.
8. Resolve a bb worker lane before spawning: `if read -r P M E < <("${CLAVAIN_SELECTED_ROOT:?}/scripts/route-spawn.sh" --role lane --lineage "$coordinator_id" --project "$project_slug"); then bb thread spawn --provider "$P" --model "$M" --reasoning-level "$E" …; else echo "Lane routing failed; no thread spawned" >&2; fi`. The resolver prints nothing on a non-zero exit. Frontier lanes use `--role frontier-planning`, or `plan-review` / `validation` with `--producer-identity` from the producer's receipt.
9. Until Quilan carry-forward ships, a pinned coordinator's self-handoff passes its own current tuple: `bb handoff --provider "$current_provider" --model "$current_model" --reasoning-level "$current_effort" …`. Set these variables from the Seat block in your own spawn prompt: `.provider`, `.model`, and `.reasoning_level`, respectively. A coordinator spawned before `--seat-out` has no Seat block: report it and do not guess. Never type model literals on spawn or handoff lines.
10. Campaign sessions (`CLAVAIN_POLICY_PROFILE` set to a nonempty value other than `default`) must supply campaign-scoped context. `CLAVAIN_DECISION_CONTEXT` is inherited unless `--context-file` overrides it. Governed roles do not probe the pool; capacity handling stays in dispatch. A stderr `fallback` line naming the head and chosen seat means the spawn used a fallback seat.

With Claude exhausted, lane, main-session and coordinator-seat fall back to gpt-6-astra medium. route-spawn refuses gpt-5.6-sol for every role (mk 2026-09-27); GPT-6 Sol is allowed. With no eligible seat, route-spawn exits 3: report it and do not spawn. A family counts as exhausted by bb's own rule (the pool `switchThreshold`) only when every up Claude account has an active family window.

Measure with `scripts/burn-report.py --since <ISO time>`: weighted burn by thread lineage, model, hour and context size, plus the 5-hour pace.

## Cross-AI Variant: Codex Agents

**Use Codex (via `clavain:interserve`):** Well-scoped tasks with clear file lists, true parallel sandboxes, cost/context optimization.
**Keep Claude:** Deep cross-file understanding, exploratory investigation, architectural decisions.

## Orchestration Patterns

### Parallel Specialists
Independent tasks, distinct domains, no shared files. All dispatched in one message.
```
Task("Review authentication module", model="sonnet")   ─┐
Task("Review database migrations", model="sonnet")     ─┤── all in one message
Task("Review API error handling", model="sonnet")      ─┘
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
Task("Review from security perspective", model="sonnet")     ─┐
Task("Review from performance perspective", model="sonnet")  ─┤── fan-out
Task("Review from UX perspective", model="sonnet")           ─┘
                     │
              Synthesize findings              ── fan-in
```
Used by `/flux-drive` and `/quality-gates`.
