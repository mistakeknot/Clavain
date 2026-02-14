# Plan: .clavain/ Agent Memory Filesystem Contract

**Bead:** Clavain-d4ao
**Phase:** executing (as of 2026-02-14T06:05:15Z)
**PRD:** [docs/prds/2026-02-13-clavain-memory-filesystem.md](../prds/2026-02-13-clavain-memory-filesystem.md)

## Overview

Implement the `.clavain/` per-project agent memory filesystem contract: directory spec, `/clavain:init` command, session-handoff/session-start integration, and doctor check.

## Steps

### Step 1: Create `/clavain:init` command

**File:** `commands/init.md`

Create a new command that scaffolds `.clavain/` in the current project:

1. Create directory structure:
   - `.clavain/learnings/`
   - `.clavain/scratch/runs/`
   - `.clavain/contracts/`
2. Create `.clavain/weather.md` with default model routing content (simple template)
3. Append `.clavain/scratch/` to `.gitignore` (if not already present)
4. Create `.clavain/README.md` documenting the directory contract (what each dir is for)
5. Must be idempotent — check existence before creating, don't overwrite existing files

**Acceptance:** Running `/init` in any git repo creates the full structure. Running it twice is a no-op.

### Step 2: Update session-handoff.sh

**File:** `hooks/session-handoff.sh`

Add `.clavain/scratch/` awareness:

1. After the existing signals detection (line 67), check if `.clavain/` directory exists in the project
2. If it exists: change the handoff instruction to write to `.clavain/scratch/handoff.md` instead of root `HANDOFF.md`
3. Ensure `.clavain/scratch/` directory exists (create if needed — `.clavain/` may exist from init but scratch could be gitignored/clean)
4. If `.clavain/` doesn't exist: keep current behavior (root HANDOFF.md)

**Acceptance:** With `.clavain/` present, handoff goes to `.clavain/scratch/handoff.md`. Without it, behavior is unchanged.

### Step 3: Update session-start.sh

**File:** `hooks/session-start.sh`

Add `.clavain/scratch/handoff.md` reading:

1. After the companion detection block (around line 82), add a block that checks for `.clavain/scratch/handoff.md`
2. If it exists and is non-empty: read its content and append to the additionalContext as "Previous session context: ..."
3. Keep it brief — inject at most the first 40 lines to avoid context bloat
4. Also check for `.clavain/weather.md` and inject a one-line summary of model routing preferences if present

**Acceptance:** New sessions in projects with `.clavain/` get handoff context automatically.

### Step 4: Add doctor check

**File:** `commands/doctor.md`

Add a new check section "3d. Agent Memory" between the existing "3c. Statusline Companion" and "4. Conflicting Plugins":

```markdown
### 3d. Agent Memory

```bash
if [ -d .clavain ]; then
  echo ".clavain: initialized"
  # Check scratch/ is gitignored
  if grep -q '.clavain/scratch' .gitignore 2>/dev/null; then
    echo "  scratch gitignore: OK"
  else
    echo "  WARN: .clavain/scratch/ not in .gitignore"
  fi
  # Check for stale handoff
  if [ -f .clavain/scratch/handoff.md ]; then
    age=$(( ($(date +%s) - $(stat -c %Y .clavain/scratch/handoff.md 2>/dev/null || stat -f %m .clavain/scratch/handoff.md 2>/dev/null || echo $(date +%s))) / 86400 ))
    if [ "$age" -gt 7 ]; then
      echo "  WARN: stale handoff (${age} days old)"
    fi
  fi
  echo "  learnings: $(ls .clavain/learnings/*.md 2>/dev/null | wc -l) entries"
else
  echo ".clavain: not initialized (run /clavain:init to set up)"
fi
```

Add to the output table: `.clavain     [initialized|not set up]`

**Acceptance:** Doctor reports `.clavain/` status.

### Step 5: Update gen-catalog.py counts

**File:** `scripts/gen-catalog.py`

Running `/clavain:init` adds a new command (`init.md`). This bumps the command count from 37 to 38. gen-catalog.py will auto-detect and propagate this.

**Action:** Run `python3 scripts/gen-catalog.py` after creating the command file.

### Step 6: Tests and verification

1. `bash -n hooks/session-handoff.sh` — syntax check
2. `bash -n hooks/session-start.sh` — syntax check
3. `python3 -c "import json; json.load(open('hooks/hooks.json'))"` — JSON valid
4. `python3 scripts/gen-catalog.py --check` — counts fresh
5. `uv run --project tests pytest tests/structural/ -x -q` — all tests pass

## Files Changed

| File | Action | Lines (est.) |
|------|--------|-------------|
| `commands/init.md` | Create | ~60 |
| `hooks/session-handoff.sh` | Edit | ~10 |
| `hooks/session-start.sh` | Edit | ~20 |
| `commands/doctor.md` | Edit | ~20 |
| `scripts/gen-catalog.py` | Run only | 0 |
| Auto-updated by gen-catalog | Count bumps | ~5 each |

## Risks

- **Count bump cascade**: New command (init.md) bumps 37→38 across 6 files. gen-catalog.py handles this automatically.
- **session-start context bloat**: Injecting handoff content could bloat additionalContext. Mitigated by 40-line cap.
- **Test count assertion**: Structural tests hardcode command count at 37. Will need updating to 38.
