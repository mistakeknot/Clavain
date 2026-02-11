---
module: Clodex
date: 2026-02-11
problem_type: integration_issue
component: cli
symptoms:
  - "error: unexpected argument '--approval-mode' found"
  - "Agent calls bare 'codex' instead of 'codex exec' — opens interactive mode or errors"
  - "Agent uses '--file' flag that does not exist in current Codex CLI"
root_cause: wrong_api
resolution_type: documentation_update
severity: medium
tags: [codex-cli, deprecated-flags, approval-mode, full-auto, clodex, ai-agent-hallucination]
---

# Troubleshooting: Codex CLI Deprecated Flags Cause Agent Dispatch Failures

## Problem
AI agents (Claude, Codex) hallucinate old Codex CLI flags when bypassing dispatch.sh, causing `unexpected argument` errors. The old API used `codex --approval-mode full-auto --model o3 -q --file task.md` as top-level flags; the current API requires `codex exec --full-auto` with completely different flag syntax.

## Environment
- Module: Clodex (Codex dispatch skill)
- Affected Component: CLI invocation in skills/clodex/
- Date: 2026-02-11

## Symptoms
- `error: unexpected argument '--approval-mode' found` when agent calls `codex --approval-mode full-auto`
- Agent opens interactive Codex session instead of non-interactive execution (called bare `codex` without `exec`)
- `unexpected argument '--file'` or `unexpected argument '-q'` — flags that don't exist in current CLI

## What Didn't Work

**Direct solution:** The problem was identified and fixed on the first attempt by reading `codex exec --help` to confirm current flag syntax and adding guards to the skill documentation.

## Solution

Three-layer defense added to prevent agents from bypassing dispatch.sh with old flags:

**1. SKILL.md guard** — "Critical: Always Use dispatch.sh" section with wrong→right mappings:
```markdown
## Critical: Always Use dispatch.sh

**NEVER call `codex` directly.** Always use `dispatch.sh` which wraps `codex exec` with correct flags.
- `codex --approval-mode full-auto` — **wrong**, use `codex exec --full-auto`
- `codex --file task.md` — **wrong**, use dispatch.sh `--prompt-file`
- Bare `codex "prompt"` — **wrong**, opens interactive mode. Always `codex exec "prompt"`
```

**2. cli-reference.md** — Deprecated flags table:
```markdown
| Wrong | Correct |
|-------|---------|
| `codex --approval-mode full-auto` | `codex exec --full-auto` |
| `codex -q` / `codex --quiet` | No quiet flag exists |
| `codex --file <FILE>` | Use `--prompt-file` (dispatch.sh) or positional arg |
```

**3. troubleshooting.md** — Error pattern rows:
```markdown
| `unexpected argument '--approval-mode'` | Old API. Use `codex exec --full-auto` |
| `unexpected argument '--file'` | No `--file` flag. Use dispatch.sh `--prompt-file` |
| `codex` hangs / opens interactive | Called bare `codex` — always use `codex exec` |
```

## Why This Works

1. **Root cause**: Codex CLI went through a breaking API change. The old version had `--approval-mode` as a top-level flag with values (`full-auto`, `suggest`, etc.). The current version uses `codex exec` as a required subcommand, with `--full-auto` as a boolean convenience flag (no value argument).

2. **Why agents hallucinate old flags**: LLMs trained on documentation or code examples from the old Codex CLI version will generate the old syntax. Since the skill prompt is the agent's primary reference, adding explicit wrong→right mappings prevents this.

3. **Why dispatch.sh is the correct abstraction**: It wraps `codex exec` with validated flags (line 316: `CMD=(codex exec)`), handles sandbox defaults, inject-docs, template assembly, and dry-run mode. Direct `codex` calls bypass all these safeguards.

## Prevention

- **Always route through dispatch.sh** — never construct `codex` commands manually in prompts or skills
- **When updating Codex CLI**: re-run `codex exec --help` and update `cli-reference.md` with any new/changed flags
- **The dispatch.sh passthrough list** (line 137-160) whitelists known Codex flags — new flags must be added there to be forwarded

## Related Issues

- See also: [new-agents-not-available-until-restart-20260210.md](./new-agents-not-available-until-restart-20260210.md) — another integration issue with plugin/agent lifecycle
