# interline Plugin Research

**Date:** 2026-02-12  
**Plugin Version:** 0.1.0  
**Repository:** `/root/projects/interline/`

## Overview

interline is a minimalist Claude Code plugin that provides a dynamic statusline renderer. It displays workflow context from companion plugins (Clavain, interphase) using a 4-layer priority system. The plugin is extremely lightweight with only 6 files total.

**Name etymology:** "interline" = between lines (statusline rendering). Companion to "interphase" (between phases).

## Complete File Structure

```
/root/projects/interline/
├── CLAUDE.md                          # Project documentation
├── .claude-plugin/
│   └── plugin.json                    # Plugin manifest
├── commands/
│   └── statusline-setup.md            # /interline:statusline-setup command
├── scripts/
│   ├── install.sh                     # Installation script (59 lines)
│   └── statusline.sh                  # Main renderer (200 lines)
└── LICENSE                            # MIT License
```

**Notable absences:**
- No AGENTS.md (no dev guide needed — too simple)
- No hooks.json (statusline configured via `~/.claude/settings.json`, not plugin hooks)
- No skills (just one command)
- No tests (minimal surface area, shell script tested manually)
- No marketplace.json (not published to marketplace yet)

## Plugin Manifest (plugin.json)

```json
{
  "name": "interline",
  "version": "0.1.0",
  "description": "Dynamic statusline for Claude Code — shows workflow phase, bead context, and Codex dispatch state. Integrates with Clavain and interphase.",
  "author": { "name": "mistakeknot" },
  "license": "MIT",
  "keywords": ["statusline", "status", "workflow", "display", "context"]
}
```

**Key points:**
- Minimal manifest (no dependencies, hooks, or complex config)
- MIT licensed
- Designed for integration with Clavain/interphase ecosystem

## Main Script: statusline.sh (200 lines)

### Purpose
Reads JSON context from stdin (provided by Claude Code), outputs a formatted status line with ANSI colors showing workflow state.

### Input Format (Claude Code Context)
```json
{
  "model": {"display_name": "Claude Opus 4.6"},
  "workspace": {
    "project_dir": "/root/projects/Clavain",
    "current_dir": "/root/projects/Clavain"
  },
  "session_id": "abc123",
  "transcript_path": "/tmp/claude-transcript-abc123.jsonl"
}
```

### 4-Layer Priority System

The statusline checks multiple sources in priority order and displays the **highest priority active layer**:

#### Layer 1: Dispatch State (Highest Priority)
- **Source:** `/tmp/clavain-dispatch-*.json` files
- **Written by:** Clavain plugin's Codex dispatch system
- **Format:** `{"name": "task-name"}`
- **Display:** `Clodex: task-name` (colored with `cfg_color_dispatch`)
- **Staleness check:** Verifies owning process still alive via `kill -0 $pid`, removes stale files
- **Toggle:** `layers.dispatch` in config

**When active:** Overrides all other layers (bead, phase, clodex mode).

#### Layer 1.5: Bead Context
- **Source:** `/tmp/clavain-bead-${session_id}.json`
- **Written by:** interphase plugin's bead lifecycle tracking
- **Format:** `{"id": "Clavain-021h", "phase": "planned"}`
- **Display:** `Clavain-021h (planned)` (colored with `cfg_color_bead`)
- **Staleness check:** Skip files >24 hours old
- **Toggle:** `layers.bead` in config

**When active:** Only if dispatch layer is empty.

#### Layer 2: Workflow Phase
- **Source:** Claude Code transcript file (last Skill invocation)
- **Method:** `tac "$transcript" | grep -m1 '"Skill"'` — scans backwards, stops at first match
- **Parsing:** Extracts skill name from tool_use JSON, strips namespace prefix
- **Mapping:** 13 skills mapped to phase names (case statement, lines 148-162)

**Skill → Phase mapping:**
| Skill Pattern | Phase Name |
|---------------|------------|
| `brainstorm*` | Brainstorming |
| `strategy` | Strategy |
| `write-plan` | Planning |
| `flux-drive` | Reviewing |
| `work`, `execute-plan` | Executing |
| `quality-gates` | Quality Gates |
| `resolve` | Resolving |
| `landing-a-change` | Shipping |
| `clodex*` | Dispatching |
| `compound`, `engineering-docs` | Documenting |
| `interpeer`, `debate` | Peer Review |
| `smoke-test` | Testing |
| `doctor`, `heal-skill` | Diagnostics |

- **Display:** Phase name (colored with `cfg_color_phase`)
- **Toggle:** `layers.phase` in config

**When active:** Only if dispatch and bead layers are empty.

#### Layer 3: Clodex Mode Flag (Always Visible When Active)
- **Source:** `.claude/clodex-toggle.flag` file in project directory
- **Written by:** Clavain's `/clodex-toggle` command
- **Display:** ` with Clodex` (rainbow-colored label, appended to model name)
- **Toggle:** `layers.clodex` in config

**Special behavior:** This is a **suffix**, not a standalone layer — appended to `[Model]` in the left portion of the statusline.

### Output Format

```
[Model with Clodex] Project:branch | Bead Context | Phase Name
```

**Example outputs:**
```
[Claude Opus 4.6] Clavain:main | Executing
[Claude Opus 4.6 with Clodex] Clavain:main | Clavain-021h (planned) | Planning
[Claude Opus 4.6] Clavain:main | Clodex: implement-feature
```

**Structure breakdown:**
1. `[Model + optional clodex suffix]` — always present
2. `Project:branch` — project name from `workspace.project_dir`, branch from git
3. Workflow context (dispatch OR bead+phase) — highest priority active layer

### Configuration System

#### Config file: `~/.claude/interline.json`

**All fields are optional** — missing file or keys = built-in defaults.

```json
{
  "colors": {
    "clodex": [210, 216, 228, 157, 111, 183],  // Per-letter rainbow (array) or single color (number)
    "dispatch": 214,      // ANSI 256-color for dispatch text
    "bead": 117,          // ANSI 256-color for bead context
    "phase": 245,         // ANSI 256-color for phase name
    "branch": 244         // ANSI 256-color for git branch
  },
  "layers": {
    "dispatch": true,     // Show dispatch state
    "bead": true,         // Show bead context
    "phase": true,        // Show workflow phase
    "clodex": true        // Show clodex mode suffix
  },
  "labels": {
    "clodex": "Clodex",           // Text for rainbow label
    "dispatch_prefix": "Clodex"   // Prefix before dispatch task name
  },
  "format": {
    "separator": " | ",           // Between status segments
    "branch_separator": ":"       // Between project and branch
  }
}
```

#### Config loading implementation (lines 11-34)

**Helpers:**
- `_il_cfg "$jq_path"` — read JSON value with jq, return empty if null/missing
- `_il_cfg_bool "$jq_path"` — return exit code 0 (true) unless value is literal `"false"`

**Default-true layers:** All layers default to enabled. Only disabled if explicitly set to `false`.

**Pre-read optimization:** Lines 21-28 read all config values once at startup, store in bash variables. Avoids repeated jq calls (expensive).

#### Color rendering (lines 36-80)

**`_il_color(code, text)`** (lines 37-44):
- Wraps text in ANSI 256-color escape codes
- If code is empty, returns plain text (no color)

**`_il_clodex_rainbow(label)`** (lines 46-80):
- **Array mode:** If `colors.clodex` is an array, cycle through colors for each letter
- **Scalar mode:** If `colors.clodex` is a number, apply single color to entire label
- **Default rainbow:** If no config, use built-in pastel rainbow `[210, 216, 228, 157, 111, 183]`

**Example color arrays:**
```json
{"colors": {"clodex": [210, 216, 228, 157, 111, 183]}}  // Pastel rainbow (6 colors)
{"colors": {"clodex": 44}}                              // Single teal
```

### Git Integration (lines 88-92)

```bash
git_branch=""
if git rev-parse --git-dir > /dev/null 2>&1; then
  git_branch=$(git symbolic-ref --short HEAD 2>/dev/null || git rev-parse --short HEAD 2>/dev/null)
fi
```

**Behavior:**
- Detects git repo in current directory
- Gets symbolic ref (branch name) or short commit hash (detached HEAD)
- Fails silently if not a git repo (empty string)

### Dispatch State Detection (lines 94-111)

**Process liveness check:**
```bash
for state_file in /tmp/clavain-dispatch-*.json; do
  [ -f "$state_file" ] || continue
  pid="${state_file##*-}"    # Extract PID from filename
  pid="${pid%.json}"
  if kill -0 "$pid" 2>/dev/null; then
    # Process alive — use this dispatch state
    name=$(jq -r '.name // "codex"' "$state_file" 2>/dev/null)
    dispatch_label="$(_il_color "$cfg_color_dispatch" "${dispatch_prefix}: ${name}")"
    break
  else
    # Stale file — owning process died without cleanup
    rm -f "$state_file"
  fi
done
```

**Key insight:** Dispatch state is tied to process lifetime. If Claude Code crashes, stale files get cleaned up automatically on next statusline render.

### Bead Context Detection (lines 113-133)

**Staleness check:**
```bash
file_age=$(( $(date +%s) - $(stat -c %Y "$bead_file" 2>/dev/null || echo 0) ))
if [ "$file_age" -lt 86400 ]; then  # 24 hours
  # Use this bead context
fi
```

**Why 24 hours?** Beads persist across sessions. Unlike dispatch state (tied to process), bead files survive Claude Code restarts. 24h prevents showing stale beads from yesterday's work.

### Transcript Scanning (lines 135-169)

**Backward scan:**
```bash
skill_line=$(tac "$transcript" 2>/dev/null | grep -m1 '"Skill"' || true)
```

**Why `tac`?** Transcript is append-only log. Most recent skill is at the end. Reverse scan with `-m1` stops immediately at first match.

**Skill extraction:**
```bash
skill_name=$(echo "$skill_line" | grep -oP '"skill"\s*:\s*"[^"]*"' | head -1 | sed 's/.*"skill"\s*:\s*"//;s/".*//')
skill_short="${skill_name##*:}"  # Strip namespace: "clavain:brainstorm" -> "brainstorm"
```

**Pattern:** Extract `"skill": "name"` from tool_use JSON, strip namespace prefix.

### Final Assembly (lines 179-198)

```bash
status_line="[$model$clodex_suffix] $project"

if [ -n "$git_branch" ]; then
  git_display="$(_il_color "$cfg_color_branch" "$git_branch")"
  status_line="$status_line${branch_sep}${git_display}"
fi

if [ -n "$dispatch_label" ]; then
  status_line="$status_line${sep}$dispatch_label"
else
  # Bead and phase shown together when both present
  if [ -n "$bead_label" ]; then
    status_line="$status_line${sep}$bead_label"
  fi
  if [ -n "$phase_label" ]; then
    status_line="$status_line${sep}$phase_label"
  fi
fi

echo -e "$status_line"
```

**Priority enforcement:** `if [ -n "$dispatch_label" ]` — dispatch overrides bead+phase. Else clause only runs when dispatch is empty.

## Installation Script: install.sh (59 lines)

### Steps

1. **Copy script** (lines 8-10):
   ```bash
   cp "$SCRIPT_DIR/statusline.sh" "$HOME/.claude/statusline.sh"
   chmod +x "$TARGET"
   ```

2. **Create default config** (lines 12-36):
   - Only if `~/.claude/interline.json` doesn't exist
   - Heredoc with default JSON (pastel rainbow, all layers enabled)

3. **Configure settings.json** (lines 38-54):
   ```python
   s['statusLine'] = {'type': 'command', 'command': os.path.expanduser('~/.claude/statusline.sh')}
   ```
   - Python one-liner using `json` module
   - Creates `~/.claude/settings.json` if missing
   - Sets `statusLine.type = "command"` and `statusLine.command = path`

**Why Python?** Modifying JSON with shell is fragile. Python's `json` module preserves formatting and handles missing keys safely.

### Output Messages

```
Created default config at ~/.claude/interline.json
Statusline installed at ~/.claude/statusline.sh
Settings updated: ~/.claude/settings.json
Customize: ~/.claude/interline.json
```

## Command: statusline-setup.md

### Metadata
```yaml
name: statusline-setup
description: Install or update the interline statusline script
allowed-tools: [Bash]
```

### Implementation (lines 13-33)

**Step 1:** Find interline plugin in cache
```bash
INTERLINE_DIR=$(ls -d ~/.claude/plugins/cache/*/interline/*/scripts/install.sh 2>/dev/null | head -1 | xargs dirname | xargs dirname)
```

**Pattern:** `~/.claude/plugins/cache/{source}/{plugin}/{version}/scripts/install.sh`

**Step 2:** Run install script
```bash
bash "$INTERLINE_DIR/scripts/install.sh"
```

**Step 3:** Verify installation
```bash
echo '{"model":{"display_name":"Test"},"workspace":{"current_dir":"/test"}}' | ~/.claude/statusline.sh
```

**Expected output:** `[Test] test`

### Configuration Reference (lines 35-73)

**Comprehensive table of all config options** (14 rows):
- Color keys (5): `clodex`, `dispatch`, `bead`, `phase`, `branch`
- Layer toggles (4): `dispatch`, `bead`, `phase`, `clodex`
- Labels (2): `clodex`, `dispatch_prefix`
- Format (2): `separator`, `branch_separator`

**Examples:**
```json
// Disable bead context, make phases red
{"layers": {"bead": false}, "colors": {"phase": 196}}

// Single teal color for Clodex label
{"colors": {"clodex": 44}}
```

## Claude Code Integration

### Statusline Configuration Path

Unlike hooks (defined in `plugin.json` with `hooks.json`), statusline is configured globally in `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "/home/claude-user/.claude/statusline.sh"
  }
}
```

**Why not a hook?** Statusline is a **rendering** concern, not an event-driven automation. Claude Code's statusline system is separate from the plugin hook API.

### Runtime Lifecycle

1. **Session start:** Claude Code reads `settings.json`, finds statusline command
2. **Each render cycle:** Claude Code executes `~/.claude/statusline.sh`, pipes JSON context via stdin
3. **Script returns:** ANSI-formatted status text written to stdout
4. **Claude Code displays:** Status text in terminal statusline

**Frequency:** Every time the prompt is shown (after each assistant turn, after user input).

## Sideband File Contracts

### Clavain Dispatch State: `/tmp/clavain-dispatch-*.json`

**Filename pattern:** `clavain-dispatch-{PID}.json`

**Written by:** Clavain's dispatch system when launching Codex tasks

**Schema:**
```json
{
  "name": "task-name",
  "timestamp": "2026-02-12T19:00:00Z"
}
```

**Lifecycle:**
- Created when dispatch starts
- Deleted when dispatch completes (via trap or cleanup)
- Cleaned up by statusline if process dies without cleanup

**interline's responsibility:** Detect stale files (process no longer running), remove them.

### interphase Bead Context: `/tmp/clavain-bead-{session_id}.json`

**Filename pattern:** `clavain-bead-{CLAUDE_SESSION_ID}.json`

**Written by:** interphase plugin's bead lifecycle hooks

**Schema:**
```json
{
  "id": "Clavain-021h",
  "phase": "planned",
  "timestamp": "2026-02-12T19:00:00Z"
}
```

**Lifecycle:**
- Created when bead enters a tracked phase (planned, active, testing, resolved)
- Updated when phase changes
- Persists across sessions (not tied to process)
- Cleaned up by statusline if >24 hours old

**interline's responsibility:** Detect stale files (age check), skip them.

## Design Philosophy

### Minimalism
- **6 files total** (including LICENSE)
- **No dependencies** (pure bash + jq, both standard on ethics-gradient)
- **No hooks** (doesn't need event-driven automation)
- **No tests** (shell script, manual testing sufficient)
- **No AGENTS.md** (surface area too small to justify)

### Separation of Concerns
- **interline:** Renders statusline (display layer)
- **Clavain:** Writes dispatch state (workflow layer)
- **interphase:** Writes bead context (issue tracking layer)

**No tight coupling:** interline reads sideband files but doesn't depend on plugin APIs. Works if plugins are missing (layers silently disabled).

### File-Based IPC
- **Why not plugin APIs?** Statusline runs on every render cycle (high frequency). API calls would be expensive.
- **Why /tmp/?** Ephemeral storage, automatic cleanup on reboot, no git tracking.
- **Why JSON?** Structured data, jq for parsing (fast, robust).

### Graceful Degradation
- Missing config file → built-in defaults
- Missing layer data → layer silently disabled
- Stale sideband files → automatic cleanup
- No git repo → branch field omitted

**Never crashes:** Every layer has fallback behavior.

## Git History Analysis

```
9e4c4e6 feat: add configurable colors, layers, labels, and separators
e483c66 feat: pastel rainbow colors for Clodex label
0bf1e69 feat: color clodex label magenta bold in statusline
2e3e5c6 fix: always show clodex mode in statusline
6a047f1 feat: initial interline statusline plugin
```

**Evolution:**
1. **Initial release** (6a047f1): Basic statusline with hardcoded formatting
2. **Clodex mode visibility** (2e3e5c6): Fixed bug where clodex flag wasn't always shown
3. **Color experimentation** (0bf1e69, e483c66): Tried magenta bold, then switched to pastel rainbow
4. **Configuration system** (9e4c4e6): Added `~/.claude/interline.json` for full customization

**Design trend:** Started simple, added configurability after validating core functionality.

## Testing Strategy

### Manual Testing (from CLAUDE.md)

```bash
bash -n scripts/statusline.sh    # Syntax check
bash -n scripts/install.sh       # Syntax check
echo '{"model":{"display_name":"Test"},"workspace":{"current_dir":"/test"}}' | bash scripts/statusline.sh
```

**Why no automated tests?**
- Shell script with external dependencies (git, jq, filesystem)
- Output includes ANSI escape codes (hard to assert)
- Visual inspection is primary validation method
- Low complexity (200 lines, mostly linear logic)

### Integration Testing
- Run `/interline:statusline-setup` in a live Claude Code session
- Verify statusline appears in next session
- Trigger each layer:
  - Dispatch: Run `/clodex` command
  - Bead: Use interphase bead workflow
  - Phase: Invoke workflow skills (`/flux-drive`, `/work`, etc.)
  - Clodex mode: Run `/clodex-toggle`

## Key Implementation Details

### Performance Optimizations

1. **Pre-read config values** (lines 21-28): Store jq outputs in bash variables, avoid repeated calls
2. **Short-circuit dispatch scan** (line 105): `break` on first valid dispatch file
3. **Backward transcript scan** (line 140): `tac | grep -m1` stops at first match
4. **Staleness checks first** (lines 101-109, 121-131): Skip expensive parsing for dead processes/old files

### Error Handling

**No set -e:** Script doesn't exit on error. Every external command has fallback:
- `jq` failures → empty string (via `2>/dev/null`)
- Git failures → empty branch (via `2>/dev/null`)
- Missing transcript → skip phase detection
- Missing sideband files → skip layer

**Defensive patterns:**
```bash
[ -f "$state_file" ] || continue          # Skip if file doesn't exist
kill -0 "$pid" 2>/dev/null                # Process check (exit code, not output)
jq -r '.name // "codex"' 2>/dev/null      # Default value on null/error
```

### ANSI Escape Code Formats

**256-color text:** `\033[38;5;{code}m{text}\033[0m`
- `38;5` = foreground color
- `{code}` = 0-255 color index
- `\033[0m` = reset formatting

**Example:** `\033[38;5;210mC\033[0m` → pink "C"

## Comparison: interline vs interphase

| Aspect | interline | interphase |
|--------|-----------|------------|
| **Purpose** | Statusline rendering | Phase tracking, gates, discovery |
| **File count** | 6 | ~30+ |
| **Hooks** | None | SessionStart, Stop, etc. |
| **Skills** | 0 | 1 (beads-workflow) |
| **Commands** | 1 | ~5+ |
| **Dependencies** | None (pure bash + jq) | Bash, jq, git, bd CLI |
| **Data flow** | Reads sideband files | Writes sideband files |
| **Complexity** | Minimal (200 lines main script) | High (phase tracking state machine) |
| **Tests** | Manual only | 68 automated tests |

**Complementary roles:** interphase generates state, interline renders it.

## Integration with Clavain Ecosystem

### Data Flow Diagram

```
┌─────────┐
│ Clavain │ writes dispatch state
└────┬────┘
     │
     v
/tmp/clavain-dispatch-*.json
     │
     │    ┌────────────┐
     │    │ interphase │ writes bead context
     │    └─────┬──────┘
     │          │
     │          v
     │    /tmp/clavain-bead-*.json
     │          │
     └──────────┼──────────┐
                │          │
                v          v
           ┌─────────────────┐
           │   interline     │ reads both
           │  statusline.sh  │
           └────────┬────────┘
                    │
                    v
            ANSI status text
                    │
                    v
           ┌─────────────────┐
           │  Claude Code    │ displays
           │   statusline    │
           └─────────────────┘
```

### Cross-Plugin Dependency Analysis

**interline's dependencies:**
- **Optional:** Clavain (for dispatch state)
- **Optional:** interphase (for bead context)
- **Required:** Claude Code (statusline API)

**Graceful degradation:**
- Without Clavain: No dispatch layer, phase layer still works (transcript-based)
- Without interphase: No bead layer, other layers still work
- Without both: Still shows `[Model] Project:branch` (git-based)

**No circular dependencies:** interline only reads, never writes. Clavain/interphase don't depend on interline.

## Future Enhancement Opportunities

### Potential Features (Not Currently Implemented)

1. **Custom phase mappings:** Allow users to define skill→phase mappings in config
2. **Layer priority override:** Let users reorder layers (e.g., phase before dispatch)
3. **Regex-based skill patterns:** Support wildcard matching for skill names
4. **Multi-bead support:** Show multiple active beads (if workflow supports it)
5. **Color themes:** Preset color schemes (dark mode, light mode, high contrast)
6. **Status icons:** Unicode symbols for layers (🔧 for executing, 🔍 for reviewing, etc.)
7. **Truncation rules:** Shorten long task names to fit terminal width
8. **Time-based context:** Show how long current phase has been active

### Current Limitations

1. **No width awareness:** Doesn't truncate for narrow terminals
2. **No color validation:** Accepts any number 0-255, doesn't verify it's a valid ANSI color
3. **Hardcoded skill mappings:** Adding new workflow skills requires editing statusline.sh
4. **Single dispatch state:** Can't show multiple concurrent Codex tasks
5. **No transition animations:** Statusline updates are instant (no fade/slide effects)

## Configuration Examples

### Minimal config (disable all color)
```json
{}
```
Result: Plain text statusline, all layers enabled, default labels/separators.

### High-contrast monochrome
```json
{
  "colors": {}
}
```
Result: No colors applied, all layers visible.

### Hide everything except dispatch
```json
{
  "layers": {
    "bead": false,
    "phase": false,
    "clodex": false
  }
}
```
Result: Only dispatch state shown (when active), otherwise just `[Model] Project:branch`.

### Custom separators
```json
{
  "format": {
    "separator": " • ",
    "branch_separator": " @ "
  }
}
```
Result: `[Model] Project @ branch • Phase Name`

### Single-color theme
```json
{
  "colors": {
    "clodex": 39,
    "dispatch": 39,
    "bead": 39,
    "phase": 39,
    "branch": 39
  }
}
```
Result: All status elements in cyan (ANSI 39).

## Troubleshooting Reference

### Issue: Statusline not appearing after install

**Diagnosis:**
```bash
grep statusLine ~/.claude/settings.json
```

**Expected output:**
```json
"statusLine": {"type": "command", "command": "/home/claude-user/.claude/statusline.sh"}
```

**Fix:** Re-run `/interline:statusline-setup`

### Issue: Statusline shows wrong phase

**Diagnosis:**
```bash
# Find transcript file
ps aux | grep claude | grep transcript

# Check last skill invocation
tail -20 /tmp/claude-transcript-*.jsonl | grep '"Skill"'
```

**Cause:** Transcript scan extracts last skill name, maps via case statement. If skill not in mapping, phase is empty.

**Fix:** Add skill to case statement in `statusline.sh` lines 148-162 (requires editing script).

### Issue: Dispatch state stuck (process died)

**Diagnosis:**
```bash
ls -lh /tmp/clavain-dispatch-*.json
cat /tmp/clavain-dispatch-*.json
```

**Cause:** Clavain dispatch crashed without cleaning up sideband file.

**Fix:** Statusline auto-removes on next render (process liveness check lines 101-109). Force cleanup:
```bash
rm /tmp/clavain-dispatch-*.json
```

### Issue: Bead context from yesterday's work

**Diagnosis:**
```bash
ls -lh /tmp/clavain-bead-*.json
stat -c %Y /tmp/clavain-bead-*.json  # File modification timestamp
```

**Cause:** Bead file >24 hours old.

**Fix:** Statusline auto-skips stale files (age check lines 121-122). Force cleanup:
```bash
rm /tmp/clavain-bead-*.json
```

### Issue: Rainbow colors not showing

**Diagnosis:**
```bash
jq '.colors.clodex' ~/.claude/interline.json
```

**Expected:** Array `[210, 216, 228, 157, 111, 183]` or number

**Fix:** Check terminal ANSI 256-color support:
```bash
for i in {0..255}; do printf "\033[38;5;${i}mColor $i\033[0m "; done; echo
```

If colors don't appear, terminal doesn't support 256-color mode.

## Summary

interline is a **hyper-focused, minimal plugin** that does one thing well: render a context-aware statusline. Its 200-line script reads state from companion plugins via file-based IPC, applies a 4-layer priority system, and outputs ANSI-formatted text. The entire codebase fits in 6 files with zero dependencies beyond standard tools (bash, jq, git).

**Key strengths:**
- **Graceful degradation:** Every layer is optional, works even with missing plugins/config
- **Performance:** Pre-read configs, short-circuit scans, minimal parsing
- **Configurability:** 14 customizable options via JSON config, all optional
- **Reliability:** No crashes (defensive coding, fallbacks everywhere)

**Design trade-offs:**
- No automated tests (manual verification sufficient for small surface area)
- Hardcoded skill→phase mappings (simplicity over extensibility)
- No AGENTS.md (too simple to need comprehensive dev guide)

**Ecosystem role:** Display layer for Clavain/interphase workflow state. Reads their sideband files, never writes. Complements rather than duplicates functionality.
