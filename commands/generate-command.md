---
name: generate-command
description: Create a new custom slash command following conventions and best practices
argument-hint: "[command purpose and requirements]"
---

# Create a Custom Claude Code Command

Goal: #$ARGUMENTS

## Steps

1. **Plan the command** — identify inputs (`$ARGUMENTS`), outputs, tools needed, success criteria
2. **Create file** at `.claude/commands/[name].md`
3. **Add YAML frontmatter** (required):
   ```yaml
   ---
   name: command-name
   description: Brief description (max 100 chars)
   argument-hint: "[what arguments the command accepts]"
   ---
   ```
4. **Write command body** using terse bullets and numbered steps. Include verification steps.
5. **Test** by invoking with appropriate arguments.

## Template

```markdown
---
name: command-name
description: What this command does
argument-hint: "[expected arguments]"
---

# Command Title

Brief intro.

## Steps

1. [Step with specifics — file paths, constraints, patterns]
2. [Step — use parallel tool calls where possible]
3. Verify: run tests, lint, check diff

## Success Criteria
- Tests pass
- Follows style guide
- Docs updated if needed
```

## Available Tools

- **Files:** Read, Edit, Write, Glob, Grep, MultiEdit
- **Dev:** Bash (git, tests, linters), Task (subagents), TodoWrite
- **Web/APIs:** WebFetch, WebSearch, gh CLI
- **Integrations:** AppSignal, Context7, Stripe, Todoist (if relevant)

## Effective Command Patterns

- Use `$ARGUMENTS` for dynamic inputs
- Reference CLAUDE.md conventions
- XML tags for structured prompts: `<task>`, `<requirements>`, `<constraints>`
- `think hard` / `plan` keywords for complex problems
- Be explicit about what NOT to modify
