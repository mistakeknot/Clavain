---
name: lane
description: Manage thematic work lanes — discover, create, tag beads, show velocity and starvation scores
---

# Lane — Thematic Work Lane Management

Group beads by theme (interop, kernel, ux, etc.) for lane-scoped sprint sequencing, starvation-weighted scheduling, and progress tracking.

## Subcommands

Parse `$ARGUMENTS`:
- Empty or `status` → Step 1: Dashboard
- `discover` → Step 2: Auto-Discover
- `create <name> --type=standing|arc` → Step 3: Create Lane
- `add <lane> <bead-ids...>` → Step 4: Add Beads

## Step 1: Show Lane Dashboard (default)

```bash
IC=$(command -v ic 2>/dev/null || echo "")
[[ -z "$IC" ]] && echo "ic not found — intercore kernel required" && exit 1
ic lane list --json && ic lane velocity --json
```

Display:
```
Lane          Type      Open  Done  Vel/wk  Starv
-------------------------------------------------
interop       standing    10     4    2.1   3.2
kernel        standing     6     8    3.5   1.7
e7-bigend     arc         12     3    1.0   4.8
```

If no lanes: suggest `/clavain:lane discover`.

## Step 2: Auto-Discover Lane Candidates

1. Query beads: `bd list --status=open --json` and `bd list --status=in_progress --json`

2. Analyze grouping signals:
   - Module tags in titles: `[interflux]`, `interop:`, `kernel:`, etc.
   - Beads with `lane:*` labels (already assigned)
   - Dependency clusters via `bd show <id>` blocks/blockedBy
   - Thematic sections in `docs/roadmap.md` if it exists

3. Propose 2-4 candidate lanes via AskUserQuestion (name, type, member count, bead IDs; include "Custom lane name" option)

4. Create confirmed lanes:
   ```bash
   ic lane create --name=<name> --type=<type> --description="<desc>"
   for bead_id in <member_ids>; do bd label add "$bead_id" "lane:<name>"; done
   ic lane sync <lane_id> --bead-ids=<comma-separated-ids>
   ```

## Step 3: Create Lane

```bash
ic lane create --name=<name> --type=<type> --description="<description>"
```

Display created lane ID and confirm.

## Step 4: Add Beads to Lane

```bash
for bead_id in <bead_ids>; do bd label add "$bead_id" "lane:<lane_name>"; done
ic lane sync <lane_name> --bead-ids=<all-member-ids>
```

Show updated status: `ic lane status <lane_name> --json`
