---
module: System
date: 2026-02-11
problem_type: best_practice
component: tooling
symptoms:
  - "Simplifying clodex SKILL.md could accidentally break flux-drive review agent dispatch"
  - "Template section-header format (GOAL:, EXPLORE_TARGETS:) appears in two independent consumers"
  - "grep for --template shows matches in both skills/clodex/ and skills/flux-drive/phases/"
root_cause: missing_workflow_step
resolution_type: workflow_improvement
severity: medium
tags: [clodex, flux-drive, templates, dispatch, refactoring-safety]
---

# Best Practice: Template System Has Multiple Independent Consumers

## Problem
When simplifying the clodex SKILL.md to drop template indirection (replacing structured section headers with plain-language prompts), it was tempting to treat the template system as a single-consumer feature. In reality, `dispatch.sh`'s template substitution is consumed by two independent skill paths with different needs.

## Environment
- Module: System (cross-skill infrastructure)
- Affected Component: `scripts/dispatch.sh`, `skills/clodex/SKILL.md`, `skills/flux-drive/phases/launch-codex.md`
- Date: 2026-02-11

## Symptoms
- `skills/clodex/SKILL.md` uses `--template megaprompt.md` with section headers (GOAL:, EXPLORE_TARGETS:, IMPLEMENT:, BUILD_CMD:, TEST_CMD:)
- `skills/flux-drive/phases/launch-codex.md` uses `--template review-agent.md` with different section headers (PROJECT:, AGENT_IDENTITY:, REVIEW_PROMPT:, AGENT_NAME:, TIER:, OUTPUT_FILE:)
- Both pass through the same `dispatch.sh` `^[A-Z_]+:$` section parser
- A naive "remove template support" refactor would break flux-drive

## What Didn't Work

**Direct solution:** The problem was identified during investigation and avoided on the first attempt by grepping for all `--template` and `--inject-docs` references across the codebase before making changes.

## Solution

**Scope the simplification to the consumer, not the infrastructure:**

1. **Changed**: `skills/clodex/SKILL.md` — dropped `--template` and `--inject-docs` from dispatch examples; replaced structured section-header format with plain-language prompts
2. **NOT changed**: `scripts/dispatch.sh` — template substitution machinery preserved for backwards compatibility
3. **NOT changed**: `skills/flux-drive/phases/launch-codex.md` — legitimately needs structured templates for review agent identity injection, tier classification, and output routing
4. **NOT changed**: `templates/megaprompt.md`, `templates/parallel-task.md`, `templates/review-agent.md`, `templates/create-review-agent.md` — all preserved

**Key grep to run before any template system changes:**
```bash
grep -r '--template\|--inject-docs\|GOAL:\|EXPLORE_TARGETS:\|PROJECT:\|AGENT_IDENTITY:' skills/ commands/ --include='*.md'
```

## Why This Works

The template system in `dispatch.sh` serves two fundamentally different use cases:

1. **General-purpose dispatch (clodex)**: Claude writes the entire prompt. Templates add unnecessary indirection — Codex is capable enough to work from plain language with goal, files, and build/test commands. The megaprompt template's Explore/Implement/Verify phases duplicate what Codex does naturally.

2. **Review agent dispatch (flux-drive)**: The template is essential. Each review agent needs its identity prompt injected (`AGENT_IDENTITY:`), its tier classified (`TIER:`), and its output routed (`OUTPUT_FILE:`). The structured format ensures consistent agent bootstrapping across 6+ concurrent review agents.

By scoping changes to the clodex consumer only, we simplified the common path without breaking the specialized path.

## Prevention

- **Before simplifying shared infrastructure**: Always grep for all consumers, not just the one you're working on
- **Template files are dependencies**: Treat them like APIs — check callers before modifying or deprecating
- **The "two consumer" pattern recurs**: `dispatch.sh` flags like `--inject-docs` and `-s workspace-write` are also used differently by clodex vs flux-drive. Same awareness applies to future changes.

## Related Issues

- See also: [unify-content-assembly-before-adding-variants-20260211.md](./unify-content-assembly-before-adding-variants-20260211.md) — similar theme of understanding shared infrastructure before modifying
