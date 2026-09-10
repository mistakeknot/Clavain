---
name: using-clavain
description: Route substantive coding, research, planning, documentation, and review through Sylveste OODARCS. Skip trivial requests.
---

# Sylveste OODARCS

Use **Observe → Orient → Decide → Act → Reflect → Compound → Synthesize** for
substantive work. Load this router once at the first substantive task; reuse it
on subsequent turns and resumed sessions unless the task or installation changes.
Select applicable workflow and domain skills automatically. Users need not know
their names. Trivial requests can be answered directly.

1. **Observe** actual files, tool results, sources, and outcomes.
2. **Orient** against the goal, constraints, existing evidence, and uncertainty.
3. **Decide** the next proportionate action and the evidence needed to judge it.
4. **Act** within the user's scope and authority; finish authorized work.
5. **Reflect** on what the outcome taught us, especially surprises or failures.
6. **Compound** a useful improvement in an authorized artifact: code, a test,
   requested documentation, or the project's tracker. Memory writes require
   their own authorization. If no durable improvement is warranted or authorized,
   retain the learning in the response or current working understanding.
7. **Synthesize** that learning with existing evidence and goals. Reconcile
   contradictions, revise conclusions or next priorities within scope, and state
   material changes. Do not silently start unrelated follow-up work.

Apply the loop at task, sprint, and session scale without compulsory headings,
invented lessons, or a forced full lifecycle. User intent and runtime policy govern
skill procedures; preserve review, verification, approval, release, and model
routing boundaries. Existing **OODARC** telemetry identifiers and execution phases
remain unchanged. See Sylveste `PHILOSOPHY.md`, the OODARCS lens, for the doctrine.

## Reasoning allocation

Before substantive planning or execution, read the selected Clavain installation's
`docs/canon/reasoning-routing.md`. Resolve roles with its `config/routing.yaml`
and an accountable decision context. Substantial uncertainty, foundational
invariants, broad consequences, difficult verification, and demonstrated
capability failure require frontier involvement. Domain names are examples.
Substantial new game, agent-system, AI/ML, graph-database, and product-strategy
capabilities require frontier planning. Keep frontier involvement while evidence
changes the plan. Hand off with decisions, constraints, verification, and escalation
conditions explicit; retain empirical acceptance. Foundational/consequential plan
review requires the other frontier model. Operational failures are not capability
strikes. Preserve stricter gates; unsupported host routing must be reported.


## Quick Router — 26 skills, 6 agents, and 57 commands

In Codex, read the selected skill's full `SKILL.md` using its path in the current
catalog. Names below are capability hints; resolve the installed name and path.
Do not run Claude slash commands in a terminal or assume they are Codex tools.
In Claude Code, invoke the corresponding Skill tool or installed command.

Routes compose across task phases. Fixing a bug requires
`intertest:systematic-debugging` for reproduction and diagnosis, then
`intertest:test-driven-development` for implementation, including its required
verification skill load. Executing an existing plan also requires
`clavain:executing-plans`; retain that plan and its acceptance criteria. Load each
required body before applying its workflow.

| Task | Primary skill | Add when relevant |
|------|---------------|-------------------|
| Diagnose a bug or failing check | `intertest:systematic-debugging` | `clavain:bug-reproduction-validator` |
| Plan implementation | `clavain:writing-plans` | `clavain:plan-reviewer` |
| Execute an existing plan | `clavain:executing-plans` | Domain skill, focused verification |
| Implement a feature or fix | `intertest:test-driven-development` | `clavain:refactor-safely` for significant refactors |
| Research a question | Available research skill matching its depth and sources | `alwe` for prior agent sessions; domain documentation skills |
| Write documentation | Guidance for the requested artifact and house style | `clavain:engineering-docs` for a solved problem; artifact-format skill |
| Audit, refactor, or consolidate documentation | `interscribe:interscribe` | `interwatch:doc-watch` for drift |
| Review code or a plan | `clavain:code-review-discipline` | `clavain:plan-reviewer`; installed Interflux engine for deeper review |
| Prepare an authorized release | `intertest:verification-before-completion` | `clavain:landing-a-change`, release/domain procedures |
| Choose next project work | `internext:next-work` | `interphase:beads-workflow` |
| Operate the portfolio agency | `clavain:remontoire` | Load only for portfolio operations |

These are common routes, not an allowlist. **Every installed unique capability
remains eligible for automatic selection**, including specialist and companion
skills. Select by the actual task and scope. Prefer the existing plan over starting
a fresh brainstorm. Read [routing-tables.md](references/routing-tables.md) when
the task needs more domain or host-specific routing detail.

For explanatory documentation requested in the response, use this writing guidance:
name the trigger, affected behavior, supporting evidence, and verification steps.
Distinguish a proposed fix from an installed or verified fix. Keep the note in the
requested destination and scope; do not turn it into a repository-documentation
audit. Load a specialist writing or artifact skill when its procedures help the
requested document.

## Boundaries and missing companions

Load detailed procedures and supporting resources only when relevant. A missing
companion is not permission to install plugins, change MCP settings, or fetch
repositories. Continue with supported tools and disclose a material capability
gap; ask only when it blocks a required outcome. Preserve a blocked external
review as a gate; switching providers or destinations is not a fallback for policy.

Delegate only when authorized and supported by the active host; otherwise execute
in the main thread and batch independent tool calls. Use the project's actual
tracker; do not create a second task system. Outside a project, maintain lightweight
in-session state. Verify current results before reporting completion.
