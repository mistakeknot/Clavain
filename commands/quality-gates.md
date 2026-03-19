---
name: quality-gates
description: Auto-select and run the right reviewer agents based on what changed — one command for comprehensive quality review
argument-hint: "[optional: specific files or 'all' for full diff]"
---

# Quality Gates

Analyzes changes, invokes appropriate specialist agents, synthesizes findings.

## Input

<review_target> #$ARGUMENTS </review_target>

No arguments → analyze current unstaged + staged changes (`git diff` + `git diff --cached`).

**Small change shortcut:** If diff is under 20 lines and touches one file, only run `interflux:review:fd-quality`. Skip phases 2-5b.

## Phase 1: Analyze Changes

```bash
git diff --name-only HEAD
git diff --cached --name-only
```

Classify each file by language (.go, .py, .ts/.tsx, .sh, .rs) and risk domain:
- auth/crypto/secrets → Safety
- migration/schema → Correctness
- hot-path/cache/query → Performance
- goroutine/async/channel → Correctness

## Phase 2: Select Reviewers

**Always run:**
- `interflux:review:fd-architecture` — structural review
- `interflux:review:fd-quality` — naming, conventions, idioms

**Risk-based:**
- Auth/crypto/input/secrets → `interflux:review:fd-safety`
- DB/migration/schema/backfill → `interflux:review:fd-correctness` + `data-migration-expert`
- Performance-critical paths → `interflux:review:fd-performance`
- Concurrent/async code → `interflux:review:fd-correctness`
- User-facing flows → `interflux:review:fd-user-product`

Max 5 agents total. Prioritize by risk.

## Phase 3: Prepare Diff and Output Dir

```bash
TS=$(date +%s)
git diff HEAD > /tmp/qg-diff-${TS}.txt
git diff --cached >> /tmp/qg-diff-${TS}.txt
OUTPUT_DIR="${PROJECT_ROOT}/.clavain/quality-gates"
mkdir -p "$OUTPUT_DIR"
rm -f "$OUTPUT_DIR"/*.md "$OUTPUT_DIR"/*.md.partial 2>/dev/null
```

## Phase 4: Run Agents in Parallel

Launch selected agents with `Task(run_in_background: true)`.

Each agent prompt MUST include:
1. Diff file path — agents read `/tmp/qg-diff-{TS}.txt` as first action
2. Changed file list with reason for selection
3. Relevant config files if touched (go.mod, tsconfig.json, Cargo.toml)

**Output contract** (include verbatim in every agent prompt):
```
## Output Contract

Write ALL findings to `{OUTPUT_DIR}/{agent-name}.md`.
Do NOT return findings in response text.
Response text: single line "Findings written to {OUTPUT_DIR}/{agent-name}.md"

File structure:
### Findings Index
- SEVERITY | ID | "Section" | Title
Verdict: safe|needs-changes|risky

### Summary
[3-5 lines]

### Issues Found
[ID. SEVERITY: Title — 1-2 sentences with evidence. file:line or hunk headers.]

### Improvements
[ID. Title — 1 sentence with rationale]

Zero findings: empty index + verdict: safe.
```

Polling: check `{OUTPUT_DIR}/` every 30s for `.md` files (not `.md.partial`). Report `[2/4 agents complete]`. After 5 min, report pending agents.

## Phase 5: Synthesize via Subagent

Do NOT read agent output files directly — delegate to avoid agent prose in host context.

```
Task(intersynth:synthesize-review):
  prompt: |
    OUTPUT_DIR={OUTPUT_DIR}
    VERDICT_LIB={CLAUDE_PLUGIN_ROOT}/hooks/lib-verdict.sh
    MODE=quality-gates
    CONTEXT="{X files changed across Y languages. Risk domains: [list]}"
```

After subagent returns: read `{OUTPUT_DIR}/synthesis.md` and present to user (~30-50 lines). Gate result (PASS/FAIL) comes from subagent return value.

## Phase 5a: Record Verdicts to Interspect (silent, fail-open)

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
            _interspect_record_verdict "$SESSION_ID" "$agent" "$status" "$findings" "$model" 2>/dev/null || true
        done
    fi
fi
```

## Phase 5b: Gate Check + Record Phase (PASS only)

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

## Phase 6: File Findings as Beads (optional)

If `.beads/` initialized, ask: "File review findings as beads issues? (recommended for >3 findings)"

If yes: `bd create --title="[quality-gates] <finding>" --type=bug --priority=3` — group related findings where appropriate.

## Notes

- Run after tests pass. Quality gates complement testing, not replace it.
- P1 findings block shipping — present prominently, ensure resolution.
