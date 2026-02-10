---
module: Smoke Tests
date: 2026-02-10
problem_type: best_practice
component: testing_framework
symptoms:
  - "6 of 8 smoke test agents noted contradictory instructions instead of providing the requested review"
  - "Agents asked for clarification about MANDATORY FIRST STEP vs 'Do NOT write files' conflict"
  - "Language reviewer agents (go, shell, security-sentinel) used Read/Write tools despite 'no tools' instruction"
root_cause: config_error
resolution_type: workflow_improvement
severity: medium
tags: [smoke-test, subagent, instruction-conflict, task-tool, mandatory-first-step]
---

# Best Practice: Smoke Test Agent Prompts Must Override the Task Tool Write-First Wrapper

## Problem

When dispatching agents via the Task tool for smoke testing, agents receive a "MANDATORY FIRST STEP" preamble (injected by the Task tool framework) that instructs them to write their full analysis to a file before responding. This conflicts with smoke test instructions that say "Do NOT use any tools. Do NOT write files." — causing 6 of 8 agents to note the contradiction and some to attempt tool use anyway.

## Environment
- Module: Smoke Tests (tests/smoke/)
- Framework Version: Claude Code 2.1.38
- Affected Component: Task tool subagent dispatch
- Date: 2026-02-10

## Symptoms
- 6 of 8 agents flagged the instruction contradiction in their responses
- Architecture-strategist, best-practices-researcher, spec-flow-analyzer, and python-reviewer asked for clarification instead of reviewing
- Security-sentinel read CLAUDE.md and AGENTS.md before reviewing (4 tool uses, 22s vs 4s for text-only agents)
- Go-reviewer and shell-reviewer attempted Write (denied), then provided the review
- TypeScript-reviewer resolved the conflict itself and provided the review directly

## What Didn't Work

**Direct solution:** The problem was identified on the first smoke test run and the behavioral pattern documented.

## Solution

The smoke test prompt prefix must be strong enough to override the write-first wrapper. The current prefix works but causes friction:

```
# Current prefix (works but 6/8 agents note the conflict):
SMOKE TEST — respond with a brief review only. Do NOT use any tools.
Do NOT use MCP tools. Do NOT write files. Just respond with text.
```

**Observed behavioral variance by agent category:**

| Category | Agents | Tool Use | Avg Duration |
|----------|--------|----------|-------------|
| Language reviewers | go, typescript, shell | 0-1 tools (Read/Write attempts) | 6-16s |
| Domain reviewers | architecture, security | 0-4 tools (security read project docs) | 4-22s |
| Research agents | best-practices | 0 tools | 4s |
| Workflow agents | spec-flow | 0 tools | 4s |

**Key findings:**
- All 8 agents produced valid output (PASS) — the conflict doesn't cause failures
- Language reviewers have stronger "read codebase" instincts in their prompts
- Security-sentinel is the most tool-hungry — it reads CLAUDE.md and AGENTS.md before any review
- Research and workflow agents are the most prompt-compliant

**Pass criteria that works despite the conflict:**
- Agent completed (no error/timeout)
- Output is non-empty (> 50 chars)
- Output doesn't contain error stack traces
- Output contains domain-relevant review content

## Why This Works

The Task tool injects a "MANDATORY FIRST STEP" preamble telling agents to write output to a file. This is a framework-level instruction, not something the smoke test prompt controls. The smoke test "Do NOT write files" instruction creates a genuine conflict that agents must resolve.

Most agents resolve it correctly (text-only response), but some — especially those with strong tool-use instincts in their agent prompts (security-sentinel, go-reviewer) — attempt tools first and fall back to text when denied. This is acceptable behavior for a smoke test because:

1. The goal is to verify agents **load and respond coherently**, not test tool-use compliance
2. Write permission is denied in subagent context anyway, so artifact files aren't created
3. The review quality from tool-using agents (security-sentinel) is actually higher

## Prevention

- **Accept the conflict as a known pattern** — don't try to suppress the MANDATORY FIRST STEP wrapper
- **Grade on output quality, not tool compliance** — smoke tests validate agent loading, not instruction following
- **Budget extra time for security-sentinel** — it consistently takes 3-5x longer due to project doc reads
- **Clean up artifact files** after smoke runs: `rm -f docs/research/smoke-test-*.md` (in case Write succeeds in other contexts)
- **Use `model: haiku` and `max_turns: 3`** to keep smoke tests fast and cheap

## Related Issues

No related issues documented yet.
