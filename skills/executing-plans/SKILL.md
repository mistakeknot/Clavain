---
name: executing-plans
description: Use when you have a written implementation plan to execute in a separate session with review checkpoints
---

<!-- compact: SKILL-compact.md — if it exists in this directory, load it instead of following the full instructions below. The compact version contains the same batch execution and interserve dispatch protocol. -->

# Executing Plans

Load plan, review critically, execute tasks in batches, report for review between batches. Batch execution with checkpoints for architect review.

**Announce at start:** "I'm using the executing-plans skill to implement this plan."

## Step 1: Load and Review Plan

1. Read plan file
2. Review critically — raise questions/concerns with human partner before starting
3. If no concerns: create TodoWrite and proceed

## Step 2: Check Execution Mode

Check for `.exec.yaml` manifest (replace plan's `.md` extension). If found → Step 2C (priority).

Check interserve flag: `[ -f "$(pwd)/.claude/clodex-toggle.flag" ] && echo INTERSERVE_ACTIVE || echo DIRECT_MODE`

Fallback chain:
- Manifest exists → **2C: Orchestrated**
- Flag exists, no manifest → **2A: Codex Dispatch**
- Neither → **2B: Direct**

## Step 2A: Codex Dispatch (interserve mode)

Dispatch tasks to Codex agents for parallelization.

1. **Classify tasks:** Independent (parallel → Codex) | Sequential (ordered dispatch) | Exploratory (Claude subagent)
2. **Batch:** Independent tasks in same batch run in parallel; max 5 agents/batch
3. **Per batch** via `clavain:interserve`:
   - Write prompt files to `/tmp/codex-task-<name>.md` (goal, files, build/test commands, verdict suffix)
   - Dispatch independent tasks in parallel Bash calls; wait for completion
   - Read `.verdict` file first (7 lines) — STATUS `pass` → trust and move on; `warn`/`fail` → read full output
   - No `.verdict` → fall back to full output
4. **Between batches:** Report pass/fail/issues; wait for feedback
5. **On failure:** Offer retry with tighter prompt, fall back to 2B, or skip

## Step 2B: Direct Execution (default)

Default: first 3 tasks per batch. Per task: mark in_progress → follow steps exactly → run verifications → mark completed.

## Step 2C: Orchestrated Execution (manifest exists)

1. **Locate orchestrator:**
   ```bash
   ORCHESTRATE=$(find ~/.claude/plugins/cache -path '*/clavain/*/scripts/orchestrate.py' 2>/dev/null | head -1)
   [ -z "$ORCHESTRATE" ] && ORCHESTRATE=$(find ~/projects -name orchestrate.py -path '*/clavain/scripts/*' 2>/dev/null | head -1)
   ```
2. **Validate:** `python3 "$ORCHESTRATE" --validate "$MANIFEST"` — on failure, report errors, fall back to 2A/2B
3. **Dry-run:** `python3 "$ORCHESTRATE" --dry-run "$MANIFEST"` — present wave breakdown (parallelism, cross-stage deps, tasks missing files)
4. **Ask for approval** (AskUserQuestion): Approve | Edit mode | Skip to manual
5. **Execute:** `python3 "$ORCHESTRATE" "$MANIFEST" --plan "$PLAN_PATH" --project-dir "$(pwd)"` with `timeout: 600000`
6. **Read summary:** `pass` → trust; `warn` → read output, assess; `fail`/`error` → offer retry/manual/skip; `skipped` → report dep failure
7. **On partial failure:** Offer re-run orchestrator (skips finished tasks) | execute failed tasks via 2B | skip

## Step 2D: Post-Task Verification

After each task (any mode): parse `<verify>...</verify>` block for `run:`/`expect:` pairs.
- `expect: exit 0` — must exit 0; `expect: contains "string"` — output must include string
- Pass → log "Verify passed for Task N"; failure → treat as Rule 1 auto-fix (3-attempt limit, then log and continue)
- No verify block → skip silently

**Vetting signal write** — when all per-task verifications pass for a plan that is part of a tracked bead, persist vetting state so the auto-proceed authz gate can evaluate at ship time (see `docs/canon/policy-merge.md`):
```bash
if [[ -n "${CLAVAIN_BEAD_ID:-}" ]]; then
  bd set-state "$CLAVAIN_BEAD_ID" vetted_at="$(date +%s)"            --reason "executing-plans task verified" 2>/dev/null || true
  bd set-state "$CLAVAIN_BEAD_ID" vetted_sha="$(git rev-parse HEAD)" --reason "executing-plans task verified" 2>/dev/null || true
  bd set-state "$CLAVAIN_BEAD_ID" tests_passed="true"                --reason "executing-plans task verified" 2>/dev/null || true
  bd set-state "$CLAVAIN_BEAD_ID" sprint_or_work_flow="true"         --reason "executing-plans task verified" 2>/dev/null || true
fi
```

## Step 3: Report

Per batch: what was implemented | verify results (pass/fail) | deviations (Rules 1-3) | deferred items | "Ready for feedback."

## Step 4: Continue

Apply feedback → next batch → repeat until complete.

## Step 4B: Must-Have Validation

After all tasks, check for `## Must-Haves` in plan header:
- **Truths:** verify observable (run commands/URLs, check code paths)
- **Artifacts:** verify file exists with listed exports (grep/read)
- **Key Links:** verify connection in source (grep import + function call)

Report results:
```
Must-Have Validation:
  Truths: 3/3 verified
  Artifacts: 2/2 exist with exports
  Key Links: 1/2 — Registration endpoint missing validate_email call
```

Failures are advisory — user decides. No `Must-Haves` section → skip silently.

## Step 5: Complete Development

Announce: "I'm using the landing-a-change skill to complete this work." → **clavain:landing-a-change** (required).

## Deviation Rules

Track all deviations for batch report.

- **Rule 1 — Auto-fix bugs:** Wrong queries, type errors, logic errors → fix inline, verify, continue. No permission.
- **Rule 2 — Auto-add critical functionality:** Missing error handling, no input validation, no auth on protected routes, missing DB indexes → add, verify, continue. No permission.
- **Rule 3 — Auto-fix blockers:** Missing dependency, broken imports, build config errors → fix, verify, continue. No permission.
- **Rule 4 — Ask about architectural changes:** New DB table, switching libraries, breaking API changes, new service layer → STOP, report finding + proposed change + alternatives. User decision required.

**Priority:** Rule 4 → STOP | Rules 1-3 → fix automatically | Unsure → treat as Rule 4.

**Scope:** Only auto-fix issues caused by the current task's changes. Pre-existing warnings/failures in unrelated files → log to `deferred-items.md`, do NOT fix.

**Fix attempt limit:** 3 attempts per task. After 3, document in "Deferred Issues" and continue.

**Analysis paralysis guard:** 5+ consecutive Read/Grep/Glob without Edit/Write/Bash → STOP. State why in one sentence, then write code or report "blocked" with specific missing info.

## Stop Conditions

Stop immediately and ask when: mid-batch blocker | critical plan gaps | unclear instruction | repeated verification failure. Never start on main/master without explicit user consent.

## Integration

- **clavain:writing-plans** — creates the plan this skill executes
- **clavain:landing-a-change** — required after all tasks complete
- **clavain:interserve** — Codex dispatch (interserve mode)
