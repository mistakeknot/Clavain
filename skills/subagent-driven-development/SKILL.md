---
name: subagent-driven-development
description: Use when executing implementation plans with independent tasks in the current session
---

<!-- compact: SKILL-compact.md — if it exists in this directory, load it instead of following the full instructions below. The compact version contains the same per-task dispatch + two-stage review protocol. -->

# Subagent-Driven Development

Execute plan by dispatching a fresh subagent per task with two-stage review after each: spec compliance first, then code quality.

**Core principle:** Fresh subagent per task + two-stage review (spec → quality) = high quality, fast iteration.

## When to Use

Have implementation plan? No → brainstorm/manual first. Yes → tasks mostly independent? No (tightly coupled) → manual. Yes → stay in this session? No → `executing-plans`. Yes → **this skill**.

**vs. executing-plans:** Same session (no context switch), fresh subagent per task (no context pollution), two-stage review per task, faster iteration (no human-in-loop between tasks).

## The Process

1. Read plan once, extract all tasks with full text and context, create TodoWrite
2. **Per task:**
   a. Dispatch implementer subagent (`./implementer-prompt.md`) with full task text + scene-setting context
   b. If subagent asks questions → answer completely, then re-dispatch
   c. Implementer implements, tests, commits, self-reviews
   d. Dispatch spec reviewer (`./spec-reviewer-prompt.md`) — confirms code matches spec (no over/under-building)
   e. If spec issues → implementer fixes → spec reviewer re-reviews (repeat until ✅)
   f. Dispatch code quality reviewer (`./code-quality-reviewer-prompt.md`) — get git SHAs first
   g. If quality issues → implementer fixes → quality reviewer re-reviews (repeat until ✅)
   h. Mark task complete in TodoWrite
3. After all tasks: dispatch final code reviewer for entire implementation
4. Use **clavain:landing-a-change**

## Prompt Templates

- `./implementer-prompt.md` — implementer subagent
- `./spec-reviewer-prompt.md` — spec compliance reviewer
- `./code-quality-reviewer-prompt.md` — code quality reviewer

## Example Workflow

```
Task 1: Hook installation script

[Dispatch implementer with full task text + context]
Implementer: "Should hook be installed at user or system level?"
You: "User level (~/.claude/hooks/)"
Implementer: implemented install-hook, 5/5 tests, added --force flag, committed

[Dispatch spec reviewer]
Spec reviewer: ✅ All requirements met, nothing extra

[Get git SHAs, dispatch code quality reviewer]
Code reviewer: ✅ Approved

[Mark Task 1 complete]

Task 2: Recovery modes

[Dispatch implementer]
Implementer: added verify/repair modes, 8/8 tests, committed

[Dispatch spec reviewer]
Spec reviewer: ❌ Missing progress reporting (spec: "every 100 items"); extra: --json flag not requested

[Implementer fixes: removed --json, added progress reporting]
Spec reviewer: ✅ Compliant

[Dispatch code quality reviewer]
Code reviewer: ⚠️ Magic number (100) — extract constant

[Implementer: extracted PROGRESS_INTERVAL]
Code reviewer: ✅ Approved

[Mark Task 2 complete]

[After all tasks: dispatch final code reviewer]
Final reviewer: All requirements met, ready to merge
```

## Advantages

**Quality gates:** self-review → spec compliance (prevents over/under-building) → code quality → final review. Issues caught before handoff.

**Efficiency:** Controller extracts all tasks upfront; subagent gets complete info (no plan file reading); questions surfaced before work begins.

**vs. manual:** Fresh context per task, no context pollution, subagent follows TDD naturally.

**Cost note:** More invocations (implementer + 2 reviewers per task + review loops), but catches issues early.

## Red Flags

- Never start on main/master without explicit user consent
- Never skip either review stage
- Never dispatch multiple implementation subagents in parallel (conflicts)
- Never make subagent read plan file — provide full text
- Never skip scene-setting context
- Never ignore subagent questions — answer before proceeding
- Never accept "close enough" on spec compliance
- Never skip re-review after fixes
- Never start code quality review before spec compliance is ✅
- Never let implementer self-review replace actual review (both required)
- Never move to next task with open review issues

**If subagent fails task:** dispatch fix subagent with specific instructions — don't fix manually (context pollution).

## Integration

- **clavain:writing-plans** — creates the plan this skill executes
- **clavain:code-review-discipline** — review template for reviewer subagents
- **clavain:landing-a-change** — required after all tasks complete
- **clavain:test-driven-development** — subagents use for each task
- **clavain:executing-plans** — alternative for parallel session (not same-session)
- **clavain:interserve** — Codex agents for parallel implementation (Claude stays as orchestrator + reviewer)
