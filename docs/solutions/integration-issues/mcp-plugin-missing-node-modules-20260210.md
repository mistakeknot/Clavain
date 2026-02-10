---
module: System
date: 2026-02-10
problem_type: integration_issue
component: tooling
symptoms:
  - "MCP server fails to start with ERR_MODULE_NOT_FOUND"
  - "Cannot find package '@modelcontextprotocol/sdk'"
  - "claude doctor reports plugin error for MCP server"
  - "/mcp command shows 'Failed to reconnect' for stdio-based plugin"
root_cause: incomplete_setup
resolution_type: environment_setup
severity: high
tags: [mcp, plugin-cache, node-modules, native-modules, canvas, libgif]
---

# Troubleshooting: MCP Plugin Cache Missing node_modules

## Problem
Claude Code's plugin cache stores source/dist files from marketplace plugins but does NOT include `node_modules/`. Stdio-based Node.js MCP servers fail to start because their dependencies aren't installed.

## Environment
- Module: System (Claude Code plugin infrastructure)
- Claude Code Version: 2.1.38
- Node.js Version: 22.22.0
- Affected Component: MCP server startup for marketplace plugins with Node.js dependencies
- Date: 2026-02-10

## Symptoms
- MCP server fails: `Error [ERR_MODULE_NOT_FOUND]: Cannot find package '@modelcontextprotocol/sdk'`
- `/mcp` command shows `Failed to reconnect to plugin:tuivision:tuivision`
- Plugin cache at `~/.claude/plugins/cache/interagency-marketplace/<plugin>/<version>/` has `dist/` but no `node_modules/`
- Running `npm install` in cache dir fails if native modules need system libraries (e.g., `canvas` needs `libgif-dev`)

## What Didn't Work

**Attempted Solution 1:** Symlink `node_modules` from source project to cache
- **Why it failed:** User rejected — fragile coupling between source project and cached plugin, breaks if source project is moved or deleted.

**Attempted Solution 2:** Direct `npm install` in cache directory
- **Why it failed initially:** Native module `canvas` requires `libgif-dev` system library. Error: `gif_lib.h: No such file or directory`. Had to install system dependency first.

## Solution

Created a bootstrap wrapper script that auto-installs dependencies on first MCP server start.

**File: `scripts/start.sh`**
```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Auto-install dependencies if missing
if [ ! -d "$PROJECT_DIR/node_modules" ]; then
  # Check for system deps needed by native modules
  if ! pkg-config --exists libgif 2>/dev/null; then
    if command -v apt-get >/dev/null 2>&1; then
      echo "Installing system dependencies for canvas..." >&2
      sudo apt-get install -y libgif-dev >/dev/null 2>&1 || true
    fi
  fi

  echo "Installing tuivision dependencies..." >&2
  cd "$PROJECT_DIR"
  npm install --no-fund --no-audit 2>&1 | tail -1 >&2
fi

exec node "$PROJECT_DIR/dist/index.js" "$@"
```

**File: `.mcp.json`** (changed from `node` to `bash` wrapper)
```json
{
  "mcpServers": {
    "tuivision": {
      "command": "bash",
      "args": ["${CLAUDE_PLUGIN_ROOT}/scripts/start.sh"],
      "env": {}
    }
  }
}
```

**Key design decisions:**
- All bootstrap output goes to `stderr` so it doesn't corrupt MCP JSON-RPC on `stdout`
- `exec` replaces the shell process so signals propagate correctly to node
- System dependency check uses `pkg-config` (works without root for detection)

## Why This Works

1. **Root cause:** Claude Code's plugin marketplace downloads git repos into a cache directory but has NO post-install lifecycle hook — no `npm install`, no `postInstall` script support in `plugin.json`. Plugins with Node.js dependencies arrive broken.

2. **The wrapper pattern** is a lazy-init approach: the `.mcp.json` entry point is a shell script that checks for deps, installs if missing, then `exec`s into the real server. First start is slow (~30s for npm install), subsequent starts are instant.

3. **Native modules** like `canvas` and `node-pty` compile platform-specific binaries via `node-gyp`, which needs C headers (e.g., `libgif-dev`). These system dependencies aren't tracked by npm and must be handled separately.

## Prevention

- **For plugin authors:** Always use a wrapper script for MCP servers with Node.js dependencies. Never assume `node_modules/` exists in the cache.
- **For native modules:** Document system-level dependencies in README and handle them in the wrapper script.
- **Alternative:** Publish to npm and use `npx` as the entry point (npm handles deps automatically), but requires npm publish setup.
- **Future:** Claude Code could add `postInstall` lifecycle hooks to `plugin.json` — but this doesn't exist today (as of 2.1.38).

## Related Issues

No related issues documented yet.
