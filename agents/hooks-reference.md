# Clavain — Hooks Reference

## Hook Conventions

- Registration in `hooks/hooks.json` — specifies event, matcher regex, and command
- Scripts in `hooks/` — use `${CLAUDE_PLUGIN_ROOT}` for portable paths
- Scripts must output valid JSON to stdout
- Use `set -euo pipefail` in all hook scripts

## Active Hooks

- **SessionStart** (matcher: `startup|resume|clear|compact`):
  - `session-start.sh` — injects `using-clavain` skill content, interserve behavioral contract (when active), upstream staleness warnings. Sources `sprint-scan.sh` for sprint awareness. On compact: injects mandatory recovery protocol (re-read CLAUDE.md, confirm conventions, check in-progress beads).
  - `context-reset-post.sh` — opens (startup/clear), carries (compact) or keeps (resume) the context epoch for observe-mode context-reset telemetry. A compacted epoch carries exposure and logs its own first-read row. Prints nothing. NOT a security boundary.
- **PreToolUse** (matcher: `Edit|Write|MultiEdit`):
  - `guard-plugin-cache.sh` — blocks edits to `~/.claude/plugins/cache/` (cached copies overwritten on install; directs to source repo)
- **PreToolUse** (matcher: `Bash|Skill|mcp__.*`):
  - `context-reset-pre.sh` — logs approval-gated actions (push, PR, release, publication, destructive override) as `would_be_reset` when the epoch is exposed or unknown, or as `approval_clean` when it is clean. It always allows and prints nothing. NOT a security boundary.
- **PostToolUse** (matcher: `Edit|Write|MultiEdit|NotebookEdit`):
  - `interserve-audit.sh` — logs source code writes when interserve mode is active (audit only, no denial)
- **PostToolUse** (matcher: `Edit|Write|MultiEdit`):
  - `catalog-reminder.sh` — reminds about catalog updates when components change
- **PostToolUse** (matcher: `Bash`):
  - `auto-publish.sh` — detects `git push` in plugin repos, auto-bumps patch version if needed, syncs marketplace, syncs GitHub repo description with current component counts
  - `bead-agent-bind.sh` — binds agent identity to beads claimed with bd update/claim (warns on overlap, notifies other agent)
- **PostToolUse** (matcher: `WebFetch|WebSearch|Bash|Task|Agent|mcp__.*|web__.*|web\.run`):
  - `context-reset-post.sh` — records exposure to untrusted content (web, remote commands including `ssh`, non-exempt MCP, browser), coalesced into accounting batches. Uncovered child agents and `Task`/`Agent` results make exposure `unknown`. Prints nothing. NOT a security boundary.
- **Stop**:
  - `auto-stop-actions.sh` — unified post-turn actions: entity-backed goal audit defects (lib-goal-audit.sh, highest priority) short-circuit the rest; otherwise detects signals via lib-signals.sh: weight >= 4 triggers /clavain:compound, bead-closed + opt-in triggers self-dispatch, weight >= 3 triggers /interwatch:watch
- **SessionEnd**:
  - `dotfiles-sync.sh` — syncs dotfile changes at end of session

## Hook Libraries

Sourced by hook scripts, not registered as hooks themselves:

| Library | Purpose |
|---------|---------|
| `lib.sh` | Shared utilities (escape_for_json, plugin path discovery) |
| `lib-intercore.sh` | Intercore CLI wrappers (ic run/state/sprint/coordination) |
| `lib-compose.sh` | Thin bridge to `clavain-cli compose` — provides `compose_dispatch()` and `compose_available()` (in `scripts/`, not `hooks/`) |
| `lib-sprint.sh` | Sprint state queries (phase, gate, budget, artifact); exports `CLAVAIN_COMPOSE_PLAN` after phase advance |
| `lib-signals.sh` | Signal detection engine for auto-stop-actions |
| `lib-spec.sh` | Agency spec loader — reads `config/agency-spec.yaml` at runtime |
| `lib-verdict.sh` | Verdict file write/read utilities for structured agent handoffs |
| `lib-gates.sh` | Phase gate shim — delegates to interphase when installed, no-op stub otherwise |
| `lib-discovery.sh` | Plugin discovery shim — delegates to interphase when installed, no-op stub otherwise |
| `lib-context-reset.sh` | Observe-mode context-reset telemetry: exposure/approval classification, epoch state, row emission (NOT a security boundary) |

### Observe-mode context-reset telemetry (mk-42j9.40) — NOT a security boundary

The context-reset hooks measure how often a "reset context before an
approval-gated action once the session has read untrusted content" rule would
fire, and what it would cost. They are hygiene telemetry only:

- **Nothing blocks, nothing is enforced, no reset is performed or requested.**
  Every row carries `verdict: "allow"`, `enforced: false` and
  `security_boundary: false`. The hooks print nothing on stdout, so normal
  permission prompts are unchanged, and they fail open (`trap 'exit 0' ERR`).
- The store is plain JSON, which any local process can edit. It is not
  tamper-resistant. Rows go to `~/.clavain/context-reset/events.jsonl` and
  per-session state to `state/<session>.json` (override the location with
  `CLAVAIN_CONTEXT_RESET_DIR`). A child agent (payload `agent_id`) keeps its own
  `state/<session>.agent.<agent>.json`, starting from the parent's exposure.
  URLs, queries and commands are never stored; rows keep the host and a hash
  reference. Redaction fails closed: unless a URL provably parses clean, its
  host is logged as `<redacted-url>`. That covers shell-built URLs (`$`,
  backticks, `${...}`, operators, whitespace), URLs cut at a substitution or
  operator boundary, an `@` after the authority, and non-numeric or empty
  ports. Nothing before the last `@` of an authority is ever logged. This is
  log hygiene, not a security boundary.
- Config lives in `config/context-reset.yaml` (override the path with
  `CLAVAIN_CONTEXT_RESET_CONFIG`). Only `mode: observe` and `mode: off` exist.
  If `approval` or `full` is configured, the hooks log an error at SessionStart,
  record nothing and never block. Enforcement needs origin tagging and
  attestation, which are deferred to mk-42j9.42.
- **Rollback:** set `mode: off` in the config, or export
  `CLAVAIN_CONTEXT_RESET_MODE=off`.
- `CLAVAIN_DISPATCH_ROLE` labels rows by role (default `interactive`).
- Bash commands are split by a heuristic, quote-aware tokenizer. It is not a
  full shell parser. `bash -c` and `eval` bodies are classified too.
- Unrecognized forms, such as `$VAR push`, wrappers like `xargs`/`make` around a
  push, unknown `*deploy*` scripts, unclassified remote URLs, or a `curl` whose
  target is a variable, increment the `coverage_gap` counter. They are never
  counted as clean.
- A `Task`/`Agent` result in the parent is recorded as `unknown` exposure
  (`source_class: subagent-result`), because which content the child read is
  not known without origin tagging (mk-42j9.42).
- `scripts/context-reset-report.sh [--json]` summarises the store:
  - exposure epochs and research batches;
  - would-be resets, exposed/unknown vs clean;
  - coverage gaps and hook errors;
  - estimated cost H × (cache-write − cache-read) in input-token-equivalents,
    for approval-triggered resets and for research-triggered resets
    (`research_batches`, `full_mode_upper_bound`);
  - a breakdown by role and mode.
- `scripts/context-reset-audit.sh --transcript FILE [--record]` reconciles a
  transcript against the store, for sessions or hosts where the hooks did not
  run. Exposure is compared per epoch and per accounting batch, and a surplus in
  one epoch never offsets a shortfall in another. Batch windows use tool-result
  timestamps, which are closest to the hooks' completion-time batching. A
  `Task`/`Agent` or uncovered-child call whose `exposure_unknown` row is missing
  is reported separately as `missed.subagent_unknown`, as uncertain exposure
  rather than definite exposure.

### Remote shared-state authority

When shared state has moved to another host, the host-local marker
`~/.config/clavain/remote-shared-state` suppresses shared-state access through the hook libraries and
automatic Stop/SessionEnd handoff actions that depend on that state. Its presence
is authoritative, including an empty file or broken symlink. Keep it outside the
plugin cache so plugin updates preserve the posture. It does not configure a
remote transport or move a database.

Install and verify this behavior before fencing a former local database. Retain
the marker until local authority is explicitly restored. Ordinary user-directed
coding remains available; task claims and shared-state writes belong on the
authority host. Dispatch counters distinguish a confirmed absent value from a
database error: only absence starts at zero; unavailable or corrupt state blocks
automatic dispatch.

Dispatch limits count reserved claim attempts, including failed or raced claims; empty scans do not consume capacity, and a counter write must succeed before a claim is attempted. Local filesystem locks and local plugin publication bookkeeping remain independent of the shared database. Keep the host-local marker out of dotfiles synchronization to the authority host.