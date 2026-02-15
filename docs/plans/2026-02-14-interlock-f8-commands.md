# F8: Interlock Commands — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Create four Claude Code slash commands for the interlock companion plugin — `/interlock:join`, `/interlock:leave`, `/interlock:status`, and `/interlock:setup` — providing explicit multi-agent coordination management.

**Bead:** Clavain-ct6u

**PRD:** `docs/prds/2026-02-14-interlock-multi-agent-coordination.md` (F8)

**Target repo:** `/root/projects/interlock/`

---

### Task 1: `/interlock:join` Command

**Files:**
- Create: `/root/projects/interlock/commands/join.md`

**Content spec:**

Frontmatter: `name: join`, `description: Register this agent for multi-agent coordination — sets name, creates onboarding flag, shows active agents`, `argument-hint: "[--name <label>]"`.

The command instructs Claude to:

1. **Parse arguments.** Read `$ARGUMENTS` for `--name <label>`. If present, use `<label>` as the agent name.

2. **Resolve agent name** with this precedence:
   - User-provided `--name <label>` (from arguments)
   - tmux pane title: `tmux display-message -p '#T' 2>/dev/null` (use if non-empty and not the default shell name)
   - Fallback: `claude-${CLAUDE_SESSION_ID:0:8}`

3. **Ensure config directory exists:**
   ```bash
   mkdir -p ~/.config/clavain
   ```

4. **Check if intermute is reachable.** Try the Unix socket first, fall back to TCP:
   ```bash
   INTERMUTE_SOCKET="${INTERMUTE_SOCKET:-/var/run/intermute.sock}"
   INTERMUTE_URL="${INTERMUTE_URL:-http://localhost:7890}"
   if [ -S "$INTERMUTE_SOCKET" ]; then
       curl -sf --unix-socket "$INTERMUTE_SOCKET" http://localhost/health
   else
       curl -sf "$INTERMUTE_URL/health"
   fi
   ```
   If unreachable, tell the user to run `/interlock:setup` first and stop.

5. **Register agent** by calling `scripts/interlock-register.sh` (delegates to `POST /api/agents`):
   ```bash
   "${INTERLOCK_ROOT:-$(dirname "$(readlink -f "$0")")/..}/scripts/interlock-register.sh" \
       --name "$AGENT_NAME" \
       --session "$CLAUDE_SESSION_ID" \
       --project "$(pwd)"
   ```
   The script outputs JSON with `id` and `name` fields.

6. **Create flag files:**
   ```bash
   touch ~/.config/clavain/intermute-joined
   echo "$AGENT_NAME" > ~/.config/clavain/intermute-agent-name
   ```

7. **List active agents** by calling `GET /api/agents` and display as a table:
   ```
   Joined coordination as "<name>"

   Active Agents:
   | Name           | Agent ID (short) | Last Seen |
   |----------------|-------------------|-----------|
   | claude-a1b2c3d4 | a1b2c3d4         | just now  |
   | planner         | e5f6g7h8         | 2m ago    |
   ```

8. **Report next steps:** Mention that coordination is now active — the SessionStart hook will auto-register on future sessions, and the pre-commit hook will enforce file reservations.

**Acceptance criteria:**
- [ ] Frontmatter has `name`, `description`, `argument-hint`
- [ ] Name precedence: `--name` > tmux pane title > `claude-${CLAUDE_SESSION_ID:0:8}`
- [ ] Creates `~/.config/clavain/intermute-joined` flag
- [ ] Creates `~/.config/clavain/intermute-agent-name` with chosen name
- [ ] Delegates registration to `scripts/interlock-register.sh`
- [ ] Lists active agents after joining
- [ ] Fails gracefully if intermute unreachable

---

### Task 2: `/interlock:leave` Command

**Files:**
- Create: `/root/projects/interlock/commands/leave.md`

**Content spec:**

Frontmatter: `name: leave`, `description: Leave multi-agent coordination — release all reservations, deregister, remove onboarding flag`.

The command instructs Claude to:

1. **Check if currently joined:**
   ```bash
   if [ ! -f ~/.config/clavain/intermute-joined ]; then
       echo "Not currently joined. Nothing to do."
   fi
   ```
   If not joined, inform the user and stop.

2. **Release all reservations and deregister** by calling `scripts/interlock-cleanup.sh`:
   ```bash
   "${INTERLOCK_ROOT:-$(dirname "$(readlink -f "$0")")/..}/scripts/interlock-cleanup.sh" \
       --session "$CLAUDE_SESSION_ID"
   ```
   The script calls `DELETE /api/agents/{id}/reservations` then `DELETE /api/agents/{id}`. If intermute is unreachable, the script should succeed silently (reservations expire via heartbeat timeout anyway).

3. **Remove flag files:**
   ```bash
   rm -f ~/.config/clavain/intermute-joined
   rm -f ~/.config/clavain/intermute-agent-name
   ```

4. **Clean up temp files:**
   ```bash
   rm -f /tmp/interlock-agent-${CLAUDE_SESSION_ID}.json
   ```

5. **Confirm:**
   ```
   Left coordination. Reservations released, agent deregistered.
   SessionStart hook will no longer auto-register.
   ```

**Acceptance criteria:**
- [ ] Checks `~/.config/clavain/intermute-joined` before acting
- [ ] Delegates cleanup to `scripts/interlock-cleanup.sh`
- [ ] Removes `intermute-joined` and `intermute-agent-name` flag files
- [ ] Removes temp agent JSON file
- [ ] Succeeds silently if intermute is unreachable

---

### Task 3: `/interlock:status` Command

**Files:**
- Create: `/root/projects/interlock/commands/status.md`

**Content spec:**

Frontmatter: `name: status`, `description: Show active agents, their reservations, heartbeat status, and human-readable names`.

The command instructs Claude to:

1. **Determine connection method** (socket > TCP, same pattern as join).

2. **Check if intermute is reachable.** If not, report "intermute service not running" and suggest `/interlock:setup`.

3. **Fetch agents** via `GET /api/agents`:
   ```bash
   AGENTS=$(curl -sf $CURL_ARGS/api/agents)
   ```

4. **Fetch reservations** via `GET /api/reservations`:
   ```bash
   RESERVATIONS=$(curl -sf $CURL_ARGS/api/reservations)
   ```

5. **Display as formatted table** showing `(name, agent-id:8)` pairs for disambiguation:
   ```
   Interlock Status
   ────────────────────────────────────
   Agents:
   | Name             | Agent ID  | Reservations | Last Seen |
   |------------------|-----------|--------------|-----------|
   | claude-a1b2c3d4  | a1b2c3d4  | 2 files      | just now  |
   | planner          | e5f6g7h8  | 0 files      | 3m ago    |

   Reservations:
   | Pattern          | Held By          | Reason       | Expires   |
   |------------------|------------------|--------------|-----------|
   | src/router.go    | claude-a1b2c3d4  | auth refactor| in 12m    |
   | src/handler.go   | claude-a1b2c3d4  | auth refactor| in 12m    |
   ────────────────────────────────────
   ```

6. **Show own status** if currently joined:
   ```bash
   if [ -f ~/.config/clavain/intermute-joined ]; then
       MY_NAME=$(cat ~/.config/clavain/intermute-agent-name 2>/dev/null || echo "unknown")
       echo "You are: $MY_NAME"
   else
       echo "You are not joined. Run /interlock:join to participate."
   fi
   ```

**Acceptance criteria:**
- [ ] Shows agents table with `(name, agent-id:8)` pairs
- [ ] Shows reservations table with holder, pattern, reason, expiry
- [ ] Indicates own agent identity if joined
- [ ] Handles intermute unreachable gracefully

---

### Task 4: `/interlock:setup` Command

**Files:**
- Create: `/root/projects/interlock/commands/setup.md`

**Content spec:**

Frontmatter: `name: setup`, `description: Self-installing setup — check/download intermute binary, create systemd unit, start service, verify health`.

The command instructs Claude to perform these steps in order:

1. **Check if intermute binary exists:**
   ```bash
   command -v intermute || ls ~/.local/bin/intermute 2>/dev/null || ls /usr/local/bin/intermute 2>/dev/null
   ```

2. **If not found, download or build:**
   - Check if Go is installed (`command -v go`). If yes, offer to build from source:
     ```bash
     cd /root/projects/intermute && go build -o ~/.local/bin/intermute ./cmd/intermute/
     ```
   - If Go not installed, download pre-built binary from GitHub releases:
     ```bash
     ARCH=$(uname -m)
     case "$ARCH" in x86_64) ARCH="amd64";; aarch64) ARCH="arm64";; esac
     curl -fsSL "https://github.com/<org>/intermute/releases/latest/download/intermute-linux-${ARCH}" \
         -o ~/.local/bin/intermute
     chmod +x ~/.local/bin/intermute
     ```
   - Verify binary works: `intermute --version`

3. **Create systemd unit** (only if it doesn't exist):
   ```bash
   if [ ! -f ~/.config/systemd/user/intermute.service ]; then
       mkdir -p ~/.config/systemd/user
   fi
   ```
   Write `intermute.service` with:
   - `ExecStart` pointing to the binary with `--socket /var/run/intermute.sock --port 7890`
   - `Restart=on-failure`
   - `Environment=INTERMUTE_DB=~/.local/share/intermute/intermute.db`

   Note: If running as root (common on this server), use system-level systemd (`/etc/systemd/system/intermute.service`) instead of user-level. Check with `whoami`.

4. **Create data directory:**
   ```bash
   mkdir -p ~/.local/share/intermute
   ```

5. **Start service:**
   ```bash
   systemctl daemon-reload
   systemctl enable intermute.service
   systemctl start intermute.service
   ```

6. **Verify health endpoint:**
   ```bash
   sleep 1
   curl -sf http://localhost:7890/health || curl -sf --unix-socket /var/run/intermute.sock http://localhost/health
   ```

7. **Report result:**
   ```
   intermute Setup Complete
   ────────────────────────
   Binary:   ~/.local/bin/intermute (vX.Y.Z)
   Service:  intermute.service (active)
   Socket:   /var/run/intermute.sock
   TCP:      http://localhost:7890
   Health:   ok

   Next: Run /interlock:join to register this agent.
   ```

   If health check fails, show diagnostics:
   ```bash
   systemctl status intermute.service
   journalctl -u intermute.service --no-pager -n 20
   ```

**Acceptance criteria:**
- [ ] Checks for existing intermute binary before downloading
- [ ] Supports both Go build-from-source and pre-built binary download
- [ ] Creates systemd unit file with socket + TCP listener
- [ ] Starts and enables the service
- [ ] Verifies health endpoint
- [ ] Shows diagnostic info on failure

---

## Pre-flight Checklist
- [ ] Verify `/root/projects/interlock/` exists (or will be created as part of plugin scaffolding)
- [ ] Verify `commands/` directory exists in target repo
- [ ] Confirm intermute API endpoints: `GET /api/agents`, `POST /api/agents`, `GET /api/reservations`, `DELETE /api/agents/{id}`, `/health`
- [ ] Confirm scripts referenced (`interlock-register.sh`, `interlock-cleanup.sh`) exist or are planned in another feature

## Post-execution Checklist
- [ ] 4 command files created: `join.md`, `leave.md`, `status.md`, `setup.md`
- [ ] All files have correct YAML frontmatter (`name`, `description`)
- [ ] `join.md` has `argument-hint` for `--name`
- [ ] All commands handle intermute-unreachable gracefully
- [ ] Name precedence implemented in `join.md`: `--name` > tmux > session fallback
- [ ] Flag file lifecycle: `join` creates, `leave` removes
- [ ] `status.md` shows `(name, agent-id:8)` pairs
- [ ] Bead Clavain-ct6u updated with completion status
