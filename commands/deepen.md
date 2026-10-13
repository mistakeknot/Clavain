---
name: deepen
description: "Rewrite an ask as a deeper version, not a bigger one: name the top practitioner's method, the rawest source, the real instruments and the external evidence that would prove the result"
argument-hint: "[the draft prompt, goal or charter to deepen]"
---

# Deepen

<deepen_args> #$ARGUMENTS </deepen_args>

If the arguments are empty, ask once for the draft ask and stop until it is given.

A **bigger** ask adds scope. A **deeper** ask keeps the scope and raises the
quality of the work: who does this best, from what material, with what
instruments, judged by what. Run in the current turn. Dispatch nothing and add
no review pass; this command is cheap by design.

## Step 1 — Read the draft

Restate the draft ask in one sentence. Say what outcome it wants, not the task it
names. If the draft cites a goal, charter or bead, read it first (never ask what
you can derive).

## Step 2 — Write four fields

Keep each to one or two lines, concrete and checkable. If a field has no honest
answer, write `unknown: <what would settle it>` rather than inventing one.

1. **Practitioner method.** Who is best at this, and what do they do that a
   first draft would not? Name the method, not a role ("a forensic accountant
   re-adds the ledger from source rows", not "act as an accountant").
2. **Rawest source.** The primary material closest to the facts: logs, rows,
   transcripts, the code itself, not a summary someone wrote about them.
3. **Instruments.** The real tools of that field (a database query, a statistical
   test, a profiler, a replay), not a markdown table of impressions.
4. **External evidence.** What a judge other than the producer could check, and
   whether that check can actually run here. Prefer a command or a held-out case
   to a reviewer's opinion.

## Step 3 — Stretch bar and rewrite

Propose **one** stretch bar: a specific number or comparison, ambitious but
believably solvable. Then write the **rewritten ask**: the original intent,
rebuilt around the four fields and the bar. It must be shorter than a plan and
state the outcome, not the mechanism.

## Output

Print, in order: the one-sentence restatement, the four fields, the stretch bar,
and the rewritten ask under the heading `Deeper ask`. Then stop. The user decides
whether to use it; do not start the work.

## Use

Optional. `/clavain:goal-form` offers it at C3 and above; `/clavain:brainstorm`
offers it at the start of Phase 2. Neither calls it automatically.
