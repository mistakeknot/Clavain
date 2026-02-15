# F7: Interlock Hooks (SessionStart, PreToolUse:Edit Advisory, Stop) -- Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Implement three Claude Code plugin hooks for the interlock companion plugin that manage agent lifecycle -- registering agents on session start, warning about file reservation conflicts before edits, and cleaning up reservations on session stop.

**Architecture:** Three hook scripts in `hooks/` delegate all intermute API calls to helper scripts in `scripts/`. The hooks read JSON from stdin (Claude Code hook protocol), check preconditions (join flag, agent ID, connectivity), and output JSON responses. All hooks exit 0 unconditionally -- graceful degradation is mandatory. The `PreToolUse:Edit` hook is advisory-only (adds `additionalContext`, never blocks).

**Tech Stack:** Bash, jq, curl. No compiled dependencies.

**Bead:** Clavain-8wy9

**PRD:** `docs/prds/2026-02-14-interlock-multi-agent-coordination.md` (F7)

**Target repo:** `/root/projects/interlock/`

**Reference patterns:**
- Clavain `hooks/session-start.sh` -- SessionStart hook with `CLAUDE_ENV_FILE` export and JSON stdin parsing
- Clavain `hooks/auto-compound.sh` -- Stop hook with sentinel files, `stop_hook_active` guard, `jq` fail-open
- Clavain `hooks/clodex-audit.sh` -- PostToolUse hook reading `tool_input.file_path` from stdin JSON
- Clavain `hooks/hooks.json` -- declarative hook registration format

---

## Design Decisions

1. **Join-flag gating:** All hooks check `~/.config/clavain/intermute-joined` first. This file is created by `/interlock:join` (F8) and removed by `/interlock:leave`. If absent, hooks exit 0 silently -- no registration, no checks, no cleanup. This means interlock is truly opt-in per-user.

2. **Script delegation:** Hooks are thin dispatchers. `session-start.sh` calls `scripts/interlock-register.sh`, `pre-edit.sh` calls `scripts/interlock-check.sh`, `stop.sh` calls `scripts/interlock-cleanup.sh`. This keeps hooks testable and allows scripts to be invoked independently (e.g., from commands or MCP tools).

3. **Connectivity tracking:** A flag file `/tmp/interlock-connected-${SESSION_ID}` is written after successful registration. If `pre-edit.sh` detects intermute is unreachable AND this flag exists, it emits a one-time warning ("intermute coordination lost") and removes the flag. Subsequent unreachable checks are silent.

4. **Advisory-only PreToolUse:Edit:** The hook outputs `additionalContext` with conflict details but always exits 0 with no `decision` field (or `decision: "allow"`). This matches the PRD requirement: "Advisory only. Git pre-commit hooks provide mandatory enforcement."

5. **Session ID sourcing:** Hooks read `session_id` from stdin JSON (same pattern as Clavain's `session-start.sh`). The SessionStart hook persists it to `CLAUDE_ENV_FILE` as `CLAUDE_SESSION_ID` for downstream hooks to use. PreToolUse and Stop hooks read it from the environment variable.

---

### Task 1: hooks.json + Hook Scaffolding

**Files:**
- Create: `/root/projects/interlock/hooks/hooks.json`
- Create: `/root/projects/interlock/hooks/lib.sh`

**Steps:**

1. Create `hooks/hooks.json` with the three hook declarations:
   ```json
   {
     "hooks": {
       "SessionStart": [
         {
           "matcher": "startup|resume|clear|compact",
           "hooks": [
             {
               "type": "command",
               "command": "${CLAUDE_PLUGIN_ROOT}/hooks/session-start.sh",
               "async": true
             }
           ]
         }
       ],
       "PreToolUse": [
         {
           "matcher": "Edit",
           "hooks": [
             {
               "type": "command",
               "command": "${CLAUDE_PLUGIN_ROOT}/hooks/pre-edit.sh",
               "timeout": 5
             }
           ]
         }
       ],
       "Stop": [
         {
           "hooks": [
             {
               "type": "command",
               "command": "${CLAUDE_PLUGIN_ROOT}/hooks/stop.sh",
               "timeout": 10
             }
           ]
         }
       ]
     }
   }
   ```
   Notes on configuration:
   - SessionStart is `async: true` because registration involves a network call to intermute that may take >100ms.
   - PreToolUse:Edit has `timeout: 5` (seconds) so a slow/hung intermute check doesn't block editing.
   - Stop has `timeout: 10` to allow reservation release (multiple API calls).

2. Create `hooks/lib.sh` with shared utilities:
   - `JOIN_FLAG="${HOME}/.config/clavain/intermute-joined"` -- constant for the opt-in flag path
   - `is_joined()` -- returns 0 if join flag exists, 1 otherwise
   - `intermute_url()` -- returns the intermute base URL. Reads from `INTERMUTE_URL` env var, falls back to `http://localhost:4200` (intermute default). If `INTERMUTE_SOCKET` is set, returns the socket path for `curl --unix-socket`.
   - `intermute_curl()` -- wrapper around curl that handles both TCP and Unix socket connections. Adds `--connect-timeout 2 --max-time 5 --silent --fail` by default. Returns curl exit code.
   - `agent_file_path()` -- given session ID, returns `/tmp/interlock-agent-${SESSION_ID}.json`
   - `connected_flag_path()` -- given session ID, returns `/tmp/interlock-connected-${SESSION_ID}`

**Acceptance criteria:**
- [ ] `hooks.json` is valid JSON (`python3 -c "import json; json.load(open('hooks/hooks.json'))"`)
- [ ] `bash -n hooks/lib.sh` passes
- [ ] `intermute_curl` supports both TCP (`INTERMUTE_URL`) and Unix socket (`INTERMUTE_SOCKET`) modes

---

### Task 2: SessionStart Hook + Registration Script

**Files:**
- Create: `/root/projects/interlock/hooks/session-start.sh`
- Create: `/root/projects/interlock/scripts/interlock-register.sh`

**Steps:**

1. Create `hooks/session-start.sh`:
   ```bash
   #!/usr/bin/env bash
   set -euo pipefail

   # Read hook input from stdin (must happen before anything else consumes it)
   HOOK_INPUT=$(cat)

   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
   source "${SCRIPT_DIR}/lib.sh"

   # Check join flag -- if not joined, exit silently
   is_joined || exit 0

   # Extract session_id from hook JSON
   SESSION_ID=$(echo "$HOOK_INPUT" | jq -r '.session_id // empty' 2>/dev/null) || SESSION_ID=""
   [[ -n "$SESSION_ID" ]] || exit 0

   # Persist session_id to CLAUDE_ENV_FILE for downstream hooks
   if [[ -n "${CLAUDE_ENV_FILE:-}" ]]; then
       echo "export CLAUDE_SESSION_ID=${SESSION_ID}" >> "$CLAUDE_ENV_FILE"
   fi

   # Delegate registration to helper script
   RESULT=$("${SCRIPT_DIR}/../scripts/interlock-register.sh" "$SESSION_ID" 2>/dev/null) || RESULT=""

   if [[ -z "$RESULT" ]]; then
       # Registration failed (intermute unreachable or error) -- silent degradation
       exit 0
   fi

   # Parse agent_id and agent_name from result
   AGENT_ID=$(echo "$RESULT" | jq -r '.agent_id // empty' 2>/dev/null) || AGENT_ID=""
   AGENT_NAME=$(echo "$RESULT" | jq -r '.name // empty' 2>/dev/null) || AGENT_NAME=""

   # Export agent identity to CLAUDE_ENV_FILE
   if [[ -n "${CLAUDE_ENV_FILE:-}" && -n "$AGENT_ID" ]]; then
       echo "export INTERMUTE_AGENT_ID=${AGENT_ID}" >> "$CLAUDE_ENV_FILE"
       echo "export INTERMUTE_AGENT_NAME=${AGENT_NAME}" >> "$CLAUDE_ENV_FILE"
   fi

   # Write agent details to temp file
   echo "$RESULT" > "$(agent_file_path "$SESSION_ID")"

   # Mark connectivity established
   touch "$(connected_flag_path "$SESSION_ID")"

   # Inject coordination context
   AGENT_COUNT=$(echo "$RESULT" | jq -r '.agent_count // "?"' 2>/dev/null) || AGENT_COUNT="?"
   cat <<ENDJSON
   {
     "hookSpecificOutput": {
       "hookEventName": "SessionStart",
       "additionalContext": "INTERLOCK: Coordination active. Registered as '${AGENT_NAME}' (${AGENT_ID:0:8}...). ${AGENT_COUNT} agent(s) online. File reservations enforced via git pre-commit hook."
     }
   }
   ENDJSON

   exit 0
   ```

2. Create `scripts/interlock-register.sh`:
   ```bash
   #!/usr/bin/env bash
   # Register this agent with intermute.
   # Args: $1 = session_id
   # Output: JSON with agent_id, name, session_id, agent_count on stdout
   # Exit: 0 on success, 1 on failure (caller handles graceful degradation)
   set -euo pipefail

   SESSION_ID="${1:?session_id required}"

   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
   source "${SCRIPT_DIR}/../hooks/lib.sh"

   # Determine agent name (precedence: stored name > tmux pane title > fallback)
   AGENT_NAME=""
   NAME_FILE="${HOME}/.config/clavain/intermute-agent-name"
   if [[ -f "$NAME_FILE" ]]; then
       AGENT_NAME="$(cat "$NAME_FILE" 2>/dev/null | head -1 | tr -d '\n')"
   fi
   if [[ -z "$AGENT_NAME" ]] && command -v tmux &>/dev/null; then
       AGENT_NAME="$(tmux display-message -p '#T' 2>/dev/null || true)"
   fi
   if [[ -z "$AGENT_NAME" ]]; then
       AGENT_NAME="claude-${SESSION_ID:0:8}"
   fi

   # Detect project name from git or directory
   PROJECT=""
   if command -v git &>/dev/null && git rev-parse --show-toplevel &>/dev/null 2>&1; then
       PROJECT="$(basename "$(git rev-parse --show-toplevel 2>/dev/null)")"
   else
       PROJECT="$(basename "$PWD")"
   fi

   # POST to intermute /api/agents
   RESPONSE=$(intermute_curl POST "/api/agents" \
       -H "Content-Type: application/json" \
       -d "$(jq -n \
           --arg name "$AGENT_NAME" \
           --arg project "$PROJECT" \
           --arg session_id "$SESSION_ID" \
           '{name: $name, project: $project, metadata: {session_id: $session_id}}')" \
       2>/dev/null) || exit 1

   AGENT_ID=$(echo "$RESPONSE" | jq -r '.agent_id // empty' 2>/dev/null) || exit 1
   [[ -n "$AGENT_ID" ]] || exit 1

   # Get agent count for context injection
   AGENTS_RESPONSE=$(intermute_curl GET "/api/agents?project=${PROJECT}" 2>/dev/null) || AGENTS_RESPONSE=""
   AGENT_COUNT=$(echo "$AGENTS_RESPONSE" | jq -r '.agents | length // 0' 2>/dev/null) || AGENT_COUNT="?"

   # Output structured result
   jq -n \
       --arg agent_id "$AGENT_ID" \
       --arg name "$AGENT_NAME" \
       --arg session_id "$SESSION_ID" \
       --arg project "$PROJECT" \
       --arg agent_count "$AGENT_COUNT" \
       '{agent_id: $agent_id, name: $name, session_id: $session_id, project: $project, agent_count: $agent_count}'

   exit 0
   ```

3. Make both scripts executable: `chmod +x hooks/session-start.sh scripts/interlock-register.sh`

**Acceptance criteria:**
- [ ] SessionStart hook: registers agent only if `~/.config/clavain/intermute-joined` exists
- [ ] SessionStart hook: writes `/tmp/interlock-agent-${SESSION_ID}.json` with agent details
- [ ] SessionStart hook: exports `INTERMUTE_AGENT_ID` and `INTERMUTE_AGENT_NAME` to `CLAUDE_ENV_FILE`
- [ ] On intermute unreachable: exit 0 silently (no error output, no additionalContext)
- [ ] `bash -n hooks/session-start.sh` passes
- [ ] `bash -n scripts/interlock-register.sh` passes

---

### Task 3: PreToolUse:Edit Advisory Hook + Check Script

**Files:**
- Create: `/root/projects/interlock/hooks/pre-edit.sh`
- Create: `/root/projects/interlock/scripts/interlock-check.sh`

**Steps:**

1. Create `hooks/pre-edit.sh`:
   ```bash
   #!/usr/bin/env bash
   # PreToolUse:Edit hook -- advisory conflict warning (never blocks).
   set -euo pipefail

   # Guard: fail-open if jq is not available
   command -v jq &>/dev/null || exit 0

   # Read hook input
   INPUT=$(cat)

   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
   source "${SCRIPT_DIR}/lib.sh"

   # Skip if not in coordination mode
   [[ -n "${INTERMUTE_AGENT_ID:-}" ]] || exit 0

   # Extract file path from Edit tool input
   FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null) || FILE_PATH=""
   [[ -n "$FILE_PATH" ]] || exit 0

   SESSION_ID="${CLAUDE_SESSION_ID:-unknown}"

   # Delegate conflict check to helper script
   CONFLICT=$("${SCRIPT_DIR}/../scripts/interlock-check.sh" "$FILE_PATH" "$INTERMUTE_AGENT_ID" 2>/dev/null) || {
       # intermute unreachable -- check if we lost connectivity
       CONNECTED_FLAG="$(connected_flag_path "$SESSION_ID")"
       if [[ -f "$CONNECTED_FLAG" ]]; then
           # First unreachable detection since last connectivity -- emit one-time warning
           rm -f "$CONNECTED_FLAG"
           cat <<ENDJSON
   {"additionalContext": "INTERLOCK WARNING: intermute coordination lost. Proceeding without reservation checks. File reservations and conflict detection are unavailable until intermute is reachable again."}
   ENDJSON
       fi
       exit 0
   }

   # No conflict -- exit silently
   [[ -n "$CONFLICT" ]] || exit 0

   # Parse conflict details
   HELD_BY=$(echo "$CONFLICT" | jq -r '.held_by // "unknown"' 2>/dev/null) || HELD_BY="unknown"
   REASON=$(echo "$CONFLICT" | jq -r '.reason // ""' 2>/dev/null) || REASON=""
   EXPIRES=$(echo "$CONFLICT" | jq -r '.expires_at // ""' 2>/dev/null) || EXPIRES=""

   # Format expiry for human readability
   EXPIRES_DISPLAY="$EXPIRES"
   if [[ -n "$EXPIRES" ]] && command -v date &>/dev/null; then
       EXPIRES_EPOCH=$(date -d "$EXPIRES" +%s 2>/dev/null || echo "")
       if [[ -n "$EXPIRES_EPOCH" ]]; then
           NOW_EPOCH=$(date +%s)
           REMAINING_MIN=$(( (EXPIRES_EPOCH - NOW_EPOCH) / 60 ))
           if [[ $REMAINING_MIN -gt 0 ]]; then
               EXPIRES_DISPLAY="in ${REMAINING_MIN}m"
           else
               EXPIRES_DISPLAY="expired"
           fi
       fi
   fi

   # Build reason display
   REASON_DISPLAY=""
   if [[ -n "$REASON" ]]; then
       REASON_DISPLAY="\"${REASON}\", "
   fi

   # Advisory output -- NOT blocking (no decision field, exit 0)
   cat <<ENDJSON
   {"additionalContext": "INTERLOCK: ${FILE_PATH} reserved by ${HELD_BY} (${REASON_DISPLAY}expires ${EXPIRES_DISPLAY})\nRecover: (1) work on other files, (2) intermute_request_release(to=\"${HELD_BY}\"), (3) wait for expiry\nNote: git commit will block until resolved."}
   ENDJSON

   exit 0
   ```

2. Create `scripts/interlock-check.sh`:
   ```bash
   #!/usr/bin/env bash
   # Check if a file path conflicts with any active reservation.
   # Args: $1 = file_path, $2 = our_agent_id
   # Output: JSON conflict details on stdout (empty if no conflict)
   # Exit: 0 on success (including no conflict), 1 on intermute unreachable
   set -euo pipefail

   FILE_PATH="${1:?file_path required}"
   OUR_AGENT_ID="${2:?agent_id required}"

   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
   source "${SCRIPT_DIR}/../hooks/lib.sh"

   # Detect project
   PROJECT=""
   if command -v git &>/dev/null && git rev-parse --show-toplevel &>/dev/null 2>&1; then
       PROJECT="$(basename "$(git rev-parse --show-toplevel 2>/dev/null)")"
   else
       PROJECT="$(basename "$PWD")"
   fi

   # Make file path relative to project root
   REL_PATH="$FILE_PATH"
   if command -v git &>/dev/null; then
       PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
       if [[ -n "$PROJECT_ROOT" && "$FILE_PATH" == "$PROJECT_ROOT"* ]]; then
           REL_PATH="${FILE_PATH#$PROJECT_ROOT/}"
       fi
   fi

   # Query active reservations for this project
   RESPONSE=$(intermute_curl GET "/api/reservations?project=${PROJECT}" 2>/dev/null) || exit 1

   # Check each reservation for path conflict (excluding our own)
   # A reservation conflicts if:
   #   1. It's held by a different agent
   #   2. Its path_pattern matches the file being edited
   #   3. It's exclusive
   CONFLICT=$(echo "$RESPONSE" | jq -r --arg path "$REL_PATH" --arg us "$OUR_AGENT_ID" '
       .reservations[]
       | select(.agent_id != $us)
       | select(.is_active == true)
       | select(.exclusive == true)
       | select(
           ($path | startswith(.path_pattern)) or
           (.path_pattern | endswith("*") and ($path | startswith(.path_pattern | rtrimstr("*")))) or
           (.path_pattern == $path)
       )
       | {held_by: .agent_id, reason: .reason, expires_at: .expires_at, pattern: .path_pattern}
   ' 2>/dev/null | head -1) || CONFLICT=""

   # If we got a conflict with just agent_id, try to resolve the name
   if [[ -n "$CONFLICT" ]]; then
       HELD_BY_ID=$(echo "$CONFLICT" | jq -r '.held_by // empty' 2>/dev/null) || HELD_BY_ID=""
       if [[ -n "$HELD_BY_ID" ]]; then
           AGENTS_RESPONSE=$(intermute_curl GET "/api/agents" 2>/dev/null) || AGENTS_RESPONSE=""
           HELD_BY_NAME=$(echo "$AGENTS_RESPONSE" | jq -r --arg id "$HELD_BY_ID" \
               '.agents[] | select(.agent_id == $id) | .name // .agent_id' 2>/dev/null) || HELD_BY_NAME="$HELD_BY_ID"
           CONFLICT=$(echo "$CONFLICT" | jq --arg name "$HELD_BY_NAME" '.held_by = $name' 2>/dev/null) || true
       fi
   fi

   # Output conflict (empty string means no conflict)
   echo "$CONFLICT"
   exit 0
   ```

3. Make both scripts executable: `chmod +x hooks/pre-edit.sh scripts/interlock-check.sh`

**Acceptance criteria:**
- [ ] PreToolUse:Edit hook: advisory warning (not blocking) with structured recovery message
- [ ] Hook skips silently if `INTERMUTE_AGENT_ID` not set (not in coordination mode)
- [ ] If previously connected and intermute becomes unreachable, emits one-time warning
- [ ] Subsequent unreachable checks are silent (flag file removed after first warning)
- [ ] Exit 0 always -- never blocks the Edit operation
- [ ] `bash -n hooks/pre-edit.sh` passes
- [ ] `bash -n scripts/interlock-check.sh` passes

---

### Task 4: Stop Hook + Cleanup Script

**Files:**
- Create: `/root/projects/interlock/hooks/stop.sh`
- Create: `/root/projects/interlock/scripts/interlock-cleanup.sh`

**Steps:**

1. Create `hooks/stop.sh`:
   ```bash
   #!/usr/bin/env bash
   # Stop hook: release all reservations and clean up temp files.
   set -euo pipefail

   # Guard: fail-open if jq is not available
   command -v jq &>/dev/null || exit 0

   # Read hook input
   INPUT=$(cat)

   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
   source "${SCRIPT_DIR}/lib.sh"

   # Skip if not in coordination mode
   [[ -n "${INTERMUTE_AGENT_ID:-}" ]] || exit 0

   # Guard: if stop hook is already active, don't re-trigger
   STOP_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null) || STOP_ACTIVE="false"
   [[ "$STOP_ACTIVE" != "true" ]] || exit 0

   SESSION_ID="${CLAUDE_SESSION_ID:-unknown}"

   # Delegate cleanup to helper script (best effort)
   "${SCRIPT_DIR}/../scripts/interlock-cleanup.sh" \
       "$INTERMUTE_AGENT_ID" "$SESSION_ID" 2>/dev/null || true

   exit 0
   ```

2. Create `scripts/interlock-cleanup.sh`:
   ```bash
   #!/usr/bin/env bash
   # Release all reservations and clean up temp files.
   # Args: $1 = agent_id, $2 = session_id
   # Exit: 0 always (best effort cleanup)
   set -euo pipefail

   AGENT_ID="${1:?agent_id required}"
   SESSION_ID="${2:?session_id required}"

   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
   source "${SCRIPT_DIR}/../hooks/lib.sh"

   # Get agent's active reservations
   RESERVATIONS=$(intermute_curl GET "/api/reservations?agent=${AGENT_ID}" 2>/dev/null) || RESERVATIONS=""

   # Release each reservation
   if [[ -n "$RESERVATIONS" ]]; then
       echo "$RESERVATIONS" | jq -r '.reservations[]? | select(.is_active == true) | .id' 2>/dev/null | while read -r RES_ID; do
           [[ -n "$RES_ID" ]] || continue
           intermute_curl DELETE "/api/reservations/${RES_ID}" \
               -H "Content-Type: application/json" \
               -d "$(jq -n --arg aid "$AGENT_ID" '{agent_id: $aid}')" \
               2>/dev/null || true
       done
   fi

   # Clean up temp files
   rm -f "$(agent_file_path "$SESSION_ID")" 2>/dev/null || true
   rm -f "$(connected_flag_path "$SESSION_ID")" 2>/dev/null || true

   # Clean up stale temp files from previous sessions (>60 min old)
   find /tmp -maxdepth 1 -name 'interlock-agent-*.json' -mmin +60 -delete 2>/dev/null || true
   find /tmp -maxdepth 1 -name 'interlock-connected-*' -mmin +60 -delete 2>/dev/null || true

   exit 0
   ```

3. Make both scripts executable: `chmod +x hooks/stop.sh scripts/interlock-cleanup.sh`

**Acceptance criteria:**
- [ ] Stop hook: releases all reservations held by this agent
- [ ] Stop hook: removes `/tmp/interlock-agent-${SESSION_ID}.json`
- [ ] Stop hook: removes `/tmp/interlock-connected-${SESSION_ID}` flag
- [ ] Stop hook: cleans up stale temp files from crashed sessions (>60 min old)
- [ ] Stop hook: skips if `INTERMUTE_AGENT_ID` not set
- [ ] Stop hook: respects `stop_hook_active` guard (prevents re-trigger)
- [ ] On intermute unreachable: best effort, exit 0
- [ ] `bash -n hooks/stop.sh` passes
- [ ] `bash -n scripts/interlock-cleanup.sh` passes

---

### Task 5: Tests + Validation

**Files:**
- Create: `/root/projects/interlock/tests/structural/test_hooks.py`

**Steps:**

1. Write structural tests in `test_hooks.py` (pytest, same pattern as Clavain's `tests/structural/`):
   ```python
   """Structural tests for interlock hooks."""
   import json
   import os
   import subprocess

   PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
   HOOKS_DIR = os.path.join(PLUGIN_ROOT, "hooks")
   SCRIPTS_DIR = os.path.join(PLUGIN_ROOT, "scripts")

   def test_hooks_json_valid():
       """hooks.json is valid JSON with expected structure."""
       with open(os.path.join(HOOKS_DIR, "hooks.json")) as f:
           data = json.load(f)
       assert "hooks" in data
       assert "SessionStart" in data["hooks"]
       assert "PreToolUse" in data["hooks"]
       assert "Stop" in data["hooks"]

   def test_hooks_json_pretooluse_matcher():
       """PreToolUse hook matches Edit tool."""
       with open(os.path.join(HOOKS_DIR, "hooks.json")) as f:
           data = json.load(f)
       pretool = data["hooks"]["PreToolUse"]
       assert len(pretool) == 1
       assert pretool[0]["matcher"] == "Edit"

   def test_hooks_json_sessionstart_async():
       """SessionStart hook is async (network call)."""
       with open(os.path.join(HOOKS_DIR, "hooks.json")) as f:
           data = json.load(f)
       ss = data["hooks"]["SessionStart"]
       assert ss[0]["hooks"][0].get("async") is True

   def test_hook_scripts_exist():
       """All hook scripts referenced in hooks.json exist."""
       expected = ["session-start.sh", "pre-edit.sh", "stop.sh"]
       for name in expected:
           path = os.path.join(HOOKS_DIR, name)
           assert os.path.isfile(path), f"Missing hook script: {name}"

   def test_hook_scripts_bash_syntax():
       """All hook scripts pass bash -n syntax check."""
       for name in ["session-start.sh", "pre-edit.sh", "stop.sh", "lib.sh"]:
           path = os.path.join(HOOKS_DIR, name)
           result = subprocess.run(["bash", "-n", path], capture_output=True)
           assert result.returncode == 0, f"{name} has bash syntax errors: {result.stderr.decode()}"

   def test_helper_scripts_exist():
       """All helper scripts exist."""
       expected = ["interlock-register.sh", "interlock-check.sh", "interlock-cleanup.sh"]
       for name in expected:
           path = os.path.join(SCRIPTS_DIR, name)
           assert os.path.isfile(path), f"Missing helper script: {name}"

   def test_helper_scripts_bash_syntax():
       """All helper scripts pass bash -n syntax check."""
       for name in ["interlock-register.sh", "interlock-check.sh", "interlock-cleanup.sh"]:
           path = os.path.join(SCRIPTS_DIR, name)
           result = subprocess.run(["bash", "-n", path], capture_output=True)
           assert result.returncode == 0, f"{name} has bash syntax errors: {result.stderr.decode()}"

   def test_hook_scripts_executable():
       """All hook and helper scripts are executable."""
       for dir_path, names in [
           (HOOKS_DIR, ["session-start.sh", "pre-edit.sh", "stop.sh"]),
           (SCRIPTS_DIR, ["interlock-register.sh", "interlock-check.sh", "interlock-cleanup.sh"]),
       ]:
           for name in names:
               path = os.path.join(dir_path, name)
               assert os.access(path, os.X_OK), f"{name} is not executable"

   def test_hook_scripts_source_lib():
       """All hook scripts source lib.sh."""
       for name in ["session-start.sh", "pre-edit.sh", "stop.sh"]:
           path = os.path.join(HOOKS_DIR, name)
           with open(path) as f:
               content = f.read()
           assert "lib.sh" in content, f"{name} does not source lib.sh"

   def test_hooks_exit_zero():
       """All hook scripts end with 'exit 0'."""
       for name in ["session-start.sh", "pre-edit.sh", "stop.sh"]:
           path = os.path.join(HOOKS_DIR, name)
           with open(path) as f:
               lines = f.read().strip().split('\n')
           assert lines[-1].strip() == "exit 0", f"{name} does not end with 'exit 0'"

   def test_join_flag_check():
       """SessionStart hook checks join flag before registration."""
       path = os.path.join(HOOKS_DIR, "session-start.sh")
       with open(path) as f:
           content = f.read()
       assert "is_joined" in content or "intermute-joined" in content, \
           "SessionStart hook must check join flag"

   def test_pretooluse_checks_agent_id():
       """PreToolUse hook checks INTERMUTE_AGENT_ID."""
       path = os.path.join(HOOKS_DIR, "pre-edit.sh")
       with open(path) as f:
           content = f.read()
       assert "INTERMUTE_AGENT_ID" in content, \
           "PreToolUse hook must check INTERMUTE_AGENT_ID"

   def test_stop_hook_checks_agent_id():
       """Stop hook checks INTERMUTE_AGENT_ID."""
       path = os.path.join(HOOKS_DIR, "stop.sh")
       with open(path) as f:
           content = f.read()
       assert "INTERMUTE_AGENT_ID" in content, \
           "Stop hook must check INTERMUTE_AGENT_ID"

   def test_stop_hook_active_guard():
       """Stop hook checks stop_hook_active to prevent re-trigger."""
       path = os.path.join(HOOKS_DIR, "stop.sh")
       with open(path) as f:
           content = f.read()
       assert "stop_hook_active" in content, \
           "Stop hook must guard against re-trigger"

   def test_connectivity_loss_warning():
       """PreToolUse hook emits one-time warning on connectivity loss."""
       path = os.path.join(HOOKS_DIR, "pre-edit.sh")
       with open(path) as f:
           content = f.read()
       assert "coordination lost" in content.lower() or "connected" in content.lower(), \
           "PreToolUse hook must handle connectivity loss"

   def test_helper_scripts_delegate_pattern():
       """Hook scripts delegate to scripts/ helpers (not direct curl)."""
       for hook_name, script_name in [
           ("session-start.sh", "interlock-register"),
           ("pre-edit.sh", "interlock-check"),
           ("stop.sh", "interlock-cleanup"),
       ]:
           path = os.path.join(HOOKS_DIR, hook_name)
           with open(path) as f:
               content = f.read()
           assert script_name in content, \
               f"{hook_name} must delegate to {script_name}"
           # Hooks should NOT contain direct curl calls
           assert "curl " not in content or "intermute_curl" in content, \
               f"{hook_name} should delegate to scripts, not call curl directly"
   ```

2. Verify all tests run and pass:
   ```bash
   cd /root/projects/interlock && uv run pytest tests/structural/test_hooks.py -v
   ```

3. Run `bash -n` on all scripts as final validation:
   ```bash
   bash -n hooks/session-start.sh && bash -n hooks/pre-edit.sh && bash -n hooks/stop.sh
   bash -n hooks/lib.sh
   bash -n scripts/interlock-register.sh && bash -n scripts/interlock-check.sh && bash -n scripts/interlock-cleanup.sh
   ```

**Acceptance criteria:**
- [ ] All 16 structural tests pass
- [ ] All scripts pass `bash -n` syntax check
- [ ] All scripts are executable
- [ ] No direct `curl` calls in hook scripts (only in lib.sh and helper scripts)
- [ ] Test file follows Clavain's pytest conventions (same pattern as `tests/structural/`)

---

## File Summary

### New files (8):
| File | Purpose |
|------|---------|
| `hooks/hooks.json` | Declarative hook registration (SessionStart, PreToolUse:Edit, Stop) |
| `hooks/lib.sh` | Shared utilities (join check, curl wrapper, path helpers) |
| `hooks/session-start.sh` | SessionStart hook -- registers agent, exports env vars |
| `hooks/pre-edit.sh` | PreToolUse:Edit hook -- advisory conflict warning |
| `hooks/stop.sh` | Stop hook -- releases reservations, cleans up temp files |
| `scripts/interlock-register.sh` | Registers agent with intermute API |
| `scripts/interlock-check.sh` | Checks file path against active reservations |
| `scripts/interlock-cleanup.sh` | Releases all reservations, removes temp files |

### Existing files (0 modified):
No modifications to existing files. All work is in the new interlock plugin repo.

---

## Pre-flight Checklist

- [ ] Verify `/root/projects/interlock/` exists or create it
- [ ] Verify `/root/projects/interlock/hooks/` and `/root/projects/interlock/scripts/` directories exist
- [ ] Verify `.claude-plugin/plugin.json` exists in interlock repo
- [ ] Verify `jq` is installed: `command -v jq`
- [ ] Verify `curl` is installed: `command -v curl`
- [ ] Read intermute agent registration API: `/root/projects/intermute/internal/http/handlers_agents.go`
- [ ] Read intermute reservation API: `/root/projects/intermute/internal/http/handlers_reservations.go`

## Post-execution Checklist

- [ ] All 8 files created in correct locations
- [ ] `python3 -c "import json; json.load(open('hooks/hooks.json'))"` passes
- [ ] `bash -n` passes on all 6 `.sh` files
- [ ] All `.sh` files are executable (`chmod +x`)
- [ ] All 16 structural tests pass: `uv run pytest tests/structural/test_hooks.py -v`
- [ ] No direct `curl` calls in hook scripts (only in `lib.sh` helper and `scripts/`)
- [ ] All hooks exit 0 unconditionally (graceful degradation)
- [ ] SessionStart respects join-flag gating
- [ ] PreToolUse:Edit is advisory-only (no `decision: "block"`)
- [ ] Stop hook cleans up all temp files
- [ ] Bead Clavain-8wy9 updated with completion status
