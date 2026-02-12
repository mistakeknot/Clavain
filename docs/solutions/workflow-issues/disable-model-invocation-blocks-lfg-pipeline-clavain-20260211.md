---
module: Clavain
date: 2026-02-11
problem_type: workflow_issue
component: tooling
symptoms:
  - "/lfg Step 1 fails with 'Skill brainstorm cannot be used with Skill tool due to disable-model-invocation'"
  - "All /lfg sub-steps (/brainstorm, /strategy, /write-plan, /work, /resolve) fail the same way"
  - "No command-to-command chaining works in any orchestrator command"
root_cause: missing_workflow_step
resolution_type: config_change
severity: high
tags: [claude-code-plugin, disable-model-invocation, command-chaining, lfg, orchestration, clavain]
---

# Troubleshooting: disable-model-invocation Blocks All Command Chaining in /lfg Pipeline

## Problem
The `/clavain:lfg` orchestrator command chains 9 sub-commands (`/brainstorm`, `/strategy`, `/write-plan`, `/flux-drive`, `/work`, `/quality-gates`, `/resolve`, plus skills). Every sub-command had `disable-model-invocation: true` in its frontmatter, causing all programmatic `Skill` tool calls to fail. The entire autonomous pipeline was broken.

## Environment
- Module: Clavain plugin (Claude Code)
- Plugin Version: 0.4.38
- Affected Component: All 25 commands and 9 skills in Clavain
- Date: 2026-02-11

## Symptoms
- `/lfg` Step 1 immediately fails: `Error: Skill brainstorm cannot be used with Skill tool due to disable-model-invocation`
- Every command in the pipeline has the same flag, so no step can chain into another
- User-invoked `/lfg` loads fine (it's a command), but it can't invoke any sub-commands programmatically

## What Didn't Work

**Attempted Solution 1:** Invoking as `clavain:brainstorm` vs `brainstorm`
- **Why it failed:** The flag blocks ALL Skill tool invocations regardless of how the name is qualified

**Attempted Solution 2:** Checking if a separate `brainstorm` skill exists (vs the `brainstorming` skill)
- **Why it failed:** There's both a command (`commands/brainstorm.md`) and a skill (`skills/brainstorming/SKILL.md`), but both had the flag set

## Solution

Removed `disable-model-invocation: true` from all 25 commands and 9 skills in Clavain. The flag was applied as a blanket default during initial plugin creation but was never evaluated per-command.

**Before (broken):** Every command frontmatter included:
```yaml
---
name: brainstorm
description: ...
disable-model-invocation: true
---
```

**After (fixed):** Flag removed entirely (defaults to `false`):
```yaml
---
name: brainstorm
description: ...
---
```

**Commands run:**
```bash
# One-liner to remove from all files
for f in $(grep -rl 'disable-model-invocation: true' commands/ skills/); do
  sed -i '/^disable-model-invocation: true$/d' "$f"
done

# Restore documentation files that had the flag in code examples
git checkout -- skills/create-agent-skills/SKILL.md
```

34 files changed, 34 deletions.

## Why This Works

1. **Root cause:** `disable-model-invocation: true` was applied as a blanket policy to all Clavain commands during initial creation, without considering that orchestrator commands (`/lfg`) need to chain sub-commands via the `Skill` tool. The flag prevents Claude's model from invoking a command — only direct user input (typing `/command`) works.

2. **Why removal is safe:** The flag was a defense against unwanted autonomous invocation (e.g., Claude deciding to deploy your code). But Clavain's commands are all development workflow tools (brainstorm, plan, review) — not destructive operations. The commands themselves have built-in user interaction gates (AskUserQuestion) where human input is needed.

3. **Orchestration pattern:** `/lfg` is user-invoked, but once running, it delegates to sub-commands via `Skill` tool calls. This is the standard Claude Code pattern for multi-step workflows. The flag breaks this pattern by treating every sub-invocation as an unauthorized autonomous action.

## Prevention

- **Evaluate per-command, not blanket:** Only use `disable-model-invocation: true` for commands with real side effects (deploy, send message, delete data). Development workflow commands should default to `false`.
- **Test command chaining after creating orchestrator commands:** If command A calls command B via Skill tool, verify B is model-invocable.
- **The flag still exists as a feature** — documented in `create-agent-skills` skill references for plugin authors who need it for destructive operations.

## Related Issues

- See also: [disable-model-invocation-blocks-skill-tool-clavain-20260211.md](./disable-model-invocation-blocks-skill-tool-clavain-20260211.md) — earlier instance where only `/compound` was affected; fixed by setting to `false` for that single command. This broader fix supersedes the per-command approach.
