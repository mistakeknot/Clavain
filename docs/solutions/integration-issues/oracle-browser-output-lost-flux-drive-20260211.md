---
module: flux-drive
date: 2026-02-11
problem_type: integration_issue
component: tooling
symptoms:
  - "Oracle browser mode output file contains only banner text, no GPT response"
  - "Oracle sessions permanently stuck as status 'running' in meta.json"
  - "Exit code 124 from timeout wrapper killing Oracle before completion"
  - "Model logs (gpt-5.2-pro.log) empty — 0 lines"
root_cause: config_error
resolution_type: documentation_update
severity: high
tags: [oracle, browser-mode, flux-drive, stdout-redirect, write-output, timeout]
---

# Troubleshooting: Oracle Browser Mode Output Lost in Flux-Drive Reviews

## Problem
When flux-drive dispatches Oracle for cross-AI review (Phase 2), the output file (`oracle-council.md.partial`) contains only Oracle's startup banner but no GPT-5.2 Pro response. The GPT response appears in the ChatGPT browser tab but is never captured to the output file.

## Environment
- Module: flux-drive (Oracle cross-AI integration)
- Oracle Version: 0.8.5
- Affected Component: `skills/flux-drive/SKILL.md` Oracle launch template
- Date: 2026-02-11

## Symptoms
- Output file contains only: `"Launching browser mode (gpt-5.2-pro) with ~4,062 tokens.\nThis run can take up to an hour (usually ~10 minutes)."`
- `oracle status` shows sessions stuck as `"running"` — never transitions to `"completed"`
- Model log files (`models/gpt-5.2-pro.log`) are empty (0 lines)
- Background Bash task exits with code 124 (SIGTERM from `timeout`)
- GPT-5.2 Pro actually responds successfully in the browser — response visible in ChatGPT tab

## What Didn't Work

**Attempted Solution 1:** Increased timeout from 480s to 600s
- **Why it failed:** GPT-5.2 Pro browser mode routinely takes 10-30 minutes. Even 600s (10min) isn't enough. The underlying problem isn't just timeout length — it's that external `timeout` sends SIGTERM which kills Oracle before it can write output.

**Attempted Solution 2:** Re-launched with shorter prompt to reduce GPT response time
- **Why it failed:** Response time is not the core issue. Even if Oracle completes within the timeout, `> file 2>&1` redirect doesn't reliably capture browser mode output due to how Oracle writes the response.

## Solution

Three changes to the Oracle launch template in `skills/flux-drive/SKILL.md`:

**Before (broken):**
```bash
timeout 480 env DISPLAY=:99 CHROME_PATH=/usr/local/bin/google-chrome-wrapper \
  oracle --wait -p "..." \
  -f "..." > {OUTPUT_DIR}/oracle-council.md.partial 2>&1 && \
  echo '<!-- flux-drive:complete -->' >> {OUTPUT_DIR}/oracle-council.md.partial && \
  mv {OUTPUT_DIR}/oracle-council.md.partial {OUTPUT_DIR}/oracle-council.md || \
  (echo -e "..." > {OUTPUT_DIR}/oracle-council.md)
```

**After (fixed):**
```bash
env DISPLAY=:99 CHROME_PATH=/usr/local/bin/google-chrome-wrapper \
  oracle --wait --timeout 1800 \
  --write-output {OUTPUT_DIR}/oracle-council.md.partial \
  -p "..." \
  -f "..." && \
  echo '<!-- flux-drive:complete -->' >> {OUTPUT_DIR}/oracle-council.md.partial && \
  mv {OUTPUT_DIR}/oracle-council.md.partial {OUTPUT_DIR}/oracle-council.md || \
  (echo -e "..." > {OUTPUT_DIR}/oracle-council.md)
```

Key changes:
1. **`--write-output <path>` instead of `> file 2>&1`** — writes clean assistant text to file
2. **Removed external `timeout` wrapper** — prevents SIGTERM killing Oracle mid-operation
3. **Added `--timeout 1800`** — Oracle's internal timeout handles cleanup properly

Also updated:
- `skills/interpeer/references/oracle-reference.md` — added `--write-output` and `--timeout` to key flags table
- `skills/interpeer/references/oracle-troubleshooting.md` — added three new troubleshooting entries

## Why This Works

Three compounding root causes were identified by reading Oracle's Node.js source:

1. **Browser mode uses `console.log()` for response output** (`dist/src/browser/sessionRunner.js:73`): The browser session runner calls `log(browserResult.answerMarkdown)` where `log` is `console.log`. This includes chalk ANSI formatting when stdout is a TTY. When piped via `> file 2>&1`, the ANSI codes contaminate the output and the response may not flush before process termination.

2. **External `timeout` sends SIGTERM** which kills Oracle before it reaches the session cleanup code (`dist/src/cli/sessionRunner.js:66-79`). This cleanup updates `meta.json` status to "completed", writes model logs, and calls `writeAssistantOutput()`. Without cleanup: sessions stay "running", logs stay empty, `--write-output` never executes.

3. **`--write-output` is purpose-built** (`dist/src/cli/sessionRunner.js:79`): It calls `writeAssistantOutput(runOptions.writeOutputPath, result.answerText, log)` which writes clean text (no ANSI, no banner) directly to the specified path. This happens after the browser scrape completes but as part of Oracle's own session lifecycle.

Oracle's internal `--timeout` (default 60m for gpt-5.2-pro) handles timeout gracefully — it marks sessions as timed-out, writes partial output, and exits cleanly.

## Prevention

- **Always use `--write-output <path>` for Oracle browser mode** — never redirect stdout (`> file`)
- **Never wrap Oracle with external `timeout`** — use `--timeout <seconds>` flag instead
- **Budget 30 minutes for GPT-5.2 Pro browser reviews** — `--timeout 1800` is a reasonable cap
- **If a session gets stuck**: use `oracle session <id>` to reattach and recover the response
- **The interpeer skill already had the correct pattern** (`--write-output` on line 200 of SKILL.md) — flux-drive was the only surface with the broken pattern

## Related Issues

- See also: [new-agents-not-available-until-restart-20260210.md](./new-agents-not-available-until-restart-20260210.md) — another integration timing issue
