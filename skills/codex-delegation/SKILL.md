---
name: codex-delegation
description: Use when executing a plan with Codex agents for parallel implementation. Requires interclode plugin and Codex CLI.
---

# Codex Delegation

Execute plan tasks using Codex agents via the interclode plugin.
Claude stays as orchestrator — planning, dispatching, reviewing, integrating.

## Prerequisites Check

Before starting, verify:
1. Interclode plugin is installed: check for `interclode:delegate` skill availability
2. Codex CLI is installed: `which codex`
3. Codex config exists: `~/.codex/config.toml`

If any prerequisite fails, suggest falling back to `clavain:subagent-driven-development`.

## The Process

### Step 1: Load Plan and Classify Tasks

Read the plan file and classify each task:

| Classification | Executor | Rationale |
|---------------|----------|-----------|
| Independent implementation | Codex agent | Well-scoped, clear files, clear tests |
| Exploratory/research | Claude subagent | Needs deep reasoning |
| Architecture-sensitive | Claude subagent | Needs cross-file understanding |
| Sequential dependency | Codex (ordered) | Must wait for prior task |

Present the classification to the user for approval.

### Step 2: Delegate to Interclode

Invoke `interclode:delegate` skill. When crafting prompts (interclode Step 3),
use the plan's task descriptions directly:

- **Task description** → interclode prompt's "## Task" section
- **Plan's "Files" list** → interclode prompt's "## Relevant Files" section
- **Plan's "Run test" step** → interclode prompt's "## Success Criteria"
- **Plan's "Commit" step** → skip (Claude will commit after review)
- **Always add**: The standard interclode constraints block

Important: Tell Codex agents NOT to commit. Claude will review and commit
after verification.

### Step 3: Review with Clavain Quality Gates

After Codex agents complete and pass interclode's verification (Step 6):

1. **Spec compliance**: Compare each agent's diff against the plan task spec.
   Use the spec-reviewer mindset from subagent-driven-development:
   - Did the agent implement everything requested?
   - Did it add things that weren't requested?
   - Did it miss edge cases from the spec?

2. **Code quality**: Dispatch a Clavain review agent if the changes are substantial:
   ```
   Task (code-reviewer): "Review the changes from the Codex agent for Task N..."
   ```

3. **Integration test**: Run the full test suite across all agent changes together,
   not just per-task tests.

### Step 4: Land the Change

Use `clavain:landing-a-change` to complete:
- Verify all tests pass (with all agent changes combined)
- Evidence checklist
- Commit with dual Co-Authored-By
- Push

## When to Fall Back to Claude

During execution, fall back to Claude subagents if:
- A Codex agent fails twice on the same task
- The task turns out to need cross-file architectural changes
- The task requires interactive exploration to understand

Don't force Codex on tasks it's not suited for.
