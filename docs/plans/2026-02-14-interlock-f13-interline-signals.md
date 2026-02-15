# F13: interline Signal Integration for Coordination Status Display

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Add a coordination status layer to interline's statusline that reads interlock's normalized JSONL signal files and shows persistent coordination status when multi-agent coordination is active.

**Tech Stack:** Bash, jq, ANSI 256-color terminal

**Bead:** Clavain-ykid
**Target Repo:** `/root/projects/interline/`

**PRD:** `docs/prds/2026-02-14-interlock-multi-agent-coordination.md` (F13)

---

## Task 1: Add Coordination Layer to Statusline Script

**Files:**
- Modify: `/root/projects/interline/scripts/statusline.sh`

**Steps:**

1. Add coordination config reading after the existing config reads (after line 29, where `cfg_color_branch` is read). Add one new line:

```bash
cfg_color_coordination=$(_il_cfg '.colors.coordination')
```

2. Insert the coordination layer between the dispatch layer (ends at line 143) and the bead layer (starts at line 146). The new block goes after line 143 (`fi` closing dispatch) and before line 145 (`# --- Layer 1.5: Active beads`). Add this block as **Layer 1.25: Coordination status**:

```bash
# --- Layer 1.25: Coordination status (interlock signal files) ---
coord_label=""
if [ -z "$dispatch_label" ] && _il_cfg_bool '.layers.coordination'; then
  if [ -n "$INTERMUTE_AGENT_ID" ]; then
    # Determine signal directory and project slug
    _il_signal_dir="/var/run/intermute/signals"
    _il_project_slug="$project"

    # Count active agents by counting signal files for this project
    _il_agent_count=0
    if [ -d "$_il_signal_dir" ]; then
      _il_agent_count=$(ls -1 "${_il_signal_dir}/${_il_project_slug}"-*.jsonl 2>/dev/null | wc -l)
    fi

    # Read this agent's signal file for latest event
    _il_signal_file="${_il_signal_dir}/${_il_project_slug}-${INTERMUTE_AGENT_ID}.jsonl"
    _il_signal_text=""
    if [ -f "$_il_signal_file" ]; then
      _il_latest=$(tail -1 "$_il_signal_file" 2>/dev/null)
      if [ -n "$_il_latest" ]; then
        # Version check: only process version 1 signals
        _il_sig_version=$(echo "$_il_latest" | jq -r '.version // 0' 2>/dev/null)
        if [ "$_il_sig_version" = "1" ]; then
          _il_signal_text=$(echo "$_il_latest" | jq -r '.text // empty' 2>/dev/null)
        else
          echo "interline: unknown signal schema version $_il_sig_version, skipping" >&2
        fi
      fi
    fi

    # Build coordination display
    if [ "$_il_agent_count" -gt 0 ] || [ -n "$_il_signal_text" ]; then
      _il_coord_display=""
      if [ "$_il_agent_count" -gt 0 ]; then
        _il_coord_display="${_il_agent_count} agents"
      fi
      if [ -n "$_il_signal_text" ]; then
        _il_signal_short=$(_il_truncate "$_il_signal_text" "$title_max")
        if [ -n "$_il_coord_display" ]; then
          _il_coord_display="${_il_coord_display} | ${_il_signal_short}"
        else
          _il_coord_display="$_il_signal_short"
        fi
      fi
      coord_label="$(_il_color "$cfg_color_coordination" "$_il_coord_display")"
    else
      # INTERMUTE_AGENT_ID is set but no signal data yet — show basic indicator
      coord_label="$(_il_color "$cfg_color_coordination" "coordination active")"
    fi
  fi
fi
```

3. Update the bead layer guard (line 147) to also suppress when coordination is active. Change:

```bash
if [ -z "$dispatch_label" ] && _il_cfg_bool '.layers.bead'; then
```

to:

```bash
if [ -z "$dispatch_label" ] && [ -z "$coord_label" ] && _il_cfg_bool '.layers.bead'; then
```

4. Update the phase layer guard (line 217) to also suppress when coordination is active. Change:

```bash
if [ -z "$dispatch_label" ] && _il_cfg_bool '.layers.phase'; then
```

to:

```bash
if [ -z "$dispatch_label" ] && [ -z "$coord_label" ] && _il_cfg_bool '.layers.phase'; then
```

5. Update the build section (lines 268-278) to include coordination in the output. Replace:

```bash
# Append workflow context (dispatch > bead + phase)
if [ -n "$dispatch_label" ]; then
  status_line="$status_line${sep}$dispatch_label"
else
  # Bead and phase are shown together: "P1 Clavain-4jeg: title... (executing) | Reviewing"
  if [ -n "$bead_label" ]; then
    status_line="$status_line${sep}$bead_label"
  fi
  if [ -n "$phase_label" ]; then
    status_line="$status_line${sep}$phase_label"
  fi
fi
```

with:

```bash
# Append workflow context (dispatch > coordination > bead + phase)
if [ -n "$dispatch_label" ]; then
  status_line="$status_line${sep}$dispatch_label"
elif [ -n "$coord_label" ]; then
  status_line="$status_line${sep}$coord_label"
else
  # Bead and phase are shown together: "P1 Clavain-4jeg: title... (executing) | Reviewing"
  if [ -n "$bead_label" ]; then
    status_line="$status_line${sep}$bead_label"
  fi
  if [ -n "$phase_label" ]; then
    status_line="$status_line${sep}$phase_label"
  fi
fi
```

6. Verify the script is syntactically valid:

```bash
bash -n /root/projects/interline/scripts/statusline.sh
```

**Smoke tests:**

Test 1 — No coordination (INTERMUTE_AGENT_ID not set):
```bash
echo '{"model":{"display_name":"Claude"},"workspace":{"current_dir":"/root/projects/TestProject"},"session_id":"test-123"}' | /root/projects/interline/scripts/statusline.sh
```
Expected: no coordination segment in output.

Test 2 — Coordination active, no signal file:
```bash
INTERMUTE_AGENT_ID="abc-123" echo '{"model":{"display_name":"Claude"},"workspace":{"current_dir":"/root/projects/TestProject"},"session_id":"test-123"}' | /root/projects/interline/scripts/statusline.sh
```
Expected: "coordination active" appears in output.

Test 3 — Coordination active with signal file:
```bash
sudo mkdir -p /var/run/intermute/signals
echo '{"version":1,"layer":"coordination","icon":"lock","text":"reserved src/main.go","priority":3,"ts":"2026-02-14T12:00:00Z"}' | sudo tee /var/run/intermute/signals/TestProject-abc-123.jsonl >/dev/null
INTERMUTE_AGENT_ID="abc-123" echo '{"model":{"display_name":"Claude"},"workspace":{"current_dir":"/root/projects/TestProject"},"session_id":"test-123"}' | /root/projects/interline/scripts/statusline.sh
```
Expected: "1 agents | reserved src/main.go" appears in output.

Test 4 — Unknown schema version:
```bash
echo '{"version":2,"layer":"coordination","text":"future format"}' | sudo tee /var/run/intermute/signals/TestProject-abc-123.jsonl >/dev/null
INTERMUTE_AGENT_ID="abc-123" echo '{"model":{"display_name":"Claude"},"workspace":{"current_dir":"/root/projects/TestProject"},"session_id":"test-123"}' | /root/projects/interline/scripts/statusline.sh 2>/tmp/interline-stderr.txt
```
Expected: Warning on stderr about unknown version. Coordination shows basic indicator or agent count only.

Test 5 — Cleanup:
```bash
sudo rm -rf /var/run/intermute/signals/TestProject-abc-123.jsonl
```

**Acceptance criteria:**
- [ ] Coordination layer reads `/var/run/intermute/signals/{project-slug}-{agent-id}.jsonl` (latest line via `tail -1`)
- [ ] Layer only activates when `INTERMUTE_AGENT_ID` env var is set
- [ ] Priority ordering: dispatch > coordination > bead > workflow > clodex
- [ ] Shows "N agents | signal-text" when signal data available
- [ ] Shows "coordination active" when `INTERMUTE_AGENT_ID` set but no signal file
- [ ] Gracefully ignores signal files with unknown schema version (logs warning to stderr)
- [ ] Falls back gracefully when signal directory or file doesn't exist
- [ ] `bash -n scripts/statusline.sh` passes

---

## Task 2: Update Config and Install Script

**Files:**
- Modify: `/root/projects/interline/scripts/install.sh`

**Steps:**

1. Add coordination defaults to the generated config in `install.sh`. The default config JSON (lines 15-40) needs two additions:

   a. Add `"coordination": 214` to the `colors` object (ANSI 214 = orange, matching the coordination/lock theme). Insert after the `"branch": 244` line:

   ```json
   "coordination": 214
   ```

   b. Add `"coordination": true` to the `layers` object. Insert after the `"clodex": true` line:

   ```json
   "coordination": true
   ```

   The full updated config block in `install.sh` should be:

   ```json
   {
     "colors": {
       "clodex": [210, 216, 228, 157, 111, 183],
       "priority": [196, 208, 220, 75, 245],
       "bead": 117,
       "phase": 245,
       "branch": 244,
       "coordination": 214
     },
     "layers": {
       "dispatch": true,
       "bead": true,
       "bead_query": true,
       "phase": true,
       "clodex": true,
       "coordination": true
     },
     "labels": {
       "clodex": "Clodex",
       "dispatch_prefix": "Clodex"
     },
     "format": {
       "separator": " | ",
       "branch_separator": ":",
       "title_max_chars": 30
     }
   }
   ```

2. Verify the install script is syntactically valid:

```bash
bash -n /root/projects/interline/scripts/install.sh
```

3. Note: existing users who already have `~/.claude/interline.json` will NOT get the new defaults (the install script only creates the config if missing). The coordination layer defaults to `true` in `_il_cfg_bool` (which returns true for any non-`"false"` value, including missing keys), and a missing color key renders without color (plain text). So existing users get coordination enabled by default with no color — acceptable degradation.

**Acceptance criteria:**
- [ ] Install script generates config with `coordination` layer toggle and color
- [ ] `bash -n scripts/install.sh` passes
- [ ] Existing config files continue to work (missing coordination keys default gracefully)

---

## Task 3: Update Documentation

**Files:**
- Modify: `/root/projects/interline/CLAUDE.md`
- Modify: `/root/projects/interline/commands/statusline-setup.md`

**Steps:**

1. Update `CLAUDE.md` priority layers section (lines 13-19). Replace:

```markdown
## Priority Layers

1. **Dispatch** — active Codex dispatch (highest priority)
2. **Bead context** — all `in_progress` beads with priority, title, and phase
3. **Workflow phase** — last invoked skill mapped to phase name
4. **Clodex mode** — passive clodex toggle flag
```

with:

```markdown
## Priority Layers

1. **Dispatch** — active Codex dispatch (highest priority)
2. **Coordination** — multi-agent coordination status from interlock signal files
3. **Bead context** — all `in_progress` beads with priority, title, and phase
4. **Workflow phase** — last invoked skill mapped to phase name
5. **Clodex mode** — passive clodex toggle flag
```

2. Update `CLAUDE.md` state sources section (lines 6-11). Add a new bullet after the Clavain dispatch line:

```markdown
- **interlock** writes `/var/run/intermute/signals/{project-slug}-{agent-id}.jsonl` (coordination signals)
```

3. Update `CLAUDE.md` configuration section (lines 37-63). Add to the JSON example:

   In the `colors` object, add: `"coordination": 214`
   In the `layers` object, add: `"coordination": true`

4. Update `CLAUDE.md` color values section (line 72-73). Add:

```markdown
- `colors.coordination` — number for coordination status text
```

5. Update `CLAUDE.md` layer toggles section (lines 78-80). Add:

```markdown
- `layers.coordination` — controls whether coordination status from interlock signal files is shown. Only active when `INTERMUTE_AGENT_ID` env var is set.
```

6. Update `commands/statusline-setup.md` configuration table (lines 39-55). Add two new rows after the `layers.clodex` row:

```markdown
| `colors.coordination` | number | `214` | ANSI 256-color for coordination status text |
| `layers.coordination` | boolean | `true` | Show coordination status from interlock signals (requires `INTERMUTE_AGENT_ID`) |
```

7. Verify all modified files are consistent and correct.

**Acceptance criteria:**
- [ ] CLAUDE.md lists 5 priority layers with coordination at position 2
- [ ] CLAUDE.md documents interlock signal files as a state source
- [ ] CLAUDE.md config example includes coordination color and layer toggle
- [ ] statusline-setup.md config table includes coordination entries

---

## Pre-flight Checklist

- [ ] Verify interline repo is clean: `cd /root/projects/interline && git status`
- [ ] Verify current statusline is syntactically valid: `bash -n /root/projects/interline/scripts/statusline.sh`
- [ ] Verify install script is valid: `bash -n /root/projects/interline/scripts/install.sh`
- [ ] Confirm `jq` is available: `command -v jq`
- [ ] Read F9 signal schema for reference: signal files are JSONL at `/var/run/intermute/signals/{project-slug}-{agent-id}.jsonl` with schema `{"version":1,"layer":"coordination","icon":"lock","text":"...","priority":3,"ts":"..."}`
- [ ] Confirm `INTERMUTE_AGENT_ID` is the env var set by interlock's SessionStart hook (F7)

## Post-execution Checklist

- [ ] All 3 tasks completed
- [ ] `bash -n scripts/statusline.sh` passes
- [ ] `bash -n scripts/install.sh` passes
- [ ] Smoke tests pass for all 5 scenarios (no coordination, active no file, active with file, unknown version, cleanup)
- [ ] Priority order is dispatch > coordination > bead > workflow > clodex
- [ ] No regressions: statusline still works when `INTERMUTE_AGENT_ID` is not set
- [ ] Config is backward-compatible: existing `interline.json` files without coordination keys still work
- [ ] Documentation matches implementation
- [ ] Modified files: `scripts/statusline.sh`, `scripts/install.sh`, `CLAUDE.md`, `commands/statusline-setup.md`
- [ ] Bead Clavain-ykid updated with completion status
