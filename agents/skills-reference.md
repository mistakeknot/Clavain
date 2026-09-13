# Clavain — Skills Reference

## Skill Conventions

- One directory per skill: `skills/<kebab-case-name>/SKILL.md`
- YAML frontmatter: `name` (must match directory name) and `description` (third-person, with trigger phrases)
- Body written in imperative form ("Do X", not "You should do X")
- Keep SKILL.md as short as the task permits; a word limit is not a target. Move conditional procedures and large examples to linked references.
- Sub-resources go in the skill directory: `examples/`, `references/`, helper `.md` files
- Description should contain specific trigger phrases so Claude matches the skill to user intent
- Descriptions are discovery metadata, not mini-manuals. Front-load the capability and task boundary; keep implementation mechanics in the body. Preserve discriminating keywords rather than truncating to a fixed character count.
- Codex budgets the available-skills catalog separately from loaded skill bodies. Use [the Codex skill audit](../docs/runbooks/codex-skills.md) to measure installed duplicates and namespace contributions; shortening bodies alone does not fix a catalog warning.
- Do not assume Claude-specific invocation flags control Codex. Codex supports `agents/openai.yaml` invocation policy. Preserve automatic discovery unless the user requests explicit-only behavior; approvals belong immediately before the authorized mutation, not in a hidden skill.

Example frontmatter:
```yaml
---
name: refactor-safely
description: Refactor significant existing code while preserving behavior with characterization tests and staged verification.
---
```

## Adding a Skill

1. Create `skills/<name>/SKILL.md` with frontmatter
2. Add to the routing table in `skills/using-clavain/SKILL.md` (appropriate stage/domain row)
3. Add to `plugin.json` skills array
4. Update `README.md` skills table

## Agent Conventions

- Flat files in category directories: `agents/review/`, `agents/workflow/`
- YAML frontmatter: `name`, `description` (with `<example>` blocks showing when to trigger), `model` (usually `inherit`)
- Description must include concrete `<example>` blocks with `<commentary>` explaining WHY to trigger
- System prompt is the body of the markdown file
- Agents are dispatched via `Task` tool — they run as subagents with their own context

Categories:
- **review/** — Review specialists (2): plan-reviewer and data-migration-expert. The 7 core fd-* agents live in the **interflux** companion plugin. The agent-native-reviewer lives in **intercraft**.
- **workflow/** — Process automation (2): PR comments, bug reproduction

### Renaming/Deleting Agents

Grep sweep checklist (10 locations): `agents/*/`, `skills/*/SKILL.md`, `commands/*.md`, `hooks/*.sh`, `hooks/lib-*.sh`, `plugin.json`, `CLAUDE.md`, `AGENTS.md`, dispatch templates, test fixtures. Do NOT update historical records (solution docs, sprint logs).

## Adding an Agent

1. Create `agents/<category>/<name>.md` with frontmatter including `<example>` blocks
2. Add to the routing table in `skills/using-clavain/SKILL.md`
3. Reference from relevant commands if applicable
4. Update `README.md` agents list
