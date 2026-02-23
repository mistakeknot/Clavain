# Subagent-Driven Development (compact)

Execute plan by dispatching fresh subagent per task, with two-stage review (spec compliance then code quality) after each.

## When to Use

Have an implementation plan + tasks are mostly independent + staying in this session. Otherwise use `executing-plans` (parallel session) or brainstorm first.

## Process

1. **Read plan once.** Extract all tasks with full text and context. Create TodoWrite.
2. **Per task:**
   a. Dispatch implementer subagent (`implementer-prompt.md`) with full task text + context
   b. Answer any questions the subagent asks before it proceeds
   c. Subagent implements, tests, commits, self-reviews
   d. Dispatch spec reviewer (`spec-reviewer-prompt.md`) — confirms code matches spec
   e. If spec issues: implementer fixes → re-review until approved
   f. Dispatch code quality reviewer (`code-quality-reviewer-prompt.md`)
   g. If quality issues: implementer fixes → re-review until approved
   h. Mark task complete
3. **After all tasks:** Dispatch final code reviewer for entire implementation
4. **Land:** Use `clavain:landing-a-change`

## Key Rules

- Fresh subagent per task (no context pollution)
- **Spec compliance BEFORE code quality** (never reverse order)
- Never skip re-review after fixes
- Never dispatch multiple implementers in parallel (conflicts)
- Provide full task text to subagent — don't make it read the plan file
- If subagent fails: dispatch fix subagent, don't fix manually

## Prompt Templates

- `./implementer-prompt.md`
- `./spec-reviewer-prompt.md`
- `./code-quality-reviewer-prompt.md`

---

*For detailed examples and comparison with other execution modes, read SKILL.md.*
