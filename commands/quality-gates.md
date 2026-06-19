---
name: quality-gates
description: Gate orchestrator — prepares diff, delegates review to flux-drive, enforces pass/fail gate
argument-hint: "[optional: specific files or 'all' for full diff]"
---

# Quality Gates

Gate orchestrator that composes flux-drive for agent selection/dispatch and owns the pass/fail gate decision. Does NOT select or dispatch agents itself — flux-drive is the single owner of agent triage.

<BEHAVIORAL-RULES>
1. **Execute phases in order.** No skipping or reordering.
2. **Write findings to files.** Agent output goes to `{OUTPUT_DIR}/`, not conversation context.
3. **Stop at gates.** FAIL blocks shipping — do not auto-proceed.
4. **Exactly 4 phases (1-4).** Do NOT invent, rename, or append phases. Resolution and shipping are the sprint orchestrator's domain.
</BEHAVIORAL-RULES>

## Progress Tracking

```
Quality Gates Progress:
- [ ] Phase 1: Analyze Changes
- [ ] Phase 2: Dispatch Review
- [ ] Phase 3: Gate Decision
- [ ] Phase 4: File Findings (optional)
```

Mark each `[x]` as you complete it. After Phase 4, quality gates is **done** — no further phases exist.

## Input

<review_target> #$ARGUMENTS </review_target>

No arguments → analyze current unstaged + staged changes (`git diff` + `git diff --cached`).

## Phase 1: Analyze Changes

```bash
git diff --name-only HEAD
git diff --cached --name-only
```

Count changed files, total diff lines, and raw B2 complexity signals:
```bash
DIFF_LINES=$(( $(git diff HEAD | wc -l) + $(git diff --cached | wc -l) ))
CHANGED_FILES=$(( $(git diff --name-only HEAD | wc -l) + $(git diff --cached --name-only | wc -l) ))
REVIEW_TOKENS=$(( DIFF_LINES * 4 ))
REVIEW_DEPTH=2
export CLAVAIN_REVIEW_TOKENS="$REVIEW_TOKENS"
export CLAVAIN_REVIEW_FILE_COUNT="$CHANGED_FILES"
export CLAVAIN_REVIEW_DEPTH="$REVIEW_DEPTH"
```

**Small change shortcut:** If `DIFF_LINES < 20` and `CHANGED_FILES == 1`, resolve `fd-quality` through B2 in shadow mode, then run only that single fd-quality agent directly (Task tool, `subagent_type: "interflux:review:fd-quality"`, `model: "${FD_QUALITY_MODEL}"`). Include the diff in the prompt. Skip Phases 2-3. After agent returns, jump to Phase 4.

```bash
ROUTING_LIB="${CLAVAIN_SOURCE_DIR:-${CLAVAIN_DIR:-${CLAUDE_PLUGIN_ROOT:-}}}/scripts/lib-routing.sh"
if [[ -f "$ROUTING_LIB" ]]; then
    # Caller-local shadow rollout: observe B2 decisions without changing the
    # global routing.yaml default for other surfaces.
    source "$ROUTING_LIB"
    declare -F _routing_load_cache >/dev/null && _routing_load_cache
    _ROUTING_CX_MODE="${CLAVAIN_QG_COMPLEXITY_MODE:-shadow}"
    FD_QUALITY_ROUTE=$(routing_resolve_agents --phase "quality-gates" --agents "fd-quality" --prompt-tokens "$REVIEW_TOKENS" --file-count "$CHANGED_FILES" --reasoning-depth "$REVIEW_DEPTH") || FD_QUALITY_ROUTE="{}"
    FD_QUALITY_MODEL=$(printf '%s' "$FD_QUALITY_ROUTE" | jq -r '."fd-quality" // "sonnet"' 2>/dev/null || echo sonnet)
else
    FD_QUALITY_MODEL="sonnet"
fi
```

Otherwise, prepare the diff file for flux-drive:

```bash
TS=$(date +%s)
DIFF_PATH="/tmp/qg-diff-${TS}.txt"
git diff HEAD > "$DIFF_PATH"
git diff --cached >> "$DIFF_PATH"
```

## Phase 2: Dispatch Review

Delegate agent selection, dispatch, and synthesis to flux-drive. flux-drive owns the triage algorithm, project agents, routing overrides, domain scoring, and content slicing.

`/interflux:flux-drive $DIFF_PATH --phase=quality-gates`

flux-drive will:
1. Detect `INPUT_TYPE = diff` from the file content
2. Run its full triage (scoring, project agents, routing overrides, domain detection)
3. Dispatch agents in stages
4. Synthesize findings via intersynth

**Capture flux-drive's outcome.** After flux-drive returns, record whether it
completed successfully into `FLUX_DRIVE_STATUS` (export it) so the gate guard
below can fail closed on error. Set `FLUX_DRIVE_STATUS=0` only if flux-drive ran
to completion and reported success; set it to a non-zero value (e.g. `1`) if
flux-drive errored, timed out, was interrupted, or produced no synthesis. Do NOT
default it to `0` — absence of a clear success signal is a failure.

```bash
export FLUX_DRIVE_STATUS="${FLUX_DRIVE_STATUS:-1}"
```

After flux-drive completes, its output directory contains `synthesis.md` and per-agent findings.

Locate the synthesis:
```bash
# flux-drive writes to docs/research/flux-drive/{INPUT_STEM}/
DIFF_STEM=$(basename "$DIFF_PATH" .txt)
FLUX_OUTPUT_DIR="${PROJECT_ROOT}/docs/research/flux-drive/${DIFF_STEM}"
# Copy synthesis to quality-gates canonical location
OUTPUT_DIR="${PROJECT_ROOT}/.clavain/quality-gates"
mkdir -p "$OUTPUT_DIR"
cp "$FLUX_OUTPUT_DIR/synthesis.md" "$OUTPUT_DIR/synthesis.md" 2>/dev/null || true
cp "$FLUX_OUTPUT_DIR/synthesis.json" "$OUTPUT_DIR/synthesis.json" 2>/dev/null || true
```

**Fail-closed guard.** Before any gate decision, verify a *fresh* review actually
landed. The `|| true` above never aborts on a missing source, so this guard is the
single source of fail-closed truth: if flux-drive errored, or the synthesis is
absent or stale (left over from a prior run), block shipping rather than passing
unreviewed code.

```bash
SYNTH_MD="$OUTPUT_DIR/synthesis.md"
SYNTH_JSON="$OUTPUT_DIR/synthesis.json"
if [[ "${FLUX_DRIVE_STATUS:-1}" -ne 0 ]]; then
    echo "quality-gates: flux-drive did not complete (status=${FLUX_DRIVE_STATUS:-unset}); no fresh review produced. Gate FAILS CLOSED (blocking shipping). Re-run /clavain:quality-gates after fixing flux-drive." >&2
    exit 1
fi
if [[ ! -f "$SYNTH_MD" || ! -f "$SYNTH_JSON" ]]; then
    echo "quality-gates: review synthesis missing ($SYNTH_MD / $SYNTH_JSON). flux-drive produced no output. Gate FAILS CLOSED (blocking shipping). Re-run /clavain:quality-gates." >&2
    exit 1
fi
if [[ "$SYNTH_MD" -ot "$DIFF_PATH" || "$SYNTH_JSON" -ot "$DIFF_PATH" ]]; then
    echo "quality-gates: review synthesis is STALE (older than the diff under review); it was not regenerated this run. Gate FAILS CLOSED (blocking shipping). Re-run /clavain:quality-gates." >&2
    exit 1
fi

# Ship-class fd-safety enforcement (fail-closed). Ship-class surfaces — plugin
# manifests, MCP configs, hook scripts, interlock/authorization/capability
# files, signing-key paths, shell-out paths — execute or gate platform code, so
# an unreviewed change is an RCE / supply-chain risk. When the diff touches any
# of them, fd-safety is a MANDATORY reviewer (see interflux SKILL.md Step 1.2a)
# and must have run THIS pass: its findings file must exist and be fresh. The
# synthesis gate (Phase 3b) still decides pass/fail on the findings; this guard
# only enforces that the mandatory reviewer actually ran. Mirrors the synthesis
# freshness guard above. Override: CLAVAIN_SKIP_SECURITY='reason'.
SHIP_CLASS_RE='(^|/)plugin\.json$|(^|/)mcp-[^/]*\.(json|ya?ml)$|(^|/)mcp-server\.|(^|/)hooks/[^/]*\.(sh|py|ts|js)$|(^|/)hooks\.json$|(^|/)(interlock|authorization|capability)[^/]*\.(json|ya?ml)$|(^|/)\.clavain/keys/|shell-exec'
changed_files=$(grep -E '^\+\+\+ b/' "$DIFF_PATH" 2>/dev/null | sed 's|^+++ b/||')
if printf '%s\n' "$changed_files" | grep -Eq "$SHIP_CLASS_RE"; then
    if [[ -n "${CLAVAIN_SKIP_SECURITY:-}" ]]; then
        echo "quality-gates: [WARNING] ship-class diff detected; fd-safety enforcement bypassed via CLAVAIN_SKIP_SECURITY='${CLAVAIN_SKIP_SECURITY}'. Recording the bypass as interspect evidence." >&2
        # Reuse Phase 3a's interspect verdict loop: drop a SKIPPED verdict that
        # the loop will record. Keeps the bypass auditable without re-sourcing
        # lib-interspect here.
        mkdir -p .clavain/verdicts 2>/dev/null || true
        printf '{"agent":"fd-safety","status":"SKIPPED_SHIP_CLASS","findings_count":0,"model":"none","reason":"%s","ts":"%s"}\n' \
            "${CLAVAIN_SKIP_SECURITY//\"/\'}" "$(date -u +%FT%TZ)" \
            > .clavain/verdicts/fd-safety.json 2>/dev/null || true
    else
        FD_SAFETY_MD="$OUTPUT_DIR/fd-safety.md"
        if [[ ! -f "$FD_SAFETY_MD" ]]; then
            echo "quality-gates: ship-class diff (plugin/MCP/hooks/interlock/keys/shell-out) requires fd-safety review, but fd-safety did not run ($FD_SAFETY_MD missing). fd-safety is MANDATORY for ship-class diffs. Gate FAILS CLOSED. Re-run /clavain:quality-gates, or set CLAVAIN_SKIP_SECURITY='reason' to override." >&2
            exit 1
        fi
        if [[ "$FD_SAFETY_MD" -ot "$DIFF_PATH" ]]; then
            echo "quality-gates: ship-class diff — fd-safety findings are STALE (older than the diff under review). Gate FAILS CLOSED. Re-run /clavain:quality-gates." >&2
            exit 1
        fi
    fi
fi
```

## Phase 3: Gate Decision

### 3a: Record Verdicts to Interspect (silent, fail-open)

```bash
if source "${CLAUDE_PLUGIN_ROOT}/hooks/lib.sh" 2>/dev/null; then
    interspect_root=$(_discover_interspect_plugin 2>/dev/null) || interspect_root=""
    if [[ -n "$interspect_root" ]]; then
        source "${interspect_root}/hooks/lib-interspect.sh"
        SESSION_ID=$(cat /tmp/interstat-session-id 2>/dev/null || echo "unknown")
        for verdict_file in .clavain/verdicts/*.json; do
            [[ -f "$verdict_file" ]] || continue
            agent=$(basename "$verdict_file" .json)
            status=$(jq -r '.status // "UNKNOWN"' "$verdict_file")
            findings=$(jq -r '.findings_count // 0' "$verdict_file")
            model=$(jq -r '.model // "unknown"' "$verdict_file")
            phase=$(jq -r '.phase // env.CLAVAIN_PHASE // env.CLAVAIN_CURRENT_PHASE // "quality-gates"' "$verdict_file")
            _interspect_record_verdict "$SESSION_ID" "$agent" "$status" "$findings" "$model" "$phase" 2>/dev/null || true
        done
    fi
fi
```

### 3b: Enforce Gate + Record Phase

Read `{OUTPUT_DIR}/synthesis.md` and present to user (~30-50 lines).

```bash
BEAD_ID="${CLAVAIN_BEAD_ID:-}"
if [[ -n "$BEAD_ID" ]]; then
    clavain-cli set-artifact "$BEAD_ID" "quality-verdict" "${OUTPUT_DIR}/synthesis.md" 2>/dev/null || true
    if ! clavain-cli enforce-gate "$BEAD_ID" "shipping" ""; then
        echo "Gate blocked: review findings stale or pre-conditions not met. Re-run /clavain:quality-gates, or set CLAVAIN_SKIP_GATE='reason' to override." >&2
    else
        clavain-cli advance-phase "$BEAD_ID" "shipping" "Quality gates passed" ""
    fi
fi
```

Do NOT set phase on FAIL — work needs fixing first.

## Phase 4: File Findings as Beads (optional, Terminal)

This is the **final phase**. After this, quality gates is complete. Do NOT add further phases — resolution and shipping are the sprint orchestrator's domain.

If `.beads/` initialized, ask: "File review findings as beads issues? (recommended for >3 findings)"

If yes: `bd create --title="[quality-gates] <finding>" --type=bug --priority=3` — group related findings where appropriate.

Do NOT display additional unchecked phases or pending steps after this phase.

## Notes

- Run after tests pass. Quality gates complement testing, not replace it.
- P1 findings block shipping — present prominently, ensure resolution.
- Agent selection, dispatch, and synthesis are flux-drive's responsibility — quality-gates does not select agents.
