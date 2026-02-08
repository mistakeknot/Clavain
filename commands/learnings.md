---
name: learnings
description: Document a recently solved problem to build institutional knowledge
argument-hint: "[optional: brief context about the fix]"
---

# /learnings

Capture a recently solved problem as structured documentation.

## Context

<context> #$ARGUMENTS </context>

## Execution

Use the `clavain:engineering-docs` skill to capture this solution. The skill provides the full 7-step documentation workflow including YAML validation, category classification, and cross-referencing.

If no context argument was provided, the skill will extract context from the recent conversation history.
