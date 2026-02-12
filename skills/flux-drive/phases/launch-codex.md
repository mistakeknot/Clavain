# Phase 2: Launch (Codex Dispatch)

**Condition**: Use this file when `DISPATCH_MODE = codex`. This routes review agents through Codex CLI instead of Claude subagents.
**Shared contracts**: See `phases/shared-contracts.md` for output format, completion signals, prompt trimming, and monitoring.

## Resolve paths (with guards)

```bash
DISPATCH=$(find ~/.claude/plugins/cache -path '*/clavain/*/scripts/dispatch.sh' 2>/dev/null | head -1)
[[ -z "$DISPATCH" ]] && DISPATCH=$(find ~/projects/Clavain -name dispatch.sh -path '*/scripts/*' 2>/dev/null | head -1)
[[ -z "$DISPATCH" ]] && { echo "FATAL: dispatch.sh not found"; exit 1; }

REVIEW_TEMPLATE=$(find ~/.claude/plugins/cache -path '*/clavain/*/skills/clodex/templates/review-agent.md' 2>/dev/null | head -1)
[[ -z "$REVIEW_TEMPLATE" ]] && REVIEW_TEMPLATE=$(find ~/projects/Clavain -path '*/skills/clodex/templates/review-agent.md' 2>/dev/null | head -1)
[[ -z "$REVIEW_TEMPLATE" ]] && { echo "FATAL: review-agent.md template not found"; exit 1; }
```

If either path resolution fails, fall back to Task dispatch (`phases/launch.md` step 2.2) for this run.

## Project Agent bootstrap (codex mode only)

Before dispatching Project Agents, check if they exist and are current:

```bash
FD_AGENTS=$(ls .claude/agents/fd-*.md 2>/dev/null)

if [[ -z "$FD_AGENTS" ]]; then
  BOOTSTRAP=true
else
  CURRENT_HASH=$(sha256sum CLAUDE.md AGENTS.md 2>/dev/null | sha256sum | cut -d' ' -f1)
  STORED_HASH=$(cat .claude/agents/.fd-agents-hash 2>/dev/null || echo "none")
  if [[ "$CURRENT_HASH" != "$STORED_HASH" ]]; then
    echo "Project Agents are stale (project docs changed) — regenerating"
    BOOTSTRAP=true
  else
    BOOTSTRAP=false
  fi
fi
```

When `BOOTSTRAP=true`, dispatch a **blocking** Codex agent to create Project Agents:

```bash
BOOTSTRAP_TEMPLATE=$(find ~/.claude/plugins/cache -path '*/clavain/*/skills/clodex/templates/create-review-agent.md' 2>/dev/null | head -1)
[[ -z "$BOOTSTRAP_TEMPLATE" ]] && BOOTSTRAP_TEMPLATE=$(find ~/projects/Clavain -path '*/skills/clodex/templates/create-review-agent.md' 2>/dev/null | head -1)
[[ -z "$BOOTSTRAP_TEMPLATE" ]] && { echo "WARNING: create-review-agent.md not found — skipping Project Agent bootstrap"; BOOTSTRAP=false; }
```

Dispatch **without `run_in_background`** so it blocks until complete. Use `--tier fast` (scoped generation task). Set `timeout: 300000` (5 minutes). If bootstrap fails or times out, skip Project Agents for this run — do NOT block the rest of the review.

## Create temp directory and task description files

```bash
FLUX_TMPDIR=$(mktemp -d /tmp/flux-drive-XXXXXX)
```

For each selected agent, write a task description file to `$FLUX_TMPDIR/{agent-name}.md`.

**IMPORTANT**: Each section header (`PROJECT:`, `AGENT_IDENTITY:`, etc.) must be on its own line with the colon at end-of-line. Content goes on subsequent lines. This matches dispatch.sh's `^[A-Z_]+:$` section parser.

```
PROJECT:
{project name} — review task (read-only)

AGENT_IDENTITY:
{paste the agent's full system prompt from the agent .md file}

REVIEW_PROMPT:
{the same prompt template from phases/launch.md, with trimmed document content, focus area, and output requirements}

AGENT_NAME:
{agent-name}

TIER:
{project|adaptive|cross-ai}
(Note: This TIER field is metadata for tracking. dispatch.sh handles model selection via its --tier flag.)

OUTPUT_FILE:
{OUTPUT_DIR}/{agent-name}.md
```

Prompt trimming for `AGENT_IDENTITY` uses the shared contract in `phases/shared-contracts.md`.

## Dispatch all agents in parallel

Launch all Codex agents via parallel Bash calls in a single message:

```bash
bash "$DISPATCH" \
  --template "$REVIEW_TEMPLATE" \
  --prompt-file "$FLUX_TMPDIR/{agent-name}.md" \
  -C "$PROJECT_ROOT" \
  -s workspace-write \
  --tier deep
```

Notes:
- Set `run_in_background: true` and `timeout: 600000` on each Bash call
- Do NOT use `--inject-docs` — Codex reads CLAUDE.md natively via `-C`
- Do NOT use `-o` for output capture — the agent writes findings directly to `{OUTPUT_DIR}/{agent-name}.md`
- **Cross-AI (Oracle)**: Unchanged — already dispatched via Bash

Monitor using the shared monitoring contract. Codex timeout is 10 minutes.

## Error handling

After all background Bash calls complete, check for missing findings files. For any agent whose `{OUTPUT_DIR}/{agent-name}.md` does not exist:
1. Check the background Bash exit code — if non-zero, log the error
2. Retry once with the same prompt file
3. If retry also produces no findings file, fall back to Task dispatch for that agent
4. Note the failure in the synthesis summary: "Agent X: Codex dispatch failed, used Task fallback"

## Cleanup

After Phase 3 synthesis completes, remove the temp directory:
```bash
rm -rf "$FLUX_TMPDIR"
```
