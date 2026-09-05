# Astra instruction audit

Date: 2026-09-05 (refresh after installed release checks)
Scope: first GPT-6 Astra canary and role-routing rollout

## Effective instruction order

1. Product/runtime safety instructions and the active session's developer policy.
2. The user's current task, explicit authorization, and constraints.
3. Global and workspace `AGENTS.md`, followed by applicable repository instructions
   and `PHILOSOPHY.md` for the component being changed.
4. Relevant skill procedures and required references, subject to the user's intent
   and the active runtime's authority. Skills do not override the task brief.

The active runtime permits delegated agents only when the user or an applicable instruction explicitly asks for them. Clavain's routing configuration describes future dispatches; it does not grant the current session permission to create agents.

## Audit findings

- Baseline: global instructions contain overlapping Compound and Clavain tool-map blocks. `Sylveste-x7va` prepares a single Clavain-generated OODARCS contract and removes contradictory routing. Record the staged patch or installed producer SHAs with each probe; do not claim staged instructions are installed. The contract preserves runtime authority and OODARC telemetry identifiers.
- Commit/push policy is consistent for this task: work is committed per repository and pushed only because the user explicitly supplied an implementation plan that requires it. Release preparation never implies deploy authority.
- Approval-heavy Clavain commands (`work`, `execute-plan`, and related commands) retain their own checkpoints when invoked. A dispatch profile cannot bypass those command contracts.
- Loaded execution, TDD, search, and Zaka skills do not alter repository authority. Zaka provides a steerable transport; it does not make an executor the release authority.
- Invoked Codex is now 0.153.3. ChatGPT-authenticated Astra execution, structured questions and steering succeeded, and the same-CLI comparison accepted 18/18 cells for each of three routes. The user-selected base profile is Astra/xhigh/Standard. Experimental context management remains isolated to `astra.config.toml`; it was not merged into base configuration.
- Codex's old March Interflux links were still exposing obsolete review instructions after the Claude plugin release. Three current skill links and 22 command wrappers now resolve to the released canonical checkout; the old links/wrappers are recoverable. This was a scoped repair, not a global companion install.
- The fresh Clavain doctor still calls `[mcp_servers.*]` legacy and recommends `[mcp.servers.*]`. The installed CLI reads the working configuration, and the [official MCP guide](https://learn.chatgpt.com/docs/extend/mcp) still specifies `[mcp_servers.<name>]`. Do not rewrite user config on that warning alone. `Sylveste-8nov` tracks an isolated real-CLI reproduction and installer correction. A sandbox-only receipt-directory warning disappeared when rechecked outside the sandbox.

## Canary invariants

- Select `codex --profile astra` only for the isolated experimental-profile lane; record its use separately. Ordinary role canary tasks use the resolved role profile. Do not merge experimental context management into the base profile or pool experimental and ordinary results without labeling them.
- Require Codex 0.153.1 or newer for an Astra dispatch profile.
- Fall back only for explicit model unavailability, account access absence, or insufficient Codex version.
- Retry HTTP 429 on the same resolved model with a bounded count.
- Treat policy/misalignment 403 and other configuration 4xx responses as terminal.
- Persist the resolved role/profile and any fallback reason. Consequential producer and validator identities must resolve to different models.
- The `main-integrator` verifies the actual checkout and retains commit, push, and deploy authority unless the user explicitly grants it elsewhere.

## OODARCS continuation boundary

The x7va instruction/catalog candidate is separate from the earlier duplicate-only
baseline. Matched TUI fixtures, including contradiction and restricted-authority
cases, are diagnostic evidence and earn no enrolled-task credit. Candidate rollout
requires the existing external review gate, producer push, narrow instruction sync,
and post-install interactive verification. A policy restriction on review is not
permission to change validator or destination. Keep `Sylveste-8nov` open and do not
invoke broad installers, automatic refresh, or an MCP-schema rewrite.
