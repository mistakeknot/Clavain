---
name: autoresearch
description: "Use when running autonomous experiment campaigns to optimize metrics. Drives init/run/log experiment loop with context recovery."
---

# Autoresearch — Autonomous Experiment Loop

Run a continuous optimization campaign: edit code, benchmark, keep improvements, discard regressions, repeat.

## Setup Phase

1. **Locate campaign YAML.** Call `init_experiment` with campaign name + first hypothesis. Tool loads YAML, creates git worktree, opens (or resumes) a JSONL segment.

2. **Check for resume.** If `init_experiment` returns `resumed: true`, read `autoresearch.md` for context — but treat the tool's response as authoritative state (experiment count, current best, baseline).

3. **Create session documents.** On first run (not resumed): generate `autoresearch.md` and `autoresearch.ideas.md` from `templates/` in this skill directory. Populate with campaign metadata from tool response.

## Experiment Loop

Repeat until `log_experiment` returns `campaign_complete: true`:

### 1. Pick next experiment
Check `next_mutation` from `init_experiment` or `log_experiment` response:

**If `next_mutation` is present** — execute the structured mutation:
- `parameter_sweep` / `enum_sweep`: find the parameter in the specified file, change its value to `params.value`
- `swap`: find `params.target` pattern in `params.files`, replace with `params.replacement`
- `toggle`: find the flag `params.flag` in `params.file`, flip its boolean value
- `scale`: find the parameter `params.param` in `params.file`, multiply by `params.factor`
- `remove`: find and remove the code block described by `params.target` in `params.file`
- `reorder`: find the items and reorder them to match `params.items`

When logging the result, include `mutation_id` and `mutation_type` from the mutation spec.

**If `next_mutation` is null** — fall back to ideas list in `autoresearch.ideas.md`. If no ideas remain, generate hypotheses or end campaign.

### 2. Make code changes
Edit files in the **worktree directory** (returned by `init_experiment`). For mutations, follow the structured spec. For ideas, keep changes small — one variable at a time.

### 3. Run benchmark
Call `run_experiment` with campaign name. Tool executes benchmark, extracts metrics, returns values.

### 4. Evaluate results
- **Improvement** (metric moved right direction) → `keep`
- **Regression** (metric moved wrong way) → `discard`
- **Negligible change** (< 0.1% of baseline) → `discard` with explanation

### 5. Log decision
Call `log_experiment` with campaign name, decision, metric value, secondary values, notes.

Check response for:
- `campaign_complete: true` → stop the loop
- `override_reason` → system overrode your decision (secondary metric regression)
- `effective_decision` → may differ from your `decision` if overridden

### 6. Update living document
- Update "Current Best" and "Experiments" counters in `autoresearch.md`
- Add experiment to "Recent Experiments" table (keep last 10)
- Move idea from "Untried" to "Tried" in `autoresearch.ideas.md`
- Record any new hypotheses discovered

## Context Recovery

When context window > 80%:
1. Write current state to `autoresearch.md`
2. Session ends naturally
3. Next session: call `init_experiment` first (JSONL store is authoritative) → rebuild `autoresearch.md` from tool response if diverged → continue from next untried idea

**Never treat `autoresearch.md` as recovery source.** JSONL store is ground truth.

## Campaign Completion

Ends when: all ideas exhausted and no new ones generated, `campaign_complete: true` returned, or user interrupts.

On completion:
1. Update `autoresearch.md` with final summary
2. Report: total experiments, kept count, cumulative improvement
3. If improvements were kept, remind user to merge the experiment branch

## Safety Notes

- `run_experiment` prompts user for approval before first benchmark (RequirePrompt gate) — expected behavior
- `log_experiment` may override `keep` → `discard` if secondary metrics regress — check `override_reason`
- All changes in git worktree — main branch never touched
- Secret files (.env, .pem, .key) auto-rejected by `KeepChanges`
