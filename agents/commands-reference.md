# Clavain — Commands Reference

## Command Conventions

- Flat `.md` files in `commands/`
- YAML frontmatter: `name`, `description`, `argument-hint` (optional)
- Body contains instructions FOR Claude (not for the user)
- Commands can reference skills: "Use the `clavain:writing-plans` skill"
- Commands can dispatch agents: "Launch `Task(interflux:review:fd-architecture)`"
- Invoked as `/clavain:<name>` by users

## Adding a Command

1. Create `commands/<name>.md` with frontmatter
2. Add to `plugin.json` commands array
3. Reference relevant skills in the body
4. Update `README.md` commands table

## Adding an MCP Server

1. Add to `mcpServers` in `.claude-plugin/plugin.json`
2. Document required environment variables in README
