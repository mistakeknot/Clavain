---
name: oracle-review
description: Use when you need cross-AI review via Oracle (GPT-5.2 Pro or other models) — for major architectural decisions, plan validation, security review, or when a second opinion from a different model adds value
---

# Oracle Cross-AI Review

## Overview

Oracle sends prompts and files to GPT-5.2 Pro (or other models) for a second opinion from a fundamentally different AI. Use it for high-stakes decisions where model diversity reduces blind spots.

**Two execution modes:**
- **Browser mode** (default on this server) — automates ChatGPT UI, no API key needed, supports GPT-5.2 Pro
- **API mode** — direct API calls, requires keys, supports multi-model parallel runs

**MCP mode** — Oracle also runs as an MCP server (`oracle-mcp`) exposing `consult` and `sessions` tools. If configured, you can call these directly without shell commands.

## When to Use Oracle

**High value:**
- Reviewing architectural plans before implementation
- Validating complex technical decisions
- Getting a second opinion on security-sensitive designs
- Reviewing merge/migration plans with many components
- Multi-model comparison (same prompt → GPT + Gemini)

**Low value (don't bother):**
- Simple code changes
- Bug fixes with obvious causes
- Tasks where speed matters more than thoroughness

## How to Invoke

### CLI Mode (Browser)

```bash
DISPLAY=:99 CHROME_PATH=/usr/local/bin/google-chrome-wrapper \
  oracle --wait -p "Your prompt here" -f "file1.md" -f "file2.go"
```

**Key flags:**
| Flag | Description |
|------|-------------|
| `--wait` | Block until Oracle completes (required for synchronous use) |
| `-p "prompt"` | The review prompt |
| `-f "files..."` | Files/globs to include (multiple allowed) |
| `-m model` | Model selection (default: gpt-5.2-pro) |
| `--engine api` | Use API mode instead of browser |
| `--models gpt-5.2-pro,gemini-3-pro` | Multi-model parallel run (API only) |
| `--dry-run` | Preview token count without calling the model |
| `--files-report` | Show per-file token breakdown |

**For long reviews:** Run in background with `run_in_background: true` and timeout 600000ms. Check progress via `tail` on the output file.

### MCP Mode

If Oracle MCP server is configured, use the `consult` tool directly:
```
consult(
  prompt="Review this plan for gaps",
  files=["docs/plans/*.md", "src/**/*.go"],
  model="gpt-5.2-pro"
)
```

Check session history:
```
sessions(hours=24, limit=10)
```

### Multi-Model Comparison

```bash
oracle --wait -p "Validate this approach" \
  --models gpt-5.2-pro,gemini-3-pro \
  --engine api \
  -f "src/**/*.go"
```

Runs the same prompt against multiple models in parallel. Useful for validating controversial decisions.

## File Handling

- **Globs:** `-f "src/**/*.go"` expands recursively
- **Exclusions:** `-f "!src/**/*_test.go"` with `!` prefix
- **Auto-excludes:** `node_modules`, `dist`, `.git`, `build`, `tmp`
- **Token budget:** ~196k tokens total, 1MB per file max
- **Use `--files-report`** to preview per-file token consumption before sending

## Prompt Writing Tips

1. **Be specific about what you want reviewed** — "Review this plan for gaps" is too vague. "Validate every keep/drop decision and identify missing components" is actionable.
2. **Ask numbered questions** — Oracle gives better structured answers when you ask "Please provide: 1. X, 2. Y, 3. Z"
3. **Include success criteria** — "Flag any security vulnerabilities. For each, explain the attack vector and propose a fix."
4. **Provide project context** — Open with a brief project description (stack, build steps, constraints). Oracle starts with zero context.
5. **Attach generously** — Whole directories beat single files. Stay under ~196k tokens.
6. **Redact secrets** — Never attach `.env`, credentials, or API keys.

## Session Management

```bash
oracle status                        # List recent sessions
oracle status --hours 72             # Sessions from last 72 hours
oracle session <id>                  # Reattach to running/completed session
oracle session <id> --render         # Replay a session
```

**Reattach, don't re-run** — if a session is already running, use `oracle session <id>` rather than starting a new one.

## Troubleshooting

**ECONNREFUSED error:**
- Verify Xvfb is running: `pgrep -f "Xvfb :99"`
- If not running: `Xvfb :99 -screen 0 1920x1080x24 &`

**Login expired / Cloudflare challenge:**
- Tell the user to open NoVNC at `http://<server-ip>:6080/vnc.html`
- Run `oracle-login` in the VNC session
- Complete the Cloudflare check and log into ChatGPT
- Then re-run the Oracle command

## Integration

**Pairs with:**
- `writing-plans` — Review plans before execution
- `plan-review` command — Use alongside Clavain's own multi-agent review for model diversity
- `brainstorming` — Get Oracle's take on approach options
- `agent-mail-coordination` — Share Oracle results across agents via Agent Mail messages (attach review output to a thread)

**Example workflow:**
1. Write a plan with `/clavain:write-plan`
2. Review with Clavain agents: `/clavain:plan-review`
3. For high-stakes plans, also get Oracle review for model diversity
4. Synthesize both reviews, resolve conflicts, then execute
