---
name: show-me-your-work
description: Keep a reviewable decision trail for long-running or unattended work, one TSV row per decision
argument-hint: "[log path; defaults to decisions.tsv in the work dir]"
disable-model-invocation: true
---

# Show me your work

Keep one decision log for work a human reviews after stepping away: autonomous
runs, multi-phase efforts, anything long enough that the reviewer can't watch it.

Adapted from the show-me-your-work skill in pstack (MIT License, Copyright (c)
2026 Lauren Tan, mirrored at backnotprop/pstack).

Log: `$ARGUMENTS`, else `decisions.tsv` in the work dir.

## The format

A single TSV file, one row per decision. Cells stay single-line, and evidence is
a pointer, not prose. Columns:

- **ts.** ISO 8601 UTC timestamp.
- **phase.** The phase or workstream.
- **decision.** What was chosen or done, one line.
- **why.** The reason in plain words.
- **evidence.** A path or id that proves it: commit SHA, PR number, `file:line`,
  or an artifact, trace or screenshot path. Never a paragraph.
- **result.** The outcome or state: `tests green`, `reverted`, `INCONCLUSIVE`,
  `open`.

```
ts	phase	decision	why	evidence	result
2026-05-24T09:40:00Z	harness	took screenshots of the old version before changing anything	so old and new can be compared	scripts/snapshot.sh, baseline/	saved 120 reference screenshots
2026-05-24T12:30:00Z	widget	threw out a helper's work because its screenshots were blank	checked the real files instead of trusting its summary	worktree reset	reverted, tightened the instructions
```

## Logging a row

Write each row the way you'd tell a teammate what you did: plain words, concrete
actions. Use `scripts/decision-log.sh <logfile> <phase> <decision> <why>
<evidence> <result>`. It stamps `ts`, writes the header on first use, turns tabs
and newlines in a cell into spaces, and prefixes any cell that starts with `=`,
`+`, `-` or `@` with a single quote so a spreadsheet never reads it as a formula.

Log decision points and checkpoints, not every action: a fork chosen, a unit
completed with its verification result, a pivot or revert with its trigger, a
blocker surfaced, a gate fixed. In a loop, one row per iteration. Skip the
trivial and the self-evident.

A run is one agent conversation. A pickup, a replacement agent or a new chat is
a new run. A run that adds to a log with rows already in it starts with a row
whose phase is `start`, naming the `ts` range of the rows it did not write.

## Where it lives

By default the log is a working artifact and stays out of git. Keep it at
`decisions.tsv` in the work dir, or `.audit/<task-slug>.tsv` when several
efforts run at once. Commit it only when the work is consequential enough that a
reviewer needs the trail to trust the result.

## Rules

- Append-only. A wrong call gets a new row that supersedes it. Never edit or
  delete history.
- Prefer evidence produced by committed scripts over hand-made one-offs.
- Never put a secret, token or private path in a row, least of all when the log
  will be committed.

## Audit before handing back

Check the log told the truth. Read this run's transcript and confirm that every
row maps to a real decision or action, that each row's evidence resolves and
shows what the row claims, and that no fork, pivot or abandoned approach that
shaped the work is missing. Correct the log, not the story: when a row is wrong,
add a row that supersedes it with what actually happened and a pointer that
resolves.

## Independent review of the trail

Before handing back, have a reviewer outside the model that did the work read the
trail and the transcript, through `/clavain:interserve` or packaged
`scripts/dispatch.sh --role cross-lab-review`. It is a scan for what is
suboptimal or risky, not a redo:

- Decisions logged with weak or absent evidence.
- Verification skipped, or claimed without proof in the transcript.
- Choices that look risky in hindsight: premature, scope-creeping, papering over
  a symptom.
- Gaps a casual skim would miss.

If no cross-lab seat is available, say so and name the same-lab reviewer you used
instead; do not present a self-review as independent.

End every reply for a run that produced a trail with an **Attention** section.
Lead with the reviewer's model on its own line (`reviewed by <model>`), then
list each flag with the row or moment it points to. "No flags" is a valid
value; the model name is not optional.

## Reviewing the trail

Read top to bottom, follow the evidence pointers, spot-check.
`column -s$'\t' -t decisions.tsv` renders it in a terminal, and GitHub renders a
committed TSV as a table.
