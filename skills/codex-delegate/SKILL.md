---
name: codex-delegate
description: Delegate well-scoped implementation, exploration, search, test-generation, or code-review tasks to Codex CLI. Not for architecture or interactive work.
---

# Codex Delegate

Take well-scoped tasks, dispatch them to Codex CLI via dispatch.sh, and return results.

## Enrolled measured work

For an enrolled task, use the canonical checkout and an explicit role through
the enrollment helper. This takes precedence over the cached dispatcher and
tier examples below. Do not choose the first cached dispatcher or use `--tier`
for enrolled work.

```bash
CLAVAIN_ROOT="${CLAVAIN_SOURCE_DIR:-$HOME/projects/Sylveste/os/Clavain}"
python3 "$CLAVAIN_ROOT/scripts/task-delivery.py" \
  --db "${CLAVAIN_TASK_INTERCORE_DB:?set the authoritative Intercore database}" \
  dispatch --enrollment-id "${CLAVAIN_TASK_ENROLLMENT_ID:?enroll before dispatch}" \
  --role deep-execution -- --prompt-file "$TASK_FILE" -C "$PROJECT_DIR" -o "$OUTPUT"
```

Choose `scout` for exploration, `routine-execution` for bounded routine work,
`deep-execution` for demanding implementation, and `validation` for independent
assessment. Validation supplies `--producer-identity`; the canonical resolver
records the effective validator relationship. The helper retains the enrollment
hash and dispatch identity; record actual provider session/thread/turn bindings
and evidence afterward, leaving unavailable identities explicitly incomplete.
Count failed attempts, validation, repairs and handoff preparation. Never retry
policy blocks or indeterminate worker outcomes automatically. Execution results
do not grant independent acceptance; the helper records acceptance separately
through Intercore decisions. Shared coordinator usage belongs once to
`cohort_shared`; human active minutes require an explicit estimate.

## Tier Selection

| Category | Tier | Sandbox |
|----------|------|---------|
| exploration, doc-update | fast | read-only |
| implementation, review, test-generation | deep | workspace-write |

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
CLAVAIN_DISPATCH_PROFILE=interserve bash "$DISPATCH" \
  --prompt-file "$TASK_FILE" \
  -C "{project_dir}" \
  -o "/tmp/codex-result-$(date +%s).md" \
  -s {read-only|workspace-write} \
  --tier {fast|deep}
```
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
  _ctx="{\"category\":\"$CATEGORY\",\"tier\":\"$TIER\",\"verdict\":\"$VERDICT\",\"retry_needed\":$RETRY,\"duration_s\":$DURATION,\"oodarc_phase\":\"act\"}"
  sqlite3 "$_db" "INSERT INTO evidence (ts,session_id,seq,source,event,override_reason,context,project) VALUES ('$_ts','$_session',$_seq,'codex-delegate','delegation_outcome','','$_ctx','$_project');" 2>/dev/null || true
fi
```
Skip silently if DB missing. This writes to the **existing** interspect `evidence` table (no new store — sylveste-104h); `oodarc_phase` is just an added field in the context JSON.

**6. Return** tier used, verdict, key output, whether retry was needed.

## Memory

Track per-project: which patterns succeed/fail, scope issues, preferred tier/sandbox, build/test commands.

## Rules

1. NEVER call `codex` directly — always use dispatch.sh
2. One task per dispatch
3. Retry once max; escalate failures to the caller
4. Always record outcomes (failures are calibration data)
5. Don't block on tracking failures
6. Report honestly — if task seems too complex for Codex, say so immediately
