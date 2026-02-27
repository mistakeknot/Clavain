# Lane Management (compact)
Manage thematic bead lanes for sequencing, starvation tracking, and progress visibility.

## Subcommands

`status` (default), `discover`, `create <name> --type=standing|arc`, `add <lane> <bead-ids...>`.

## Core Workflow

1. Verify `ic` is installed.
2. Dashboard with `ic lane list --json` and `ic lane velocity --json`.
3. Discover lanes by clustering open/in-progress beads by module/title/labels/dependencies.
4. Create lanes (`ic lane create`) and tag members (`lane:<name>`).
5. Sync membership (`ic lane sync`) and show status (`ic lane status <lane> --json`).

## Quick Commands

```bash
ic lane list --json
ic lane velocity --json
ic lane create --name=<name> --type=<standing|arc> --description="<desc>"
bd label add <bead_id> "lane:<name>"
ic lane sync <lane> --bead-ids=<comma-separated-ids>
```

## Key Rules

- Use `standing` for ongoing themes and `arc` for bounded epics.
- Keep bead labels and kernel membership in sync.

---
*For argument parsing details, discovery heuristics, and full interactive flow, read SKILL.md.*
