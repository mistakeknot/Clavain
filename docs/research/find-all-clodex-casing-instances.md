# Clodex Casing Analysis — User-Facing Text Audit

**Date**: 2026-02-16  
**Task**: Find all instances of "clodex" (lowercase) in user-facing text that should be "Clodex" (proper case)

## Naming Convention

Modules that don't start with "inter" use proper case (like "Clavain"). Therefore:
- **User-facing text** (descriptions, messages, hook reasons, session context): "Clodex"
- **Technical identifiers** (file/dir names, Go package names, JSON keys, variable names, MCP server names, tool names): "clodex"

## Current Convention (Reference Files)

These files already use proper case correctly:
- `plugins/clodex/CLAUDE.md` — uses lowercase "clodex" appropriately (title, commands, technical refs)
- `os/clavain/hooks/clodex-audit.sh` — script name (lowercase correct)
- `os/clavain/scripts/clodex-toggle.sh` — script name (lowercase correct), but user messages use "Clodex" properly

## Instances Requiring Changes

### 1. **plugins/clodex/hooks/pre-read-intercept.sh**

**Line 2** (comment):
```bash
# PreToolUse:Read hook — intercept large code file reads when clodex-toggle is ON.
```
**Should be**:
```bash
# PreToolUse:Read hook — intercept large code file reads when Clodex toggle is ON.
```

**Line 67** (hook reason message — USER-FACING):
```bash
{"decision": "block", "reason": "CLODEX: ${rel_path} is ${line_count} lines. Use codex_query(question='...', files=['${file_path}']) to save ~${line_count} tokens. Modes: answer (default), summarize, extract."}
```
**Should be**:
```bash
{"decision": "block", "reason": "Clodex: ${rel_path} is ${line_count} lines. Use codex_query(question='...', files=['${file_path}']) to save ~${line_count} tokens. Modes: answer (default), summarize, extract."}
```

---

### 2. **plugins/clodex/internal/tools/tools.go**

**Line 17** (comment):
```go
// RegisterAll registers all clodex MCP tools.
```
**Should be**:
```go
// RegisterAll registers all Clodex MCP tools.
```

**Line 72** (tool description — USER-FACING):
```go
mcp.WithDescription("Classify markdown sections into flux-drive domains via Codex spark dispatch."),
```
**Should be**:
```go
mcp.WithDescription("Classify markdown sections into flux-drive domains via Clodex spark dispatch."),
```

**Line 108** (tool description — USER-FACING):
```go
mcp.WithDescription("Ask Codex to analyze file(s) and return a compact answer. Saves Claude context by delegating file reading to Codex."),
```
**Should be**:
```go
mcp.WithDescription("Ask Clodex to analyze file(s) and return a compact answer. Saves Claude context by delegating file reading to Clodex."),
```

---

### 3. **plugins/clodex/.claude-plugin/plugin.json**

**Line 4** (description — USER-FACING):
```json
"description": "Codex spark classifier — lightweight section classification via MCP",
```
**Should be**:
```json
"description": "Clodex spark classifier — lightweight section classification via MCP",
```

---

### 4. **os/clavain/hooks/session-start.sh**

**Line 136** (companion context message — USER-FACING):
```bash
companions="${companions}\\n- **CLODEX MODE: ON** — Route source code changes through Codex (preserves Claude token budget for orchestration)...
```
**Should be**:
```bash
companions="${companions}\\n- **Clodex MODE: ON** — Route source code changes through Clodex (preserves Claude token budget for orchestration)...
```

This message also mentions "Codex" multiple times where it should say "Clodex":
- "Route source code changes through Codex" → "through Clodex"
- "If Codex unavailable" → "If Clodex unavailable"
- All remaining "Codex" references in this context block should be "Clodex"

The full corrected line 136 should be:
```bash
companions="${companions}\\n- **Clodex MODE: ON** — Route source code changes through Clodex (preserves Claude token budget for orchestration).\\n  1. Plan: Read/Grep/Glob freely\\n  2. Prompt: Write task to /tmp/, dispatch via /clodex\\n  3. Verify: read output, run tests, review diffs\\n  4. Git ops (add/commit/push) are yours — do directly\\n  Bash: read-only for source files (no redirects, sed -i, tee). Git + test/build OK.\\n  Direct-edit OK: .md/.json/.yaml/.yml/.toml/.txt/.csv/.xml/.html/.css/.svg/.lock/.cfg/.ini/.conf/.env, /tmp/*\\n  Everything else (code files): dispatch via /clodex. If Clodex unavailable: /clodex-toggle off, or use /subagent-driven-development.\\n  **Token savings:** For understanding code, prefer codex_query(question, files) over Read for files >200 lines.\\n  Modes: 'answer' (focused response), 'summarize' (structural overview), 'extract' (specific snippets).\\n  Read is still fine for: small files, config/docs, exact content needed for editing, targeted reads with offset."
```

---

## Instances That Are CORRECT (Do Not Change)

### Technical Identifiers (All Correct)

- **File/directory names**: `plugins/clodex/`, `clodex-audit.sh`, `clodex-toggle.sh`, `clodex-toggle.flag` — all lowercase ✓
- **Go package names**: `package tools`, `package query`, `package classify`, `package extract` — all lowercase ✓
- **Go module**: `module github.com/mistakeknot/clodex` — lowercase ✓
- **Binary name**: `bin/clodex-mcp` — lowercase ✓
- **MCP server name** (plugin.json): `"clodex"` in `mcpServers` object — lowercase ✓
- **Tool name**: `codex_query` (NOT changed to `Clodex_query`) — lowercase ✓
- **Environment variable**: `CLODEX_DISPATCH_PATH` — uppercase technical identifier ✓
- **Temp file patterns**: `clodex-query-prompt-*.txt`, `clodex-output-*.json`, `clodex-test-*.go` — lowercase ✓
- **Session flag files**: `/tmp/clodex-read-denied-*` — lowercase ✓

### Comments (Context-Dependent)

These are already correct because they refer to technical elements:
- `plugins/clodex/CLAUDE.md:1` — "# clodex" (title, matches repo name) ✓
- `plugins/clodex/CLAUDE.md:8-9` — command examples with `clodex` binary ✓
- `plugins/clodex/hooks/pre-read-intercept.sh:10` — variable `flag_file="$project_dir/.claude/clodex-toggle.flag"` ✓
- `plugins/clodex/hooks/pre-read-intercept.sh:12` — "If clodex mode is OFF" (lowercase is fine in code comment) ✓
- `plugins/clodex/hooks/pre-read-intercept.sh:30` — "matches clodex-audit.sh allowlist" (script name) ✓
- Test descriptions in `hook_test.sh` and `integration_test.sh` — these are test code, not user-facing ✓

### Error Messages (Internal)

These are stderr messages for developers, not end users — lowercase is acceptable:
- `cmd/clodex-mcp/main.go:24` — `fmt.Fprintf(os.Stderr, "clodex-mcp: dispatch path %q: %v\n", ...)` ✓
- `cmd/clodex-mcp/main.go:27` — `fmt.Fprintf(os.Stderr, "clodex-mcp: dispatch path %q is a directory...")` ✓
- `cmd/clodex-mcp/main.go:34` — `fmt.Fprintf(os.Stderr, "clodex-mcp: %v\n", err)` ✓
- `bin/launch-mcp.sh:8` — `echo '{"error":"go not found — cannot build clodex-mcp..."}'` ✓

---

## Summary

**Total instances requiring changes**: 6 lines across 4 files

**Files to update**:
1. `plugins/clodex/hooks/pre-read-intercept.sh` — 2 instances (lines 2, 67)
2. `plugins/clodex/internal/tools/tools.go` — 3 instances (lines 17, 72, 108)
3. `plugins/clodex/.claude-plugin/plugin.json` — 1 instance (line 4)
4. `os/clavain/hooks/session-start.sh` — 1 instance (line 136, with multiple "Codex" → "Clodex" substitutions within)

**Pattern**: All changes are in user-facing descriptions, hook reason messages, and session context — never in technical identifiers, file names, or code structure.
