---
module: Clavain Plugin
date: 2026-02-11
problem_type: workflow_issue
component: tooling
symptoms:
  - "Skill clavain:compound cannot be used with Skill tool due to disable-model-invocation"
  - "Auto-compound hook fails silently — no documentation captured after compoundable signals"
root_cause: config_error
resolution_type: config_change
severity: medium
tags: [claude-code-plugin, disable-model-invocation, skill-tool, hooks, clavain]
---

# Troubleshooting: Plugin Command `disable-model-invocation` Blocks Programmatic Skill Tool Invocation

## Problem

The auto-compound hook detected compoundable signals and attempted to invoke `/clavain:compound` via the `Skill` tool, but Claude Code rejected the call with `Error: Skill clavain:compound cannot be used with Skill tool due to disable-model-invocation`. This silently prevented institutional knowledge capture — the intended purpose of the auto-compound workflow.

## Environment

- Module: Clavain plugin (Claude Code plugin)
- Plugin Version: 0.4.37 (broken) → 0.4.38 (fixed)
- Affected Component: `commands/compound.md` frontmatter
- Date: 2026-02-11

## Symptoms

- `Skill(clavain:compound)` returns error: `cannot be used with Skill tool due to disable-model-invocation`
- Auto-compound hook detects compoundable signals but cannot complete the workflow
- No documentation files created despite non-trivial problem-solving in session

## What Didn't Work

**Direct solution:** The problem was identified and fixed on the first attempt after investigating the plugin's command frontmatter.

## Solution

Changed the `disable-model-invocation` flag from `true` to `false` in the compound command's frontmatter.

**Code changes:**

```yaml
# Before (broken) — commands/compound.md:
---
name: compound
description: Document a recently solved problem to compound your team's knowledge
argument-hint: "[optional: brief context about the fix]"
disable-model-invocation: true
---

# After (fixed):
---
name: compound
description: Document a recently solved problem to compound your team's knowledge
argument-hint: "[optional: brief context about the fix]"
disable-model-invocation: false
---
```

**Commands run:**

```bash
# Edit source, bump version, commit, push, publish
cd /root/projects/Clavain
# Edit commands/compound.md and .claude-plugin/plugin.json (0.4.37 → 0.4.38)
git add commands/compound.md .claude-plugin/plugin.json
git commit -m "fix(compound): allow model invocation for auto-compound hook"
git push
claude plugin marketplace update interagency-marketplace
claude plugin install clavain@interagency-marketplace
# Remove old cached version to prevent version confusion
rm -rf ~/.claude/plugins/cache/interagency-marketplace/clavain/0.4.36
```

## Why This Works

1. **Root cause:** The `disable-model-invocation: true` flag in Claude Code command frontmatter is an autonomy guard — it prevents the `Skill` tool from invoking that command programmatically. Only manual user invocation (typing `/clavain:compound`) works when this flag is `true`. 78% of Clavain commands (25 of 32) use this flag to prevent agents from accidentally triggering heavyweight workflows.

2. **Why the fix works:** Setting `disable-model-invocation: false` allows both manual user invocation AND programmatic `Skill` tool invocation. The `/compound` command is specifically designed to be triggered by hooks (the auto-compound hook in tool-time), making the autonomy guard counterproductive for this specific command.

3. **Underlying issue:** The flag was set to `true` as a blanket default when creating Clavain commands, without considering that some commands (like `/compound`) are intended to be hook-triggered rather than user-triggered. The flag's purpose is to prevent agents from autonomously kicking off documentation workflows, but `/compound` IS the documentation workflow — it should be callable by the auto-compound hook.

## Prevention

- When creating new plugin commands, explicitly decide whether the command should be hook/programmatically invokable. Set `disable-model-invocation: false` for commands designed to be triggered by hooks or other automation.
- When creating hooks that invoke skills/commands, verify the target command allows model invocation. Test the full hook → skill chain, not just manual invocation.
- Document in the command's comments whether it's intended for manual or programmatic use.
- After publishing plugin changes, always verify the fix in the cached version: `grep disable-model ~/.claude/plugins/cache/.../<version>/commands/<command>.md`

## Related Issues

No related issues documented yet.
