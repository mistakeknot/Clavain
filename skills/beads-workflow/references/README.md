# Beads Upstream Mirror

This directory is a mirror target for selected files from `steveyegge/beads`:

- `claude-plugin/skills/beads/resources/*`
- `claude-plugin/skills/beads/adr/*`
- selected skill companion docs (`README.md`, `CLAUDE.md`)

Mappings are defined in `upstreams.json` and applied by `.github/workflows/sync.yml`.
Treat mirrored files as upstream-owned; local edits should go into `skills/beads-workflow/SKILL.md`.
