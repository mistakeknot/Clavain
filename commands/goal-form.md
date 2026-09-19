---
name: goal-form
description: "Collaborative goal-formation ritual: research-first inter-elicitation → charter → stakes-routed review → mint (ic goal) → /goal handoff"
argument-hint: "[goal description or bead id]"
---

# Goal Formation Ritual

Form the best possible goal by maximizing comparative advantage: the USER
holds intent, stakes, taste, and go/no-go; YOU hold research breadth, prior
art, repo state, and candidate enumeration. The ritual front-loads
collaboration where errors compound — /goal is a work-until-done loop, so
goal quality is the highest-leverage variable in the cycle.

## Step 1 — Research first (never ask what you can derive)

Before any question: `bd ready` + `bd show` on candidate beads, repo state,
`ic goal list --project="$PWD" --status=open` (existing goals), and
`ic goal audit --project="$PWD"` (defects that may deserve the next goal).
For seeded candidates (from /clavain:next-goal), the seed bead's description
is ONE MORE RESEARCH INPUT — run the full pass anyway (KD 13).

### What the project is FOR

The pass above is entirely tracker-and-repo shaped: it says what work exists,
never what the work is for or who consumes it. Read the three documents that
answer that, where they exist — `docs/charter.md`, `docs/non-goals.md`, and the
serving map (`docs/serving-map.yaml` by convention; jawnomicon's is
`data/exports/publish-log.yaml`).

**A project with none of them is the common case.** Note it in one line and
carry on with the pass above unchanged. Nothing here blocks, nothing here is
a prerequisite, and a missing charter is not a finding to report.

`/clavain:next-goal` already resolves all three into `.serving` via
`scripts/next-goal-candidates.sh` and leaves `serving_status` on its receipt, so
a seeded candidate arrives with this read done. Reuse it rather than re-reading
the files — with the same caveat that governs the seed bead itself: reuse is for
the cached read, not for the judgement built on it.

**Stakes-scaled, with an ordering caveat.** The C1-C5 class is not known until
Step 2, so Step 1 always does the cheap half and the expensive half waits:

- **Always, here:** which of the three exist, `.serving.charter.headline`, and
  how many rows sit in `.serving.map.blocked`. One line. The helper has already
  cached it, so it costs nothing.
- **C1-C2:** that one-line summary is the whole read. Do not open the files.
- **C3+:** once Step 2 has classified, come back and read `docs/charter.md` and
  `docs/non-goals.md` in full, plus the `reason` on every
  `.serving.map.blocked` row, before drafting the charter in Step 4.

## Step 2 — Stakes classification

`clavain-cli classify-complexity "" "<description>"` → C1–C5 routes ceremony:
- **C1:** ONE confirming AskUserQuestion, then draft the charter directly.
- **C2–C3:** short interview (2-4 single questions), charter, lint, mint.
- **C4–C5:** full interview + flux-melange review of the charter before
  ratification (`/flux-melange <charter> --goal="stress-test this goal
  charter: scope, condition judgeability, risks, alternatives"`).

## Step 3 — Interview (single-question AskUserQuestion, one at a time)

Ask ONLY genuine user-authority questions: intent, success definition,
scope appetite, risk tolerance, tradeoffs. Progression: purpose → who is
waiting → constraints → success criteria → edge cases. Recommended option
FIRST. **Skip the who-is-waiting question when the serving map already
answered it** — Step 1's rule holds, and asking what the repo states is how
an interview spends the user's attention on what it could have derived.
Anchoring instrumentation (KD 13): after each question, record
(first-listed option, chosen option) via
`clavain-cli interspect-evidence goal-form-anchor "<first>" "<chosen>"`
if the verb exists; otherwise skip silently.

## Step 4 — Charter

Write `docs/goals/YYYY-MM-DD-<slug>-charter.md`: Title · Why (leverage) ·
Scope (in/out) · Acceptance criteria · **Completion condition** (the
LITERAL string handed to /goal — never a paraphrase; write it so the
evaluator can judge it from surfaced output: commands, exit codes, bead
closes; bound it with "or stop after N turns") · Successor obligations.

**The completion condition follows `docs/guide-goal-shape.md`** —
OUTCOME / GATE n / DONE WHEN / OUT, and its four rules. Two of them bind
hardest on YOU as the drafter:

- **State the outcome, not the mechanism.** Exact signatures, discriminant
  numbers, and `file.rs:120` refs are plan content, not goal content.
- **Never write the user's ruling in the user's voice.** "and I am ruling
  it" in a charter you drafted satisfies a canon gate with your own
  document. Carry the open call into the condition as a QUESTION; put your
  recommendation in the handoff message, not inside the goal.

The condition also carries `WHO'S WAITING` (guide-goal-shape rule 5): the
consumer whose capability changes when this lands, or `nobody` written out.
Where the serving map answered, name the consumer and the `blocked_by` it is
waiting on. Where the project has no serving documents, answer from the
interview — the user holds that fact even when no file records it — and if the
answer really is `nobody`, write `nobody`. `ic goal lint-condition` has no rule
for this line, so Step 5 will not catch a missing one.

A non-goal the charter would cross is a defect in the charter, not an obstacle
to route around. Name the constraint, put the re-ruling to the user, and leave
it open. Do not write scope that crosses a standing line, and do not narrow the
line to fit the scope.

An unresolved design call from Step 3 becomes a `GATE`, never a ruling.

## Step 5 — Lint + mint

`ic goal lint-condition --file=<condition-extract>` — fix errors (the
tier-independent gate; C1 goals get this too). Then:
`clavain-cli goal-mint "<title>" --project="$PWD" --condition-file=<path>
--charter=<charter-path> --complexity=<N> [--bead=<id>]`
Bead binding is stakes-scaled (KD 3): epic for C4/C5, task bead or none
for C1.

## Step 6 — Handoff

Print the goal-mint paste block verbatim and STOP. The user invokes /goal —
session binding is theirs, not yours.
