# Research: F13 interline Signal Integration — Pre-Plan Analysis

**Date:** 2026-02-14
**Scope:** Implementation plan for interline reading interlock's coordination signal files
**Bead:** Clavain-ykid

---

## Context Gathered

### 1. PRD Acceptance Criteria (F13)

From `docs/prds/2026-02-14-interlock-multi-agent-coordination.md`, F13 specifies:

- Reads `/var/run/intermute/signals/{project-slug}-{agent-id}.jsonl` (latest line)
- Coordination layer inserted into priority: dispatch > **coordination** > bead > workflow > clodex
- Persistent indicator when coordination active: `N agents | M files reserved` (shown only when `INTERMUTE_AGENT_ID` is set)
- Signal-based updates: reservation changes, new messages
- Gracefully ignores signal files with unknown schema version (logs warning, falls back to "no coordination status")
- Falls back gracefully when no signal file exists

### 2. Current interline Architecture

**File:** `/root/projects/interline/scripts/statusline.sh` (281 lines)

The statusline has 4 layers, each gated by a config toggle:

1. **Layer 1 — Dispatch** (lines 122-143): Reads `/tmp/clavain-dispatch-*.json`, checks PID liveness, shows "Clodex: name (activity)". Highest priority — if dispatch is active, lower layers are suppressed for bead/phase.
2. **Layer 1.5 — Bead context** (lines 146-213): Reads `/tmp/clavain-bead-${session_id}.json` sideband + queries `bd list --status=in_progress`. Only shown if dispatch is NOT active. Shows "P1 Clavain-4jeg: title... (phase)".
3. **Layer 2 — Workflow phase** (lines 216-249): Scans transcript for last Skill invocation, maps to phase name. Only shown if dispatch is NOT active.
4. **Layer 3 — Clodex mode** (lines 252-257): Checks for `.claude/clodex-toggle.flag`. Passive suffix appended to model display.

**Priority suppression logic (lines 268-278):**
- If `dispatch_label` is set: show dispatch only (suppress bead + phase)
- Else: show bead + phase together (both can coexist)
- Clodex suffix is always appended if active (it modifies the model display, not the status segments)

**Config system:**
- Config file: `~/.claude/interline.json`
- Layer toggles: `.layers.dispatch`, `.layers.bead`, `.layers.bead_query`, `.layers.phase`, `.layers.clodex`
- Colors: `.colors.dispatch`, `.colors.bead`, `.colors.phase`, `.colors.branch`, `.colors.clodex`, `.colors.priority[]`
- Helper functions: `_il_cfg()` reads config keys, `_il_cfg_bool()` checks boolean toggles (default true), `_il_color()` wraps text in ANSI 256-color

**Stdin JSON input (line 7):**
```json
{"model":{"display_name":"Claude"},"workspace":{"project_dir":"/path","current_dir":"/path"},"transcript_path":"...","session_id":"..."}
```

Key variables extracted: `model`, `project_dir`, `project` (basename), `transcript`, `session_id`, `git_branch`.

### 3. F9 Signal File Format

From `docs/research/write-f9-signals-plan.md`:

```json
{"version":1,"layer":"coordination","icon":"lock","text":"reserved src/*.go","priority":3,"ts":"2026-02-14T12:00:00Z"}
```

Fields:
- `version` (int): Schema version for forward compat. F13 should only process version 1.
- `layer` (string): Always "coordination" for interlock signals.
- `icon` (string): "lock" (reserve), "unlock" (release), "mail" (message).
- `text` (string): Human-readable description, <100 chars.
- `priority` (int): 3 for reservations, 4 for messages.
- `ts` (string): ISO 8601 UTC timestamp.

Signal file path pattern: `/var/run/intermute/signals/{project-slug}-{agent-id}.jsonl`
- `project-slug` = `basename $(git rev-parse --show-toplevel)`
- `agent-id` = from `INTERMUTE_AGENT_ID` env var

### 4. Insertion Point Analysis

The new coordination layer must go between dispatch (Layer 1) and bead (Layer 1.5). In the current code:

- **After line 143** (end of dispatch block): Insert new Layer 1.25 — coordination
- **Line 147**: Current bead layer checks `[ -z "$dispatch_label" ]` — needs to also check `[ -z "$coord_label" ]`
- **Line 217**: Current phase layer checks `[ -z "$dispatch_label" ]` — needs to also check `[ -z "$coord_label" ]`
- **Lines 268-278**: Build section needs coordination between dispatch and bead

The PRD says coordination should be a **persistent indicator**, not suppress bead/phase. Looking more closely at the acceptance criteria: "Persistent indicator when coordination active: `N agents | M files reserved`" — this implies coordination status is shown alongside other layers, not suppressing them.

However, the priority ordering says `dispatch > coordination > bead > workflow > clodex`, which in the existing pattern means coordination suppresses lower layers when active. But the "persistent" qualifier and the "N agents | M files reserved" summary format suggest this is an always-visible overlay when `INTERMUTE_AGENT_ID` is set.

**Resolution:** The coordination layer should behave like bead context — it's shown when dispatch is NOT active, and it coexists with bead/phase. When dispatch IS active, dispatch takes over (it already suppresses everything). The "persistent" qualifier means it's shown as long as coordination is active, not just when there's a new signal event.

### 5. Summary Count Approach

The PRD wants "N agents | M files reserved" — but the signal file only has individual events (reserve/release). To get counts, we need to aggregate.

**Option A:** Parse all signal files in the directory (one per agent) to count active agents and sum reservations. This means scanning the directory, reading last line of each file.

**Option B:** Have interlock write a summary signal file (e.g., `{project-slug}-summary.jsonl`) with aggregate counts. This adds complexity to F9.

**Option C:** Read only this agent's signal file for latest event text, and separately count signal files in the directory for the agent count.

**Chosen approach:** Option C — count `.jsonl` files in the signal directory matching the project slug for agent count, read the latest signal for current status. This is fast (ls + tail -1), requires no aggregation logic, and works with the existing F9 schema.

For "M files reserved": the latest signal's `text` field already contains the relevant info (e.g., "reserved src/*.go"), but for a summary we'd need to count active reservations. Since this is purely display and the signal file doesn't track running totals, we'll show agent count + latest event text instead of exact reservation counts. If the user wants exact counts, `/interlock:status` provides them.

**Revised display format:** `"N agents | latest-signal-text"` when coordination is active.

### 6. Config Extensions

New config keys needed in `~/.claude/interline.json`:

- `.layers.coordination` (bool, default true) — toggle coordination layer
- `.colors.coordination` (int) — ANSI 256-color for coordination text

### 7. Files To Modify

**Target repo:** `/root/projects/interline/`

1. `scripts/statusline.sh` — Add coordination layer, config reading, build section changes
2. `scripts/install.sh` — Add coordination defaults to generated config
3. `CLAUDE.md` — Document new layer in priority list and config table
4. `commands/statusline-setup.md` — Add coordination config key to table

### 8. Graceful Degradation

- `INTERMUTE_AGENT_ID` not set → skip coordination layer entirely (zero cost)
- Signal directory doesn't exist → skip (no error)
- Signal file doesn't exist → show basic "coordination active" indicator
- Signal file has unknown version → log warning to stderr, skip signal data
- jq not available → already required by other layers (safe to assume)

### 9. Test Strategy

No formal test suite exists in interline (it's a 281-line shell script). Validation is manual:
1. Syntax check: `bash -n scripts/statusline.sh`
2. Smoke test: pipe JSON to statusline.sh with mock signal files
3. Structural test in Clavain: verify config keys documented

The plan should include smoke test commands for each scenario.
