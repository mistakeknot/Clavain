---
name: oracle-review
description: Use when you need cross-AI review via Oracle (GPT-5.2 Pro) — for major architectural decisions, plan validation, or when a second opinion from a different model adds value
---

# Oracle Cross-AI Review

## Overview

Oracle sends prompts and files to GPT-5.2 Pro via browser automation, providing a second opinion from a fundamentally different AI model. Use it for high-stakes decisions where model diversity reduces blind spots.

## When to Use Oracle

**High value:**
- Reviewing architectural plans before implementation
- Validating complex technical decisions
- Getting a second opinion on security-sensitive designs
- Reviewing merge/migration plans with many components

**Low value (don't bother):**
- Simple code changes
- Bug fixes with obvious causes
- Tasks where speed matters more than thoroughness

## How to Invoke

```bash
DISPLAY=:99 CHROME_PATH=/usr/local/bin/google-chrome-wrapper \
  oracle --wait -p "Your prompt here" -f "file1.md" -f "file2.go"
```

**Key flags:**
- `--wait` — Block until Oracle completes (required for synchronous use)
- `-p "prompt"` — The review prompt
- `-f "files..."` — Files/globs to include as context
- `-m model` — Model selection (default: gpt-5.2-pro)
- `--engine browser` — Use browser mode (default on this server)

**For long reviews:** Run in background with `run_in_background: true` and timeout 600000ms. Check progress via `tail` on the output file.

## Prompt Writing Tips

1. **Be specific about what you want reviewed** — "Review this plan for gaps" is too vague. "Validate every keep/drop decision and identify missing components" is actionable.
2. **Ask numbered questions** — Oracle gives better structured answers when you ask "Please provide: 1. X, 2. Y, 3. Z"
3. **Include success criteria** — "Flag any security vulnerabilities. For each, explain the attack vector and propose a fix."
4. **Provide full context** — Include the relevant files. Oracle can't read your codebase directly.

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
- `plan_review` — Use alongside Clavain's own multi-agent review for model diversity
- `brainstorming` — Get Oracle's take on approach options

**Example workflow:**
1. Write a plan with `/clavain:write-plan`
2. Review with Clavain agents: `/clavain:plan_review`
3. For high-stakes plans, also get Oracle review for model diversity
4. Synthesize both reviews, resolve conflicts, then execute
