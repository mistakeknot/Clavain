---
name: grill-me
description: Interview the user relentlessly about a plan or design until every branch of the decision tree is settled
argument-hint: "[plan, design or idea to stress-test; add --docs to record a glossary and decision records as you go]"
disable-model-invocation: true
---

# Grill me

Stress-test a plan before it is written down or built. Interview the user until
you share one understanding of it. Nothing is built, planned or edited from
here; a settled tree goes to `/clavain:strategy` or `/clavain:write-plan`.

Adapted from the grilling, grill-me, grill-with-docs and domain-modeling skills
in mattpocock/skills (MIT License, Copyright (c) 2026 Matt Pocock).

Target: `$ARGUMENTS`. With no argument, grill the plan or design in the
conversation so far.

## The design tree

Map the plan as a tree: every decision branches into the decisions that hang
off it. The **frontier** is every decision whose prerequisites are already
settled, so you can ask it now without guessing at an answer you haven't heard.

Work the tree in rounds:

1. Ask the whole frontier in one round. Number each question, and give your
   recommended answer to each.
2. Wait for the user's answers.
3. Recompute the frontier. Settled decisions push it outward and unblock the
   questions that depended on them. A question whose answer depends on another
   question still open in this round belongs to a later round.

Format a question like this:

```
❓ **Q1** - **<question title>**: <question body, with the options if there are several>

➡️ <your recommended answer>
```

Word each question so "yes" accepts your recommendation.

## Rules

- **Facts are your job, decisions are the user's.** When a question needs a fact
  from the repo, the tools or the environment, look it up yourself (or send a
  subagent) instead of asking. A running lookup holds back only the questions
  downstream of it; ask the rest of the frontier now.
- Challenge terms. When the user uses a word that conflicts with the code or the
  project's existing vocabulary, say so and ask which meaning wins. Invent an
  edge-case scenario when a decision looks settled too easily.
- The session ends when the frontier is empty: every branch visited, nothing
  silently assumed. State the settled tree in a few lines and wait for the user
  to confirm it before anything acts on it.

## `--docs`

With `--docs`, write the model down as it crystallises, creating each file only
when there is something to put in it:

- `GLOSSARY.md` at the repo root: one entry per resolved term, in the project's
  own words.
- `docs/adr/NNNN-<slug>.md`: one short decision record per decision that is
  hard to reverse, surprising without context, or the result of a real
  trade-off.

Do not create either file for terms and decisions that came up but were not
settled.
