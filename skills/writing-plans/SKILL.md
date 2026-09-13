---
name: writing-plans
description: Plan multi-step implementation from a spec or requirements before editing code.
---

# Writing Plans

Use an existing approved design when available. Read the relevant repository
instructions, philosophy, source, prior solutions and task history. Do not restart
a brainstorm when the user supplied a plan. Announce this skill once.

Follow the selected installation's `docs/canon/reasoning-routing.md`: record the
accountable decision context, resolve planning and required independent review,
and preserve frontier involvement while uncertainty changes the plan. Operational
failures do not justify downgrading a required model or gate.

Write `docs/plans/YYYY-MM-DD-<feature-name>.md` with the goal, architecture,
constraints, alignment and conflict/risk. Name observable outcomes, artifacts,
consumer connections and acceptance evidence. Use the project's existing tracker.

For each small logical task specify exact files, dependencies, implementation
decisions, meaningful tests and commands with expected results. Use test-first
implementation for behavior changes. Retain real user, device, play or production
verification where required; a fixture cannot replace acceptance. Define explicit
handoff decisions, constraints, verification and escalation conditions.

Read [plan-format.md](references/plan-format.md) when writing task templates,
verification blocks or an execution manifest. For independent execution with
three or more tasks, include a dependency manifest if delegation is authorized
and supported. Resolve role/model/effort through policy; no implicit model choice.

Review the plan against the source and required gates. If implementation is
already authorized, continue with `clavain:executing-plans`. Ask only for missing
information or authority that changes the work. Preserve user-requested review
checkpoints and separate publication authority.
