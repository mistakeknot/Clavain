---
name: plan-review
description: Have multiple specialized agents review a plan in parallel
argument-hint: "[plan file path or plan content]"
disable-model-invocation: true
---

## Progress Tracking

This command is the **Validate** leg of the OODARC loop — a decision gate that checks the plan before commitment. Display and update:

```
plan-review (OODARC: Validate — decision gate):
- [ ] Gauge lint (BLOCKING): plan-gauge-lint.py <plan> --repo-root <repo>
- [ ] Route: /flux-melange (DEFAULT for design-shaping plans) vs fixed trio (routine mechanical plans only)
- [ ] Dispatch 3 review agents in parallel (plan-reviewer, fd-architecture, fd-quality)
- [ ] Collect all three verdicts
- [ ] Synthesize into a unified, prioritized review
```

## Step 0 — gauge lint (blocking)

Run this **before** dispatching any reviewer, and do not proceed while it reports findings:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/plan-gauge-lint.py" <plan.md> --repo-root <repo> \
  [--extra-artifact <file present at verify time but not written by the plan>]...
```

It applies the plan's own edits to a virtual copy of the tree, then runs the plan's
verify commands against the result and compares against the plan's stated
expectations. Exit 1 means at least one verify block cannot pass however faithfully
the plan is executed. Fix the plan and re-run — these findings are not advisory, and
they are not a reviewer's opinion about style.

**Why blocking.** In pilot 1 (shadow-work, 2026-07-27) three defects were run through
two independently authored plans, twice. Across four executions every one of ~60 edits
applied byte-exact with zero drift, and *every single stop was a defect in the plan's
own verify block* — six in total. Five share one shape: the plan's emitted text is
simultaneously the artifact and an input to a checker the same author wrote, and
nobody ever executed one against the other. Two frontier-tier authors, a frontier-tier
reviewer, and the harness each shipped an instance of it. Reading a gauge does not
catch this; running it does. Replayed against the two real plans, the linter flags all
four strikes before any execution — and clears exactly the class that a repair fixes,
leaving the unrepaired one standing.

Codes: `GAUGE001` self-match (a verify forbids text the plan writes) · `GAUGE002`
unescaped metacharacter in a literal search · `GAUGE003` emitted text breaks the
target file's shell quoting · `GAUGE004` a `cargo test` verify that cannot compile the
tests it asserts on · `GAUGE005` a verify that runs a build artifact rebuilt only when
absent.

`--self-test` replays all six pilot-1 defects plus a clean control; run it to confirm
the linter still works after any change to it. `--json` for machine consumption.

**Routing (first checkbox — standing rule 2026-08-28):** `/interflux:flux-melange <plan file> --goal="find what makes this plan fail and what it's missing" --weights=risk-hunt` is the DEFAULT review for any design-shaping plan — one derived from a brainstorm/PRD, an architecture pivot, a migration, a novel subsystem, or anywhere a missed flaw is expensive (requires interflux). Its adaptive rounds chase the scary-but-unconfirmed finding rather than reporting it once. The fixed trio below is the exception, reserved for routine mechanical plans (small bugfix or refactor plans with no design content).

Launch three review agents in parallel using the Task tool to review the provided plan:

1. **plan-reviewer** — Use the Task tool with `subagent_type: "clavain:review:plan-reviewer"` to review the plan against implementation standards and completeness.

2. **fd-architecture** — Use the Task tool with `subagent_type: "interflux:review:fd-architecture"` to evaluate architectural decisions, component boundaries, and design patterns.

3. **fd-quality** — Use the Task tool with `subagent_type: "interflux:review:fd-quality"` to check for over-engineering, unnecessary complexity, and YAGNI violations.

All three agents should receive the plan content and run concurrently (use a single message with multiple Task tool calls). After all agents complete, synthesize their findings into a unified review with prioritized issues.
