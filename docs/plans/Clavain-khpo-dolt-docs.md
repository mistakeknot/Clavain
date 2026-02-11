# Plan: Update docs for beads Dolt transition (Clavain-khpo)

## Goal
Update Clavain documentation to reflect beads' transition from SQLite to Dolt as default backend.

## Steps

### Step 1: Update AGENTS.md
In the beads/bd section, note:
- Default backend is now Dolt (version-controlled SQL with cell-level merge)
- JSONL maintained for git portability
- Fallback to JSONL mode when CGO unavailable
- SQLite completely removed from beads

### Step 2: Update `skills/beads-workflow/SKILL.md`
Add note about Dolt backend:
- `bd init` creates a Dolt database by default
- `.beads/dolt/` directory contains the Dolt database (gitignored)
- `.beads/issues.jsonl` is the git-portable sync layer
- If Dolt issues surface, `bd doctor --fix --source=jsonl` rebuilds from JSONL

### Step 3: Commit
Commit message: `docs: note beads Dolt transition in AGENTS.md and beads-workflow skill`

## Verification
- Grep for "SQLite" in Clavain docs — should not claim SQLite is the backend
- Grep for "Dolt" — should appear in AGENTS.md and beads-workflow skill
