# Clavain — Architecture

## Directory Structure

```
Clavain/
├── .claude-plugin/plugin.json     # Plugin manifest (name, version, MCP servers)
├── skills/                        # 16 discipline skills (ls skills/*/SKILL.md)
├── agents/
│   ├── review/                    # 2: plan-reviewer, data-migration-expert
│   └── workflow/                  # 2: bug-reproduction-validator, pr-comment-resolver
├── commands/                      # 45 slash commands (ls commands/*.md)
│   └── interpeer.md              # Quick cross-AI peer review (+ 43 others)
├── hooks/                         # 7 active hooks + 8 lib-*.sh libraries
│   ├── hooks.json                 # Hook registration (4 event types, 6 bindings)
│   └── lib-*.sh                   # Shared: intercore, sprint, signals, spec, verdict, gates, discovery
├── cmd/clavain-cli/               # Go CLI binary (budget, checkpoint, claim, compose, phase, sprint, cxdb, scenario, evidence, policy)
├── config/                        # Agency specs, fleet registry, routing config, CXDB types, scenario schema, policy defaults
├── scripts/                       # bump-version, orchestrate.py, dispatch, fleet management
├── tests/                         # structural (pytest), shell (bats-core), smoke (subagent)
└── .github/workflows/             # CI: eval, sync, test, secret-scan, upstream-check
```

## How It Works

### SessionStart Hook

On every session start, resume, clear, or compact, the `session-start.sh` hook:

1. Reads `skills/using-clavain/SKILL.md`
2. JSON-escapes the content
3. Outputs `hookSpecificOutput.additionalContext` JSON
4. Claude Code injects this as system context

This means every session starts with the 3-layer routing table, so the agent knows which skill/agent/command to invoke for any task.

### 3-Layer Routing

The `using-clavain` skill provides a routing system:

1. **Stage** — What phase? (explore / plan / execute / debug / review / ship / meta)
2. **Domain** — What kind of work? (code / data / deploy / docs / research / workflow / design / infra)
3. **Concern** — What review concern? (architecture / safety / correctness / quality / user-product / performance)

Each cell maps to specific skills, commands, and agents.

### Component Types

| Type | Location | Format | Triggered By |
|------|----------|--------|-------------|
| **Skill** | `skills/<name>/SKILL.md` | Markdown with YAML frontmatter (`name`, `description`) | `Skill` tool invocation |
| **Agent** | `agents/<category>/<name>.md` | Markdown with YAML frontmatter (`name`, `description`, `model`) | `Task` tool with `subagent_type` |
| **Command** | `commands/<name>.md` | Markdown with YAML frontmatter (`name`, `description`, `argument-hint`) | `/clavain:<name>` slash command |
| **Hook** | `hooks/hooks.json` + scripts | JSON registration + bash scripts | Automatic on registered events |
| **MCP Server** | `.claude-plugin/plugin.json` `mcpServers` | JSON config | Automatic on plugin load |

### Interspect Routing Overrides

Interspect (companion plugin) monitors flux-drive agent dispatches and user corrections. When evidence reaches a threshold, it proposes permanent routing overrides stored in `.claude/routing-overrides.json`. See the interspect plugin's own AGENTS.md for full details on commands (`/interspect:propose`, `/interspect:revert`, `/interspect:status`), library functions, and canary monitoring.

### Factory Substrate

The factory substrate adds validation-first quality infrastructure to the sprint lifecycle. It uses CXDB (Turn DAG + Blob CAS) for append-only recording and a scenario bank with satisfaction scoring for quality gates.

**CXDB (Turn DAG)** — records sprint execution as an immutable trajectory:
- `clavain-cli cxdb-start/stop/status/setup` — service lifecycle
- `clavain-cli cxdb-sync <sprint-id>` — backfill turns from Intercore events
- `clavain-cli cxdb-fork <sprint-id> <turn-id>` — O(1) branched trajectory
- Auto-starts via SessionStart hook when binary is installed
- Type schemas at `config/cxdb-types.json` (7 turn types: phase, dispatch, artifact, scenario, satisfaction, evidence, policy_violation)

**Scenario Bank** — dev/holdout separation with YAML schema:
- `clavain-cli scenario-create <name> [--holdout]` — scaffold scenario
- `clavain-cli scenario-list [--holdout] [--dev]` — list with metadata
- `clavain-cli scenario-validate` — check all scenarios against v1 schema
- `clavain-cli scenario-run <pattern> [--sprint=<id>]` — execute scenarios
- Directory: `.clavain/scenarios/{dev,holdout,satisfaction}/`
- Schema: `config/scenario-schema.yaml`
- Dev scenarios are failure-derived; holdout scenarios are spec-derived. Agents never see holdout during build phases.

**Satisfaction Scoring** — closed-loop quality calibration:
- `clavain-cli scenario-score <run-id> [--summary]` — score scenario run
- `clavain-cli scenario-calibrate` — compute optimal threshold from history (needs 20+ sprints)
- Default threshold: 0.7 (configurable in `.clavain/budget.yml`)
- Gate: sprints cannot ship unless holdout satisfaction >= threshold
- Integrated into `enforce-gate` for the `shipping` phase

**Evidence Pipeline** — converts failures to regression tests:
- `clavain-cli evidence-to-scenario <finding-id>` — finding -> dev scenario (never holdout)
- `clavain-cli evidence-pack <bead-id>` — create evidence pack from sprint failure
- `clavain-cli evidence-list [bead-id]` — list evidence packs
- Flux-drive regressions auto-generate dev scenarios via `createFluxDriveDevScenario()`

**Agent Capability Policies** — holdout contamination prevention:
- `clavain-cli policy-check <agent> <action> [--path=<p>]` — evaluate against phase policy
- `clavain-cli policy-show` — display current policy
- Default policy: holdout denied during build phases, allowed during shipping (quality gates)
- Violations recorded as CXDB turns; contaminated satisfaction scores are invalidated
- Project override: `.clavain/policy.yml`
