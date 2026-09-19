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

WHO'S WAITING: the consumer that can do something new once this
lands, and what they cannot do until it does. "nobody" is a
permitted answer and has to be written down, never left off.

GATE n — <what kind>: a question, left open, with who decides it.
"Bring me options" / "recommend one" is the instruction; the answer
is not in the goal.

DONE WHEN: predicates an evaluator can judge from surfaced output —
a command, an exit code, a bead close, an artifact state. Bound it:
"or stop after N turns".

OUT: what is explicitly not in scope, with the ruling it follows from.
```

## Five rules

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

**5. Name who is waiting, even when nobody is.** `WHO'S WAITING` is the only
line in the form that is about the world outside the repo. The other four
describe the work. This one says whose capability changes when the work lands,
and it is the question the rest of the form cannot ask.

Measured in jawnomicon on 2026-09-19: canon was byte-identical across exports
v34, v35 and v36 — three releases whose whole difference was an overlay that,
in the publish ledger's own words, "the game has no surface for". Two
registered consumers had deferred both of the last two exports on exactly that
ground. Nothing in the goal path surfaced it, because nothing read the file
that said so. Ranking on `dependent_count` could not have: a bead that unblocks
four other beads scores well whether or not any of the five reaches a consumer.

So the answer is allowed to be `nobody`, and it still has to be typed. A goal
nobody is waiting on is frequently the right one — refactors, migrations,
paying down a gate someone will trip over later. What is not right is not
knowing, and an omitted line reads identically to a line whose answer was
`nobody`. Writing it makes the unwaited-on goal visible AS one, to the drafter
first and the user second.

*`ic goal lint-condition` does not check this line.* It enforces the mechanical
half — predicates, ventriloquism, plan detail — and gained no rule here, so a
goal missing `WHO'S WAITING` still exits 0. The line is enforced by the reader,
and by `/clavain:next-goal` Step 2, where a candidate with no answer cannot
sort on the serving axis and loses to one that has it. Do not read a clean lint
as evidence the line is there.

### Where the answer comes from

Three files answer it without guesswork, and `/clavain:next-goal` already reads
all three into `.serving` before it ranks:

| file | what it settles |
|---|---|
| `docs/charter.md` | what the project is for, and who consumes its output |
| `docs/non-goals.md` | standing constraints the goal is expected to stay behind |
| the serving map | which consumer is blocked, on what, and for how many releases |

The serving map is `docs/serving-map.yaml` by convention; jawnomicon's is
`data/exports/publish-log.yaml`. Most projects have none of the three, and that
is not a blocker — answer from what you know and say which it was. `WHO'S
WAITING: nobody — no consumer registry in this repo` is a complete answer. What
it must not become is silence.

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

Then check `WHO'S WAITING` by eye. The lint has no rule for it, so a goal
missing the line passes this command — which is precisely the gap rule 5
exists in, rather than alongside.

## Prose

Keep the rationale that earns the goal its place — a goal nobody understands
the point of gets executed literally and uselessly. Keep it short and put it
in `OUTCOME`. Aphorisms are not requirements: "an open P0 epic whose substance
shipped is a lie on the board" is a good line and told the executor nothing it
could act on.
