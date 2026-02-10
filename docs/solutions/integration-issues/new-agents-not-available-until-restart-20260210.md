---
module: flux-drive
date: 2026-02-10
problem_type: integration_issue
component: agent-dispatch
symptoms:
  - "Agent type 'clavain:review:fd-v2-*' not found"
  - "Task tool lists old agent names but not newly created ones"
  - "New agent .md files exist on disk but aren't available as subagent_type"
root_cause: session_lifecycle
resolution_type: workaround
severity: medium
tags: [agents, subagent-type, session-start, plugin-registry, flux-drive-v2]
---

# New Agent Files Not Available as subagent_type Until Session Restart

## Problem
When new agent `.md` files are created (or committed) during a Claude Code session, they are not available as `subagent_type` values in the Task tool until the session is restarted. The agent registry is loaded once at session start from the plugin's `agents/` directory and is not refreshed mid-session.

## Environment
- Module: flux-drive (agent dispatch)
- Claude Code Version: 2.1.38
- Affected Component: Task tool `subagent_type` parameter
- Date: 2026-02-10

## Symptoms
- `Task` tool returns: `Agent type 'clavain:review:fd-v2-architecture' not found. Available agents: [list of old v1 agents]`
- The agent `.md` file exists at `agents/review/fd-v2-architecture.md` and passes validation
- The available agents list shows only agents that existed when the session started

## Root Cause
Claude Code's plugin system loads the agent registry at session initialization. This registry maps agent file paths to `subagent_type` identifiers (e.g., `agents/review/fd-v2-architecture.md` → `clavain:review:fd-v2-architecture`). Creating new files mid-session doesn't update this registry — it's a static snapshot.

This is the expected behavior, not a bug. The session-start loading is by design for performance and consistency.

## Resolution

### Immediate Workaround (Same Session)
Use `subagent_type: general-purpose` and paste the agent's full system prompt content into the task prompt. This is the "Project Agent" dispatch path:

```
Task(
  subagent_type: "general-purpose",
  prompt: "<full agent .md content>\n\n---\n\n<review task prompt>",
  run_in_background: true
)
```

The agent gets the same instructions — it just doesn't have the native `subagent_type` routing.

### Proper Fix
1. Commit the new agent files
2. Push to remote
3. Bump plugin version and publish (`scripts/bump-version.sh <version>`)
4. Restart the Claude Code session

After restart, the new agents appear in the Task tool's available agents list.

## Prevention
When implementing new agents that need immediate testing via flux-drive:
1. Create the agent files
2. Commit, push, publish
3. Restart session
4. **Then** run flux-drive validation

Do not attempt to test new agents via their native `subagent_type` in the same session they were created.

## Cross-References
- `skills/flux-drive/SKILL.md` — Agent Roster section defines the `subagent_type` mappings
- `skills/flux-drive/phases/launch.md` — Step 2.2 dispatches agents by type
- Convention-based discovery: `agents/review/{name}.md` → `clavain:review:{name}`
