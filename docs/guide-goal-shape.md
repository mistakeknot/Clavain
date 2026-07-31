# Goal shape

The canonical form for `/goal` text. One place, because the alternative is
re-improvising it per draft — which is how it drifted.

`/clavain:goal-form` Step 4 and `/clavain:next-goal`'s paste block both point
here. `ic goal lint-condition` enforces the mechanical half.

## Why this file exists

On 2026-07-29 a user read back five consecutive `/goal` blocks and said they
"sound kind of weird". Every one had been drafted by the agent and pasted
verbatim. The machinery was not missing — `goal-form` is a well-formed ritual,
and `next-goal` already required the emitted text to be lint-clean. The lint
just had nothing to say about shape.

The worst of the five contained `and I am ruling it`,
`AnimalCommand::Rotate { animal, site } at discriminant 1`, `wards.rs:568`,
and `I am answering its canon question`. It linted to two findings, both about
predicates. Add a predicate and it returned `null`, exit 0.

## The form

```
/goal <Project> — <outcome in one clause>

OUTCOME: what is true when this is done, and what is true now that
makes it worth doing. Two or three sentences. Numbers if you have
them.

GATE n — <what kind>: a question, left open, with who decides it.
"Bring me options" / "recommend one" is the instruction; the answer
is not in the goal.

DONE WHEN: predicates an evaluator can judge from surfaced output —
a command, an exit code, a bead close, an artifact state. Bound it:
"or stop after N turns".

OUT: what is explicitly not in scope, with the ruling it follows from.
```

## Four rules

**1. State the outcome, not the mechanism.** The frontier tier writes goals;
plans carry exact paths, signatures, and machine-checkable steps for a weaker
executor (capability-routing doctrine). A goal holding both cannot be
re-planned without being rewritten. Exact type signatures, discriminant
numbers, `file.rs:120` refs, and named test files belong in the plan.

*`ic goal lint-condition` warns: `plan detail`.*

**2. Never write the user's ruling in the user's voice.** "and I am ruling
it", "I am answering its canon question" — the agent drafts the decision, the
user pastes it, and the agent's design call arrives pre-approved as canon.
That satisfies a canon gate with a document the agent authored. Two real
rulings landed this way before anyone noticed.

State the open call as a **question**, recommend an answer in the message
*around* the goal, and let the user rule.

*`ic goal lint-condition` errors: `ventriloquism`. This one blocks minting.*

**3. An open call stays open.** A goal that both names a design question and
answers it has no gate — it has a decision with a question mark painted on it.
If the answer is genuinely obvious, it is not a gate; drop it and state the
assumption in `OUTCOME`.

*`ic goal lint-condition` warns: `pre-ruled call`.*

**4. First person is fine; ventriloquism is not.** "I play a year and can lose
a bird" is the user stating an outcome and reads well. "mine to decide", "do I
reverse that?" is the deliberative form and is exactly right. What is caught
is first person attached to a decision being made *inside the goal text*.

## What stays allowed

The lint's ventriloquism rule is an error, so its precision is load-bearing —
a false positive blocks a legitimate goal. These forms are deliberately not
caught, and `TestVentriloquismPrecision` in intercore pins them:

| form | example |
|---|---|
| outcome in first person | `I play a year and can lose a bird` |
| deliberative future | `canon call, mine to make: do I reverse that?` |
| deferred decision | `I will decide once you report the rate` |
| reported history | `I decided last week to cut water from scope` |

## Before handing over a goal

```bash
ic goal lint-condition --text="<the goal text>"
```

Exit 0 with no output means clean. Fix errors; read warnings and fix them
unless you can say why the goal legitimately needs the mechanism named.

## Prose

Keep the rationale that earns the goal its place — a goal nobody understands
the point of gets executed literally and uselessly. Keep it short and put it
in `OUTCOME`. Aphorisms are not requirements: "an open P0 epic whose substance
shipped is a lie on the board" is a good line and told the executor nothing it
could act on.
