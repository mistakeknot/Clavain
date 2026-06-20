---
name: plan-review
description: Have multiple specialized agents review a plan in parallel
argument-hint: "[plan file path or plan content]"
---

## Progress Tracking

This command is the **Validate** leg of the OODARC loop — a decision gate that checks the plan before commitment. Display and update:

```
plan-review (OODARC: Validate — decision gate):
- [ ] Dispatch 3 review agents in parallel (plan-reviewer, fd-architecture, fd-quality)
- [ ] Collect all three verdicts
- [ ] Synthesize into a unified, prioritized review
```

Launch three review agents in parallel using the Task tool to review the provided plan:

1. **plan-reviewer** — Use the Task tool with `subagent_type: "clavain:review:plan-reviewer"` to review the plan against implementation standards and completeness.

2. **fd-architecture** — Use the Task tool with `subagent_type: "interflux:review:fd-architecture"` to evaluate architectural decisions, component boundaries, and design patterns.

3. **fd-quality** — Use the Task tool with `subagent_type: "interflux:review:fd-quality"` to check for over-engineering, unnecessary complexity, and YAGNI violations.

All three agents should receive the plan content and run concurrently (use a single message with multiple Task tool calls). After all agents complete, synthesize their findings into a unified review with prioritized issues.
