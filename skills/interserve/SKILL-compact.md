# Interserve (compact)

Dispatch tasks to Codex CLI agents. Claude orchestrates — planning, dispatching, verifying, committing.

## Prerequisites

Codex CLI installed (`which codex`). If unavailable, fall back to `clavain:subagent-driven-development`.

## Step 0: Resolve dispatch.sh

```bash
DISPATCH=$(find ~/.claude/plugins/cache -path '*/clavain/*/scripts/dispatch.sh' 2>/dev/null | head -1)
[ -z "$DISPATCH" ] && DISPATCH=$(find ~/projects/Clavain -name dispatch.sh -path '*/scripts/*' 2>/dev/null | head -1)
```

**NEVER call `codex` directly.** Always use `dispatch.sh`.

## Model Tiers

| Tier | Model | Use for |
|------|-------|---------|
| fast | gpt-5.3-codex-spark | Read-only, verification, quick reviews |
| deep | gpt-5.3-codex | Implementation, complex reasoning |

`--tier` and `-m` are mutually exclusive. For x-high: `CLAVAIN_DISPATCH_PROFILE=interserve bash "$DISPATCH" ...`

## Routing

| Situation | Mode |
|-----------|------|
| Single task | Megaprompt |
| 2+ independent tasks | Parallel delegation |
| Sequential dependent tasks | Ordered delegation |
| Complex decision first | Debate (see references/debate-mode.md) |

## Megaprompt Mode

1. Write prompt file: goal, files, build/test commands, verdict suffix (`VERDICT: CLEAN | NEEDS_ATTENTION`)
2. Save to `/tmp/codex-task-$(date +%s).md`
3. Dispatch:
   ```bash
   CLAVAIN_DISPATCH_PROFILE=interserve bash "$DISPATCH" \
     --prompt-file "$TASK_FILE" -C "$PROJECT_DIR" \
     -o "/tmp/codex-result-$(date +%s).md" -s workspace-write --tier deep
   ```
   Use `timeout: 600000`.
4. Read `.verdict` sidecar first. `pass` → trust. `warn`/`fail` → read full output, retry once.
5. If retry fails: offer Split mode, direct edit, or skip.

## Parallel Delegation

1. Classify tasks: independent → Codex, exploratory → Claude subagent, sequential → ordered dispatch
2. Check file overlap — combine or serialize conflicting tasks
3. Write one prompt file per task
4. Launch all Bash calls in a single message. `timeout: 600000` each.
5. Verify each: read output, build, test, review diff. Use `clavain:landing-a-change` to commit.

## Scope test commands

Always use `-run TestPattern`, `-short`, `-timeout=60s`. NEVER broad `go test ./... -v`.

---

*For debate mode, Oracle escalation, split mode fallback, or CLI flag reference, read the references/ directory.*
