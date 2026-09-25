---
name: using-clavain
description: Route substantive coding, research, planning, documentation, and review through Sylveste OODARCS. Skip trivial requests.
---

# Sylveste OODARCS

Load this router once at the first substantive task and reuse it on resume unless the task or installation changes. Apply Observe → Orient → Decide → Act → Reflect → Compound → Synthesize: inspect evidence, align with intent, choose proportional action and verification, finish authorized work, then reconcile results. Compound in authorized artifacts only; memory writes require permission. State material changes when synthesizing. Do not force seven headings or start unrelated follow-up work. Existing OODARC telemetry names remain unchanged. See `PHILOSOPHY.md` for the full lens.

Read the selected `docs/canon/reasoning-routing.md` before substantive planning or execution and record its accountable decision context. It contains the binding classification, role, frontier, reviewer, failure, evidence and authority rules. Code behavior changes and execution of plans count even when small. Select installed skills by actual task, read each selected body before applying it, and retain all unique specialist and companion capabilities. Trivial requests stay lightweight. Load reference detail only as needed.

## Quick Router — 26 skills, 6 agents, and 57 commands

In Codex, read the selected skill's full `SKILL.md` from its path in the current catalog. Claude slash commands are not shell commands or Codex APIs. In Claude Code, invoke the corresponding Skill tool or installed command. Names below are capability hints; resolve the installed path before use.

Routes compose across phases. Fixing a bug requires `intertest:systematic-debugging` for reproduction and diagnosis, then `intertest:test-driven-development` for implementation and its verification skill. Executing an existing plan requires `clavain:executing-plans`; keep its acceptance criteria. Load each required body before work.

| Task | Primary skill | Add when relevant |
|------|---------------|-------------------|
| Diagnose bug or failure | `intertest:systematic-debugging` | `clavain:bug-reproduction-validator` |
| Plan implementation | `clavain:writing-plans` | `clavain:plan-reviewer` |
| Execute existing plan | `clavain:executing-plans` | Domain skill, focused verification |
| Implement feature or fix | `intertest:test-driven-development` | `clavain:refactor-safely` for significant refactors |
| Research | Matching research skill | Prior sessions and domain references |
| Document a solution | Matching documentation skill | `clavain:engineering-docs` when useful |
| Audit or consolidate docs | `interscribe:interscribe` | `interwatch:doc-watch` for drift |
| Review code or plan | `clavain:code-review-discipline` | `clavain:plan-reviewer` or the Interflux deeper-review engine |
| Prepare an authorized release | `intertest:verification-before-completion` | `clavain:landing-a-change` and release procedure |
| Choose next work | `internext:next-work` | `interphase:beads-workflow` |
| Operate portfolio agency | `clavain:remontoire` | Only for portfolio operations |

Every installed unique capability remains eligible beyond this table. Prefer an existing valid plan. Read [routing-tables.md](references/routing-tables.md) for specialty and host detail when needed.

## Boundaries and missing companions

User authority and host restrictions govern. Preserve independent review, fresh verification, empirical acceptance and publication gates from the short canon. A missing companion does not authorize installation or a provider switch; preserve a blocked review. Delegate only when authorized and supported. Use the project tracker; do not create a second task system. Outside a project use lightweight in-session state. Verify fresh results before completion. Apply its inline explanatory-writing guidance: name the trigger, affected behavior, evidence and verification; distinguish proposed from verified changes without forcing a repository-documentation audit.
