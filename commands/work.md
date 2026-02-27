---
name: work
description: Execute work plans efficiently while maintaining quality and finishing features
argument-hint: "[plan file, specification, or todo file path]"
---

# Work Plan Execution Command

Execute a work plan efficiently while maintaining quality and finishing features.

## Introduction

This command takes a work document (plan, specification, or todo file) and executes it systematically. The focus is on **shipping complete features** by understanding requirements quickly, following existing patterns, and maintaining quality throughout.

> **When to use this vs `/execute-plan`:** Use `/work` for autonomous feature shipping from a spec or plan. Use `/execute-plan` when you want batch execution with architect review checkpoints between batches (3 tasks at a time).

## Input Document

<input_document> #$ARGUMENTS </input_document>

<BEHAVIORAL-RULES>
These rules are non-negotiable for this orchestration command:

1. **Execute steps in order.** Do not skip, reorder, or parallelize phases unless the phase explicitly allows it. Each phase's output feeds into later phases.
2. **Write output to files, read from files.** Every phase that produces an artifact MUST write it to disk (docs/, .clavain/, etc.). Later phases read from these files, not from conversation context. This ensures recoverability and auditability.
3. **Stop at checkpoints for user approval.** When a phase defines a gate, checkpoint, or AskUserQuestion — stop and wait. Never auto-approve on behalf of the user.
4. **Halt on failure and present error.** If a phase fails (test failure, gate block, tool error), stop immediately. Report what failed, what succeeded before it, and what the user can do. Do not retry silently or skip the failed phase.
5. **Local agents by default.** Use local subagents (Task tool) for dispatch. External agents (Codex, interserve) require explicit user opt-in or an active interserve-mode flag. Never silently escalate to external dispatch.
6. **Never enter plan mode autonomously.** Do not call EnterPlanMode during orchestration. The plan was already created before this command runs. If scope changes mid-execution, stop and ask the user.
</BEHAVIORAL-RULES>

## Execution Workflow

### Phase 1: Quick Start

1. **Read Plan and Clarify**

   - Read the work document completely
   - Review any references or links provided in the plan
   - If anything is unclear or ambiguous, ask clarifying questions now
   - Get user approval to proceed
   - **Do not skip this** - better to ask questions now than build the wrong thing

1b. **Check for Prior Learnings**

   If the plan does NOT contain a `## Prior Learnings` section (meaning it wasn't written via the `writing-plans` skill, or no learnings were found at plan time):
   - Spawn `Task(subagent_type="interflux:learnings-researcher")` with keywords from the plan title and goal
   - If relevant learnings found: present key insights before proceeding, and note them in conversation context
   - If no relevant learnings found: proceed silently
   - This step is advisory — never blocks execution

2. **Setup Environment**

   Ensure you're on the main branch and up to date:

   ```bash
   git pull
   ```

   Work will be committed directly to main (trunk-based development).

3. **Create Todo List**
   - Use TodoWrite to break plan into actionable tasks
   - Include dependencies between tasks
   - Prioritize based on what needs to be done first
   - Include testing and quality check tasks
   - Keep tasks specific and completable

### Phase 1b: Gate Check + Record Phase

Before starting execution, enforce the gate (requires plan-reviewed for P0/P1 beads):
```bash
BEAD_ID=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" infer-bead "<input_document_path>")
if ! "${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" enforce-gate "$BEAD_ID" "executing" "<input_document_path>"; then
    echo "Gate blocked: run /interflux:flux-drive on the plan first, or set CLAVAIN_SKIP_GATE='reason' to override." >&2
    # Stop and tell user — do NOT proceed to execution
fi
"${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" advance-phase "$BEAD_ID" "executing" "Executing: <input_document_path>" "<input_document_path>"
```

### Phase 2: Execute

1. **Task Execution Loop**

   For each task in priority order:

   ```
   while (tasks remain):
     - Mark task as in_progress in TodoWrite
     - Read any referenced files from the plan
     - Look for similar patterns in codebase
     - Implement following existing conventions
     - Write tests for new functionality
     - Run tests after changes
     - Mark task as completed in TodoWrite
     - Mark off the corresponding checkbox in the plan file ([ ] → [x])
     - Evaluate for incremental commit (see below)
   ```

   **IMPORTANT**: Always update the original plan document by checking off completed items. Use the Edit tool to change `- [ ]` to `- [x]` for each task you finish. This keeps the plan as a living document showing progress and ensures no checkboxes are left unchecked.

2. **Incremental Commits**

   After completing each task, evaluate whether to create an incremental commit:

   | Commit when... | Don't commit when... |
   |----------------|---------------------|
   | Logical unit complete (model, service, component) | Small part of a larger unit |
   | Tests pass + meaningful progress | Tests failing |
   | About to switch contexts (backend → frontend) | Purely scaffolding with no behavior |
   | About to attempt risky/uncertain changes | Would need a "WIP" commit message |

   **Heuristic:** "Can I write a commit message that describes a complete, valuable change? If yes, commit. If the message would be 'WIP' or 'partial X', wait."

   **Commit workflow:**
   ```bash
   # 1. Verify tests pass (use project's test command)
   # Examples: npm test, pytest, go test, cargo test, etc.

   # 2. Stage only files related to this logical unit (not `git add .`)
   git add <files related to this logical unit>

   # 3. Commit with conventional message
   git commit -m "feat(scope): description of this unit"
   ```

   **Handling merge conflicts:** If conflicts arise during rebasing or merging, resolve them immediately. Incremental commits make conflict resolution easier since each commit is small and focused.

   **Note:** Incremental commits use clean conventional messages without attribution footers. The final Phase 4 commit/PR includes the full attribution.

3. **Follow Existing Patterns**

   - The plan should reference similar code - read those files first
   - Match naming conventions exactly
   - Reuse existing components where possible
   - Follow project coding standards (see CLAUDE.md)
   - When in doubt, grep for similar implementations

4. **Test Continuously**

   - Run relevant tests after each significant change
   - Don't wait until the end to test
   - Fix failures immediately
   - Add new tests for new functionality

5. **Track Progress**
   - Keep TodoWrite updated as you complete tasks
   - Note any blockers or unexpected discoveries
   - Create new tasks if scope expands
   - Keep user informed of major milestones

### Phase 3: Quality Check

1. **Run Core Quality Checks**

   Always run before committing:

   ```bash
   # Run full test suite (use project's test command)
   # Examples: npm test, pytest, go test, cargo test, etc.

   # Run linting (per CLAUDE.md)
   # Use project's linter before pushing
   ```

2. **Reviewer Agents** — delegate to `/quality-gates`

   If the change is risky or large, run `/clavain:quality-gates` instead of manually selecting reviewers. It auto-selects the right agents based on what changed.

   For a cross-AI second opinion, run `/clavain:interpeer quick`.

3. **Final Validation**
   - All TodoWrite tasks marked completed
   - All tests pass
   - Linting passes
   - Code follows existing patterns
   - No console errors or warnings

### Phase 4: Ship It

1. **Commit to Trunk**

   ```bash
   # Stage specific files (NOT git add .)
   git add <changed-files>
   git status  # Review what's being committed
   git diff --staged  # Check the changes

   # Commit with conventional format
   git commit -m "feat(scope): description of what and why

   Co-Authored-By: Claude <noreply@anthropic.com>"

   git push
   ```

2. **Notify User**
   - Summarize what was completed
   - Note any follow-up work needed
   - Suggest next steps if applicable

---

## Key Principles

### Start Fast, Execute Faster

- Get clarification once at the start, then execute
- Don't wait for perfect understanding - ask questions and move
- The goal is to **finish the feature**, not create perfect process

### The Plan is Your Guide

- Work documents should reference similar code and patterns
- Load those references and follow them
- Don't reinvent - match what exists

### Test As You Go

- Run tests after each change, not at the end
- Fix failures immediately
- Continuous testing prevents big surprises

### Quality is Built In

- Follow existing patterns
- Write tests for new code
- Run linting before pushing
- Use reviewer agents for complex/risky changes only

### Ship Complete Features

- Mark all tasks completed before moving on
- Don't leave features 80% done
- A finished feature that ships beats a perfect feature that doesn't

## Quality Checklist

Before committing, verify:

- [ ] All clarifying questions asked and answered
- [ ] All TodoWrite tasks marked completed
- [ ] Tests pass (run project's test command)
- [ ] Linting passes (use project's linter)
- [ ] Code follows existing patterns
- [ ] Commit messages follow conventional format

## When to Use Quality Gates

**Don't review by default.** Run `/clavain:quality-gates` only when:

- Large refactor affecting many files (10+)
- Security-sensitive changes (authentication, permissions, data access)
- Performance-critical code paths
- Complex algorithms or business logic
- User explicitly requests thorough review

For most features: tests + linting + following patterns is sufficient.

## Common Pitfalls to Avoid

- **Analysis paralysis** - Don't overthink, read the plan and execute
- **Skipping clarifying questions** - Ask now, not after building wrong thing
- **Ignoring plan references** - The plan has links for a reason
- **Testing at the end** - Test continuously or suffer later
- **Forgetting TodoWrite** - Track progress or lose track of what's done
- **80% done syndrome** - Finish the feature, don't move on early
- **Over-reviewing simple changes** - Save reviewer agents for complex work
