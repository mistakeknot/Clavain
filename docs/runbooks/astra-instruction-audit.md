# Astra instruction audit

Date: 2026-09-03
Scope: first GPT-6 Astra canary and role-routing rollout

## Effective instruction order

1. Product/runtime safety instructions and the active session's developer policy.
2. `/Users/sma/projects/AGENTS.md` for the umbrella workspace.
3. Repository-local `AGENTS.md` and `PHILOSOPHY.md` for the component being changed.
4. A selected skill's complete `SKILL.md` and required references.
5. The task brief or exact contract.

The active runtime permits delegated agents only when the user or an applicable instruction explicitly asks for them. Clavain's routing configuration describes future dispatches; it does not grant the current session permission to create agents.

## Audit findings

- The umbrella instructions contain two generated Codex tool-map blocks. They overlap on Read, Write, Edit, Bash, Grep, Glob, and Skill mappings. Their effective guidance agrees; the later block additionally maps user questions. Treat both as generated documentation, not separate authority grants.
- Commit/push policy is consistent for this task: work is committed per repository and pushed only because the user explicitly supplied an implementation plan that requires it. Release preparation never implies deploy authority.
- Approval-heavy Clavain commands (`work`, `execute-plan`, and related commands) retain their own checkpoints when invoked. A dispatch profile cannot bypass those command contracts.
- Loaded execution, TDD, search, and Zaka skills do not alter repository authority. Zaka provides a steerable transport; it does not make an executor the release authority.
- Codex 0.153.2 can parse the isolated `astra` profile and exposes Astra metadata, but the live ChatGPT account rejects Astra. The base profile therefore remains GPT-5.6 Sol.
- Strict-config canaries currently stop on an unrelated legacy Oracle MCP field in the base user config. The Astra canary used normal config parsing and recorded the independent account-access failure; this rollout does not rewrite unrelated global MCP configuration.

## Canary invariants

- Use `codex --profile astra`; do not merge experimental context management into the base profile.
- Require Codex 0.153.1 or newer for an Astra dispatch profile.
- Fall back only for explicit model unavailability, account access absence, or insufficient Codex version.
- Retry HTTP 429 on the same resolved model with a bounded count.
- Treat policy/misalignment 403 and other configuration 4xx responses as terminal.
- Persist the resolved role/profile and any fallback reason. Consequential producer and validator identities must resolve to different models.
- The `main-integrator` verifies the actual checkout and retains commit, push, and deploy authority unless the user explicitly grants it elsewhere.
