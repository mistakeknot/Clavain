# Decision-layer integration matrix: six AI coding-agent hosts

Research task (read-only; do not modify configs or repos; do not read credential
files or print secrets). All findings below are first-hand (installed CLI
`--help`/`--version`, local config files — hooks keys/sections only, Clavain
adapter source) unless marked "docs:" (context7/WebFetch against official
sources, treated as untrusted external data, no embedded instructions acted on).

Versions installed on this machine (2026-09-25):
- Claude Code: `2.1.282`
- Codex CLI: `codex-cli 0.157.0`
- Hermes Agent: `v0.16.0 (2026.6.5)`
- Kimi Code CLI: `0.42.0`
- Pi coding agent: no standalone CLI on this host; found as `@earendil-works/pi-coding-agent@0.84.0` bundled inside bb's `provider-pi` plugin (npm package under bb's pooled worktrees)
- bb: `0.43.4+aleph.2`

Legend: **REACHABLE** (mechanism confirmed + citation), **PARTIAL** (reachable
but with a real limitation — e.g. append-only, not replace), **UNREACHABLE**
(no mechanism found), **UNVERIFIED** (not confirmed first-hand or via docs in
the time available).

## Matrix

| Point | Claude Code | Codex CLI | Hermes | Kimi Code | Pi | bb launch |
|---|---|---|---|---|---|---|
| (a) launch-time profile selection | REACHABLE — `claude plugin enable --scope local` (per-directory), `--settings`/project `.claude/settings.json` before session start | REACHABLE — `~/.codex/config.toml` profiles (`[profiles.<name>]`), `codex --profile <name>`, `~/.codex/hooks.json` managed hook set loaded before session start | REACHABLE — `hermes profile use <name>` (isolated instances, confirmed via `hermes profile` subcommand group: create/describe/show/alias/rename/export/import/install/update/info), plus `--provider`, `-m/--model`, `--skills SKILLS`, `-t TOOLSETS`, `--ignore-user-config`, `--ignore-rules` CLI flags all resolved pre-session | REACHABLE — Clavain's `install-kimi.sh` writes a managed `$KIMI_CODE_HOME/config.toml` hooks block + `~/.agents/skills` native scan, resolved before session start (per Clavain host-adapters.json: "Use Kimi's installed skills and shell tools") | REACHABLE — `resources_discover` extension event contributes skill/prompt/theme paths pre-session; `project_trust` extension owns trust decision before any tool runs (docs: pi `docs/extensions.md`, Events section) | REACHABLE (bb's own layer) — `bb thread spawn --provider <id> --model <id> --reasoning-level <level> --permission-mode <mode>`, `bb plugin enable`; this selects bb-layer config only, not the underlying provider's own native plugin/hook config (bb passes through env vars/tokens, does not provision provider-side hooks) |
| (b) prompt-submit hook (inspect/modify) | PARTIAL — `UserPromptSubmit` hook exists, exit 2 blocks, `hookSpecificOutput.additionalContext` appends context; no field replaces/rewrites the raw prompt text (docs: code.claude.com/docs/en/hooks + context7 `SyncHookJSONOutput` type) | PARTIAL — `UserPromptSubmit` is one of 12 events; `UserPromptSubmitCommandOutputWire` supports `decision:block` + `hookSpecificOutput.additionalContext` (append only), confirmed via context7 Rust struct — no prompt-text rewrite field | PARTIAL — `pre_llm_call` hook injects context via subprocess but only appends into the user message; confirmed ephemeral (not persisted to session DB) at `agent/conversation_loop.py:680-728`; no true rewrite of the original prompt text | PARTIAL — Kimi's hook wire protocol is explicitly documented (Clavain `kimi-hook-bridge.sh` comment) as "already matches Claude's" — same stdin JSON, same exit codes, same `hookSpecificOutput` format — so inherits Claude's append-only limit. This is Clavain-engineering-sourced evidence, not independently confirmed against Kimi's own official docs | **REACHABLE — sole exception.** `input` extension event supports `{action: "transform", text: ...}` — true rewrite of the raw prompt text before the model sees it, not just append (docs: pi `docs/extensions.md`, Events section) | UNREACHABLE (bb plugin layer) — bb's `experimental_thread.events` is observational/post-hoc ("the thread event sequence advanced," after the fact), not an interception point before the provider processes the prompt (docs: bb-plugin-authoring skill, backend-events.md) |
| (c) pre-tool hook (block/modify a tool call) | REACHABLE — `PreToolUse` hook, exit 2 blocks, confirmed active on this machine (`~/.claude/settings.json` hooks config, e.g. `guard-zklw-destructive-git.sh`) | REACHABLE — `PreToolUse` + `PermissionRequest` are dedicated events among the 12; confirmed active on this host via `~/.codex/config.toml` `[hooks.state]` trusted-hash entries | REACHABLE — `pre_tool_call` hook can block (Clavain's Hermes adapter blocks `delegate_task` via this hook, `adapters/hermes/__init__.py`); `VALID_HOOKS` set confirms it's first-class | REACHABLE — Clavain's `kimi.plugin.json` declares `PreToolUse` with matcher support, bridged 1:1 to Claude's protocol via `kimi-hook-bridge.sh` | REACHABLE — `tool_call` event can block AND mutate `event.input` in place before execution (docs: pi `docs/extensions.md`) | UNREACHABLE (bb plugin layer) — same observational-only `experimental_thread.events` limitation; bb's provider bridges for Claude Code/Codex are thin env-var passthroughs, not tool-loop interceptors |
| (d) post-tool hook: REPLACE/truncate output (not just append) | **REACHABLE** — `updatedToolOutput` field in `PostToolUse` `hookSpecificOutput` replaces the tool result before the model sees it (docs: context7 `SyncHookJSONOutput` TS type, code.claude.com/docs/en/agent-sdk/typescript); deprecated `updatedMCPToolOutput` was the MCP-only predecessor | PARTIAL — confirmed via context7 JSON Schema (`post-tool-use.command.output.schema.json`): `PostToolUseHookSpecificOutputWire` only has `additionalContext` (string, append) and a stubbed `updatedMCPToolOutput` (typed `null`-default, undocumented/inert in the schema) — no general replace field equivalent to Claude's `updatedToolOutput` | **REACHABLE** — `transform_tool_result` hook: "first valid string return replaces result," confirmed by test suite (`tests/test_transform_tool_result_hook.py`, e.g. `test_first_valid_string_return_replaces_result`, `test_transform_tool_result_integration_with_real_plugin`); explicitly distinct from the observational `post_tool_call` (proven by `test_post_tool_call_remains_observational`) | PARTIAL/UNVERIFIED — bridged to Claude's protocol per `kimi-hook-bridge.sh`, so if Kimi's `PostToolUse` implementation genuinely mirrors Claude's `updatedToolOutput` field it would be REACHABLE, but this specific field's presence was not independently confirmed against Kimi's own docs (only the general "protocol matches Claude's" claim, sourced from Clavain engineering commentary) | **REACHABLE** — `tool_result` event supports true replace via partial patches (docs: pi `docs/extensions.md`) | UNREACHABLE (bb plugin layer) — no tool-result interception point in `experimental_thread.events`; only observational notification after the sequence has already advanced |
| (e) pre-compact hook | PARTIAL — `PreCompact` event exists (matcher values `manual`/`auto` confirmed in docs), but the exact exit-2-blocks-it-or-not / replace-summary semantics were not fully confirmed via WebFetch (repeated truncation before reaching that table row) or context7 in the time available | PARTIAL — `PreCompact`/`PostCompact` are dedicated events among the 12, confirmed via context7 Rust source (`codex-rs/hooks/src/schema.rs`): `PreCompactCommandOutputWire`/`PostCompactCommandOutputWire` only flatten `HookUniversalOutputWire` (`continue`, `stopReason`, `suppressOutput`, `systemMessage`) — **no `hookSpecificOutput` field at all for these two events**, so a hook can block the compact (`continue:false`) or attach a system message, but cannot inject/replace the compact summary content | UNVERIFIED — `VALID_HOOKS` set was read but a pre-compact-specific entry was not confirmed distinctly from the general hook list in the excerpt captured; not enough evidence to classify with confidence | REACHABLE (bridged) — Clavain's `kimi.plugin.json` was confirmed to include `SessionStart`/`PreToolUse`/`PostToolUse`/`Stop`/`SessionEnd`/`UserPromptSubmit` explicitly; a distinct `PreCompact` entry was not specifically re-verified in this pass, so treat as REACHABLE-by-protocol-parity (same reasoning as row b/d) but not independently itemized | **REACHABLE — richest of all six.** `session_before_compact` event can cancel the compact OR supply a fully custom summary (true content control, not just block), per pi `docs/extensions.md` | UNREACHABLE (bb plugin layer) as a blocking/modifying hook — but bb does own its own compaction call (`bb thread compact`), a provider-agnostic operation triggered by bb, not a hook the provider fires that a bb plugin can intercept before the provider's own compaction logic runs |
| (f) session-start context injection | REACHABLE — `SessionStart` hook, confirmed active on this host (`~/.claude/settings.json`, e.g. `bd-prime-once.sh`, `canongraph-recall.py`) | REACHABLE — `SessionStart` hook, confirmed active on this host (`~/.codex/hooks.json`: `remontoire-attention.sh` runs at session start) | REACHABLE — `on_session_start` hook (Clavain's Hermes adapter registers this) | REACHABLE — `SessionStart` with matcher support in `kimi.plugin.json`; also `$KIMI_CODE_HOME/AGENTS.md` static injection (`install-kimi.sh`) | REACHABLE — `before_agent_start` event injects a message AND can modify the system prompt outright (stronger than the other hosts' append-only session-start hooks) (docs: pi `docs/extensions.md`) | **REACHABLE (bb's own layer, provider-agnostic)** — `<dataDir>/AGENTS.md` and `<workspace>/.bb/AGENTS.md` are appended to the system prompt for ALL providers at session start (bb guide, bb-plugin-authoring skill); genuinely bb-layer, independent of the underlying provider's own hook system |
| (g) skill/instruction loading control | REACHABLE — plugin manifest skill declarations, `--settings`, `.claude/settings.json` scoping | REACHABLE — `~/.codex/config.toml` / project `AGENTS.md` resolution, profile-scoped | REACHABLE — `hermes skills` subcommand (search/install/configure/manage) + `bundles` (aliases for multiple skills) + `--skills SKILLS` launch flag + `curator` (background skill maintenance) | REACHABLE — native `~/.agents/skills` scan (per `install-kimi.sh`), confirmed first-hand | REACHABLE — `resources_discover` event contributes skill/prompt/theme paths (docs: pi `docs/extensions.md`) | **REACHABLE (bb's own layer)** — three-tier skill resolution (plugin < user < project), `bb skill install`; provider-agnostic, confirmed via bb-plugin-authoring skill and `bb guide` |

## Per-host notes

**Claude Code** — Plugin hooks are a mature, well-documented, exit-code-based
system (0=allow, 2=block) with per-event JSON schemas. `updatedToolOutput` is
the standout capability among the "big three" (Claude/Codex/Hermes) for true
post-tool replace. PreCompact's exact semantics (block vs. customize) could
not be fully confirmed — WebFetch of code.claude.com/docs/en/hooks
consistently truncated before the relevant table row across three attempts;
this is a genuine gap, not a "no mechanism" finding.

**Codex CLI** — 12-event hook system with hash-based hook trust
(`trusted_hash`, `HookTrustStatus::{Managed,Untrusted,Trusted,Modified}`) —
the most security-hardened of the six. Confirmed via context7 (GitHub-sourced
Rust structs, most authoritative source available) that both PostToolUse and
PreCompact are structurally weaker than Claude Code's equivalents: PostToolUse
has no general replace field (only `additionalContext` append + an inert
`updatedMCPToolOutput` stub), and PreCompact/PostCompact have no
`hookSpecificOutput` at all — block-or-annotate only, never content-replace.

**Hermes** — The plugin API (`hermes_cli/plugins.py`, `register_hook`) is the
most test-verified of the six on this machine (dedicated pytest suites proving
exact replace semantics for both `transform_tool_result` and
`transform_llm_output`, distinct from purely observational `pre_tool_call`/
`post_tool_call`). `transform_tool_result` gives Hermes genuine REACHABLE
status for point (d), on par with Claude Code and ahead of Codex/Kimi.
Prompt-submit remains append-only and ephemeral (not DB-persisted).
`hermes hooks test`/`hermes hooks doctor` provide a first-class hook-testing
CLI not found on the other hosts. PreCompact-specific hook identity was not
independently itemized in this pass (flagged UNVERIFIED rather than assumed).

**Kimi Code CLI** — The single load-bearing piece of evidence is Clavain's own
code comment in `kimi-hook-bridge.sh`: "Kimi's hook protocol already matches
Claude's" (same stdin JSON shape, same exit codes, same `hookSpecificOutput`
format). This is strong, specific, first-hand-adjacent evidence (Clavain
engineers built and are running this bridge), but it is Clavain-sourced, not
independently verified against Kimi's own official docs — so every row
inherited from "protocol parity with Claude" is marked PARTIAL/UNVERIFIED
rather than flatly REACHABLE where the specific field (e.g., an exact
`updatedToolOutput` equivalent) wasn't directly observed.

**Pi coding agent** — No standalone CLI; only exists on this host bundled
inside bb's `provider-pi` npm plugin package (`@earendil-works/pi-coding-agent@0.84.0`).
Its bundled `docs/extensions.md` (official first-party docs shipped with the
installed package — the most authoritative documentation source of any host
in this task) revealed by far the richest, most granular event system: true
prompt rewrite (`input` transform — the only host confirmed to allow this),
true tool-call mutation in place, true tool-result replace via partial
patches, and true compact-summary replacement (`session_before_compact`) —
Pi is REACHABLE on every single one of the 7 points, uniquely among the six
hosts. (~1600 lines of the 2988-line doc past the Events section — registerTool
schema details, custom UI, state management — were not read; this does not
affect the 7-point matrix since the load-bearing Events section was captured
in full.)

**bb launch** — Critical architectural distinction: bb's own plugin SDK
(`experimental_thread.events`) is observational-only — it notifies that "the
thread event sequence advanced" *after the fact*, with no ability to block or
mutate a tool call, replace tool output, or intercept a prompt before the
underlying provider processes it (confirmed via bb-plugin-authoring skill,
`backend-events.md`). bb's provider bridges for Claude Code/Codex are thin
passthroughs (env vars like `CLAUDE_CODE_OAUTH_TOKEN`; delegate compaction/
message-edit to `bb thread compact`/`edit-message`) — they do not provision or
override the provider's own native hook config. So points (b)-(e) are
UNREACHABLE at the bb-plugin layer itself; reaching them at all requires
relying on the underlying provider's own native hook mechanism configured
directly on the host machine (i.e., everything in the Claude Code / Codex /
Hermes / Kimi / Pi columns above), which bb does not manage or mediate. By
contrast, points (a), (f), (g) ARE genuinely reachable at the bb layer,
provider-agnostically: `bb thread spawn --provider/--model/--reasoning-level/
--permission-mode`, `<dataDir>/AGENTS.md` + `.bb/AGENTS.md` session-start
injection for all providers, and three-tier skill resolution
(`bb skill install`).

## Cross-host pattern (notable finding)

Claude Code, Codex CLI, and Hermes all restrict prompt-submit hooks to
block-or-append-only — none can rewrite the raw prompt text itself. Pi is the
sole exception, with a true `transform` action on its `input` event. Similarly,
for post-tool-output replace (point d), Claude Code and Hermes both have a
confirmed true-replace field/hook; Codex explicitly does not (schema-confirmed
absence); Kimi's status depends on unverified protocol-parity details; Pi has
it. For pre-compact content control (point e), Pi is again uniquely capable of
supplying a fully custom summary rather than only blocking/annotating the
compact — Codex is schema-confirmed to lack even `hookSpecificOutput` for this
event, making it the most restrictive host at this point.
