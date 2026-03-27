# Contributing to Clavain

Thanks for your interest in contributing! Clavain is part of the [Sylveste](https://github.com/mistakeknot/Sylveste) ecosystem.

## Quick start

```bash
# Fork and clone
git clone https://github.com/<your-username>/Clavain.git
cd Clavain

# Test locally with Claude Code
claude --plugin-dir .

# Run tests
bats tests/shell/           # Shell tests (requires bats-core)
pytest tests/structural/    # Structural validation (requires pytest)

# Build the Go CLI (optional — Bash fallback works without it)
go build -C cmd/clavain-cli -o bin/clavain-cli-go .
```

## Workflow

1. **Fork + PR** — branch protection is enabled on `main`. Direct pushes are blocked for non-admins.
2. **One PR per change** — keep PRs focused. Bug fixes, features, and refactors should be separate.
3. **Tests must pass** — CI runs shellcheck, pytest, and bats. PRs that break CI won't be merged.

## What to work on

- Open [issues](https://github.com/mistakeknot/Clavain/issues) labeled `good first issue`
- Shell test coverage for commands in `commands/`
- Documentation improvements (README, skill descriptions)
- Bug reports with reproduction steps

## Structure

```
skills/           # Slash command skills (SKILL.md + optional SKILL-compact.md)
commands/         # Markdown command definitions
agents/           # Review and workflow agents
hooks/            # Event-driven automation (SessionStart, PostToolUse, etc.)
cmd/clavain-cli/  # Go CLI for performance-critical commands
bin/              # Shim + pre-compiled binaries
scripts/          # Build and utility scripts
tests/            # Shell (bats) and structural (pytest) tests
```

## Code style

- **Shell**: Follow existing patterns in `hooks/`. Run `shellcheck` before submitting.
- **Go**: Standard `gofmt`. The CLI uses `encoding/binary` for wire protocols — keep it simple.
- **Skills/Commands**: Markdown with YAML frontmatter. See existing files for structure.

## Full contributing guide

For detailed setup, testing matrix, commit conventions, and plugin development workflow, see the [Sylveste Contributing Guide](https://github.com/mistakeknot/Sylveste/blob/main/docs/guide-contributing.md).
