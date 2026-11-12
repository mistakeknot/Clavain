---
name: writing-plans
description: Plan multi-step implementation from a spec or requirements before editing code.
---

# Writing Plans

Use an existing approved design when available. Read the relevant repository
instructions, philosophy, source, prior solutions and task history. Continue from
the user's supplied plan. Announce this skill once.

Read the glossary before naming plan tasks: starting at the repo root, check `docs/glossary.md`, `GLOSSARY.md`, then `CONCEPTS.md` in each directory up to the workspace root; use the first file found, or continue if none exists.

Follow the selected installation's `docs/canon/reasoning-routing.md`: record the
accountable decision context, resolve planning and required independent review,
and preserve frontier involvement while uncertainty changes the plan. Operational
failures do not justify downgrading a required model or gate.

Write `docs/plans/YYYY-MM-DD-<feature-name>.md` with the goal, architecture,
spec pointer, global constraints, review focus, alignment and conflict/risk.
Name observable outcomes, artifacts, consumer connections and acceptance
evidence. Keep progress exclusively in the project's existing tracker rather
than markdown checkboxes.

Write for a capable engineer who has not seen this codebase or spec: they write
idiomatic code once they know the exact interface and test. A plan records the
decisions they cannot make alone (files, names and signatures, the spec's
values, the tests that prove each task), not the code. A plan longer than the
code it describes has written the code; a line that decides nothing ("TBD",
"handle edge cases", a type no task defines) is the opposite failure.

Size each task as a thin end-to-end slice that can be demonstrated on its own,
fits one fresh session and carries its own test cycle and review gate. Fold setup,
configuration and docs into the task that needs them. Name each task's blockers
(or state none); schedule preparatory refactors first and make dependent slices
wait for them. For each task give exact files, an Interfaces block (what it consumes
and produces, with exact signatures), meaningful tests, commands with expected
results and a `<verify>` block. Use test-first implementation for behavior
changes. Retain real user, device, play or production verification where
required; a fixture cannot replace acceptance. Define explicit handoff decisions,
constraints, verification and escalation conditions.

Done when each task names its interfaces, blockers, test cycle and acceptance evidence.

Read [plan-format.md](references/plan-format.md) when writing the header, task
steps, verification blocks, the self-review or an execution manifest. For
independent execution with three or more tasks, include a dependency manifest if
delegation is authorized and supported. Resolve role/model/effort through policy;
no implicit model choice.

Self-review the plan against the source: spec coverage, step scan, type
consistency, review focus and proportion. Fix findings inline. Then hand off:
recommend Subagent-driven (`clavain:subagent-driven-development`) or Native
(`clavain:executing-plans`) with one reason drawn from the plan. If
implementation is already authorized, continue with the chosen or recommended
method. Otherwise link the saved plan for review; approving an idea or a scope
is not approval of a plan the user has not seen. Ask only for missing
information or authority that changes the work. Preserve user-requested review
checkpoints and separate publication authority.

Done when the self-review findings are resolved and the plan is handed off with the required review and authority checkpoints preserved.
