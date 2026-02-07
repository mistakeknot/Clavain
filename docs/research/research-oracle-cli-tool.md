# Research: Oracle CLI Tool

**Date:** 2026-02-06
**Source:** https://github.com/steipete/oracle
**Package:** `@steipete/oracle` (npm), version 0.8.5
**Author:** Peter Steinberger (steipete)
**License:** Public repository

---

## 1. Purpose and Overview

Oracle is a CLI tool that bundles prompts alongside project files, enabling AI models to provide contextual answers. The core value proposition is **cross-AI review**: when you are working with one AI (e.g., Claude Code), you can send your code and a prompt to a different AI (e.g., GPT-5.2 Pro) for a second opinion, architectural review, debugging help, or design validation.

The tagline is "Whispering your tokens to the silicon sage."

Oracle's key differentiator is the "bundle once, reuse anywhere" approach -- it assembles a context bundle (prompt + files) that can be sent to APIs, automated through browser interaction, or manually copy-pasted.

---

## 2. Supported Models

Oracle is model-agnostic and supports multiple providers:

| Provider | Models |
|----------|--------|
| **OpenAI** | GPT-5.2 Pro (default), GPT-5.1 Pro, GPT-5.2, GPT-5.1, GPT-5.1 Codex, GPT-5.2-instant |
| **Google** | Gemini 3 Pro |
| **Anthropic** | Claude Sonnet 4.5, Claude Opus 4.1 |
| **OpenRouter** | Any model ID supported by OpenRouter |

The default model is GPT-5.2 Pro, making the primary use case "ask GPT for a second opinion while working in Claude."

---

## 3. Installation

Three installation methods:

```bash
# Global npm install
npm install -g @steipete/oracle

# Homebrew
brew install steipete/tap/oracle

# Direct execution (no install)
npx -y @steipete/oracle
```

**Requirement:** Node.js 22+

After installation, the package provides two binaries:
- `oracle` -- the main CLI
- `oracle-mcp` -- the MCP server

---

## 4. CLI Interface

### 4.1 Basic Usage

```bash
oracle "<prompt>" --file <files...> [options]
# or
oracle -p "<prompt>" -f <files...> [options]
```

**Both prompt and files are required.** Oracle assembles a context bundle from the files and sends it alongside the prompt to the chosen AI model.

### 4.2 Core Flags

| Flag | Short | Description |
|------|-------|-------------|
| `--prompt` | `-p` | The query/instruction text (required) |
| `--file` | `-f` | Files/directories/globs to attach (required). Multiple allowed. Prefix with `!` to exclude. |
| `--engine` | `-e` | Execution mode: `api` or `browser` |
| `--model` | `-m` | Single model identifier |
| `--models` | | Comma-separated list for multi-model parallel runs |
| `--wait` | | Block until completion (default for API; browser detaches by default) |
| `--dry-run` | | Preview token count without calling the model |
| `--files-report` | | Show per-file token usage breakdown |
| `--render` | | Display the assembled markdown bundle |
| `--copy` | | Copy the assembled bundle to clipboard |
| `--write-output` | | Save the model's answer to a file |
| `--slug` | | Human-readable session identifier for easy reattachment |
| `--force` | | Start new session even if duplicate prompt is already running |
| `--verbose` | | Enable verbose logging |

### 4.3 Browser-Specific Flags

| Flag | Description |
|------|-------------|
| `--browser-model-strategy` | How to select model in browser UI |
| `--browser-thinking-time` | Reasoning depth: `light`, `standard`, `extended`, `heavy` |
| `--chatgpt-url` | Target specific ChatGPT workspace/project URL |

### 4.4 Execution Engines

**API Mode** (most reliable):
- Requires API keys: `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`
- Supports multi-model parallel runs
- Synchronous by default

**Browser Mode** (experimental but powerful):
- Automates ChatGPT/Gemini web UI via headless Chrome
- No API key needed -- uses your logged-in session
- Supports GPT-5.2 Pro (which may not be available via API)
- Sessions detach by default; can be reattached
- Requires Chrome and a display (real or virtual via Xvfb)
- Stable on macOS; functional on Linux with Xvfb + noVNC setup

**Manual/Clipboard Mode:**
- `--render --copy` assembles the bundle and copies to clipboard
- User pastes into ChatGPT/Gemini manually
- Useful when browser automation is unavailable

### 4.5 Session Management

Sessions are persisted under `~/.oracle/sessions/`:

```bash
oracle status                          # List recent sessions
oracle status --hours 72               # Show sessions from last 72 hours
oracle session <session-id>            # Reattach to running/completed session
oracle session <id> --render           # Replay a session
oracle status --clear --hours 168      # Prune old sessions (>1 week)
```

### 4.6 Example Commands

```bash
# Architecture review
oracle "Review this spec against the codebase. Identify gaps and risks." \
  --file prd/spec.md --file "src/**/*.rs"

# Code review with exclusions
oracle "Review for security issues" \
  --file "src/**/*.ts" --file "!src/**/*.test.ts"

# Multi-model comparison
oracle "Validate this approach" \
  --models gpt-5.2-pro,gemini-3-pro --file src/main.ts

# Dry run to check token usage
oracle "Review the API" --file "src/api/**" --dry-run

# Copy bundle for manual pasting
oracle --render --copy -p "Prompt" --file "src/**/*.ts"
```

---

## 5. File Handling

Oracle handles files intelligently:

- **Glob patterns:** `--file "src/**/*.ts"` expands recursively
- **Exclusions:** `--file "!src/**/*.test.ts"` with `!` prefix
- **Auto-exclusions:** Skips `node_modules`, `dist`, `coverage`, `.git`, `.turbo`, `.next`, `build`, `tmp` unless explicitly included
- **Respects `.gitignore`**
- **Size guard:** Rejects files > 1 MB
- **Token budget:** Target ~196k tokens total
- **Browser attachments:** Auto-paste up to ~60k characters, then upload as files

Use `--files-report` to preview per-file token consumption before sending.

---

## 6. Configuration

Configuration stored in `~/.oracle/config.json` (JSON5 format):

```json
{
  "engine": "browser",
  "model": "gpt-5.2-pro",
  "browser": {
    "manualLogin": true,
    "manualLoginProfileDir": "/root/.oracle/browser-profile"
  }
}
```

Key configuration options:
- Default engine (api/browser)
- Default model
- Browser profile directory (for persistent login cookies)
- Manual login mode (user logs in once, session persists)
- ChatGPT project URL targeting

Environment variables:
- `OPENAI_API_KEY` -- for API mode with OpenAI
- `GEMINI_API_KEY` -- for API mode with Google
- `ANTHROPIC_API_KEY` -- for API mode with Anthropic
- `ORACLE_HOME_DIR` -- override session storage location
- `DISPLAY` -- X11 display for browser mode (e.g., `:99` for Xvfb)
- `CHROME_PATH` -- path to Chrome/Chromium binary

---

## 7. MCP Server Integration

Oracle provides a Model Context Protocol (MCP) server for integration with AI coding tools like Claude Code and Cursor.

### 7.1 MCP Server Binary

The `oracle-mcp` binary runs the MCP server over stdio transport.

### 7.2 MCP Tools Exposed

The MCP server registers **two tools** and **one resource type**:

#### Tool: `consult`

Runs a one-shot Oracle session. This is the primary tool for cross-AI review.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `prompt` | string | Yes | The instruction/question |
| `files` | string[] | No | File paths or glob patterns to attach |
| `model` | string | No | Single model identifier |
| `models` | string[] | No | Multiple models for fan-out (API only) |
| `engine` | enum | No | `api` or `browser` |
| `browserModelLabel` | string | No | ChatGPT UI label override |
| `browserAttachments` | enum | No | `auto`/`never`/`always` |
| `browserBundleFiles` | boolean | No | Consolidate files into single upload |
| `browserThinkingTime` | enum | No | `light`/`standard`/`extended`/`heavy` |
| `browserKeepBrowser` | boolean | No | Keep Chrome open after completion |
| `search` | boolean | No | Enable provider search (API only) |
| `slug` | string | No | Human-readable session ID |

**Implementation:** Resolves configuration, validates engine availability, creates a session, streams logs, executes via `performSessionRun()`, returns metadata + model response (tailed to 4000 bytes).

#### Tool: `sessions`

Inspects Oracle session history.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | No | Specific session ID or slug |
| `hours` | number | No | Historical window (default: 24h) |
| `limit` | number | No | Max results (default: 100) |
| `includeAll` | boolean | No | Ignore time window |
| `detail` | boolean | No | Include full metadata, request, and logs |

**Returns:** Session list (id, createdAt, status, model, mode) or detailed session with full log text.

#### Resource: Session Resources

Registers session data as MCP resources for browsing/reading by the client.

### 7.3 Integration with Claude Code

Oracle can be configured as an MCP server in Claude Code's `~/.claude/settings.json`. When configured:

- Claude Code sessions automatically have Oracle's `consult` and `sessions` tools available
- The MCP command auto-starts Xvfb and sets `CHROME_PATH` on Linux
- Claude can invoke `consult` to get GPT-5.2 Pro reviews of code during a session

This enables the **cross-AI review** workflow: Claude Code uses the `consult` tool to send code to GPT-5.2 Pro (or other models) and receives the review back, all within the same conversation.

### 7.4 Cursor IDE Integration

Oracle also provides `.cursor/mcp.json` configuration for Cursor IDE integration via deeplink.

---

## 8. Claude Code Skill

Oracle ships with a Claude Code / Codex skill in the `skills/oracle/` directory:

**File:** `skills/oracle/SKILL.md`

The skill documents:
- How to invoke Oracle from within Claude Code sessions
- Recommended workflow: browser mode with GPT-5.2 Pro
- File attachment mechanics (globs, exclusions, auto-skips)
- Token budget management (~196k tokens)
- Session management (reattach instead of re-run)
- Prompt best practices (assume zero project knowledge, include project briefing)
- Security guidance (redact secrets, avoid `.env` files)

To install: copy `skills/oracle/` to `~/.codex/skills/oracle/`

---

## 9. Remote Browser Service

Oracle includes a remote browser service for distributed setups:

```bash
oracle serve
```

This enables shared browser sessions across network clients, useful for:
- Headless servers that need browser automation
- Shared team setups where one machine handles ChatGPT login

---

## 10. Advanced Features

### 10.1 Multi-Model Runs
```bash
oracle "Validate approach" --models gpt-5.2-pro,gemini-3-pro
```
Runs the same prompt against multiple models in parallel with aggregated cost/usage tracking.

### 10.2 Azure OpenAI Support
Supports Azure OpenAI endpoints via configuration.

### 10.3 Gemini Image Generation
```bash
oracle --generate-image <file>
```

### 10.4 YouTube Video Analysis
```bash
oracle --youtube <url>
```
Uses Gemini browser mode to analyze video content.

### 10.5 Timeout Controls
Supports flexible timeout formats: `10m`, `2h`, `30s`, `500ms`.

---

## 11. Local Setup on This Server (ethics-gradient)

Oracle v0.8.5 is already installed globally on this server at `/usr/bin/oracle`.

**Configuration:** Browser mode with GPT-5.2 Pro, manual login, persistent browser profile at `~/.oracle/browser-profile`.

**Key environment (from `~/.zshrc`):**
- `DISPLAY=:99` (Xvfb virtual display)
- `CHROME_PATH=/usr/local/bin/google-chrome-wrapper`

**MCP integration:** Configured in `~/.claude/settings.json` -- Claude Code sessions have Oracle tools available automatically.

**Known patch:** `promptComposer.js` line ~352 needs re-patching after npm updates (ChatGPT UI change broke fallback commit detection).

**Re-login procedure:** Run `oracle-login`, access Chrome via noVNC at `http://100.69.187.66:6080/vnc.html`, log into ChatGPT.

---

## 12. Best Practices

1. **Always attach files** -- Oracle starts with zero project context
2. **Attach generously** -- Whole directories beat single files; stay under ~196k tokens
3. **Provide context** -- Open with project briefing (stack, build steps, constraints)
4. **Be specific** -- Spell out the question, prior attempts, and why it matters
5. **Use globs** -- `--file "src/**/*.rs"` is easier than listing files
6. **Exclude test files** -- `--file "!**/*.test.ts"` reduces noise
7. **Check tokens first** -- `--files-report` shows per-file usage
8. **Redact secrets** -- Never attach `.env`, credentials, or API keys
9. **Reattach don't re-run** -- Use `oracle session <id>` for long-running sessions
10. **Allow time for Pro models** -- GPT-5.2 Pro can take up to 10 minutes

---

## 13. Architecture Summary

```
oracle CLI
  |
  +-- Context Bundle (prompt + files -> markdown)
  |     |
  |     +-- Token counting & file filtering
  |     +-- Glob expansion, .gitignore respect
  |     +-- Size guards (1MB per file, ~196k total)
  |
  +-- Execution Engines
  |     |
  |     +-- API Mode: Direct API calls (OpenAI, Google, Anthropic, OpenRouter)
  |     +-- Browser Mode: Headless Chrome automating ChatGPT/Gemini UI
  |     +-- Manual Mode: --render --copy for clipboard
  |
  +-- Session Management
  |     |
  |     +-- Persistent storage (~/.oracle/sessions/)
  |     +-- Reattach, replay, status queries
  |
  +-- MCP Server (oracle-mcp)
        |
        +-- consult tool: Run one-shot Oracle sessions
        +-- sessions tool: Query session history
        +-- session resources: Browse session data
```

---

## 14. Key Takeaways

- **Primary use case:** Cross-AI review -- get GPT-5.2 Pro to review code while working in Claude Code
- **Two execution modes:** API (reliable, needs keys) and Browser (no keys, automates ChatGPT UI)
- **MCP-native:** Integrates directly with Claude Code as an MCP server, making `consult` and `sessions` tools available in-session
- **File-centric:** Designed around bundling project files with prompts for contextual AI review
- **Session-persistent:** Long-running sessions can be detached and reattached
- **Multi-model capable:** Can fan out the same prompt to multiple models for comparison
- **Already deployed locally:** v0.8.5 installed on ethics-gradient, configured for browser mode with GPT-5.2 Pro
