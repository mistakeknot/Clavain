# Safety Review: intermute + Clavain Integration Brainstorm

**Date:** 2026-02-14
**Reviewer:** fd-safety
**Document:** `docs/brainstorms/2026-02-14-intermute-clavain-integration-brainstorm.md`
**Risk Classification:** High

---

## Executive Summary

This integration introduces **exploitable security boundaries** and **irreversible failure modes** in a multi-session local development environment. While the system is not network-facing, the threat model includes **multiple untrusted Claude Code sessions** running concurrently as the same user (claude-user) with no privilege separation.

**Critical findings:**
1. **Port 7338 is an unauthenticated trust boundary** — hooks blindly trust localhost responses
2. **Signal file injection via /tmp** — world-writable directory enables fake events
3. **Reservation bypass via Edit tool** — agents can circumvent PreToolUse hook checks
4. **Credential leakage via signal files** — reservation metadata may expose file paths, agent names, or session contexts
5. **Irreversible state corruption** — no rollback mechanism for bad reservations or orphaned locks
6. **No deployment safety mechanisms** — crash recovery is undefined

---

## Threat Model

### Environment

- **System:** Local development server (`ethics-gradient`)
- **User:** All Claude Code sessions run as `claude-user` (non-root, no privilege separation between sessions)
- **Network:** intermute binds to `localhost:7338` (not exposed externally)
- **Concurrency:** 2-10+ simultaneous `cc` sessions in tmux panes, plus N subagents dispatched via `/clodex`
- **Persistence:** SQLite DB at `/var/lib/intermute/intermute.db` (shared state)

### Trust Boundaries

1. **Hook → intermute HTTP API** (unauthenticated localhost)
2. **Agent → signal files in /tmp** (world-writable)
3. **PreToolUse hook → Edit tool call** (bypassable)
4. **intermute DB → filesystem reservation enforcement** (no kernel-level enforcement)

### Attack Surface

- **Malicious sessions:** One Claude Code session can impersonate another, inject fake signals, or squat on port 7338
- **Stale state:** Crashed sessions leave orphaned reservations with no guaranteed cleanup
- **Race conditions:** Signal file writes + reads are not atomic
- **Denial of service:** An agent can reserve `**/*` and starve all other agents

---

## Security Findings

### 1. Port 7338 Trust Boundary (CRITICAL)

**Issue:** Hooks in `session-start.sh` and `PreToolUse:Edit` call `http://localhost:7338` without verifying that intermute is the process responding.

**Attack scenario:**
```bash
# Malicious session in another tmux pane
$ nc -l 7338  # Listen on intermute's port before the real service starts
# Or:
$ python3 -m http.server 7338  # Return fake JSON responses
```

**Impact:**
- **Agent registration hijacking:** Fake server returns arbitrary `agent_id`, breaking reservation logic
- **Reservation bypass:** Fake `/api/reservations/check` always returns `{"conflict": false}`
- **Data exfiltration:** Malicious server logs all reservation requests (file paths, reasons, session IDs)

**Mitigation:**

1. **Add authentication layer:**
   ```bash
   # In session-start.sh
   INTERMUTE_TOKEN=$(cat /var/lib/intermute/.token)  # Generated at service start
   curl -H "Authorization: Bearer ${INTERMUTE_TOKEN}" ...
   ```

2. **Verify server identity via challenge-response:**
   ```bash
   # intermute returns a signed challenge in /health response
   HEALTH_RESP=$(curl -sf http://localhost:7338/health)
   SIGNATURE=$(echo "$HEALTH_RESP" | jq -r '.signature')
   # Verify signature against known intermute public key
   ```

3. **Use Unix domain socket instead of TCP:**
   ```bash
   # intermute listens on /var/run/intermute.sock (mode 0660, group claude-user)
   curl --unix-socket /var/run/intermute.sock http://localhost/api/agents
   ```
   - **Benefit:** Kernel enforces file permissions, no port-squat risk
   - **Trade-off:** Requires Go http.Server to support unix sockets (trivial: `net.Listen("unix", ...)`)

**Residual risk if not fixed:** HIGH — any local process can intercept coordination protocol.

---

### 2. Signal File Injection (HIGH)

**Issue:** Signal files in `/tmp/intermute-signal-{project-slug}-{agent-id}.json` are world-writable by default (inherits `/tmp` permissions: `drwxrwxrwt`).

**Attack scenario:**
```bash
# Malicious session writes fake signal file
cat > /tmp/intermute-signal-Clavain-abc123.json <<EOF
{
  "type": "reservation.released",
  "agent": "TrustedAgent",
  "path": "src/critical.go",
  "timestamp": "2026-02-14T12:00:00Z"
}
EOF
```

**Impact:**
- **interline shows false status** — agent believes file is available when it's actually reserved
- **Reservation bypass** — agent edits file thinking it's safe
- **Social engineering** — fake messages from trusted agents

**Mitigation:**

1. **Use a dedicated signal directory with restricted permissions:**
   ```bash
   # In intermute startup
   mkdir -p /var/run/intermute/signals
   chmod 0700 /var/run/intermute/signals  # Only intermute process can write
   chown intermute:intermute /var/run/intermute/signals
   ```

2. **Sign signal files with HMAC:**
   ```go
   // internal/signal/signal.go
   func (sw *SignalWriter) Emit(event SignalEvent) error {
       payload, _ := json.Marshal(event)
       mac := hmac.New(sha256.New, sw.secretKey)
       mac.Write(payload)
       signed := SignedSignal{Payload: event, Signature: hex.EncodeToString(mac.Sum(nil))}
       return os.WriteFile(sw.path, json.Marshal(signed), 0644)
   }
   ```
   - Hooks verify signature before trusting signal content
   - Secret key generated at intermute startup, stored in `/var/lib/intermute/.signal-key` (mode 0600)

3. **Use inotify on the intermute DB file instead of signal files:**
   - Hooks watch `/var/lib/intermute/intermute.db` for mtime changes
   - On change, query API to get latest state
   - **Trade-off:** More API calls, but eliminates signal injection vector

**Residual risk if not fixed:** MEDIUM — requires local shell access, but trivial to exploit.

---

### 3. Edit Tool Reservation Bypass (HIGH)

**Issue:** PreToolUse hooks are advisory, not mandatory. An agent can call the Edit tool directly if:
- The hook crashes or times out
- The agent uses a subagent without the Clavain plugin loaded
- The hook is disabled via `.claude/settings.json`

**Attack scenario:**
```bash
# Agent A reserves src/router.go
# Agent B's session has Clavain uninstalled or hook disabled
Agent B: Edit(file_path="src/router.go", old_string="...", new_string="...")
# Edit succeeds, overwrites Agent A's work
```

**Impact:**
- **Merge conflicts** — destructive overwrites of in-progress work
- **Data loss** — no git commit means lost edits
- **Coordination failure** — reservation system is useless if not enforced

**Mitigation:**

1. **Git-level enforcement (must-have):**
   ```bash
   # .git/hooks/pre-commit (generated by intermute)
   CHANGED_FILES=$(git diff --cached --name-only)
   for file in $CHANGED_FILES; do
       CONFLICT=$(curl -sf "http://localhost:7338/api/reservations/check?project=$(pwd)&path=${file}")
       if echo "$CONFLICT" | jq -e '.conflict == true' >/dev/null; then
           echo "ERROR: $file is reserved by $(echo "$CONFLICT" | jq -r '.held_by')"
           exit 1
       fi
   done
   ```
   - **Benefit:** Kernel-enforced (git won't commit without pre-commit success)
   - **Trade-off:** Agents must commit to trigger check (doesn't prevent Edit, only commit)

2. **intermute-aware Edit wrapper skill:**
   ```markdown
   # skills/safe-edit/SKILL.md
   Before calling Edit tool:
   1. Call intermute_check_conflicts(file_path)
   2. If conflict, prompt user or auto-reserve
   3. Then call Edit
   ```
   - **Trade-off:** Relies on agent discipline, not enforcement

3. **Filesystem-level enforcement (Linux inotify):**
   - intermute sets files as read-only when reserved by another agent
   - Hooks use `setfacl` or `chmod` to enforce
   - **Trade-off:** Requires elevated privileges, complex cleanup

**Recommended:** Git pre-commit hook (1) + safe-edit skill (2) as defense-in-depth.

**Residual risk if not fixed:** HIGH — reservation system is security theater without enforcement.

---

### 4. Credential Handling

**Issue:** No credentials are explicitly stored in the design, but **bearer token auth** is mentioned for intermute's existing API.

**Concerns:**

1. **Token storage location:**
   - If stored in env vars (`INTERMUTE_TOKEN`), visible in `/proc/{pid}/environ` to all claude-user processes
   - If stored in `.claude.json`, may leak via Claude Code debug logs or session export

2. **Token scope:**
   - Design mentions "project scoping" but doesn't define token issuance
   - If one token per project, rotating tokens requires updating all sessions

3. **localhost bypass:**
   - Design mentions "localhost bypass" — does this mean no auth for localhost callers?
   - If so, any local process can call intermute's HTTP API

**Mitigation:**

1. **Use Unix domain sockets (see Finding 1)** — eliminates need for bearer tokens
2. **If TCP is required:**
   - Store token in `/var/lib/intermute/.tokens/{project-slug}` (mode 0600, owner intermute)
   - Hooks read token via `sudo -u intermute cat /var/lib/intermute/.tokens/...`
   - **Trade-off:** Requires sudo passwordless rule for claude-user

3. **Disable localhost bypass:**
   - All API calls require auth, even from localhost
   - Prevents port-squat attacks from bypassing auth

**Residual risk if not addressed:** MEDIUM — depends on localhost bypass policy.

---

### 5. Signal File Content Leakage (LOW)

**Issue:** Signal files in `/tmp` may expose:
- File paths being edited (e.g., `src/auth/password_manager.go`)
- Agent names (e.g., `claude-abc123` reveals session ID prefix)
- Reservation reasons (e.g., "Fixing SQLi vulnerability in login handler")

**Impact:**
- **Information disclosure** — other users on the system can `cat /tmp/intermute-signal-*` to see what's being worked on
- **Metadata leakage** — reservation timestamps reveal work patterns

**Mitigation:**

1. **Use restricted signal directory** (see Finding 2)
2. **Encrypt signal file content:**
   ```go
   // Encrypt JSON payload with AES-GCM, key derived from INTERMUTE_SECRET
   func (sw *SignalWriter) Emit(event SignalEvent) error {
       plaintext, _ := json.Marshal(event)
       ciphertext := encrypt(plaintext, sw.key)
       return os.WriteFile(sw.path, ciphertext, 0644)
   }
   ```

**Residual risk if not fixed:** LOW — requires local shell access, but may violate confidentiality policies.

---

## Deployment & Migration Risks

### 6. intermute Crash Recovery (CRITICAL)

**Issue:** If intermute crashes mid-reservation, the SQLite DB may have:
- Orphaned reservations with `expires_at` far in the future
- Agents marked as active but their processes are dead
- No immediate cleanup mechanism until next sweep (60s interval)

**Failure scenario:**
```bash
# Agent A reserves src/*.go for 1 hour
# intermute crashes (OOM, SIGKILL, kernel panic)
# Agent A's session also crashes
# intermute restarts
# src/*.go is still reserved for 59 more minutes → other agents are blocked
```

**Impact:**
- **Deadlock** — agents wait indefinitely for stale reservations to expire
- **Manual intervention required** — human must SSH in and run `sqlite3` to delete orphaned rows

**Mitigation:**

1. **Startup sweep on intermute launch:**
   ```go
   // cmd/intermute/main.go
   func main() {
       // On startup, release all reservations older than 5 minutes
       store.ReleaseStaleReservations(5 * time.Minute)
       // Then start sweep goroutine
   }
   ```

2. **Graceful shutdown hook:**
   ```go
   // On SIGTERM/SIGINT, release all reservations
   func (s *Server) Shutdown(ctx context.Context) error {
       s.store.ReleaseAllReservations()  // Blanket release
       return s.httpServer.Shutdown(ctx)
   }
   ```

3. **Circuit breaker for reservation API:**
   - If 5+ reservation checks fail in 30s, assume intermute is unhealthy
   - Hooks fall back to "allow all edits" mode with a warning

**Residual risk if not fixed:** HIGH — stale locks can deadlock entire team.

---

### 7. Rollback Procedures (CRITICAL)

**Issue:** No rollback mechanism is defined for:
- Bad reservations (e.g., agent reserved `**/*` accidentally)
- Corrupted SQLite DB (write conflict during crash)
- Incompatible intermute version upgrade

**Current state:** Design has no backup/restore strategy.

**Mitigation:**

1. **DB snapshots before risky operations:**
   ```bash
   # Before intermute upgrade
   cp /var/lib/intermute/intermute.db /var/lib/intermute/intermute.db.backup-$(date +%s)
   ```

2. **Reservation expiry override API:**
   ```bash
   # Emergency release of all reservations
   curl -X POST http://localhost:7338/api/admin/release-all
   ```

3. **Rollback to empty state:**
   ```bash
   # Stop intermute, delete DB, restart (fresh state)
   systemctl stop intermute
   rm /var/lib/intermute/intermute.db
   systemctl start intermute
   ```
   - **Trade-off:** Loses all message history and agent registry

**Pre-deploy checks:**
- [ ] Test intermute startup sweep releases stale reservations
- [ ] Test circuit breaker fallback when intermute is down
- [ ] Test `release-all` API under load (10+ agents)

**Post-deploy verification:**
- [ ] Monitor `/var/log/intermute/intermute.log` for circuit breaker OPEN events
- [ ] Check SQLite DB size growth over 24h (should be <10MB for 10 agents)
- [ ] Verify signal files are cleaned up after agent Stop hooks

---

### 8. Partial Failure Handling

**Issue:** Hook execution can fail at multiple points:
- `curl` to intermute times out (network blip, intermute overloaded)
- JSON parsing fails (malformed response)
- Signal file write fails (`/tmp` is full)

**Current design:** Hooks use `curl -sf` which silently fails and continues.

**Impact:**
- **Silent degradation** — agent proceeds without reservation, causes conflict later
- **No observability** — hooks don't log failures

**Mitigation:**

1. **Explicit error handling in hooks:**
   ```bash
   # In PreToolUse:Edit hook
   if ! CONFLICT=$(curl -sf --max-time 5 "http://localhost:7338/api/reservations/check?..."); then
       echo '{"decision":"warn","message":"intermute unavailable, edit at your own risk"}'
       exit 0  # Allow edit but warn
   fi
   ```

2. **Fallback to local state file:**
   ```bash
   # If intermute is down, hooks read/write local reservation state
   LOCAL_STATE="/tmp/intermute-local-state-${SESSION_ID}.json"
   # Other sessions won't see this, but prevents self-conflict
   ```

3. **Dead letter queue for failed signals:**
   - intermute retries signal writes 3 times before logging failure
   - Failed signals written to `/var/lib/intermute/failed-signals.log` for audit

**Residual risk if not fixed:** MEDIUM — silent failures create unpredictable behavior.

---

## Additional Concerns

### 9. Auto-Reserve Default Setting (MEDIUM)

**Issue:** Design mentions optional auto-reserve on first edit (`CLAVAIN_AUTO_RESERVE=true`).

**Risk:** If enabled by default:
- Agent edits `package.json` to check version → auto-reserves it → blocks other agents from updating dependencies
- Agent edits `.gitignore` → blocks other agents from adding entries

**Recommendation:**
- **Default: OFF** — require explicit `intermute_reserve_files` call
- **Opt-in per workflow** — enable via environment variable or skill parameter
- **Scope to relevant files** — auto-reserve only `*.go`, `*.py`, etc., not config files

---

### 10. Reservation Granularity

**Issue:** Glob patterns (`src/*.go`) can over-reserve or under-reserve.

**Scenarios:**
- Agent reserves `src/*.go` to refactor one file → blocks all Go edits
- Agent reserves `src/router.go` → doesn't block edits to `src/router_test.go`

**Recommendation:**
- **Default to file-level** — `intermute_reserve_files(["src/router.go"])`
- **Allow glob for coordinated work** — `intermute_reserve_files(["src/auth/*"], exclusive=true, reason="Rewriting auth layer")`
- **Warning on broad patterns** — intermute logs a warning if pattern matches >10 files

---

### 11. Message Protocol Spam

**Issue:** If every reservation emits a broadcast message, agents' inboxes fill up quickly.

**Impact:**
- **Inbox clutter** — 100 reservations/hour = 100 messages
- **Signal-to-noise ratio** — important messages (blocked work) drown in reservation spam

**Recommendation:**
- **Signals only, no messages** — reservation events emit signal files, not inbox messages
- **Opt-in broadcast** — `intermute_reserve_files(..., notify=true)` to explicitly send a message

---

## Risk Summary Table

| Finding | Severity | Exploitability | Blast Radius | Mitigation Priority |
|---------|----------|----------------|--------------|---------------------|
| 1. Port 7338 trust | CRITICAL | High (trivial port squat) | High (full bypass) | Must-fix (use unix socket) |
| 2. Signal injection | HIGH | Medium (requires local access) | Medium (fake status) | Must-fix (restricted dir + HMAC) |
| 3. Edit bypass | HIGH | High (disable hook) | High (data loss) | Must-fix (git pre-commit) |
| 4. Credential leakage | MEDIUM | Low (depends on impl) | Low (info disclosure) | Should-fix (unix socket) |
| 5. Signal content leak | LOW | Low (requires shell) | Low (metadata only) | Nice-to-fix (encrypt) |
| 6. Crash recovery | CRITICAL | N/A (operational risk) | High (deadlock) | Must-fix (startup sweep) |
| 7. Rollback undefined | CRITICAL | N/A (operational risk) | High (no recovery) | Must-fix (DB snapshots + admin API) |
| 8. Partial failures | MEDIUM | N/A (reliability) | Medium (silent conflicts) | Should-fix (explicit errors) |
| 9. Auto-reserve default | MEDIUM | N/A (footgun) | Medium (over-locking) | Should-fix (default OFF) |
| 10. Glob over-reserve | LOW | N/A (usability) | Low (inconvenience) | Nice-to-fix (warnings) |
| 11. Message spam | LOW | N/A (usability) | Low (noise) | Nice-to-fix (signals only) |

---

## Recommendations

### Must-Fix Before Deployment

1. **Replace TCP with Unix domain socket** (`/var/run/intermute.sock`) — eliminates port-squat and auth complexity
2. **Move signal files to restricted directory** (`/var/run/intermute/signals/`, mode 0700) and add HMAC signatures
3. **Implement git pre-commit hook enforcement** — reservation bypass is unacceptable for multi-agent safety
4. **Add startup sweep** — release all reservations >5 minutes old on intermute launch
5. **Define rollback procedure** — DB snapshots + `release-all` admin API

### Should-Fix Before Production Use

6. **Explicit hook error handling** — warn on intermute unavailability instead of silent fallback
7. **Default auto-reserve to OFF** — require explicit reservation calls
8. **Circuit breaker for reservation API** — hooks fall back to "warn" mode after 5 consecutive failures

### Nice-to-Have Enhancements

9. **Encrypt signal file content** — prevents metadata leakage to other local users
10. **Reservation pattern warnings** — log if a glob matches >10 files
11. **Signals-only coordination** — no broadcast messages for reservation events

---

## Deployment Checklist

**Pre-deploy:**
- [ ] intermute runs as systemd service with automatic restart
- [ ] Unix socket path exists and is writable by intermute user
- [ ] DB directory has correct permissions (0700, owner intermute)
- [ ] Startup sweep tested with synthetic stale reservations

**Post-deploy (first hour):**
- [ ] Monitor `/var/log/intermute/intermute.log` for startup sweep activity
- [ ] Check signal file directory permissions (`ls -la /var/run/intermute/signals/`)
- [ ] Test reservation conflict with two live sessions
- [ ] Verify git pre-commit hook blocks conflicting commits

**Post-deploy (first day):**
- [ ] Check SQLite DB size growth
- [ ] Verify no orphaned reservations after intentional crash test
- [ ] Audit signal files for correct HMAC signatures
- [ ] Test rollback: stop service, restore DB backup, restart

---

## Threat Model Revisited

**Original assumption:** Local development, trusted users.

**Reality check:** Multiple Claude Code sessions are **semi-autonomous agents** with:
- No human oversight during subagent dispatch
- Access to the same filesystem, ports, and credentials
- Potential to accidentally or intentionally interfere with each other

**Revised threat model:** Treat concurrent sessions as **untrusted peers** requiring:
- Cryptographic proof of identity (HMAC signatures, unix socket permissions)
- Kernel-level enforcement (git hooks, file permissions)
- Explicit error boundaries (circuit breakers, rollback procedures)

---

## Conclusion

This integration is **deployable with critical fixes** but **not safe in current form**. The use of TCP localhost without authentication, world-writable signal files, and advisory-only reservation checks creates exploitable attack vectors and irreversible failure modes.

**Priority fixes (blocking deployment):**
1. Unix domain socket for intermute API
2. Restricted signal directory with HMAC signatures
3. Git pre-commit hook enforcement
4. Startup sweep for stale reservations
5. Rollback procedure documentation

**With these mitigations:** Risk reduces to MEDIUM (operational discipline required, no code-level vulnerabilities).

**Without these mitigations:** Risk remains HIGH (exploitable by any local process, data loss likely).

---

**Next steps:**
1. Flux-drive review of this safety analysis
2. Refine design to incorporate must-fix mitigations
3. Prototype unix socket + HMAC signal implementation
4. Write pre-deploy test suite for crash recovery scenarios
