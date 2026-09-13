# Conditional execution protocols

Use only the selected, authorized host mode. The SKILL.md entry point owns the
completion, verification and authority rules.

## Step 2A: Codex Dispatch (interserve mode)

Dispatch tasks to Codex agents for parallelization.

1. **Classify tasks:** Independent (parallel → Codex) | Sequential (ordered dispatch) | Exploratory (Claude subagent)
2. **Batch:** Independent tasks in same batch run in parallel; max 5 agents/batch
3. **Per batch** via `clavain:interserve`:
   - Write prompt files to `/tmp/codex-task-<name>.md` (goal, files, build/test commands, verdict suffix)
   - Dispatch independent tasks in parallel Bash calls; wait for completion
   - Read `.verdict` file first (7 lines) — STATUS `pass` → trust and move on; `warn`/`fail` → read full output
   - No `.verdict` → fall back to full output
4. **Between batches:** Report pass/fail/issues; continue within existing authorization
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
4. Check whether this execution mode is already authorized. Ask only for missing authority.
5. **Execute:** `python3 "$ORCHESTRATE" "$MANIFEST" --plan "$PLAN_PATH" --project-dir "$(pwd)"` with `timeout: 600000`
   - **Review pipeline is ON by default** (goal 7d610151): per task, the orchestrator runs the plan's `<verify>` blocks as machine gates, then dispatches an INDEPENDENT reviewer on the task-scoped git diff (never the executor's self-report), then loops fix→re-review up to 2 rounds. Governed review resolves the validation role and executor identity; legacy tier-only runs remain ungoverned. Preserve independent review; adjust rounds with `ORC_MAX_FIX_ROUNDS`; the sealed `<plan>.criteria.md` sidecar is handed to reviewers automatically when present. Do not disable required independent review.
6. **Read summary:** `pass` → reviewed and approved (with review on); `warn` → read output, assess; `fail`/`error` → offer retry/manual/skip; `skipped` → report dep failure
   - **`escalated`** → review/verify still failing after the fix-round budget (two strikes). Read the task's `review-*.md` + `verify-*.txt` artifacts, rule on the findings yourself (controller judgment — this is the doctrine's escalation seat), then re-run or fix via 2B.
   - **`question`** → the executor asked instead of guessing (`VERDICT: QUESTION …` — the question is in the summary line). Answer it, fold the answer into the plan or task prompt, re-run.
7. **On partial failure or a killed run:** re-run with `--resume <run_id>` (the run id is the directory name under `.clavain/orchestrate-runs/` — its `journal.jsonl` records which tasks finished; complete tasks are skipped with dependency edges satisfied, everything else re-dispatches into the same run dir) | execute failed tasks via 2B | skip. A killed run's stranded push guard is swept automatically on the next invocation.

