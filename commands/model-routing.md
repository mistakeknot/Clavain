---
name: model-routing
description: Toggle subagent model routing between economy (smart defaults) and quality (all Opus) mode
argument-hint: "[economy|quality|status]"
disable-model-invocation: true
---

# Model Routing

Toggle how subagents pick their model tier.

## Current Mode

<routing_arg> #$ARGUMENTS </routing_arg>

### `status` (or no argument)

Report the current routing by reading all agent frontmatter:

```bash
grep -r '^model:' agents/{review,research,workflow}/*.md
```

Summarize as:

```
Model Routing Status:
  Research (5): [model] — best-practices, framework-docs, git-history, learnings, repo-research
  Review (9):   [model] — fd-architecture, fd-safety, fd-correctness, fd-quality, fd-user-product, fd-performance, plan-reviewer, agent-native, data-migration
  Workflow (2):  [model] — bug-reproduction, pr-comment-resolver

Mode: [economy|quality|mixed]
```

### `economy` (default)

Set smart defaults optimized for cost:

| Category | Model | Rationale |
|----------|-------|-----------|
| Research (5) | `haiku` | Grep, read, summarize — doesn't need reasoning |
| Review (9) | `sonnet` | Structured analysis with good judgment |
| Workflow (2) | `sonnet` | Code changes need reliable execution |

Apply by editing each agent's frontmatter `model:` line:

```bash
# Research → haiku
sed -i 's/^model: .*$/model: haiku/' agents/research/*.md

# Review + Workflow → sonnet
sed -i 's/^model: .*$/model: sonnet/' agents/review/*.md agents/workflow/*.md
```

### `quality`

Maximum quality — all agents use the parent session's model (typically Opus):

```bash
sed -i 's/^model: .*$/model: inherit/' agents/{review,research,workflow}/*.md
```

**Use when:** Critical reviews, production deployments, complex architectural decisions where you want maximum reasoning on every agent.

## Important

- Changes take effect immediately for new agent dispatches in this session
- Does not affect agents already running
- Economy mode saves ~5x on research and ~3x on review vs. quality mode
- Individual agents can still be overridden with `model: <tier>` in the Task tool call
