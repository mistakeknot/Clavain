# Research Notes: Interlock F6 MCP Server Plan

**Date:** 2026-02-14
**Purpose:** Analysis supporting the implementation plan at `docs/plans/2026-02-14-interlock-f6-mcp-server.md`

## Key Design Decisions

### 1. Go MCP Server (not bash)

A bash MCP server would require fragile JSON-RPC parsing. Go is available on the system (`go version go1.22.2 linux/amd64`) and has multiple mature MCP stdio libraries:

- **Official SDK:** `github.com/modelcontextprotocol/go-sdk` (maintained by MCP org + Google)
- **Community:** `github.com/mark3labs/mcp-go` (popular, simple `ServeStdio` API)

Recommendation: Use `mark3labs/mcp-go` for simplicity. The official SDK is newer but `mcp-go` has the most community adoption and the simplest API for stdio servers.

### 2. Plugin Structure

All companion plugins follow the same structure (verified against interpath, interwatch, interphase):

```
/root/projects/interlock/
  .claude-plugin/plugin.json   # Name, version, MCP server config
  CLAUDE.md                    # Quick reference
  AGENTS.md                    # Development guide
  LICENSE                      # MIT
  README.md                    # Public docs
  .gitignore                   # tests/.venv, bin/interlock-mcp (binary)
  cmd/interlock-mcp/main.go   # MCP server entry point
  internal/client/client.go    # intermute HTTP client (socket + TCP)
  internal/tools/tools.go      # 9 tool definitions + handlers
  go.mod                       # Go module
  go.sum                       # Dependencies
  scripts/interlock.sh         # Discovery marker (like interpath.sh)
  scripts/build.sh             # Build binary
  tests/
    structural/
      conftest.py
      helpers.py
      test_structure.py        # Plugin structure tests
      test_tools.py            # Tool schema tests
    pyproject.toml
```

### 3. MCP Server in plugin.json

The MCP server must be declared in `.claude-plugin/plugin.json` (not a separate `.mcp.json`). This is how all companion plugins declare their MCP servers. Example from interflux:

```json
{
  "mcpServers": {
    "qmd": {
      "type": "stdio",
      "command": "qmd",
      "args": ["mcp"]
    }
  }
}
```

For interlock, the binary lives at `${CLAUDE_PLUGIN_ROOT}/bin/interlock-mcp`, so it must use `CLAUDE_PLUGIN_ROOT` expansion.

### 4. Clavain Integration Pattern

Every companion follows the same integration:

1. **Discovery function** in `hooks/lib.sh` (env var + plugin cache search)
2. **Session-start detection** in `hooks/session-start.sh` (companion list)
3. **Doctor check** in `commands/doctor.md` (health verification)
4. **Setup install** in `commands/setup.md` (marketplace install)
5. **Routing table entry** in `skills/using-clavain/references/routing-tables.md`

Marker file convention: `scripts/interlock.sh` (consistent with `scripts/interpath.sh`, `scripts/interwatch.sh`)

### 5. intermute API Connection Strategy

Try Unix socket first (`/var/run/intermute.sock`), fall back to TCP (`127.0.0.1:7338`). In Go, this is done by creating an `http.Client` with a custom `DialContext` that connects to the Unix socket:

```go
client := &http.Client{
    Transport: &http.Transport{
        DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
            return net.Dial("unix", "/var/run/intermute.sock")
        },
    },
}
```

The fallback path uses a standard `http.Client` pointing at `http://127.0.0.1:7338`.

### 6. Error Handling Philosophy

MCP tool errors are **content**, not protocol errors. When intermute returns HTTP 5xx, the MCP tool should return a successful JSON-RPC response with error content in the result:

```json
{
  "content": [{"type": "text", "text": "{\"error\":\"intermute unavailable\",\"code\":503,\"retry_after\":30}"}],
  "isError": true
}
```

This matches the MCP protocol specification: tool execution errors are reported via `isError: true` in the tool result, not via JSON-RPC error responses.

### 7. Version Fallback

If intermute doesn't have the `GET /api/reservations/check` endpoint (returns 404), the `check_conflicts` tool falls back to `GET /api/reservations?project=X` and filters client-side by pattern match. This is less efficient but functionally equivalent.

### 8. Agent Identity

The MCP server needs an agent_id to make API calls. This should be derived from:
1. `INTERLOCK_AGENT_ID` env var (explicit override)
2. `CLAUDE_SESSION_ID` env var (auto from hook injection)
3. Fallback: hostname + PID

The agent_id is passed as an env var in plugin.json or auto-detected at startup.

### 9. Test Strategy

Following the companion plugin test convention:
- **Structural tests (pytest):** Plugin structure, tool schema validation, binary existence
- **Unit tests (Go):** Tool handler logic, HTTP client mocking, error scenarios
- **No smoke tests initially:** Smoke tests require a running intermute instance

### 10. Build Strategy

The Go binary should be built by `scripts/build.sh` and placed at `bin/interlock-mcp`. The binary should be committed to the repo (for immediate use) OR built on install via a post-install hook. Given that Claude Code plugin cache doesn't run post-install scripts, the binary must be either:
- Pre-built and committed (simplest, platform-specific)
- Built by `scripts/build.sh` which the setup.md documents

Recommendation: Build on setup. The setup.md command tells users to run `scripts/build.sh` after install. The binary is gitignored.
