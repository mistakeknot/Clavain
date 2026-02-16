# Interserve Behavioral Contract

> This contract is enforced purely through session-start context injection. There is no PreToolUse hook.

## Three Rules

1. **Plan freely** — Read, Grep, Glob are unrestricted
2. **Dispatch source code changes** — Use /interserve to send implementation tasks to Codex agents
3. **Edit non-code directly** — .md, .json, .yaml, .yml, .toml, .txt, .csv, .xml, .html, .css, .svg, .lock, .cfg, .ini, .conf, .env, /tmp/*

## Bash Restriction

Bash is read-only for source files. No writing (redirects, sed -i, tee), no deleting (rm), no renaming (mv).
Allowed: git commands, test runners, build tools, read-only inspection.

## Exception

Git operations (add, commit, push) are Claude's responsibility — do them directly.

## When Codex is Unavailable

If Codex CLI is not installed, fall back to /subagent-driven-development or run /interserve-toggle to turn off.
