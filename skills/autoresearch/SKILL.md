---
name: autoresearch
description: "Use when running autonomous experiment campaigns to optimize metrics. Drives init/run/log experiment loop with context recovery."
---

# Autoresearch — Autonomous Experiment Loop

Run a continuous optimization campaign: edit code, benchmark, keep improvements, discard regressions, repeat.

## Setup Phase

1. **Locate campaign YAML.** The user provides a campaign name. Call `init_experiment` with the campaign name and a hypothesis for the first experiment. The tool loads the YAML, creates a git worktree, and opens (or resumes) a JSONL segment.

2. **Check for resume.** If `init_experiment` returns `resumed: true`, the campaign is continuing from a previous session. Read the `autoresearch.md` living document for context, but treat the tool's response as the authoritative state (experiment count, current best, baseline).

3. **Create session documents.** On first run (not resumed), generate `autoresearch.md` and `autoresearch.ideas.md` from the templates in this skill's `templates/` directory. Populate with campaign metadata from the tool response.

## Experiment Loop

Repeat until `campaign_complete: true` is returned by `log_experiment`:

### 1. Pick an idea
Read the next untried idea from `autoresearch.ideas.md`. If no ideas remain, analyze the code in the worktree to generate new hypotheses. If you cannot generate any, the campaign is done — call `log_experiment` with a final summary.

### 2. Make code changes
Edit files in the **worktree directory** (returned by `init_experiment`) to implement the hypothesis. Keep changes small and focused — one variable at a time.

### 3. Run benchmark
Call `run_experiment` with the campaign name. The tool executes the benchmark command from the YAML, extracts metrics, and returns values.

### 4. Evaluate results
Compare the returned metric value against the current best:
- **Improvement** (metric moved in the right direction): decide `keep`
- **Regression** (metric moved wrong way): decide `discard`
- **Negligible change** (< 0.1% of baseline): decide `discard` with notes explaining why

### 5. Log decision
Call `log_experiment` with the campaign name, decision, metric value, secondary values, and notes.

**Important:** Check the response for:
- `campaign_complete: true` → stop the loop
- `override_reason` → the system overrode your decision due to secondary metric regression
- `effective_decision` → may differ from your `decision` if overridden

### 6. Update living document
After each experiment, update `autoresearch.md`:
- Update the "Current Best" and "Experiments" counters
- Add the experiment to the "Recent Experiments" table (keep last 10)
- Move the idea from "Untried" to "Tried" in `autoresearch.ideas.md`
- Record any new ideas discovered during the experiment

## Context Recovery

When approaching context limits (context window > 80%):

1. Write the current state to `autoresearch.md` (it's a write-through cache)
2. The session will end naturally
3. On the next session, `/autoresearch` resumes:
   - Call `init_experiment` first — it reads the JSONL store (authoritative source)
   - Rebuild `autoresearch.md` from the tool's response if it diverges
   - Continue the loop from the next untried idea

**Never treat `autoresearch.md` as the recovery source.** The JSONL store is ground truth. The living document is a convenience cache for agent context.

## Campaign Completion

A campaign ends when any of:
- All ideas exhausted and no new ones generated
- `log_experiment` returns `campaign_complete: true` (budget or failure cap reached)
- User interrupts

On completion:
1. Update `autoresearch.md` with final summary
2. Report: total experiments, kept count, cumulative improvement
3. If improvements were kept, remind the user to merge the experiment branch

## Safety Notes

- `run_experiment` will prompt the user for approval before the first benchmark execution (RequirePrompt gate). This is expected — the benchmark command comes from YAML.
- `log_experiment` may override your `keep` decision to `discard` if secondary metrics regress beyond thresholds. Check `override_reason` in the response.
- All changes happen in a git worktree — the main branch is never touched.
- Secret files (.env, .pem, .key) are automatically rejected by `KeepChanges`.
