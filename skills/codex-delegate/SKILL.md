---
name: codex-delegate
description: Delegate well-scoped implementation, exploration, search, test-generation, or code-review tasks to Codex CLI. Not for architecture or interactive work.
---

# Codex Delegate

Take well-scoped tasks, dispatch them through dispatch.sh under a governed role, and return results.

**The role decides the backend.** `dispatch.sh` resolves the role through `config/routing.yaml` and runs whatever seat the policy names. That is the Codex CLI backend only when routing resolves the role to it; otherwise the resolved seat (for example a Claude model) runs the task. Do not choose a backend, model or tier yourself, and do not call `codex` directly. Nothing here changes routing, adds a spend path or adds a model choice.

## Enrolled measured work

For a task with an authoritative enrollment, follow the "Enrolled measured work"
section of `clavain:interserve-engine`. It takes precedence over the dispatcher
discovery and role examples below, and it is the one place the enrollment
invocation, role choice and evidence rules are kept. Do not choose the first
cached dispatcher or use `--tier` for enrolled work.

## Role Selection

| Category | Role | Sandbox |
|----------|------|---------|
| exploration, doc-update | `scout` | read-only |
| implementation, test-generation | `deep-execution` (`routine-execution` for bounded routine edits) | workspace-write |
| review | `validation` (add `--producer-identity` from the author's receipt) | read-only |

## Workflow

**1. Resolve dispatch.sh**
```bash
DISPATCH=$(find ~/.claude/plugins/cache -path '*/clavain/*/scripts/dispatch.sh' 2>/dev/null | head -1)
[ -z "$DISPATCH" ] && DISPATCH=$(find ~/projects -name dispatch.sh -path '*/clavain/*/scripts/*' 2>/dev/null | head -1)
```
If not found, report failure — do not call codex directly.

**2. Write prompt to `/tmp/codex-delegate-$(date +%s).md`**

Frame the task as one OODARC **Act** leg (the dispatched agent will also receive an Orient briefing when `--inject-docs` is used):
- **Orient:** name the relevant files/conventions and what "done right" looks like for this task class — be specific about file paths.
- **Act:** one clear objective per dispatch; include build/test commands for code changes.
- **Reflect:** end with `VERDICT: CLEAN | NEEDS_ATTENTION` + one-line summary, so you (the caller) can Reflect on the outcome and Compound any lesson.

**3. Dispatch**
```bash
CLAVAIN_DECISION_CONTEXT="$DECISION_FILE" bash "$DISPATCH" \
  --role {scout|routine-execution|deep-execution|validation} \
  --prompt-file "$TASK_FILE" \
  -C "{project_dir}" \
  -o "/tmp/codex-result-$(date +%s).md" \
  -s {read-only|workspace-write}
```
`$DECISION_FILE` is a JSON decision context (see `docs/canon/reasoning-routing.md`); settled routine work is `{"reasons": [], "rationale": "...", "investigation_active": false}`. Set `CLAVAIN_ROUTING_POLICY` as that canon describes. `--tier` cannot satisfy role resolution; do not use it.
Use `timeout: 600000`.

**4. Read results**
- Check `.verdict` sidecar first; `pass` → brief summary; `warn`/`fail` → read full output
- Retry once with tighter scope; if retry fails, return failure to the caller

**5. Reflect — record outcome** (OODARC Reflect leg: the dispatch ran the *Act* leg; capturing its result here is how the caller Reflects and Compounds)
```bash
_db="$(git rev-parse --show-toplevel 2>/dev/null || pwd)/.clavain/interspect/interspect.db"
if command -v sqlite3 &>/dev/null && [ -f "$_db" ]; then
  _ts=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  _session="${CLAUDE_SESSION_ID:-unknown}"
  _project="$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")"
  _seq=$(sqlite3 "$_db" "SELECT COALESCE(MAX(seq),0)+1 FROM evidence WHERE session_id='$_session';" 2>/dev/null || echo "1")
  # oodarc_phase tags which leg this evidence is about, so cross-session
  # learning can attribute by leg. The dispatch performed the Act leg.
  _ctx="{\"category\":\"$CATEGORY\",\"role\":\"$ROLE\",\"verdict\":\"$VERDICT\",\"retry_needed\":$RETRY,\"duration_s\":$DURATION,\"oodarc_phase\":\"act\"}"
  sqlite3 "$_db" "INSERT INTO evidence (ts,session_id,seq,source,event,override_reason,context,project) VALUES ('$_ts','$_session',$_seq,'codex-delegate','delegation_outcome','','$_ctx','$_project');" 2>/dev/null || true
fi
```
Skip silently if DB missing. This writes to the **existing** interspect `evidence` table (no new store); `oodarc_phase` is just an added field in the context JSON.

**6. Return** role used, verdict, key output, whether retry was needed.

## Memory

Track per-project: which patterns succeed/fail, scope issues, preferred role/sandbox, build/test commands.

## Rules

1. NEVER call `codex` directly — always use dispatch.sh
2. One task per dispatch
3. Retry once max; escalate failures to the caller
4. Always record outcomes (failures are calibration data)
5. Don't block on tracking failures
6. Report honestly — if task seems too complex for Codex, say so immediately
