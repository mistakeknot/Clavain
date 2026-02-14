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
- `fd-architecture` — structural review for every change
- `fd-quality` — naming, conventions, language-specific idioms (auto-detects language)

**Risk-based (based on file paths and content):**
- Auth/crypto/input handling/secrets → `fd-safety`
- Database/migration/schema/backfill → `fd-correctness` + `data-migration-expert`
- Performance-critical paths → `fd-performance`
- Concurrent/async code → `fd-correctness`
- User-facing flows → `fd-user-product`

**Threshold:** Don't run more than 5 agents total. Prioritize by risk.

### Phase 3: Gather Context for Agents

Before launching agents, gather the diff context they will review:

```bash
# Unified diff (staged + unstaged)
git diff HEAD > /tmp/qg-diff.txt
git diff --cached >> /tmp/qg-diff.txt

# Changed file list with reasons for agent selection
git diff --name-only HEAD
git diff --cached --name-only
```

### Phase 4: Run Agents in Parallel

Launch selected agents using the Task tool with `run_in_background: true`. Each agent prompt MUST include:

1. **The unified diff** — paste the content of `/tmp/qg-diff.txt` (or inline the diff if small)
2. **Changed file list** — with why each file was selected for this agent
3. **Relevant config files** — if any were touched (e.g., go.mod, tsconfig.json, Cargo.toml)

Ask agents to **reference diff hunks** in findings (file:line or hunk header like `@@ -10,5 +10,7 @@`).

```
Task(fd-architecture): "Review this diff for structural issues. [paste diff]. Reference specific hunks."
Task(fd-quality): "Review this diff for naming, conventions, and idioms. [paste diff]. Reference file:line."
Task(fd-safety): "Scan this diff for security vulnerabilities. [paste diff]. Reference specific hunks."
```

### Phase 5: Synthesize Results

Collect all agent findings and present:

```markdown
## Quality Gates Report

### Changes Analyzed
- X files changed across Y languages
- Risk domains detected: [safety, correctness, performance, etc.]

### Agents Invoked
1. fd-architecture — [pass/findings]
2. fd-quality — [pass/findings]
3. fd-safety — [pass/findings]

### Findings Summary
- P1 CRITICAL: [count] — must fix
- P2 IMPORTANT: [count] — should fix
- P3 NICE-TO-HAVE: [count] — optional

### Gate Result: [PASS / FAIL]

[If FAIL: list P1 items that must be addressed]
```

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

- **Don't over-review small changes.** If the diff is under 20 lines and touches one file, only run `fd-quality`.
- **Run after tests pass.** Quality gates complement testing, not replace it.
- **P1 findings block shipping.** Present them prominently and ensure resolution.
