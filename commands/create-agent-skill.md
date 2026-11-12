---
name: create-agent-skill
description: Create or edit Claude Code skills with expert guidance on structure and best practices
allowed-tools: Skill(create-agent-skills)
argument-hint: [skill description or requirements]
disable-model-invocation: true
---

Invoke the create-agent-skills skill for: $ARGUMENTS

When pruning instructions, prefer a concrete action and end each step with a
"Done when" condition. The companion reference `testing-skills-with-subagents.md`
recommends explicit negations for observed rationalizations: retain those targeted
counters and safety constraints when a positive rewrite would lose their force.

Done when the skill changes are checked against the supplied requirements and
any targeted counters still address the observed failure.
