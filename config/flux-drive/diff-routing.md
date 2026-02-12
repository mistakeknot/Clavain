# Diff-to-Agent Routing Configuration

This file maps file patterns and hunk keywords to flux-drive review agents. Used by the orchestrator when a diff input exceeds 1000 lines to soft-prioritize hunks per agent.

**How it works**: Each domain-specific agent receives priority file hunks in full + a compressed summary (filename + change stats) for other files. Cross-cutting agents always get the full diff. No information is lost.

---

## Cross-Cutting Agents (always full diff)

These agents need the complete diff regardless of size:

| Agent | Reason |
|-------|--------|
| fd-architecture | Module boundaries, coupling, and design patterns span all files |
| fd-quality | Naming, conventions, and style apply everywhere |

---

## Domain-Specific Agents

### fd-safety

**Priority file patterns:**
- `**/auth/**`, `**/authentication/**`, `**/authorization/**`
- `**/deploy/**`, `**/deployment/**`, `**/infra/**`, `**/terraform/**`
- `**/credential*`, `**/secret*`, `**/vault/**`
- `**/migration*`, `**/migrate*`
- `**/.env*`, `**/docker-compose*`, `**/Dockerfile*`
- `**/security/**`, `**/rbac/**`, `**/permissions/**`
- `**/middleware/auth*`, `**/middleware/session*`
- `**/ssl/**`, `**/tls/**`, `**/cert*`
- `**/*-policy*`, `**/iam/**`
- `**/ci/**`, `**/.github/workflows/**`, `**/.gitlab-ci*`

**Priority hunk keywords** (case-insensitive, match within diff hunk lines):
`password`, `secret`, `token`, `api_key`, `apikey`, `api-key`, `credential`, `private_key`, `encrypt`, `decrypt`, `hash`, `salt`, `bearer`, `oauth`, `jwt`, `session`, `cookie`, `csrf`, `cors`, `helmet`, `sanitize`, `escape`, `inject`, `trust`, `allow_origin`, `chmod`, `chown`, `sudo`, `root`, `admin`

### fd-correctness

**Priority file patterns:**
- `**/migration*`, `**/migrate*`, `**/schema*`
- `**/model*`, `**/models/**`, `**/entity/**`, `**/entities/**`
- `**/db/**`, `**/database/**`, `**/repository/**`, `**/repo/**`
- `**/queue/**`, `**/worker/**`, `**/job/**`, `**/consumer/**`
- `**/sync/**`, `**/lock*`, `**/mutex*`, `**/semaphore*`
- `**/transaction*`, `**/atomic*`
- `**/state/**`, `**/store/**`, `**/reducer*`
- `**/*_test.*`, `**/*_spec.*`, `**/test_*`, `**/spec_*`

**Priority hunk keywords** (case-insensitive):
`transaction`, `commit`, `rollback`, `deadlock`, `mutex`, `lock`, `unlock`, `semaphore`, `atomic`, `race`, `concurrent`, `goroutine`, `channel`, `select`, `async`, `await`, `promise`, `future`, `spawn`, `thread`, `sync.Once`, `sync.Map`, `WaitGroup`, `BEGIN`, `SAVEPOINT`, `CONSTRAINT`, `FOREIGN KEY`, `INDEX`, `ON DELETE`, `ON UPDATE`, `CASCADE`

### fd-performance

**Priority file patterns:**
- `**/render*`, `**/component*`, `**/view*`, `**/template*`
- `**/query*`, `**/queries/**`, `**/sql/**`
- `**/cache*`, `**/redis*`, `**/memcached*`
- `**/benchmark*`, `**/perf*`, `**/profile*`
- `**/index*`, `**/search*`
- `**/batch*`, `**/bulk*`, `**/stream*`
- `**/loop*`, `**/iterator*`
- `**/webpack*`, `**/vite*`, `**/bundle*`
- `**/image*`, `**/asset*`, `**/static/**`

**Priority hunk keywords** (case-insensitive):
`O(n`, `O(n^2`, `O(log`, `loop`, `for `, `while `, `forEach`, `map(`, `filter(`, `reduce(`, `SELECT`, `JOIN`, `WHERE`, `GROUP BY`, `ORDER BY`, `LIMIT`, `N+1`, `eager`, `lazy`, `prefetch`, `cache`, `memoize`, `useMemo`, `useCallback`, `debounce`, `throttle`, `batch`, `bulk`, `pool`, `connection`, `timeout`, `ttl`, `expir`

### fd-user-product

**Priority file patterns:**
- `**/cli/**`, `**/cmd/**`, `**/command*`
- `**/ui/**`, `**/tui/**`, `**/view*`, `**/component*`
- `**/template*`, `**/layout*`, `**/page*`
- `**/form*`, `**/input*`, `**/prompt*`
- `**/route*`, `**/router*`, `**/navigation*`
- `**/error*`, `**/message*`, `**/notification*`
- `**/help*`, `**/usage*`, `**/readme*`
- `**/onboard*`, `**/wizard*`, `**/setup*`
- `**/config*` (user-facing configuration)

**Priority hunk keywords** (case-insensitive):
`user`, `prompt`, `flow`, `step`, `wizard`, `onboard`, `error message`, `usage`, `help`, `flag`, `--`, `subcommand`, `menu`, `dialog`, `modal`, `toast`, `alert`, `confirm`, `cancel`, `submit`, `validate`, `placeholder`, `label`, `aria-`, `accessibility`, `a11y`, `i18n`, `locale`

### fd-game-design

**Priority file patterns:**
- `**/game/**`, `**/games/**`
- `**/simulation/**`, `**/sim/**`
- `**/tick/**`, `**/tick_*`, `**/*_tick.*`
- `**/storyteller/**`, `**/drama/**`, `**/narrative/**`
- `**/needs/**`, `**/mood/**`, `**/desire*`
- `**/ecs/**`, `**/entity/**`, `**/component/**`, `**/system/**`
- `**/balance/**`, `**/tuning/**`, `**/config/balance*`
- `**/ai/**`, `**/behavior/**`, `**/behaviour/**`, `**/utility_ai*`
- `**/procedural/**`, `**/procgen/**`, `**/worldgen/**`
- `**/combat/**`, `**/inventory/**`, `**/crafting/**`

**Priority hunk keywords** (case-insensitive):
`tick`, `tick_rate`, `delta_time`, `fixed_update`, `simulation`, `storyteller`, `drama`, `tension`, `pacing`, `cooldown`, `spawn_rate`, `difficulty`, `balance`, `tuning`, `weight`, `score`, `utility`, `need`, `mood`, `satisfaction`, `decay`, `threshold`, `feedback_loop`, `death_spiral`, `rubber_band`, `catch_up`, `emergent`, `procedural`, `seed`, `noise`, `perlin`, `wave_function`, `agent_ai`, `behavior_tree`, `state_machine`, `blackboard`, `steering`, `pathfind`, `navmesh`

---

## Overlap Resolution

A file matching priority patterns for multiple agents is marked as priority for **all** of them. This is expected — a migration file is relevant to both fd-safety (credential handling during migration) and fd-correctness (data integrity).

---

## 80% Overlap Threshold

If an agent's priority files cover >= 80% of total changed lines in the diff, skip slicing for that agent and send the full diff. The overhead of compressed summaries is not worth it when almost everything is priority.

---

## Extending This Configuration

**To add patterns for an existing agent:**
Add glob patterns to the agent's "Priority file patterns" list or keywords to the "Priority hunk keywords" list.

**To add a new domain-specific agent:**
Create a new `### agent-name` section under "Domain-Specific Agents" with:
1. Priority file patterns (glob syntax)
2. Priority hunk keywords (comma-separated, case-insensitive)

**To make an agent cross-cutting:**
Add it to the "Cross-Cutting Agents" table. It will always receive the full diff.

**Pattern syntax:**
- File patterns use glob syntax: `*` matches within a directory, `**` matches across directories
- Keywords are matched case-insensitively as substrings within diff hunk lines (the `+` and `-` lines)
- A file is priority if it matches ANY file pattern OR any hunk in the file contains ANY keyword
