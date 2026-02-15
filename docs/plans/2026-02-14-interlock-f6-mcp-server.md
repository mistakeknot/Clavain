# Interlock F6 MCP Server — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Build a thin MCP stdio server (Go binary) that wraps intermute's HTTP/socket API, exposing 9 tools for file reservation, conflict checking, messaging, and agent coordination. Ship as a new companion plugin at `/root/projects/interlock/`.

**Architecture:** Single Go binary (`cmd/interlock-mcp/main.go`) using `mark3labs/mcp-go` for MCP stdio transport. HTTP client connects to intermute via Unix socket (fallback to TCP). Each MCP tool maps 1:1 to intermute API endpoints. Plugin structure follows the companion plugin conventions (interpath, interwatch, interflux).

**Tech Stack:** Go 1.22 (binary), Python (structural tests), Bash (scripts)

**Bead:** Clavain-kfvq
**Phase:** planned
**PRD:** (F6 acceptance criteria in task context)

**Research:** `docs/research/write-f6-mcp-server-plan.md`

---

## File Layout

```
/root/projects/interlock/
  .claude-plugin/
    plugin.json                    # Plugin manifest with MCP server declaration
  cmd/
    interlock-mcp/
      main.go                      # MCP server entry point + tool registration
  internal/
    client/
      client.go                    # intermute HTTP client (Unix socket + TCP fallback)
      client_test.go               # Client unit tests with mock HTTP server
    tools/
      reserve.go                   # reserve_files, release_files, release_all tools
      conflicts.go                 # check_conflicts, my_reservations tools
      messaging.go                 # send_message, fetch_inbox, request_release tools
      agents.go                    # list_agents tool
      tools_test.go                # Tool handler tests
      errors.go                    # Shared error response helpers
  scripts/
    interlock.sh                   # Discovery marker file
    build.sh                       # Build the Go binary
  bin/
    .gitkeep                       # Binary dir (interlock-mcp binary is gitignored)
  tests/
    structural/
      conftest.py                  # Shared fixtures
      helpers.py                   # Test helpers
      test_structure.py            # Plugin structure validation
      test_tools.py                # MCP tool schema validation
    pyproject.toml                 # pytest config
  go.mod                           # Go module definition
  go.sum                           # Dependency checksums
  CLAUDE.md                        # Quick reference
  AGENTS.md                        # Development guide
  LICENSE                          # MIT
  README.md                        # Public documentation
  .gitignore                       # bin/interlock-mcp, tests/.venv, etc.
```

---

### Task 1: Scaffold Plugin Structure + Go Module

**Files:**
- Create: `/root/projects/interlock/.claude-plugin/plugin.json`
- Create: `/root/projects/interlock/go.mod`
- Create: `/root/projects/interlock/scripts/interlock.sh`
- Create: `/root/projects/interlock/scripts/build.sh`
- Create: `/root/projects/interlock/bin/.gitkeep`
- Create: `/root/projects/interlock/.gitignore`
- Create: `/root/projects/interlock/LICENSE`
- Create: `/root/projects/interlock/CLAUDE.md`
- Create: `/root/projects/interlock/README.md`

**Steps:**

1. Create the repository directory and initialize git:
   ```bash
   mkdir -p /root/projects/interlock
   cd /root/projects/interlock && git init
   ```

2. Create `.claude-plugin/plugin.json`:
   ```json
   {
     "name": "interlock",
     "version": "0.1.0",
     "description": "MCP server for intermute file reservation and agent coordination. 9 tools: reserve, release, conflict check, messaging, agent listing. Companion plugin for Clavain.",
     "author": {
       "name": "mistakeknot"
     },
     "license": "MIT",
     "keywords": [
       "mcp",
       "file-reservation",
       "agent-coordination",
       "intermute",
       "multi-agent",
       "conflict-prevention"
     ],
     "mcpServers": {
       "interlock": {
         "type": "stdio",
         "command": "${CLAUDE_PLUGIN_ROOT}/bin/interlock-mcp",
         "args": [],
         "env": {
           "INTERMUTE_SOCKET": "/var/run/intermute.sock",
           "INTERMUTE_URL": "http://127.0.0.1:7338"
         }
       }
     }
   }
   ```

3. Initialize Go module:
   ```bash
   cd /root/projects/interlock
   go mod init github.com/mistakeknot/interlock
   ```

4. Create `scripts/interlock.sh` (discovery marker):
   ```bash
   #!/usr/bin/env bash
   # Marker file for Clavain companion plugin discovery.
   # Presence of this file signals that Interlock MCP server is available.
   echo "interlock-mcp marker"
   ```
   Make executable: `chmod +x scripts/interlock.sh`

5. Create `scripts/build.sh`:
   ```bash
   #!/usr/bin/env bash
   # Build the interlock-mcp binary.
   set -euo pipefail
   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
   PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
   cd "$PROJECT_ROOT"
   echo "Building interlock-mcp..."
   go build -o bin/interlock-mcp ./cmd/interlock-mcp/
   echo "Built: bin/interlock-mcp"
   ```
   Make executable: `chmod +x scripts/build.sh`

6. Create `.gitignore`:
   ```
   bin/interlock-mcp
   tests/.venv/
   tests/.pytest_cache/
   tests/structural/__pycache__/
   ```

7. Create `CLAUDE.md`:
   ```markdown
   # Interlock

   > See `AGENTS.md` for full development guide.

   ## Overview

   MCP server wrapping intermute's HTTP API for file reservation and agent coordination. 9 tools, 0 commands, 0 skills, 0 hooks. Companion plugin for Clavain.

   ## Quick Commands

   ```bash
   # Build binary
   bash scripts/build.sh

   # Run tests
   cd /root/projects/interlock && uv run --project tests pytest tests/structural/ -v

   # Run Go tests
   cd /root/projects/interlock && go test ./...

   # Validate structure
   python3 -c "import json; json.load(open('.claude-plugin/plugin.json'))"
   ```
   ```

8. Create `LICENSE` (MIT, same as other companions).

9. Create `README.md` with overview of 9 tools and usage instructions.

10. Commit:
    ```bash
    git add -A && git commit -m "feat: scaffold interlock plugin structure"
    ```

**Acceptance criteria:**
- [ ] `plugin.json` is valid JSON with `mcpServers.interlock` declared
- [ ] `scripts/interlock.sh` marker file exists and is executable
- [ ] `go.mod` exists with module path
- [ ] `scripts/build.sh` exists and is executable

---

### Task 2: intermute HTTP Client

**Files:**
- Create: `/root/projects/interlock/internal/client/client.go`
- Create: `/root/projects/interlock/internal/client/client_test.go`

**Steps:**

1. Create `internal/client/client.go` with:

   - `Client` struct holding `*http.Client`, `baseURL string`, `agentID string`, `projectName string`
   - `NewClient(opts ...Option) *Client` constructor with functional options:
     - `WithSocketPath(path string)` — configure Unix socket transport
     - `WithBaseURL(url string)` — configure TCP base URL
     - `WithAgentID(id string)` — set agent identity
     - `WithProject(name string)` — set project name
   - `connect()` logic: try Unix socket first (check file exists at `INTERMUTE_SOCKET` or `/var/run/intermute.sock`), fall back to TCP at `INTERMUTE_URL` or `http://127.0.0.1:7338`
   - Request methods mapping to intermute API:
     - `CreateReservation(pattern, reason string, ttlMinutes int, exclusive bool) (*Reservation, error)`
     - `DeleteReservation(id string) error`
     - `ListReservations(filters map[string]string) ([]Reservation, error)`
     - `CheckConflicts(project, pattern string) (*ConflictResult, error)`
     - `RegisterAgent(name, project string, capabilities []string, metadata map[string]string) (*Agent, error)`
     - `ListAgents(project string) ([]Agent, error)`
     - `SendMessage(to, subject, body string) error`
     - `FetchInbox(agent, project, cursor string) (*InboxResult, error)`
   - `Reservation`, `Agent`, `ConflictResult`, `InboxResult` structs
   - Error handling: HTTP 5xx returns `IntermunteError{Code, Message, RetryAfter}`, HTTP 404 on `/api/reservations/check` sets `client.hasAtomicCheck = false` for version fallback
   - All methods use `context.Context` for cancellation

2. Create `internal/client/client_test.go` with:

   - Mock HTTP server using `net/http/httptest`
   - Test `CreateReservation` success path (201 response)
   - Test `DeleteReservation` success path (204 response)
   - Test `ListReservations` with filters (200 response)
   - Test `CheckConflicts` success path (200 response)
   - Test `CheckConflicts` fallback when endpoint returns 404 (version fallback)
   - Test HTTP 5xx returns `intermuteError` with retry_after
   - Test Unix socket connection (use `httptest.NewUnstartedServer` with Unix listener)
   - Test TCP fallback when socket file doesn't exist

3. Install dependency:
   ```bash
   cd /root/projects/interlock && go mod tidy
   ```

4. Run tests:
   ```bash
   cd /root/projects/interlock && go test ./internal/client/ -v
   ```

5. Commit:
   ```bash
   git add internal/client/ go.mod go.sum
   git commit -m "feat: intermute HTTP client with socket/TCP fallback"
   ```

**Acceptance criteria:**
- [ ] Unix socket connection works when socket file exists
- [ ] TCP fallback works when socket file is absent
- [ ] HTTP 5xx returns structured `intermuteError` (never panics)
- [ ] `CheckConflicts` falls back to `ListReservations` + client-side filter on 404
- [ ] All client methods accept `context.Context`

---

### Task 3: MCP Tool Definitions + Handlers

**Files:**
- Create: `/root/projects/interlock/internal/tools/reserve.go`
- Create: `/root/projects/interlock/internal/tools/conflicts.go`
- Create: `/root/projects/interlock/internal/tools/messaging.go`
- Create: `/root/projects/interlock/internal/tools/agents.go`
- Create: `/root/projects/interlock/internal/tools/errors.go`
- Create: `/root/projects/interlock/internal/tools/tools_test.go`

**Steps:**

1. Create `internal/tools/errors.go` with shared error helpers:

   - `errorResult(msg string, code int, retryAfter int) mcp.CallToolResult` — returns MCP tool result with `isError: true` and structured JSON error content:
     ```json
     {"error": "intermute unavailable", "code": 503, "retry_after": 30}
     ```
   - `fromintermuteError(err *client.intermuteError) mcp.CallToolResult` — converts client errors to MCP format
   - `successResult(data any) mcp.CallToolResult` — JSON-encodes data as MCP text content

2. Create `internal/tools/reserve.go` with 3 tools:

   **`reserve_files`** tool:
   - Input schema: `patterns` (string array, required), `reason` (string, required), `ttl_minutes` (int, default 30), `exclusive` (bool, default true)
   - Handler: loop over patterns, call `client.CreateReservation` for each
   - Response: JSON array of reservation objects `[{id, pattern, agent, exclusive, expires_at}]`
   - On partial failure: return succeeded reservations + error for failed ones

   **`release_files`** tool:
   - Input schema: `reservation_ids` (string array, required)
   - Handler: loop over IDs, call `client.DeleteReservation` for each
   - Response: `{"released": ["id1", "id2"], "errors": [{"id": "id3", "error": "not found"}]}`

   **`release_all`** tool:
   - Input schema: (none)
   - Handler: `client.ListReservations(agent=self)`, then delete each
   - Response: `{"released_count": N}`

3. Create `internal/tools/conflicts.go` with 2 tools:

   **`check_conflicts`** tool:
   - Input schema: `patterns` (string array, required)
   - Handler: call `client.CheckConflicts` for each pattern
   - Response: `{"conflicts": [{pattern, held_by, exclusive, expires_at, reason}], "clear": ["pattern1"]}`

   **`my_reservations`** tool:
   - Input schema: (none)
   - Handler: `client.ListReservations(agent=self)`
   - Response: JSON array of reservation objects

4. Create `internal/tools/messaging.go` with 3 tools:

   **`send_message`** tool:
   - Input schema: `to` (string, required), `subject` (string, required), `body` (string, required)
   - Handler: `client.SendMessage`
   - Response: `{"sent": true, "to": "agent-name"}`

   **`fetch_inbox`** tool:
   - Input schema: `cursor` (string, optional)
   - Handler: `client.FetchInbox(self, project, cursor)`
   - Response: `{"messages": [{from, subject, body, timestamp}], "next_cursor": "..."}`

   **`request_release`** tool:
   - Input schema: `agent_name` (string, required), `pattern` (string, required), `reason` (string, required)
   - Handler: sends a structured message via `client.SendMessage` with subject `"release-request"` and JSON body containing `{pattern, reason, requester}`
   - Response: `{"sent": true, "to": "agent-name", "type": "release-request"}`

5. Create `internal/tools/agents.go` with 1 tool:

   **`list_agents`** tool:
   - Input schema: (none)
   - Handler: `client.ListAgents(project)`
   - Response: JSON array of agent objects `[{name, project, capabilities, status}]`

6. Create `internal/tools/tools_test.go` with:

   - Mock `client.Client` interface (or inject mock HTTP handler)
   - Test each tool handler returns correct JSON schema on success
   - Test each tool handler returns structured error on intermute 5xx (never crashes)
   - Test `reserve_files` with multiple patterns (partial success scenario)
   - Test `release_all` when agent has 0 reservations (empty response, not error)
   - Test `request_release` formats message body as JSON with pattern + reason
   - Test `check_conflicts` fallback behavior (no conflicts = empty array, not null)

7. Run tests:
   ```bash
   cd /root/projects/interlock && go test ./internal/tools/ -v
   ```

8. Commit:
   ```bash
   git add internal/tools/
   git commit -m "feat: 9 MCP tool handlers for file reservation and messaging"
   ```

**Acceptance criteria:**
- [ ] 9 tool handlers implemented: reserve_files, release_files, release_all, check_conflicts, my_reservations, send_message, fetch_inbox, list_agents, request_release
- [ ] All tools return structured JSON in MCP text content format
- [ ] All tools handle intermute 5xx gracefully: `{"error":"...","code":503,"retry_after":30}` with `isError: true`
- [ ] No tool handler panics on any input
- [ ] Empty results return empty arrays `[]`, not null

---

### Task 4: MCP Server Entry Point + Build

**Files:**
- Create: `/root/projects/interlock/cmd/interlock-mcp/main.go`

**Steps:**

1. Create `cmd/interlock-mcp/main.go`:

   ```go
   package main

   import (
       "fmt"
       "os"

       "github.com/mark3labs/mcp-go/mcp"
       "github.com/mark3labs/mcp-go/server"
       "github.com/mistakeknot/interlock/internal/client"
       "github.com/mistakeknot/interlock/internal/tools"
   )

   func main() {
       // Initialize intermute client
       c := client.NewClient(
           client.WithSocketPath(os.Getenv("INTERMUTE_SOCKET")),
           client.WithBaseURL(os.Getenv("INTERMUTE_URL")),
           client.WithAgentID(getAgentID()),
           client.WithProject(getProject()),
       )

       // Create MCP server
       s := server.NewMCPServer(
           "interlock",
           "0.1.0",
           server.WithToolCapabilities(true),
       )

       // Register 9 tools
       tools.RegisterAll(s, c)

       // Serve via stdio
       if err := server.ServeStdio(s); err != nil {
           fmt.Fprintf(os.Stderr, "interlock-mcp: %v\n", err)
           os.Exit(1)
       }
   }

   func getAgentID() string {
       if id := os.Getenv("INTERLOCK_AGENT_ID"); id != "" {
           return id
       }
       if id := os.Getenv("CLAUDE_SESSION_ID"); id != "" {
           return "claude-" + id
       }
       hostname, _ := os.Hostname()
       return fmt.Sprintf("%s-%d", hostname, os.Getpid())
   }

   func getProject() string {
       if p := os.Getenv("INTERLOCK_PROJECT"); p != "" {
           return p
       }
       // Derive from current working directory name
       dir, _ := os.Getwd()
       return filepath.Base(dir)
   }
   ```

2. Add a `RegisterAll` function in `internal/tools/` that registers all 9 tools with the MCP server, including:
   - Tool name
   - Description
   - Input schema (JSON Schema)
   - Handler function

3. Install mcp-go dependency:
   ```bash
   cd /root/projects/interlock && go get github.com/mark3labs/mcp-go@latest && go mod tidy
   ```

4. Build the binary:
   ```bash
   bash /root/projects/interlock/scripts/build.sh
   ```

5. Verify the binary starts and responds to MCP initialize:
   ```bash
   echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' | /root/projects/interlock/bin/interlock-mcp
   ```
   Expected: JSON-RPC response with server info and 9 tools listed.

6. Commit:
   ```bash
   git add cmd/interlock-mcp/ go.mod go.sum
   git commit -m "feat: MCP stdio server entry point with 9 registered tools"
   ```

**Acceptance criteria:**
- [ ] `bin/interlock-mcp` binary builds without errors
- [ ] Binary responds to MCP `initialize` request with server name and version
- [ ] Binary lists 9 tools in `tools/list` response
- [ ] Binary reads from stdin, writes to stdout (MCP stdio transport)
- [ ] Agent ID derived from env vars with fallback chain
- [ ] Project name derived from env var or cwd

---

### Task 5: Structural + Schema Tests

**Files:**
- Create: `/root/projects/interlock/tests/pyproject.toml`
- Create: `/root/projects/interlock/tests/structural/conftest.py`
- Create: `/root/projects/interlock/tests/structural/helpers.py`
- Create: `/root/projects/interlock/tests/structural/test_structure.py`
- Create: `/root/projects/interlock/tests/structural/test_tools.py`

**Steps:**

1. Create `tests/pyproject.toml`:
   ```toml
   [project]
   name = "interlock-tests"
   version = "0.1.0"
   requires-python = ">=3.10"
   dependencies = ["pytest>=7.0"]

   [tool.pytest.ini_options]
   testpaths = ["structural"]
   ```

2. Create `tests/structural/conftest.py`:
   ```python
   """Shared fixtures for Interlock structural tests."""
   import json
   from pathlib import Path
   import pytest

   @pytest.fixture(scope="session")
   def project_root() -> Path:
       return Path(__file__).resolve().parent.parent.parent

   @pytest.fixture(scope="session")
   def plugin_json(project_root: Path) -> dict:
       with open(project_root / ".claude-plugin" / "plugin.json") as f:
           return json.load(f)
   ```

3. Create `tests/structural/test_structure.py`:
   - `test_plugin_json_valid` — name is "interlock", has version, description
   - `test_mcp_server_declared` — `plugin_json["mcpServers"]["interlock"]` exists with `type: "stdio"`
   - `test_mcp_command_path` — command contains `interlock-mcp`
   - `test_marker_file_exists` — `scripts/interlock.sh` exists and is executable
   - `test_required_directories` — `.claude-plugin`, `cmd`, `internal`, `scripts`, `tests` exist
   - `test_claude_md_exists` — `CLAUDE.md` exists
   - `test_agents_md_exists` — `AGENTS.md` exists
   - `test_license_exists` — `LICENSE` exists
   - `test_go_mod_exists` — `go.mod` exists with correct module path
   - `test_binary_dir_exists` — `bin/` directory exists

4. Create `tests/structural/test_tools.py`:
   - `test_tool_count` — exactly 9 tools defined (parse Go source files for tool registrations)
   - `test_tool_names` — verify all 9 tool names: `reserve_files`, `release_files`, `release_all`, `check_conflicts`, `my_reservations`, `send_message`, `fetch_inbox`, `list_agents`, `request_release`
   - `test_each_tool_has_description` — every tool registration includes a description string
   - `test_reserve_files_has_required_params` — patterns and reason are required
   - `test_release_files_has_required_params` — reservation_ids is required
   - `test_send_message_has_required_params` — to, subject, body are required
   - `test_request_release_has_required_params` — agent_name, pattern, reason are required
   - `test_error_handler_exists` — `internal/tools/errors.go` exists

5. Create `tests/structural/helpers.py`:
   ```python
   """Helpers for parsing Go source files."""
   import re
   from pathlib import Path

   def find_tool_registrations(project_root: Path) -> list[str]:
       """Find all MCP tool names registered in Go source."""
       tools_dir = project_root / "internal" / "tools"
       names = []
       for f in tools_dir.glob("*.go"):
           if f.name.endswith("_test.go"):
               continue
           content = f.read_text()
           # Match mcp.NewTool("tool_name", ...) pattern
           for m in re.finditer(r'mcp\.NewTool\(\s*"(\w+)"', content):
               names.append(m.group(1))
       return sorted(names)
   ```

6. Run tests:
   ```bash
   cd /root/projects/interlock && uv run --project tests pytest tests/structural/ -v
   ```

7. Commit:
   ```bash
   git add tests/
   git commit -m "test: structural and schema tests for interlock plugin"
   ```

**Acceptance criteria:**
- [ ] All structural tests pass
- [ ] Tool count test guards against regressions (exactly 9)
- [ ] Tool name test verifies all 9 expected names
- [ ] MCP server declaration validated in plugin.json

---

### Task 6: Clavain Integration + Documentation

**Files:**
- Modify: `/root/projects/Clavain/hooks/lib.sh` (add `_discover_interlock_plugin`)
- Modify: `/root/projects/Clavain/hooks/session-start.sh` (add interlock detection)
- Modify: `/root/projects/Clavain/commands/doctor.md` (add 3f health check)
- Modify: `/root/projects/Clavain/commands/setup.md` (add install + build step)
- Create: `/root/projects/interlock/AGENTS.md`

**Steps:**

1. Add discovery function to `/root/projects/Clavain/hooks/lib.sh`:
   ```bash
   # Discover the interlock companion plugin root directory.
   # Checks INTERLOCK_ROOT env var first, then searches the plugin cache.
   # Output: plugin root path to stdout, or empty string if not found.
   _discover_interlock_plugin() {
       if [[ -n "${INTERLOCK_ROOT:-}" ]]; then
           echo "$INTERLOCK_ROOT"
           return 0
       fi
       local f
       f=$(find "${HOME}/.claude/plugins/cache" -maxdepth 5 \
           -path '*/interlock/*/scripts/interlock.sh' 2>/dev/null | sort -V | tail -1)
       if [[ -n "$f" ]]; then
           # interlock.sh is at <root>/scripts/interlock.sh, so strip two levels
           echo "$(dirname "$(dirname "$f")")"
           return 0
       fi
       echo ""
   }
   ```

2. Add interlock detection to `hooks/session-start.sh` (after interwatch detection block):
   ```bash
   interlock_root=$(_discover_interlock_plugin)
   if [[ -n "$interlock_root" ]]; then
       companions="${companions}\\n- **interlock**: file reservation MCP server (9 tools for intermute API)"
   fi
   ```

3. Add doctor check 3f to `commands/doctor.md`:
   ```markdown
   **3f — File Reservation (interlock):**
   ```bash
   if ls ~/.claude/plugins/cache/*/interlock/*/scripts/interlock.sh 2>/dev/null | head -1 >/dev/null; then
     echo "interlock: installed"
     if ls ~/.claude/plugins/cache/*/interlock/*/bin/interlock-mcp 2>/dev/null | head -1 >/dev/null; then
       echo "interlock binary: built"
     else
       echo "interlock binary: NOT BUILT — run: bash \$(find ~/.claude/plugins/cache -path '*/interlock/*/scripts/build.sh' | head -1)"
     fi
   else
     echo "interlock: not installed (file reservation unavailable)"
   fi
   ```
   ```

4. Add install step to `commands/setup.md`:
   ```markdown
   claude plugin install interlock@interagency-marketplace
   # Build the MCP binary (required after install):
   bash "$(find ~/.claude/plugins/cache -path '*/interlock/*/scripts/build.sh' | head -1)"
   ```

5. Create `/root/projects/interlock/AGENTS.md` with:
   - Architecture overview (MCP stdio server wrapping intermute HTTP API)
   - 9 tool reference table (name, description, required params, response format)
   - Connection strategy (Unix socket with TCP fallback)
   - Error handling conventions (tool errors as content, never protocol errors)
   - Build instructions (`scripts/build.sh`)
   - Test instructions (`go test ./...` and `uv run --project tests pytest tests/structural/ -v`)
   - Environment variables: `INTERMUTE_SOCKET`, `INTERMUTE_URL`, `INTERLOCK_AGENT_ID`, `INTERLOCK_PROJECT`

6. Run Clavain's structural tests to verify no regressions:
   ```bash
   cd /root/projects/Clavain && bash -n hooks/lib.sh && bash -n hooks/session-start.sh
   cd /root/projects/Clavain && uv run --project tests pytest tests/structural/ -v
   ```

7. Commit in interlock repo:
   ```bash
   cd /root/projects/interlock
   git add AGENTS.md
   git commit -m "docs: AGENTS.md development guide"
   ```

8. Commit in Clavain repo:
   ```bash
   cd /root/projects/Clavain
   git add hooks/lib.sh hooks/session-start.sh commands/doctor.md commands/setup.md
   git commit -m "feat: integrate interlock companion plugin discovery and health checks"
   ```

**Acceptance criteria:**
- [ ] `_discover_interlock_plugin` follows same pattern as other discovery functions
- [ ] Session-start detects and reports interlock availability
- [ ] Doctor check 3f verifies both plugin installation AND binary build
- [ ] Setup documents both install and build steps
- [ ] Clavain shell syntax checks pass after modifications
- [ ] Clavain structural tests pass after modifications

---

## Execution Order

```
Task 1 (scaffold)
  |
  v
Task 2 (HTTP client)
  |
  v
Task 3 (tool handlers)  <-- depends on client types/interfaces
  |
  v
Task 4 (entry point + build)  <-- depends on tools + client
  |
  v
Task 5 (tests)  <-- depends on all code existing
  |
  v
Task 6 (Clavain integration)  <-- depends on plugin being functional
```

All tasks are sequential. Task 2 and Task 3 could theoretically be parallelized (define interfaces first), but keeping them sequential avoids interface mismatches.

---

## Verification Checklist

After all tasks are complete, verify:

```bash
# 1. Binary builds and runs
cd /root/projects/interlock && bash scripts/build.sh
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' | bin/interlock-mcp | head -1

# 2. Go tests pass
cd /root/projects/interlock && go test ./... -v

# 3. Structural tests pass
cd /root/projects/interlock && uv run --project tests pytest tests/structural/ -v

# 4. Plugin manifest is valid
python3 -c "import json; d=json.load(open('/root/projects/interlock/.claude-plugin/plugin.json')); assert 'interlock' in d['mcpServers']; print('OK')"

# 5. Discovery marker exists
test -x /root/projects/interlock/scripts/interlock.sh && echo "marker OK"

# 6. Clavain integration passes
cd /root/projects/Clavain && bash -n hooks/lib.sh && bash -n hooks/session-start.sh
cd /root/projects/Clavain && uv run --project tests pytest tests/structural/ -v

# 7. Tool list shows 9 tools
echo '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' | /root/projects/interlock/bin/interlock-mcp | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['result']['tools']), 'tools')"
```

---

## Risks

1. **`mark3labs/mcp-go` API changes** — the library is actively maintained. Pin to a specific version in `go.mod` to avoid breaking changes. Check the latest release before starting Task 4.

2. **intermute not running during development** — all tool handlers must handle connection refused gracefully. Go unit tests use mock HTTP servers (no real intermute needed).

3. **Binary distribution** — the Go binary is platform-specific. `scripts/build.sh` compiles for the current platform. If interlock needs to work on macOS too, consider adding `GOOS`/`GOARCH` flags to build.sh.

4. **Plugin cache binary survival** — Claude Code may delete and re-clone the plugin cache on updates. After plugin update, users must re-run `scripts/build.sh`. Document this in setup.md and AGENTS.md.

5. **Agent ID uniqueness** — if multiple Claude sessions use the same agent ID, reservations may conflict. The fallback chain (env var -> session ID -> hostname+PID) should provide sufficient uniqueness, but document the `INTERLOCK_AGENT_ID` env var for explicit control.
