---
name: quality-gates
description: Auto-select and run the right reviewer agents based on what changed — one command for comprehensive quality review
argument-hint: "[optional: specific files or 'all' for full diff]"
---

# Quality Gates

Run the right set of reviewer agents automatically based on change risk. This command analyzes what changed and invokes the appropriate specialists.

## Input

<review_target> #$ARGUMENTS </review_target>

If no arguments provided, analyze the current unstaged + staged changes (`git diff` + `git diff --cached`).

## Execution Flow

### Phase 1: Analyze Changes

```bash
# Get changed files
git diff --name-only HEAD
git diff --cached --name-only
```

Classify each changed file by:
- **Language**: .go → Go, .py → Python, .ts/.tsx → TypeScript, .sh → Shell, .rs → Rust
- **Risk domain**: auth/crypto/secrets → Safety, migration/schema → Correctness, hot-path/cache/query → Performance, goroutine/async/channel → Correctness

### Phase 2: Select Reviewers

Based on analysis, invoke the appropriate agents in parallel:

**Always run:**
- `interflux:review:fd-architecture` — structural review for every change
- `interflux:review:fd-quality` — naming, conventions, language-specific idioms (auto-detects language)

**Risk-based (based on file paths and content):**
- Auth/crypto/input handling/secrets → `interflux:review:fd-safety`
- Database/migration/schema/backfill → `interflux:review:fd-correctness` + `data-migration-expert`
- Performance-critical paths → `interflux:review:fd-performance`
- Concurrent/async code → `interflux:review:fd-correctness`
- User-facing flows → `interflux:review:fd-user-product`

**Threshold:** Don't run more than 5 agents total. Prioritize by risk.

### Phase 3: Gather Context and Prepare Output Directory

Before launching agents, prepare the diff and output infrastructure:

```bash
# Unified diff (staged + unstaged)
TS=$(date +%s)
git diff HEAD > /tmp/qg-diff-${TS}.txt
git diff --cached >> /tmp/qg-diff-${TS}.txt

# Output directory for agent findings (cleaned each run, gitignored)
OUTPUT_DIR="${PROJECT_ROOT}/.clavain/quality-gates"
mkdir -p "$OUTPUT_DIR"
rm -f "$OUTPUT_DIR"/*.md "$OUTPUT_DIR"/*.md.partial 2>/dev/null

# Changed file list with reasons for agent selection
git diff --name-only HEAD
git diff --cached --name-only
```

### Phase 4: Run Agents in Parallel

Launch selected agents using the Task tool with `run_in_background: true`.

**Critical: File-based output contract.** Each agent prompt MUST include this output section:

```
## Output Contract

Write ALL findings to `{OUTPUT_DIR}/{agent-name}.md`.
Do NOT return findings in your response text.
Your response text should be a single line: "Findings written to {OUTPUT_DIR}/{agent-name}.md"

File structure:

### Findings Index
- SEVERITY | ID | "Section" | Title
Verdict: safe|needs-changes|risky

### Summary
[3-5 lines]

### Issues Found
[ID. SEVERITY: Title — 1-2 sentences with evidence. Reference file:line or hunk headers.]

### Improvements
[ID. Title — 1 sentence with rationale]

Zero findings: empty index + verdict: safe.
```

Each agent prompt MUST also include:

1. **The diff file path** — tell agents to Read `/tmp/qg-diff-{TS}.txt` as their first action
2. **Changed file list** — with why each file was selected for this agent
3. **Relevant config files** — if any were touched (e.g., go.mod, tsconfig.json, Cargo.toml)

**Polling for completion** (after dispatch):
1. Check `{OUTPUT_DIR}/` every 30 seconds for `.md` files (not `.md.partial`)
2. Report progress: `[2/4 agents complete]`
3. After 5 minutes, report any agents still pending
4. If an agent has no `.md` file after timeout, check its background task output for errors

### Phase 5: Synthesize Results via Subagent

**Do NOT read agent output files yourself.** Delegate synthesis to a subagent so agent prose never enters the host context.

Launch the **intersynth synthesis agent** (foreground, not background — you need its result):

```
Task(intersynth:synthesize-review):
  prompt: |
    OUTPUT_DIR={OUTPUT_DIR}
    VERDICT_LIB={CLAUDE_PLUGIN_ROOT}/hooks/lib-verdict.sh
    MODE=quality-gates
    CONTEXT="{X files changed across Y languages. Risk domains: [list]}"
```

The intersynth agent reads all agent output files, validates structure, deduplicates findings, writes verdict JSON files, and returns a compact summary. See the agent's built-in instructions for the full protocol.

After the synthesis subagent returns:
1. Read `{OUTPUT_DIR}/synthesis.md` and present it to the user (this is the compact report, ~30-50 lines)
2. The gate result (PASS/FAIL) comes from the subagent's return value — no additional file reading needed

### Phase 5b: Gate Check + Record Phase (on PASS only)

If the gate result is **PASS**, enforce the shipping gate and record the phase transition:
```bash
export GATES_PROJECT_DIR="."; source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-gates.sh"
BEAD_ID="${CLAVAIN_BEAD_ID:-}"
if [[ -n "$BEAD_ID" ]]; then
    if ! enforce_gate "$BEAD_ID" "shipping" ""; then
        echo "Gate blocked: review findings are stale or pre-conditions not met. Re-run /clavain:quality-gates, or set CLAVAIN_SKIP_GATE='reason' to override." >&2
        # Do NOT advance phase — stop and tell user
    else
        advance_phase "$BEAD_ID" "shipping" "Quality gates passed" ""
    fi
fi
```
Do NOT set the phase if the gate result is FAIL — the work needs fixing first.

### Phase 6: File Findings as Beads (optional)

If the project has `.beads/` initialized, ask the user:
> "File review findings as beads issues for tracking? (recommended for >3 findings)"

If yes, for each significant finding:
```bash
bd create --title="[quality-gates] <brief finding>" --type=bug --priority=3
```

Group related findings into a single bead where appropriate. This makes review output actionable across sessions — per Yegge's recommendation that code reviews should produce trackable issues.

## Important

- **Don't over-review small changes.** If the diff is under 20 lines and touches one file, only run `interflux:review:fd-quality`.
- **Run after tests pass.** Quality gates complement testing, not replace it.
- **P1 findings block shipping.** Present them prominently and ensure resolution.
