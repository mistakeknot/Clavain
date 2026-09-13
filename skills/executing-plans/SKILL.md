---
name: executing-plans
description: Execute a written implementation plan in a separate session with review checkpoints.
---

# Executing Plans

Announce this skill, read the supplied plan, and check current files and repository
instructions. Treat the plan as intent; resolve material contradictions before
dependent work. Preserve unrelated changes. Use the existing project tracker.

Follow `docs/canon/reasoning-routing.md` from the selected installation. Record
reasons and rationale, resolve the execution role, and preserve frontier planning
and independent review requirements. Hand off only with decisions, constraints,
verification and escalation conditions. Missing authentication is an operational
blocker, not permission to change the required reviewer or destination.

Execute sequentially by default. If a companion `.exec.yaml` exists or the project
has `.claude/clodex-toggle.flag`, read
[execution-modes.md](references/execution-modes.md) for that mode before dispatch.
Use only authorized delegation and available host capabilities. Pattern F runs
also require [pattern-f-contracts.md](references/pattern-f-contracts.md).

For each logical task: mark progress, implement the specified behavior, run the
meaningful checks, inspect their results and preserve review evidence. Use
`intertest:test-driven-development` for behavior changes. Report material findings
between batches and continue authorized work without ceremonial approval requests.

Verification blocks require a zero process exit as well as the declared
expectation. Reject unknown expectation syntax; output text never overrides a
nonzero exit. Missing tools, malformed inputs or unavailable services are
UNVERIFIABLE. Do not turn unavailable evidence into a pass or a capability failure.

Validate all required outcomes and consumer connections after implementation.
Source presence is not invoked behavior. Retain fresh host, play, device or
production evidence where the plan requires it. Incomplete must-haves remain
open; do not mark a task accepted from structural checks alone.

Fix bugs and blockers introduced by this work within scope. Two demonstrated
capability failures require policy escalation; a disproven premise requires
immediate escalation. Ask when a new architectural decision changes authorized
scope, or required information/authority is missing. Continue unaffected work.

Use `clavain:landing-a-change` after verification and required independent review.
Commit and push when already authorized; publication retains its own authority.
Close only tasks whose required implementation and acceptance evidence exists.
