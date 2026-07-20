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

## Step 2 — Stakes classification

`clavain-cli classify-complexity "" "<description>"` → C1–C5 routes ceremony:
- **C1:** ONE confirming AskUserQuestion, then draft the charter directly.
- **C2–C3:** short interview (2-4 single questions), charter, lint, mint.
- **C4–C5:** full interview + flux-melange review of the charter before
  ratification (`/flux-melange <charter> --goal="stress-test this goal
  charter: scope, condition judgeability, risks, alternatives"`).

## Step 3 — Interview (single-question AskUserQuestion, one at a time)

Ask ONLY genuine user-authority questions: intent, success definition,
scope appetite, risk tolerance, tradeoffs. Progression: purpose →
constraints → success criteria → edge cases. Recommended option FIRST.
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
