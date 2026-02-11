# Plan: Extract swarm patterns into /lfg (Clavain-fg41)

## Goal
Add optional parallel execution to `/lfg` for independent plan steps, using patterns from upstream's orchestrating-swarms skill.

## Context
- Upstream has 1.7K-line orchestrating-swarms skill — too large to port wholesale
- Key insight: most /lfg steps are strictly sequential (brainstorm→strategy→plan→execute)
- Parallelization opportunity: within Step 5 (execute work) when plan has independent modules, and Steps 6-7 (test + quality-gates can overlap)
- Clavain already uses parallel agents in quality-gates and resolve

## Steps

### Step 1: Update `skills/dispatching-parallel-agents/SKILL.md`
Add a "Swarm Patterns" reference section with 3 extracted patterns:
- **Parallel Specialists** — independent plan steps run concurrently (Task tool, multiple calls in one message)
- **Pipeline** — sequential with handoff (agent N output → agent N+1 input)
- **Fan-out/Fan-in** — dispatch N agents, collect all results, synthesize

Keep it concise (not 1.7K lines). These patterns are natively supported by Claude Code's Task tool.

### Step 2: Update `commands/lfg.md`
Add note at Step 5 (execute): "When plan has independent modules, dispatch them in parallel using the `dispatching-parallel-agents` skill."

Add note at Steps 7-8 (quality-gates + resolve): "These can run in parallel — quality-gates spawns review agents while resolve addresses known findings."

### Step 3: Run tests and commit
Commit message: `docs: add swarm orchestration patterns to dispatching-parallel-agents`

## Verification
- No code changes, just skill/command documentation updates
- dispatching-parallel-agents SKILL.md should reference the 3 patterns
- /lfg should mention parallel execution at appropriate steps
