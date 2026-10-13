---
name: deepen
description: "Rewrite a draft ask as a deeper version of the same task, not a bigger one: practitioner method, rawest source, instruments, external evidence, one stretch bar"
argument-hint: "[draft prompt, goal, or charter path — defaults to the draft in context]"
---

# Deepen

<deepen_args> #$ARGUMENTS </deepen_args>

"I want a deeper version of this task, not a bigger one." A draft ask usually
says what to produce. It rarely says how the best person in the field would
produce it, from what material, with what tools, or who outside the producer
would confirm it worked. This command asks those questions once and returns a
rewritten ask. Source: bead mk-3mo0w.

## Input

The draft is the argument: inline text, or a path to a charter or brainstorm.
With no argument, use the draft currently in the conversation (the approach
being chosen in brainstorm Phase 2, or the charter in goal-form Step 4).

## The five fields

Answer each in one or two lines, from what you can verify here. Write
`unknown` rather than inventing an answer.

1. **Practitioner method.** Who does this work best, and what do they *do*?
   Name the method, not a persona: a forensic accountant re-adds the figures;
   a performance engineer profiles before reading code.
2. **Rawest source.** The primary material closest to the thing itself: logs,
   raw exports, the corpus, the database. Not a summary, dashboard or doc
   about it.
3. **Instruments.** The real tools of the field that are available in this
   environment: a query engine, a profiler, a statistical test, a replay
   harness, a reproduction host. Mark any that are missing as missing.
4. **External evidence.** What outside the producer would confirm or refute
   the result: a command's verdict, a test run, a consumer using it, an
   independent review. Something the producer writes is not external.
5. **Stretch bar.** One specific, measurable bar that is harder than the draft
   implies, with a sentence on why it is still reachable.

## Rewrite

Then print the rewritten ask. It keeps the draft's scope, deliverables and
audience, and changes how the work is done and judged:

```
DEEPENED ASK
<the rewritten prompt, goal or charter section>

CHANGED
- <each change from the draft, one line each>
```

## Rules

- **Deeper, not bigger.** A field that would add a deliverable, a consumer or
  a new area of scope is out. Drop it and note it under CHANGED as "not
  adopted: widens scope".
- **One pass, in this turn.** Do not dispatch agents or start a review for
  this. It costs one reasoning pass.
- **The caller decides.** Return the rewrite; do not execute it. In
  brainstorm and goal-form the user chooses between the draft and the
  rewrite.
- **Feed the premise.** When the rawest source can falsify the belief the
  draft rests on, say so. goal-form uses it as the charter's `PREMISE` test.
- **Goal shape still applies.** A rewritten goal follows
  `docs/guide-goal-shape.md`: outcome, not mechanism.
