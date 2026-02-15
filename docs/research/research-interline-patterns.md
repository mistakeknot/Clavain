# Research: interline Statusline Plugin Patterns

## Executive Summary

The **interline** statusline plugin is a minimal companion plugin that renders Claude Code's statusline by reading JSON input from Claude Code's runtime environment and state files written by sister plugins (Clavain, interphase). It uses a 4-layer priority system with file-based sidebands to display dispatch state, bead context, workflow phase, and configuration flags.

**Key insight:** interline demonstrates a lightweight, decoupled integration pattern: plugins write state files to `/tmp/` using predictable namespaces, and a single renderer reads them without direct function calls or dependencies. This enables real-time context visibility without tight coupling.

---

## 1. interline Implementation Details

### Current Architecture

**Directory structure:**
```
/root/projects/interline/
├── .claude-plugin/
│   └── plugin.json
├── CLAUDE.md
├── commands/
│   └── statusline-setup.md
└── scripts/
    ├── install.sh
    └── statusline.sh
```

**Plugin metadata** (`plugin.json`):
- Version: `0.1.0`
- Single command: `/interline:statusline-setup`
- No hooks defined — configuration is via Claude Code's `settings.json`, not plugin hooks
- Licensed as MIT

### statusline.sh: The Renderer

**Location:** `/root/projects/interline/scripts/statusline.sh` (118 lines)

**Invocation pattern:**
- Claude Code calls it automatically on every "Status" hook event (fires ~every 300ms when transcript updates)
- Input: JSON via stdin with session context (model, directories, transcript path, session_id, cost metrics)
- Output: First line of stdout becomes the statusline text
- Supports ANSI color codes

**Input JSON schema** (from Claude Code):
```json
{
  "hook_event_name": "Status",
  "session_id": "abc123...",
  "transcript_path": "/path/to/transcript.jsonl",
  "cwd": "/current/working/directory",
  "model": { "id": "claude-opus-...", "display_name": "Opus" },
  "workspace": {
    "current_dir": "/current/working/directory",
    "project_dir": "/original/project/directory"
  },
  "version": "1.0.80",
  "output_style": { "name": "default" },
  "cost": {
    "total_cost_usd": 0.01234,
    "total_duration_ms": 45000,
    "total_api_duration_ms": 2300,
    "total_lines_added": 156,
    "total_lines_removed": 23
  }
}
```

**4-Layer Priority System:**

1. **Layer 1: Dispatch state** (highest priority)
   - Files: `/tmp/clavain-dispatch-*.json`
   - Pattern: `/tmp/clavain-dispatch-<PID>.json` where PID is the Codex process ID
   - Content: `{"name": "...", "workdir": "...", "started": <timestamp>}`
   - Display: `Clodex: <name>` (e.g., "Clodex: vet")
   - Process check: Verifies PID still alive with `kill -0 $pid`; deletes stale files if process is dead
   - Implementation (lines 21–36): Loops through glob, extracts PID from filename, validates

2. **Layer 1.5: Bead context** (only if no dispatch active)
   - Files: `/tmp/clavain-bead-${session_id}.json` (session-keyed)
   - Content: `{"id": "Clavain-abc123", "phase": "planned", "reason": "...", "ts": <timestamp>}`
   - Display format: `Clavain-abc123 (planned)` or just `Clavain-abc123` if no phase
   - Stale-file handling: Checks file age; ignores if >24h old (line 46: `$(date +%s) - $(stat -c %Y ...)`
   - Implementation (lines 38–57): Extracts from input's `session_id`, reads sideband file, parses with jq

3. **Layer 2: Workflow phase** (only if no dispatch or bead active)
   - Source: Transcript file scanning (last Skill invocation detected)
   - Scanning: `tac` (reverse) → first "Skill" match → extract skill name from JSON
   - Mapping: Skill name → human-readable phase label
   - Implemented mapping (lines 70–84):
     - `brainstorm*` → "Brainstorming"
     - `write-plan` → "Planning"
     - `flux-drive` → "Reviewing"
     - `work|execute-plan` → "Executing"
     - `quality-gates` → "Quality Gates"
     - `resolve` → "Resolving"
     - `landing-a-change` → "Shipping"
     - `clodex*` → "Dispatching"
     - `compound|engineering-docs` → "Documenting"
     - `interpeer|debate` → "Peer Review"
     - `smoke-test` → "Testing"
     - `doctor|heal-skill` → "Diagnostics"
   - Implementation (lines 59–87): Scans transcript for last Skill in reverse, strips namespace prefix (`clavain:` → just the skill name)

4. **Layer 3: Clodex mode flag** (lowest priority, passive)
   - File: `$project_dir/.claude/clodex-toggle.flag`
   - Display: Appends " with Clodex" to model name if file exists
   - Implementation (lines 89–95): Check for flag file

**Output assembly** (lines 97–117):
```
[$model$clodex_suffix] $project:$git_branch | [dispatch_label | bead_label phase_label]
```

Examples:
- `[Opus] Clavain:main | Clodex: vet`
- `[Opus] Clavain:main | Clavain-021h (planned) | Planning`
- `[Opus] Clavain:main | Reviewing`

---

## 2. Clavain Dispatch State File Protocol

### File Location and Naming

**Path:** `/tmp/clavain-dispatch-<PID>.json`

**Naming scheme:**
- PID is the shell process ID of the dispatch.sh script itself (`$$`)
- Enables interline to verify the process is still alive before reading
- Predictable cleanup: trap on EXIT/INT/TERM removes the file when dispatch exits

**Lifecycle:**
```bash
STATE_FILE="/tmp/clavain-dispatch-$$.json"
trap 'rm -f "$STATE_FILE"' EXIT INT TERM
printf '{"name":"%s","workdir":"%s","started":%d}\n' \
  "${NAME:-codex}" "${WORKDIR:-.}" "$(date +%s)" > "$STATE_FILE"
```

Source: `/root/projects/Clavain/scripts/dispatch.sh` lines 451–454

### State File Content

**Schema:**
```json
{
  "name": "vet",           // --name parameter or "codex" default
  "workdir": "/path/to/project",  // -C parameter or .
  "started": 1707500000   // Unix timestamp (date +%s)
}
```

**Semantics:**
- `name` is user-supplied label for tracking (usually task name like "vet", "audit", "refactor")
- `workdir` tracks which project the dispatch is operating on
- `started` allows statusline to display elapsed time (not currently used by interline, but available)

### Reliability & Cleanup

**Process validation:**
```bash
if kill -0 "$pid" 2>/dev/null; then
  # Process is alive — safe to read
else
  # Process is dead — remove stale file
  rm -f "$state_file"
fi
```

**Why this matters:**
- If dispatch.sh terminates abnormally (SIGKILL, crash), trap doesn't fire → orphaned file
- interline detects this and cleans up automatically
- Next dispatch.sh can reuse the same filename if PID recycles

---

## 3. interphase Bead State File Protocol

### File Location and Naming

**Path:** `/tmp/clavain-bead-${CLAUDE_SESSION_ID}.json`

**Naming scheme:**
- Session-based key (`CLAUDE_SESSION_ID` from environment)
- One file per Claude Code session (shared across multiple beads if same session)
- Enables statusline to match bead context to the running session

**Lifecycle:**
```bash
local session_id="${CLAUDE_SESSION_ID:-}"
[ -z "$session_id" ] && return 0  # Fail-safe: no-op if session ID unavailable
local state_file="/tmp/clavain-bead-${session_id}.json"
jq -n -c \
    --arg id "$bead_id" --arg phase "$phase" \
    --arg reason "$reason" --arg ts "$(date +%s)" \
    '{id:$id, phase:$phase, reason:$reason, ts:($ts|tonumber)}' \
    > "$state_file" 2>/dev/null || true
```

Source: `/root/projects/interphase/hooks/lib-gates.sh` lines 264–273

### State File Content

**Schema:**
```json
{
  "id": "Clavain-021h",      // Bead ID (e.g., issue tracker reference)
  "phase": "planned",         // Current gate phase (null, planned, ready, done, etc.)
  "reason": "user_advanced",  // Reason for phase change (gate_check, user_advanced, etc.)
  "ts": 1707500000           // Unix timestamp
}
```

**Semantics:**
- `id` is the immutable bead identifier from the issue tracker
- `phase` is the current lifecycle phase (from interphase's `lib-phase.sh`)
- `reason` documents why the phase changed (debugging/telemetry value)
- `ts` allows statusline to detect stale updates (>24h old)

### Reliability & Stale File Handling

**Stale file detection in interline:**
```bash
file_age=$(( $(date +%s) - $(stat -c %Y "$bead_file" 2>/dev/null || echo 0) ))
if [ "$file_age" -lt 86400 ]; then
  # File is fresh (<24h) — safe to read
else
  # File is stale (>24h old) — ignore
fi
```

**Why 24h threshold:**
- Prevents displaying old bead context after a long idle period
- Sessions can last >24h (multi-day debugging), so threshold is conservative
- Filesystem mtime is reliable across systems

**Error handling:**
```bash
jq ... > "$state_file" 2>/dev/null || true
```
- Silently succeeds even if jq fails or file write fails
- Never blocks workflow (fail-safe design)
- Statusline degrades gracefully if sideband unavailable

---

## 4. Integration Patterns in Clavain

### Where Clavain Writes Dispatch State

**Script:** `/root/projects/Clavain/scripts/dispatch.sh`

**Trigger:** On every Codex dispatch (before executing command)

**Context:**
- Used by the `/clavain:clodex` skill (full-pipeline Codex orchestrator)
- Wrapped by compound-engineering's `dispatch` skill
- Enables statusline to show which sub-task is running during multi-step workflows

**Example workflow:**
1. User runs `/full-pipeline "describe the architecture"`
2. Codex generates task descriptions for sub-agents
3. For each task, `dispatch.sh` writes state file
4. interline renders "Clodex: vet" (or other task name) in statusline
5. User sees progress without verbose logging

### Setup & Installation

**Command:** `/interline:statusline-setup`

**What it does:**
1. Locates interline plugin in cache: `~/.claude/plugins/cache/*/interline/*/scripts/install.sh`
2. Runs `install.sh` which:
   - Copies `statusline.sh` to `~/.claude/statusline.sh`
   - Updates `~/.claude/settings.json` to configure statusLine:
     ```json
     {
       "statusLine": {
         "type": "command",
         "command": "~/.claude/statusline.sh"
       }
     }
     ```

**Setup.md integration:** `/root/projects/Clavain/commands/setup.md` (line 35)
- Listed as required plugin: `claude plugin install interline@interagency-marketplace`
- Installed during Clavain modpack bootstrap

**Doctor.md integration:** `/root/projects/Clavain/commands/doctor.md`
- Check 3c verifies interline installation
- Detects: `ls ~/.claude/plugins/cache/*/interline/*/scripts/statusline.sh`
- Reports status and links install command if missing

---

## 5. Communication Protocol Summary

### Sideband File Pattern

**Design principle:** Decoupled via filesystem

```
┌─────────────────────────────────────────────────────────────────┐
│ Clavain dispatch.sh (running Codex task)                        │
│ └─ writes /tmp/clavain-dispatch-<PID>.json                      │
└─────────────────────────────────────────────────────────────────┘
                            ↓
                    (file on disk)
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ interline statusline.sh (runs via Claude Code Status hook)       │
│ └─ reads /tmp/clavain-dispatch-*.json every 300ms               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ interphase lib-gates.sh (running gate validation)               │
│ └─ writes /tmp/clavain-bead-<SESSION>.json                      │
└─────────────────────────────────────────────────────────────────┘
                            ↓
                    (file on disk)
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ interline statusline.sh (runs via Claude Code Status hook)       │
│ └─ reads /tmp/clavain-bead-<SESSION>.json every 300ms           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Claude Code runtime (Session context)                           │
│ └─ passes JSON to statusline via stdin (model, workspace, etc)  │
└─────────────────────────────────────────────────────────────────┘
                            ↓
                        (stdin)
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ interline statusline.sh                                          │
│ └─ combines all inputs → renders single-line status output      │
└─────────────────────────────────────────────────────────────────┘
```

### Guarantees & Limitations

**What the protocol provides:**
- ✅ Real-time visibility into active tasks
- ✅ Process-aware cleanup (stale file detection)
- ✅ Session-scoped bead context
- ✅ Fault-tolerant (missing files don't crash statusline)
- ✅ Zero coupling (plugins don't call each other)

**What the protocol lacks:**
- ❌ Ordering guarantees (if two files exist, behavior is first-match-wins)
- ❌ Explicit acknowledgment (writer doesn't know if reader read the state)
- ❌ Cross-process synchronization (events are point-in-time reads)
- ❌ Structured logging (state changes aren't recorded persistently)
- ❌ Error propagation (read failures silently degrade)

---

## 6. Gaps and Improvement Opportunities

### 1. Stale File Cleanup

**Current state:**
- Dispatch files: Cleaned up by trap handler (reliable)
- Bead files: Ignored if >24h old, but never deleted
- Problem: `/tmp/` accumulates orphaned bead files after many sessions

**Improvement:**
- Add periodic cleanup script (daily cron or systemd timer)
- Delete bead files older than 24h
- Or: Implement auto-cleanup in interline itself (scan and remove stale files)

**Example fix (cron):**
```bash
0 6 * * * find /tmp -name 'clavain-bead-*.json' -mtime +1 -delete
```

### 2. Transcript Scanning Performance

**Current state:**
- interline scans entire transcript file on every status update (~300ms)
- Uses `tac` (reverse read) + `grep -m1` to find last Skill invocation
- On large transcripts (>10,000 lines), this is expensive

**Impact:** Slower statusline updates on long-running sessions

**Improvement options:**
1. **Cache last-seen skill:** Store in `/tmp/clavain-skill-<SESSION>.json`, update on every Skill invocation
2. **Limit transcript scan:** Only read last N lines instead of entire file
3. **Use jq instead of grep:** Parse transcript JSON properly instead of regex

**Example fix (cache approach):**
```bash
# In interphase's skill-tracking hook:
echo "$skill_name" > "/tmp/clavain-skill-${CLAUDE_SESSION_ID}.json"

# In interline:
skill_name=$(cat "/tmp/clavain-skill-${SESSION_ID}.json" 2>/dev/null)
```

### 3. Priority Layer Conflicts

**Current state:**
- Layer 1 (dispatch) completely hides Layer 2 (phase)
- Once Codex dispatch starts, workflow phase disappears from statusline
- Problem: User can't see what they were doing before dispatch launched

**Improvement:**
- Combine dispatch and phase: `[Opus] Clavain | Clodex: vet (was Planning)`
- Or: Add a "previous phase" field to dispatch state file

**Example schema:**
```json
{
  "name": "vet",
  "workdir": "...",
  "started": ...,
  "previous_phase": "Planning"  // Optional
}
```

### 4. Multi-Domain Bead Support

**Current state:**
- Only one bead per session (`/tmp/clavain-bead-<SESSION>.json`)
- If workflow touches multiple beads sequentially, only the latest is visible

**Improvement:**
- Track bead stack: `/tmp/clavain-bead-<SESSION>-stack.json`
- Display primary bead + depth: `Clavain-021h [2/5]` (2 of 5 beads in workflow)
- Requires: interphase's lib-gates.sh to append to stack on gate transitions

### 5. Input JSON Validation

**Current state:**
- interline uses loose jq queries with `//` fallbacks
- If Claude Code changes input schema, script silently degrades

**Improvement:**
- Add schema validation at startup
- Warn if required fields are missing
- Document minimum Claude Code version requirement

**Example fix:**
```bash
# At top of statusline.sh
required_fields=("model.display_name" "workspace.project_dir" "session_id")
for field in "${required_fields[@]}"; do
  if ! echo "$input" | jq -e ".$field" >/dev/null 2>&1; then
    echo "[ERROR] Missing field: $field" >&2
  fi
done
```

### 6. Coloring and Format Customization

**Current state:**
- Statusline output is plain text (no ANSI colors)
- Hard to scan in the terminal

**Improvement:**
- Add color support: dispatch state in red, phase in blue, bead ID in green
- Allow customization via environment variables or config file
- Example: `INTERLINE_DISPATCH_COLOR=1` enables colors

**Benefits:**
- Easier to spot active dispatch
- Differentiates layers visually
- Aligns with modern shell statuslines (starship, oh-my-zsh)

### 7. Race Condition: Dispatch Cleanup vs. Read

**Current state:**
```bash
# Writer (dispatch.sh)
trap 'rm -f "$STATE_FILE"' EXIT

# Reader (interline)
if [ -f "$state_file" ]; then
  name=$(jq -r '.name // "codex"' "$state_file")
fi
```

**Edge case:** Between the `[ -f ]` check and the `jq` read, dispatch.sh exits and removes the file
- Result: jq reads empty file or missing file → empty `name` → displays "Clodex: codex" (fallback)
- Low impact, but non-ideal

**Improvement:**
- Use atomic read: `jq ... "$state_file" 2>/dev/null || true`
- Or: Use file locking (flock) if precision is critical

### 8. Documentation & Examples

**Current state:**
- CLAUDE.md is minimal (3 bullet points)
- No examples of how to extend or customize
- No troubleshooting guide

**Improvement:**
- Add reference documentation: input/output schemas, file format specs
- Example customizations: display elapsed time, show cost, custom phase mapping
- Troubleshooting section: why statusline isn't updating, how to debug

---

## 7. Similar Patterns in the Wild

### Inspiration from Other Tools

**tmux statusline:**
- Reads environment via hooks and scripts
- Supports command execution with configurable refresh rate
- Supports interpolation of variables (session name, window, etc.)

**zsh prompt (PROMPT_COMMAND):**
- Re-executed before every prompt
- Can read arbitrary files and state
- Supports ANSI colors

**starship prompt:**
- Modular system with plugins
- Each module reads config and OS state independently
- ~300ms update budget (similar to Claude Code)

**Lessons:**
- Keep renderer stateless (read current state each invocation)
- Use simple file formats (JSON, not databases)
- Fail gracefully if state files missing
- Support zero-config defaults

---

## 8. Security & Reliability Considerations

### File Permissions

**Current state:**
- `/tmp/clavain-*.json` files created with default umask (typically 0644 or 0664)
- Readable by any user on the system

**Risk:** Sensitive information in dispatch workdir or bead ID could be leaked to other users

**Mitigation:**
- Create files with restrictive permissions: `umask 0077` before write
- Or: Use session-specific directory: `/tmp/clavain-${USER}-${SESSION_ID}/`

### Path Injection

**Current state:**
- interline reads `project_dir` from Claude Code input (untrusted)
- Used to check for `.claude/clodex-toggle.flag`

**Risk:** Malicious project could set a symlink to `/etc/passwd` as `.claude/clodex-toggle.flag` → interline reads it

**Mitigation:**
- Use `realpath` to resolve symlinks before checking flag file
- Or: Check for flag in current directory only, not arbitrary project_dir

### Resource Exhaustion

**Current state:**
- interline scans entire transcript on every update (no limit)
- Could read arbitrarily large files

**Risk:** Transcript with millions of lines could slow statusline rendering

**Mitigation:**
- Add line limit: only read last 1000 lines
- Or: Implement caching (see improvement #2)

---

## 9. Testing & Validation Approach

### Current Test Coverage

**No automated tests found for interline** — only bash syntax checks mentioned in CLAUDE.md:
```bash
bash -n scripts/statusline.sh
bash -n scripts/install.sh
```

### Recommended Test Suite

**Unit tests (bash):**
```bash
# Test 1: Dispatch layer priority
input='{"model":{"display_name":"Opus"},"workspace":{"current_dir":"/tmp"},"session_id":"test"}'
echo "$input" | mock_dispatch_state | statusline.sh
# Expected: "Clodex: test" in output

# Test 2: Bead layer
# Create /tmp/clavain-bead-test.json, verify output includes bead ID

# Test 3: Phase layer from transcript
# Mock transcript with last Skill=flux-drive, verify "Reviewing" in output

# Test 4: Stale bead file ignored
# Create bead file with mtime >24h old, verify it's ignored

# Test 5: Process validation
# Create dispatch file with dead PID, verify it's deleted
```

**Integration tests (in Clavain):**
- Run a dispatch job, verify statusline updates
- Verify statusline recovers after dispatch completes

---

## 10. Summary: Key Patterns & Conventions

### Naming Conventions

- **Dispatch files:** `/tmp/clavain-dispatch-<PID>.json` (process-keyed)
- **Bead files:** `/tmp/clavain-bead-<SESSION_ID>.json` (session-keyed)
- **Namespace prefix:** `clavain-` (allows other tools to use `/tmp/` without conflicts)

### JSON Schema Conventions

**Dispatch state:**
- Minimal: name, workdir, started
- No nested objects or arrays

**Bead state:**
- Minimal: id, phase, reason, ts (timestamp)
- All top-level keys

### Error Handling Conventions

- **Silent failures:** `jq ... || true` (don't crash on parsing errors)
- **Graceful degradation:** Missing files → show fewer layers
- **Stale data detection:** Compare file mtime to current time

### Performance Conventions

- **300ms budget:** Statusline updates at most every 300ms (Claude Code rate limit)
- **Fast-fail checks:** Process validation (kill -0) before reading
- **Lazy evaluation:** Only read files that might exist (glob patterns)

---

## Conclusion

**interline exemplifies lightweight companion integration:**
- Single responsibility: render statusline from multiple input sources
- Decoupled via filesystem: no function calls, no dependencies
- Fault-tolerant: handles missing/corrupt state files gracefully
- Extensible: new plugins can write to `/tmp/clavain-<resource>-*.json` without changing interline

**Key improvement opportunities:**
1. Stale file cleanup (cron)
2. Transcript scanning optimization (cache last skill)
3. Layer interaction (combine dispatch + phase)
4. Validation & error reporting
5. Color support
6. Security hardening

The protocol is production-ready for current use but would benefit from documentation refinement and optional performance optimizations for long-running sessions.
