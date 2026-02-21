---
name: lane
description: Manage thematic work lanes — discover, create, tag beads, show velocity and starvation scores
---

# Lane — Thematic Work Lane Management

Use this skill to manage thematic work lanes that group beads by theme (e.g., interop, kernel, ux). Lanes enable lane-scoped sprint sequencing, starvation-weighted scheduling, and progress tracking.

## Subcommands

Parse `$ARGUMENTS` to determine which subcommand to run:

- Empty or `status` → **Show Lane Dashboard** (Step 1)
- `discover` → **Auto-Discover Lane Candidates** (Step 2)
- `create <name> --type=standing|arc` → **Create Lane** (Step 3)
- `add <lane> <bead-ids...>` → **Add Beads to Lane** (Step 4)

## Step 1: Show Lane Dashboard (default)

Run `ic lane list --json` and `ic lane velocity --json` to get current lane state.

```bash
IC=$(command -v ic 2>/dev/null || echo "")
if [[ -z "$IC" ]]; then
    echo "ic not found — intercore kernel required"
    exit 1
fi
```

Display a formatted table:

```
Lane          Type      Open  Done  Vel/wk  Starv
-------------------------------------------------
interop       standing    10     4    2.1   3.2
kernel        standing     6     8    3.5   1.7
e7-bigend     arc         12     3    1.0   4.8
```

If no lanes exist, suggest running `/clavain:lane discover` to auto-discover candidates.

## Step 2: Auto-Discover Lane Candidates

Analyze the bead graph to propose lane groupings:

1. **Query open beads:**
   ```bash
   bd list --status=open --json 2>/dev/null
   bd list --status=in_progress --json 2>/dev/null
   ```

2. **Analyze grouping signals:**
   - **Module tags in titles:** Look for patterns like `[interflux]`, `[clavain]`, `[autarch]`, `interop:`, `kernel:`
   - **Label prefixes:** Beads with `lane:*` labels are already assigned
   - **Dependency clusters:** Use `bd show <id>` to find connected components via blocks/blockedBy
   - **Roadmap groupings:** Check `docs/roadmap.md` for thematic sections if it exists

3. **Propose lanes** via AskUserQuestion:
   - Present 2-4 candidate lanes with member counts
   - Include a "Custom lane name" option
   - For each candidate: show name, type (standing for ongoing themes, arc for time-bounded epics), and member bead IDs

4. **Create confirmed lanes:**
   ```bash
   ic lane create --name=<name> --type=<type> --description="<desc>"
   ```

5. **Tag member beads:**
   ```bash
   for bead_id in <member_ids>; do
       bd label add "$bead_id" "lane:<name>"
   done
   ```

6. **Sync membership:**
   ```bash
   ic lane sync <lane_id> --bead-ids=<comma-separated-ids>
   ```

## Step 3: Create Lane

Parse `$ARGUMENTS` for name and type:

```bash
# Expected: /clavain:lane create <name> --type=standing|arc [--description=<desc>]
ic lane create --name=<name> --type=<type> --description="<description>"
```

Display the created lane ID and confirm.

## Step 4: Add Beads to Lane

Parse `$ARGUMENTS` for lane name and bead IDs:

```bash
# Expected: /clavain:lane add <lane-name> <bead-id-1> <bead-id-2> ...
# Tag each bead with the lane label
for bead_id in <bead_ids>; do
    bd label add "$bead_id" "lane:<lane_name>"
done

# Sync membership in kernel
ic lane sync <lane_name> --bead-ids=<all-member-ids>
```

After adding, display updated lane status with `ic lane status <lane_name> --json`.
