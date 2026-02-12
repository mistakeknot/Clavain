# Domain-Aware Agent Generation for Flux-Drive

**Date:** 2026-02-12
**Status:** Brainstorm refined — ready for planning

## What We're Building

Make flux-drive adaptable to project domains by adding a **domain knowledge library** that feeds three channels:

1. **Dynamic injection** (default, automatic) — during Phase 1 triage, detect the project's domain, load matching profiles, and append domain-specific review checklists to each core agent's prompt
2. **`/flux-gen` command** (opt-in, power user) — generate 2-4 new domain-specific review agents in `.claude/agents/fd-*.md` with deep expertise baked into their system prompts
3. **Game design agent** — a new core plugin agent (`fd-game-design`) that reviews game design concerns: balance, pacing, player psychology, feedback loops, emergent behavior. Shipped with the plugin, not generated per-project.

### Motivating Example

Running flux-drive on **agent-fortress** (a Dwarf Fortress-style persistent simulation game with Go kernel + Python LLM layer) should:
- Auto-detect `game-simulation` domain
- Inject game-specific review criteria into core agents (fd-architecture gets "tick loop determinism", fd-correctness gets "simulation state consistency", etc.)
- Activate `fd-game-design` in triage (scores 2 because domain matches)
- Optionally (`/flux-gen`): generate `fd-simulation-kernel`, `fd-game-systems`, `fd-agent-narrative` agents

## Why This Approach

### Problem
Flux-drive's 6 core agents carry deep software engineering expertise but no domain-specific knowledge. They can check coupling and security but don't know about tick budget accounting, utility AI anti-patterns, or drama curve calibration.

### Why not just project agents?
Research found project-level fd-*.md agents are a "dead feature" — only 2 projects ever created them. Friction too high. Dynamic injection is automatic and zero-friction.

### Why a core game design agent?
Game design review (balance, pacing, player psychology, emergent behavior) is a fundamentally distinct discipline that doesn't map onto any of the 6 existing agents. fd-user-product is closest but thinks about UX flows, not utility curves and death spirals. A dedicated agent ensures game projects get proper design review without requiring `/flux-gen`.

### Why both channels?
Dynamic injection handles 90% of cases (domain-specific bullets for existing agents). `/flux-gen` serves the 10% where a project needs dedicated agents with full system prompts (e.g., a simulation kernel reviewer). The game design agent fills the gap between these — always available for game projects, no generation needed.

## Key Decisions

### 1. Architecture: First-Class Domain Profiles (Approach A)

```
config/flux-drive/domains/
├── index.yaml              # domain → detection signals mapping
├── game-simulation.md      # curated domain expertise
├── ml-pipeline.md
├── web-api.md
├── cli-tool.md
├── mobile-app.md
├── embedded-systems.md
├── library-sdk.md
├── data-pipeline.md
├── claude-code-plugin.md   # plugin manifests, hooks, skills, MCP
├── tui-app.md              # Bubble Tea, terminal state, keyboard input
└── desktop-tauri.md        # Tauri IPC, Rust-TS bridge, native APIs
```

11 curated domain profiles. Single source of truth: feed dynamic injection, `/flux-gen`, and triage scoring.

### 2. Detection: Auto-detect + Persist

- Phase 1 gains "Step 1.0: Domain Classification" before document profiling
- Reads: directory structure, file extensions, build files, CLAUDE.md/AGENTS.md, framework markers
- Matches against `index.yaml` signal patterns (multiple domains can match)
- Generates `.claude/flux-drive.yaml` on first run (caches classification + overrides)
- Subsequent runs read the YAML first, re-detect only if project docs changed (hash-based staleness)

### 3. Knowledge Source: Curated Profiles + LLM Fill

- Ship 11 curated domain profiles for common project types
- If no curated profile matches, LLM generates domain-specific review criteria from project docs
- LLM-generated criteria cached in `.claude/flux-drive.yaml` under `generated_criteria:`

### 4. Agent Naming: New Domain Agents alongside Core

`/flux-gen` creates agents named for the domain concern:
- `fd-simulation-kernel.md`, `fd-game-systems.md`, `fd-agent-narrative.md`

These run **alongside** core agents (including fd-game-design), not replacing them.

### 5. fd-game-design: New Core Plugin Agent

Added to the plugin's agent roster (7th core agent). Pre-filtered in triage like other domain agents — only activates when game-related signals are detected. Covers:
- Balance & tuning (utility curves, difficulty scaling, resource economy)
- Pacing & drama (storyteller systems, tension arcs, cooldowns)
- Player psychology (agency, feedback loops, death spiral prevention)
- Emergent behavior (system interactions, unintended consequences)
- Procedural content quality (generation variety, coherence, replay value)

---

## Deep Dive 1: Domain Profile Content & Structure

### Profile Format

Each profile is organized into two sections with distinct consumers:

```markdown
# {Domain Name}

## Detection Signals
[Used by Step 1.0 to match projects to domains]

## Injection Criteria
[Used by dynamic injection — concise, 3-5 items per agent, token-budgeted]
[Organized by core agent name]

## Agent Specifications
[Used by /flux-gen — full agent definitions with system prompts]
[Each spec becomes a .claude/agents/fd-{name}.md file]
```

### Why Two Sections?

**Injection criteria** must be concise (token budget ~200 tokens per agent, ~1400 total across 7 agents). They contain the "you'd never think to check this" items — domain-specific gotchas that generic agents miss.

**Agent specifications** are unlimited. They contain complete review checklists, domain context, and the full system prompt for a standalone agent. Only read when `/flux-gen` is invoked.

### Example: game-simulation.md

```markdown
# Game Simulation

## Detection Signals

directories: kernel/, tick/, simulation/, world/, ecs/, storyteller/
files: **/tick*.go, **/game_loop*, **/entity*.rs, **/needs*.py
frameworks: bevy, ggez, ebitengine, godot, unity, unreal
keywords: tick loop, game loop, simulation, procedural generation,
          ECS, entity component, utility AI, storyteller, drama

## Injection Criteria

### fd-architecture
- Tick loop must be deterministic: no map iteration, no goroutines, no I/O in hot path
- LLM calls at edges only — simulation produces valid state every tick without LLM
- All simulation state in serializable structs (no hidden globals, no closures over mutable state)
- RNG state serialized with save files (seed + call count or full PRNG state)
- Event queue uses stable ordering (priority queue, not channel select)

### fd-correctness
- No floating-point in critical gameplay math (use integers/fixed-point for health, currency, inventory)
- Same seed + same inputs must produce identical state after N ticks (determinism property test)
- Entity deletion must clean up ALL references (event queue, relationship graph, spatial index)
- Multi-field state updates use staging pattern (build new state, swap atomically)
- Event handlers can schedule future events but never process them in the same tick

### fd-safety
- Player commands validated against fortress ownership (can't command other player's agents)
- Trade/transfer uses two-phase commit (deduct from sender + credit receiver atomically)
- LLM prompts never include player-controlled data in system position
- LLM output sanitized before display (strip links, profanity filter, length cap)

### fd-quality
- Table-driven tests for utility functions (need decay, mood calculation, action scoring)
- Property-based tests for invariants (no negative health, inventory weight ≤ capacity)
- Replay tests in CI: record input stream + seed, verify byte-identical state at tick N
- Benchmark critical paths (BenchmarkTickLoop, BenchmarkPathfinding)

### fd-performance
- Tick time < 50% of budget under normal load (measure with 100 agents, max events)
- Object pooling for frequent allocations (events, pathfinding nodes, temp buffers)
- Preallocate slices with capacity, reuse instead of append-infinitely
- GC pauses < 1ms (set GOMEMLIMIT, monitor GC metrics, avoid allocations in tick loop)
- LLM requests batched (10 event summaries in one prompt, not 10 separate calls)

### fd-user-product
- Player feels meaningful but not required (agent acts by default, player enriches)
- Dilemma queue shows consequences of past choices (values learning feedback)
- Journal narrative reflects agent personality and mood (not generic template)

### fd-game-design
- Utility AI: needs decay curves produce interesting decisions (not always eat→sleep→eat)
- Storyteller: drama budget with cooldowns prevents event spam and death spirals
- Mood system: negative feedback loops have recovery paths (sleeping restores multiple needs)
- Cross-fortress economy: resource transfers are atomic, reputation prevents griefing
- Death spiral prevention: difficulty reduces after catastrophic loss, comeback mechanics exist

## Agent Specifications

### fd-simulation-kernel
Purpose: Reviews the deterministic simulation kernel for correctness and performance
Languages: Go (primary), Rust (if applicable)
Focus areas:
- Tick loop determinism (no RNG scatter, no map iteration, no concurrent mutation)
- Fixed timestep with accumulator pattern (simulation decoupled from rendering)
- State serialization completeness (RNG state, event queue, AI internal state)
- Schema versioning with forward migration (old saves load in new code)
- Replay system (record inputs + seed, reproduce byte-identical state)
- GC pressure minimization (sync.Pool, avoid defer in hot paths, concrete types)
- Floating-point discipline (integers for gameplay math, IEEE 754 if floats needed)
Checklist: [200+ items from research — see full profile]

### fd-game-systems
Purpose: Reviews game design systems for balance, emergence, and player experience
Languages: Any (design-level review)
Focus areas:
- Utility AI tuning: need curves, action scoring, behavior emergence
- Storyteller balance: drama curve, event pacing, arc tracking
- Death spiral prevention: negative feedback loops, recovery mechanics
- Cross-fortress economy: trade safety, reputation, agent portability
- Mood/needs interaction: positive loops bounded, negative loops with recovery
Checklist: [150+ items from research]

### fd-agent-narrative
Purpose: Reviews the LLM-powered narrative layer for quality, cost, and safety
Languages: Python (primary)
Focus areas:
- Prompt management (Jinja2 templates, versioning, unit tests for rendering)
- Cost efficiency (batching, caching, circuit breaker on API failures)
- Memory/salience decay (bounded growth, relevant recall)
- Journal coherence (personality colors narrative, mood affects tone)
- Values-learning feedback loops (player choices shape agent behavior)
- Prompt injection containment (LLM is narrator not authority, output sanitized)
Checklist: [100+ items from research]
```

### Token Budget for Injection

Each agent receives its injection criteria as an additional section:

```
## Domain-Specific Review Criteria (game-simulation)
- [3-5 bullets from the profile]
```

At ~40 tokens per bullet, 5 bullets per agent, 7 agents = **~1,400 tokens total overhead**. This is well within budget (typical agent prompt is 2,000-4,000 tokens).

For multi-domain projects (game-simulation + web-api), cap at 5 bullets per agent total (mix from both profiles, prioritize the primary domain).

---

## Deep Dive 2: Detection & index.yaml

### Detection Algorithm

```
Step 1.0: Domain Classification

1. Check .claude/flux-drive.yaml
   - Exists AND project_hash matches current → load cached, skip detection
   - Exists BUT stale → re-detect, preserve user overrides
   - Missing → full detection

2. Gather signals (read-only, fast)
   - List top-level directories (ls -d */)
   - Sample file extensions (find . -type f | sed 's/.*\.//' | sort | uniq -c | sort -rn | head 20)
   - Read CLAUDE.md + AGENTS.md (already read in Phase 1)
   - Check for framework markers (go.mod, package.json, Cargo.toml, pyproject.toml, etc.)
   - Read first 5 lines of key build files for framework imports

3. Score each domain in index.yaml
   - For each signal type (directories, files, frameworks, keywords):
     count matches / total signals in that type
   - Weighted average: directories 0.3, files 0.2, frameworks 0.3, keywords 0.2
   - Domain matches if weighted score ≥ min_confidence

4. If no domain matches AND project has CLAUDE.md/AGENTS.md:
   - LLM generates domain classification from project docs
   - Produces: domain name, 3-5 injection criteria per agent
   - Cached as generated_criteria in flux-drive.yaml

5. Write .claude/flux-drive.yaml with results
```

### index.yaml Full Structure

```yaml
# Domain detection signals for flux-drive
# Each domain has signals grouped by type and a confidence threshold
# Multiple domains can match the same project (game + web-api for multiplayer)

domains:
  game-simulation:
    profile: game-simulation.md
    signals:
      directories:
        - kernel/
        - tick/
        - simulation/
        - world/
        - ecs/
        - storyteller/
        - agent/  # when combined with game signals
      files:
        - "**/tick*.go"
        - "**/game_loop*"
        - "**/entity*.rs"
        - "**/needs*.py"
        - "**/mood*.py"
        - "**/storyteller*"
      frameworks:
        - bevy
        - ggez
        - ebitengine
        - godot
        - unity
        - unreal
        - amethyst
        - macroquad
      keywords:
        - tick loop
        - game loop
        - simulation
        - procedural generation
        - ECS
        - entity component
        - utility AI
        - storyteller
        - drama
        - fortress
        - dwarf
    min_confidence: 0.4
    # Game projects often have unique structures, so lower threshold

  ml-pipeline:
    profile: ml-pipeline.md
    signals:
      directories:
        - model/
        - models/
        - training/
        - data/
        - pipeline/
        - notebooks/
        - experiments/
        - features/
      files:
        - "*.ipynb"
        - "**/train*.py"
        - "**/model*.py"
        - "**/dataset*.py"
        - "**/pipeline*.py"
        - "*.onnx"
        - "*.safetensors"
      frameworks:
        - pytorch
        - tensorflow
        - transformers
        - langchain
        - scikit-learn
        - mlflow
        - wandb
        - huggingface
      keywords:
        - training
        - inference
        - model
        - dataset
        - embedding
        - fine-tune
        - epoch
        - gradient
        - loss function
    min_confidence: 0.5

  web-api:
    profile: web-api.md
    signals:
      directories:
        - routes/
        - controllers/
        - handlers/
        - middleware/
        - api/
        - endpoints/
        - views/
      files:
        - "**/route*.ts"
        - "**/handler*.go"
        - "**/controller*.py"
        - "**/views*.py"
        - "**/api*.ts"
        - "openapi.yaml"
        - "swagger.json"
      frameworks:
        - express
        - fastapi
        - gin
        - rails
        - django
        - next.js
        - flask
        - spring
        - nestjs
        - hono
      keywords:
        - endpoint
        - REST
        - GraphQL
        - middleware
        - authentication
        - API
        - request
        - response
        - router
    min_confidence: 0.5

  cli-tool:
    profile: cli-tool.md
    signals:
      directories:
        - cmd/
        - commands/
        - cli/
      files:
        - "**/main.go"  # with cobra/cli imports
        - "**/cli*.py"
        - "**/command*.ts"
      frameworks:
        - cobra
        - clap
        - click
        - typer
        - commander
        - yargs
        - oclif
      keywords:
        - command-line
        - CLI
        - flag
        - subcommand
        - argument
        - terminal
    min_confidence: 0.5

  mobile-app:
    profile: mobile-app.md
    signals:
      directories:
        - ios/
        - android/
        - lib/  # Flutter
        - app/  # React Native
        - screens/
        - components/
      files:
        - "*.swift"
        - "*.kt"
        - "*.dart"
        - "AndroidManifest.xml"
        - "Info.plist"
        - "pubspec.yaml"
      frameworks:
        - swiftui
        - jetpack compose
        - flutter
        - react native
        - expo
        - kotlin multiplatform
      keywords:
        - mobile
        - iOS
        - Android
        - screen
        - navigation
        - gesture
        - notification
    min_confidence: 0.5

  embedded-systems:
    profile: embedded-systems.md
    signals:
      directories:
        - drivers/
        - hal/
        - bsp/
        - firmware/
        - hw/
      files:
        - "*.c"
        - "*.h"
        - "Makefile"
        - "*.ld"  # linker scripts
        - "CMakeLists.txt"
      frameworks:
        - zephyr
        - freertos
        - embassy
        - arduino
        - stm32
        - esp-idf
      keywords:
        - interrupt
        - register
        - GPIO
        - DMA
        - UART
        - SPI
        - firmware
        - bare-metal
    min_confidence: 0.5

  library-sdk:
    profile: library-sdk.md
    signals:
      directories:
        - pkg/
        - src/lib/
        - examples/
        - docs/
        - benchmarks/
      files:
        - "*.d.ts"  # type definitions
        - "**/lib.rs"
        - "**/mod.rs"
      frameworks: []  # libraries don't depend on frameworks
      keywords:
        - library
        - SDK
        - API
        - public API
        - semver
        - breaking change
        - backwards compatible
    min_confidence: 0.6
    # Higher threshold — many projects have docs/ and examples/

  data-pipeline:
    profile: data-pipeline.md
    signals:
      directories:
        - dags/
        - pipelines/
        - etl/
        - transforms/
        - schemas/
        - warehouse/
      files:
        - "**/dag*.py"
        - "**/pipeline*.py"
        - "*.sql"
        - "dbt_project.yml"
      frameworks:
        - airflow
        - dagster
        - prefect
        - dbt
        - spark
        - flink
        - kafka
        - beam
      keywords:
        - ETL
        - pipeline
        - DAG
        - transform
        - warehouse
        - schema
        - batch
        - stream
    min_confidence: 0.5

  claude-code-plugin:
    profile: claude-code-plugin.md
    signals:
      directories:
        - .claude-plugin/
        - skills/
        - agents/
        - commands/
        - hooks/
      files:
        - "plugin.json"
        - "**/SKILL.md"
        - "hooks/*.sh"
        - "commands/*.md"
        - "agents/**/*.md"
      frameworks: []  # no traditional frameworks
      keywords:
        - plugin
        - skill
        - subagent
        - hook
        - PreToolUse
        - PostToolUse
        - SessionStart
        - MCP server
        - slash command
    min_confidence: 0.5

  tui-app:
    profile: tui-app.md
    signals:
      directories:
        - tui/
        - ui/
        - views/
        - components/
      files:
        - "**/model.go"  # Bubble Tea pattern
        - "**/view.go"
        - "**/update.go"
        - "**/styles.go"
      frameworks:
        - bubbletea
        - bubbles
        - lipgloss
        - tview
        - ratatui
        - crossterm
        - tcell
        - ink
        - blessed
      keywords:
        - terminal
        - TUI
        - Bubble Tea
        - tea.Model
        - lipgloss
        - ratatui
        - terminal UI
    min_confidence: 0.5

  desktop-tauri:
    profile: desktop-tauri.md
    signals:
      directories:
        - src-tauri/
        - src/
        - desktop/
      files:
        - "tauri.conf.json"
        - "Cargo.toml"
        - "src-tauri/src/main.rs"
        - "src-tauri/src/lib.rs"
      frameworks:
        - tauri
        - electron
        - wails
        - neutralinojs
      keywords:
        - desktop app
        - Tauri
        - IPC
        - invoke
        - native
        - window
        - tray
    min_confidence: 0.5
```

### Edge Cases

**Multi-domain projects**: A multiplayer game with REST API matches both `game-simulation` and `web-api`. Both profiles are loaded. Injection criteria are merged (cap at 5 per agent, primary domain gets priority). `/flux-gen` uses the primary domain (highest confidence score) for agent generation.

**No match**: If no domain reaches `min_confidence`, fall back to LLM generation. The LLM reads the project's CLAUDE.md/AGENTS.md and generates:
- A domain name (freeform, not from index.yaml)
- 3-5 injection criteria per relevant agent
- Optionally: 1-2 `/flux-gen` agent specs

These are cached in `flux-drive.yaml` under `generated_criteria:` and `generated_agents:`.

**False positives**: A project with a `model/` directory isn't necessarily ML. The weighted scoring and `min_confidence` threshold prevent most false positives. If detection is wrong, users edit `flux-drive.yaml` to override.

---

## Deep Dive 3: Dynamic Injection Mechanics

### Injection Point

Domain criteria are injected into agent prompts during Phase 2 (Launch), alongside the existing knowledge injection. The prompt template gains a new section:

```markdown
## Review Context

### Document Summary
{from Phase 1 document profile}

### Domain-Specific Review Criteria ({domain name})
{3-5 bullets from matched domain profile, filtered to this agent}

### Prior Knowledge
{0-5 entries from qmd semantic search — existing mechanism}

### Focus Areas
{section assignments from Phase 1 triage}

## Document to Review
{trimmed document content}
```

### Token Budget

| Component | Tokens | Notes |
|-----------|--------|-------|
| Agent system prompt | 2,000-4,000 | Existing, unchanged |
| Document summary | 200-400 | Existing |
| Domain criteria | 150-250 | NEW: 3-5 bullets × ~40 tokens |
| Prior knowledge | 300-500 | Existing: 0-5 entries |
| Focus areas | 100-200 | Existing |
| Document content | 4,000-20,000 | Existing, trimmed to fit |
| **Total overhead** | **~200 tokens** | Negligible |

Domain injection adds ~200 tokens per agent. For 7 agents, that's ~1,400 tokens total. Well within budget.

### Multi-Domain Injection

When a project matches 2+ domains, criteria are merged:
1. Primary domain (highest confidence): 3-5 items per agent
2. Secondary domain(s): 1-2 items per agent
3. Cap: 5 items per agent total
4. Dedup: if both profiles have similar criteria, keep the more specific one

### Prompt Construction

The injection is **additive** — it adds a section to the agent's prompt, doesn't modify the agent's system prompt. This means:
- Core agents remain unchanged (no need to edit fd-architecture.md)
- Domain criteria are clearly labeled as domain-specific (agents can distinguish)
- Easy to disable per-project (remove domain from flux-drive.yaml)

### Criteria Selection

Not all criteria from a profile apply to all documents. During triage, flux-drive selects criteria based on:
1. **Agent relevance**: Only inject fd-architecture criteria into fd-architecture, etc.
2. **Section coverage**: If the document has no security sections, skip fd-safety domain criteria
3. **Diff relevance**: For diff inputs, only inject criteria that match changed file patterns

---

## Deep Dive 4: /flux-gen Agent Generation

### Command Definition

```yaml
---
name: flux-gen
description: Generate domain-specific review agents for the current project based on detected domain profiles. Creates .claude/agents/fd-*.md files that run alongside core agents during flux-drive reviews.
argument-hint: "[domain-override]"
---
```

### Generation Flow

```
/flux-gen [domain-override]

1. Load or create .claude/flux-drive.yaml
   - If exists and fresh: use cached domains
   - If missing: run full detection (same as Phase 1 Step 1.0)
   - If domain-override provided: use that domain instead

2. Load domain profile(s) from config/flux-drive/domains/
   - Read the "Agent Specifications" section
   - If no curated profile matches: LLM generates agent specs from project analysis

3. For each agent spec in the profile:
   a. Read project docs (CLAUDE.md, AGENTS.md) for project-specific context
   b. LLM generates full agent .md file combining:
      - Domain spec (from profile): purpose, focus areas, base checklist
      - Project context: actual languages, frameworks, conventions, architecture
      - Standard structure: frontmatter, First Step, Review Approach, Output Format
   c. Write to .claude/agents/fd-{name}.md

4. Write staleness hash: sha256sum of CLAUDE.md + AGENTS.md + domain profile
   → .claude/agents/.fd-agents-hash

5. Report:
   GENERATED: fd-simulation-kernel.md, fd-game-systems.md, fd-agent-narrative.md
   DOMAIN: game-simulation
   HASH: abc123

   These agents will be included in future flux-drive runs.
   Re-run /flux-gen after major project changes to refresh.
```

### Generated Agent Template

```markdown
---
name: fd-{domain-concern}
description: "Project-specific {domain concern} reviewer for {project name}. {1-2 sentence purpose}."
model: sonnet
---

You are a domain-specific reviewer for {project name}, focused on {domain concern}.

## First Step (MANDATORY)

Check for project documentation in this order:
1. `CLAUDE.md` in the project root
2. `AGENTS.md` in the project root

If docs exist, ground all recommendations in the project's documented conventions.
If docs do not exist, apply domain best practices and note assumptions.

## Domain Context

{Brief description of the project's domain and why this review dimension matters}

## Review Approach

### {Subdomain 1}
- [ ] {Concrete, checkable item grounded in THIS project's architecture}
- [ ] {Another item}
...

### {Subdomain 2}
- [ ] {Item}
...

## Focus Rules

- Prioritize {high-impact items for this domain}
- Prefer {actionable, specific guidance} over {generic advice}
- Separate must-fix (P0-P1) from improvement suggestions (P2-P3)

## What NOT to Flag

- {Anti-pattern 1 — why it's excluded in this domain}
- {Anti-pattern 2}

## Output Format

Use the standard flux-drive Findings Index format.
```

### Staleness & Refresh

- Hash includes: CLAUDE.md + AGENTS.md + domain profile content
- If project docs change → agents are stale
- If domain profile is updated (plugin update) → agents are stale
- Flux-drive warns during triage if project agents are stale
- User can re-run `/flux-gen` to refresh, or delete agents to fall back to injection-only

### Relationship to Core Agents

Generated agents run **alongside** core agents, not replacing them:
- Core fd-architecture reviews module boundaries, coupling, patterns (universal)
- Generated fd-simulation-kernel reviews tick loop, determinism, serialization (domain-specific)
- Both contribute findings; synthesis deduplicates and notes convergence

Triage scoring gives generated agents a +1 bonus (same as existing project agent bonus).

---

## fd-game-design: New Core Agent

### Why a Core Agent (Not Just a Profile)

Game design review requires a fundamentally different lens than software engineering:
- fd-user-product asks "is the UX intuitive?" — fd-game-design asks "is this fun?"
- fd-performance asks "is it fast?" — fd-game-design asks "does the pacing feel right?"
- fd-correctness asks "are there bugs?" — fd-game-design asks "do the systems produce interesting emergent behavior?"

This expertise is reusable across ALL game projects, not just one. It belongs in the plugin.

### Agent Definition Sketch

```markdown
---
name: fd-game-design
description: "Flux-drive Game Design reviewer — evaluates balance, pacing, player
  psychology, feedback loops, emergent behavior, and procedural content quality.
  Reads project docs when available for codebase-aware analysis.
  Examples:
  <example>Context: User designed a needs-based AI system for game agents.
  user: \"Review the utility AI system for the agent behavior\"
  assistant: \"I'll use the fd-game-design agent to evaluate the needs curves,
  action scoring, and emergent behavior patterns.\"
  <commentary>Utility AI tuning involves game design balance, not just code
  correctness.</commentary></example>
  <example>Context: User wrote a storyteller/drama management system.
  user: \"Check if the storyteller pacing feels right\"
  assistant: \"I'll use the fd-game-design agent to review the drama curve,
  event cooldowns, and death spiral prevention.\"
  <commentary>Drama pacing is a game design concern about player
  experience.</commentary></example>"
model: sonnet
---

You are a Flux-drive Game Design Reviewer. You evaluate game systems for
balance, pacing, player psychology, and emergent behavior quality.

## First Step (MANDATORY)

Check for project documentation in this order:
1. `CLAUDE.md` in the project root
2. `AGENTS.md` in the project root
3. Game design documents (GDD, PRD, design docs)

If docs exist, operate in codebase-aware mode.
If docs do not exist, apply established game design principles.

## Review Approach

### 1. Balance & Tuning
- Are resource costs/rewards calibrated for interesting tradeoffs?
- Do difficulty curves match intended player experience?
- Are numerical systems (damage, health, economy) balanced against each other?
- Can players find dominant strategies that trivialize the game?
- Are there multiple viable playstyles/paths?

### 2. Pacing & Drama
- Does the experience have rhythm (tension/release cycles)?
- Are cooldowns/timers preventing event spam?
- Does difficulty escalate appropriately with game progression?
- Are there recovery periods after high-tension moments?
- Does the storyteller/event system create narrative arcs?

### 3. Player Psychology & Agency
- Does the player feel their choices matter?
- Are consequences of decisions visible and understandable?
- Is the feedback loop tight enough (action → visible result)?
- Are failure states recoverable and educational (not punitive)?
- Does the game respect the player's time and attention?

### 4. Feedback Loops & Death Spirals
- Are positive feedback loops bounded (can't snowball infinitely)?
- Do negative feedback loops have recovery mechanisms?
- Is there rubber-banding or catch-up mechanics for losing players?
- Can the game reach unrecoverable states? If so, is that intentional?
- Are death spirals detectable and preventable?

### 5. Emergent Behavior & Systems Interaction
- Do independent systems interact to produce unexpected outcomes?
- Are emergent behaviors desirable or degenerate?
- Is the possibility space rich enough for player creativity?
- Are edge cases in system interactions handled gracefully?
- Do AI agents produce believable, varied behavior?

### 6. Procedural Content Quality
- Does generated content feel coherent and intentional?
- Is there sufficient variety to prevent repetition fatigue?
- Are procedural elements constrained enough to be meaningful?
- Does the generation algorithm respect game balance?
- Can players distinguish procedural from authored content? (Should they?)

## Focus Rules

- Prioritize "is this fun?" over "is this correct?"
- Flag systems that produce degenerate player behavior
- Identify missing feedback (where players can't tell what's happening)
- Note balance concerns even if code is technically correct
- Suggest playtesting strategies for uncertain balance questions

## What NOT to Flag

- Code style, naming, or engineering quality (fd-quality handles this)
- Performance bottlenecks (fd-performance handles this)
- Security vulnerabilities (fd-safety handles this)
- Generic UX patterns (fd-user-product handles this)
```

### Triage Integration

fd-game-design gets pre-filter rules similar to other domain agents:
- **Game filter**: Skip fd-game-design unless document/project mentions game, simulation, AI behavior, storyteller, balance, or procedural generation
- Always passes filter when `game-simulation` domain is detected

---

## .claude/flux-drive.yaml Full Spec

```yaml
# flux-drive domain classification
# Auto-generated on first flux-drive run. Edit to override.
# Delete to force re-detection.

# Metadata
detected_at: "2026-02-12"
project_hash: "abc123def456"  # sha256(CLAUDE.md + AGENTS.md + go.mod/package.json/etc)

# Detected domains (from index.yaml matching)
domains:
  - name: game-simulation
    confidence: 0.85
    source: curated        # curated | generated
  - name: web-api
    confidence: 0.45
    source: curated

# Primary domain (highest confidence, used for /flux-gen)
primary_domain: game-simulation

# Detected tech stack
languages: [go, python]
frameworks: []
build_files: [go.mod, pyproject.toml]

# LLM-generated criteria (when no curated profile matched)
# Format: agent_name → list of criteria strings
generated_criteria: {}

# LLM-generated agent specs (for /flux-gen when no curated profile)
generated_agents: {}

# ── User Overrides (edit below this line) ──

# Force additional domains
# additional_domains:
#   - multiplayer-networking

# Skip specific agents during triage
# skip_agents:
#   - fd-user-product

# Add custom injection criteria per agent
# extra_criteria:
#   fd-architecture:
#     - "Verify ECS queries are batched for cache locality"
#   fd-correctness:
#     - "Check that WebSocket messages are processed in order"

# Override detection (skip auto-detect entirely)
# override_domains:
#   - game-simulation
#   - web-api
```

---

## Deep Dive 5: Orchestrator Overhaul

The current orchestrator has three limitations that domain awareness exposes:

1. **Coarse scoring (0/1/2)** — doesn't capture domain relevance gradations
2. **Hard 8-agent cap** — arbitrary ceiling that prevents full domain coverage
3. **Basic expansion logic** — Stage 2 decision ignores domain context

### 5.1 Enhanced Triage Scoring

**Current**: 3-point scale (0/1/2) + category bonus (+1).

**Proposed**: 5-point relevance scale + domain multiplier.

```
Score Components:
  base_score:     0-3 (irrelevant / tangential / adjacent / core domain)
  domain_boost:   0-2 (domain profile match amplifies relevant agents)
  project_bonus:  0-1 (project has CLAUDE.md/AGENTS.md)
  domain_agent:   0-1 (for domain-specific agents like fd-game-design)

  final_score = base_score + domain_boost + project_bonus + domain_agent
  max possible = 3 + 2 + 1 + 1 = 7
```

**Domain boost logic**: When a domain profile is active:
- Agents with injection criteria for this domain get +1
- Agents whose injection criteria contain ≥3 high-priority items get +2
- Agents with no injection criteria for this domain get +0

Example for agent-fortress (game-simulation domain):

| Agent | Base | Domain Boost | Project | Total | Stage |
|-------|------|-------------|---------|-------|-------|
| fd-game-design | 3 | +2 (core) | +1 | 6 | 1 |
| fd-architecture | 2 | +1 (5 items) | +1 | 4 | 1 |
| fd-correctness | 2 | +2 (5 items, high-priority) | +1 | 5 | 1 |
| fd-performance | 2 | +1 (5 items) | +1 | 4 | 1 |
| fd-quality | 2 | +1 (4 items) | +1 | 4 | 2 |
| fd-safety | 1 | +1 (4 items) | +1 | 3 | 2 |
| fd-user-product | 1 | +1 (3 items) | +1 | 3 | 2 |
| fd-simulation-kernel* | 3 | +2 (generated) | +1 | 6 | 1 |

*If generated via /flux-gen

### 5.2 Dynamic Slot Allocation

**Current**: Hard cap at 8 agents.

**Problem**: With 7 core agents + fd-game-design + 2-3 generated agents + Oracle, we could want 11+ agents. The hard cap forces good agents to be excluded.

**Proposed**: Adaptive ceiling based on review scope and domain density.

```
Slot Calculation:

base_slots = 4                      # minimum for any review
scope_slots:
  - single file:        +0
  - small diff (<500 lines): +1
  - large diff (500+):  +2
  - directory/repo:     +3
domain_slots:
  - 0 domains matched:  +0
  - 1 domain matched:   +1
  - 2+ domains matched: +2
generated_slots:
  - has /flux-gen agents: +2

total_ceiling = base_slots + scope_slots + domain_slots + generated_slots
hard_maximum = 12                   # absolute cap for resource sanity
```

**Examples**:
- Single-file review, no domain → 4 slots (lean review)
- Repo review, game-simulation → 4+3+1 = 8 slots (standard)
- Repo review, game-simulation + web-api, with /flux-gen → 4+3+2+2 = 11 slots (full coverage)
- Small diff, no domain → 4+1 = 5 slots (quick check)

**Stage allocation** with more slots:
- **Stage 1**: Top 40% of slots (ceiling × 0.4, rounded up, min 2, max 5)
- **Stage 2**: Remaining slots
- **Expansion pool**: Agents that scored above threshold but didn't get a slot — these are candidates for expansion

### 5.3 Domain-Aware Staged Expansion

**Current**: Binary expansion decision (launch all Stage 2 / stop / pick specific).

**Proposed**: Domain-guided expansion that considers what Stage 1 found and what Stage 2 agents can add.

```
Expansion Algorithm:

After Stage 1 completes:

1. Classify findings by domain:
   findings_by_domain = {
     "architecture": [P1, P2],
     "game-design": [P0],
     "correctness": []
   }

2. Score expansion candidates:
   For each Stage 2 agent:
     expansion_score = 0
     if any P0 in adjacent domain: expansion_score += 3
     if any P1 in adjacent domain: expansion_score += 2
     if Stage 1 agents disagree in this domain: expansion_score += 2
     if domain profile says "always expand for this domain": expansion_score += 1
     if agent has domain injection criteria: expansion_score += 1

3. Decision:
   if max(expansion_scores) >= 3: RECOMMEND expansion (specific agents)
   elif max(expansion_scores) >= 2: OFFER expansion (user choice)
   else: RECOMMEND stop (Stage 1 sufficient)

4. Present to user with reasoning:
   "Stage 1 found a P0 in game design (death spiral in storyteller).
    fd-correctness has domain criteria for simulation state consistency
    and could validate whether this is a code bug or design issue.
    Launch fd-correctness + fd-quality for Stage 2?"
```

**Domain adjacency map** (which domains are related):

```yaml
adjacency:
  fd-architecture: [fd-performance, fd-quality]
  fd-correctness: [fd-safety, fd-performance]
  fd-safety: [fd-correctness, fd-architecture]
  fd-quality: [fd-architecture, fd-user-product]
  fd-user-product: [fd-quality, fd-game-design]
  fd-performance: [fd-architecture, fd-correctness]
  fd-game-design: [fd-user-product, fd-correctness, fd-performance]
```

A P0 in fd-game-design triggers expansion of adjacent agents (fd-user-product, fd-correctness, fd-performance) because game design issues often have correctness and performance implications.

### 5.4 Orchestrator Rewrite Summary

| Aspect | Current | Proposed |
|--------|---------|----------|
| Scoring | 0/1/2 + bonus | 0-7 with domain boost |
| Slot cap | Hard 8 | Adaptive 4-12 |
| Stage 1 size | Top 2-3 | Top 40% of slots (2-5) |
| Expansion trigger | Finding severity only | Severity + domain adjacency + disagreement |
| Expansion granularity | All / none / pick | Recommended specific agents with reasoning |
| Domain awareness | None | Domain boost in scoring, domain-guided expansion, adjacency map |

---

## Deep Dive 6: Token Efficiency

Running 12 agents means 12 parallel API calls, each with its own prompt. Token costs scale linearly with agent count. Here's the current budget and optimization opportunities.

### Current Token Budget per Agent

| Component | Tokens | Repeated? | Notes |
|-----------|--------|-----------|-------|
| Agent system prompt | 2,000-4,000 | No (unique per agent) | Loaded via `subagent_type` for plugin agents |
| Output format override | ~400 | **Yes (12×)** | Identical boilerplate in every prompt |
| Knowledge context | ~500 (5 entries × ~100) | Partially (different entries per agent) | Retrieved via qmd search |
| Domain injection criteria | ~200 (5 bullets × ~40) | **Partially (same profile, different bullets)** | NEW |
| Project context | ~100 | **Yes (12×)** | Project root, document path, divergence note |
| Document content | 4,000-20,000 | **Yes (12×)** | The big one |
| Focus area / section map | ~200 | No (different per agent) | Pyramid scan assignments |
| **Total per agent** | **~7,400-25,400** | | |
| **Total for 12 agents** | **~89,000-305,000** | | |

### Where the Tokens Go

```
12-agent review of a 2,000-line plan:

Document content:     12 × 12,000 = 144,000 tokens (47%)
Agent system prompts: 12 ×  3,000 =  36,000 tokens (12%)
Output format:        12 ×    400 =   4,800 tokens  (2%)
Knowledge context:    12 ×    500 =   6,000 tokens  (2%)
Domain criteria:      12 ×    200 =   2,400 tokens  (1%)
Project context:      12 ×    100 =   1,200 tokens  (0%)
Focus areas:          12 ×    200 =   2,400 tokens  (1%)
Agent output tokens:  12 ×  2,000 =  24,000 tokens  (8%)
─────────────────────────────────────────────────────────
Orchestrator (Phase 1+3):           ~80,000 tokens (26%)
─────────────────────────────────────────────────────────
TOTAL                              ~301,000 tokens
```

**47% of tokens are the document repeated 12 times.** This is the elephant in the room.

### Optimization Opportunities

#### O1: Document Slicing for All Input Types (HIGH IMPACT)

**Current**: Diff slicing exists for diffs ≥1000 lines. File/directory inputs are sent in full to every agent.

**Proposed**: Extend the Pyramid Scan (Step 1.2c) to produce per-agent document slices:
- Each agent gets: its focus sections in full + other sections as 1-2 line summaries
- Already partially implemented (section mapping exists) but not used for trimming

**Impact**: For a 2,000-line plan with 6 sections, an agent focused on 2 sections gets ~800 lines + ~50 lines of summaries instead of 2,000 lines. **~60% reduction in document tokens per agent.**

**Risk**: Agents might miss cross-section issues. Mitigation: cross-cutting agents (fd-architecture, fd-quality) still get full document.

**Token savings**: 144,000 → ~72,000 for domain agents, ~36,000 for cross-cutting = **~108,000 tokens** (~36% total reduction)

#### O2: Progressive Document Depth (MEDIUM IMPACT)

**Current**: Every agent gets the full document at the same depth.

**Proposed**: Three depth levels based on agent priority:
- **Stage 1 agents** (top 3-5): Full document
- **Stage 2 agents**: Focus sections full + summaries for rest
- **Expansion pool agents**: Summaries only, with ability to request full sections

**Impact**: Stage 2 agents use ~50% fewer document tokens. Expansion agents use ~80% fewer.

**Risk**: Late-stage agents miss nuance. Mitigation: they can request full sections via a "Request full content: Section X" mechanism in their findings.

#### O3: Shared Context via Reference (MEDIUM IMPACT, PLATFORM-DEPENDENT)

**Current**: Each agent prompt includes the document inline.

**Proposed**: If the platform supports it, write the document to a temp file and reference it:
```
Read the document at: {OUTPUT_DIR}/input-document.md
```

**Impact**: Document tokens sent once (by Read tool), not 12 times in prompts.

**Risk**: Depends on agent having Read tool access. Plugin agents do have Read access. This works.

**Token savings**: 144,000 → 12,000 (document read once per agent, but prompt only includes the path). **~132,000 tokens saved** (~44% total reduction)

**Caveat**: Agents still need to read the file, which counts against their context window. But it removes the prompt duplication — the orchestrator's prompt construction is where cost scales.

#### O4: Output Format Compression (LOW IMPACT, EASY WIN)

**Current**: 50-line output format block (~400 tokens) repeated in every prompt.

**Proposed**: Compress to essential rules only:
```
## Output Rules
Write to {OUTPUT_DIR}/{name}.md.partial, rename to .md when done.
Start with: ### Findings Index (- SEVERITY | ID | "Section" | Title; Verdict: safe|needs-changes|risky)
Then: Summary, Issues, Improvements, Assessment sections.
Add <!-- flux-drive:complete --> before rename.
```

**Impact**: ~400 → ~120 tokens per agent. **~3,400 tokens saved** across 12 agents.

**Risk**: Minimal — agents are sonnet/opus, they follow compressed instructions fine.

#### O5: Conditional Knowledge Injection (LOW IMPACT, EASY WIN)

**Current**: Always query qmd for 5 knowledge entries per agent, even when the knowledge layer is sparse.

**Proposed**: Skip knowledge query when `config/flux-drive/knowledge/` has <3 entries. Also: skip for agents where no domain-relevant knowledge exists (pre-filter by agent name tag).

**Impact**: Saves ~500 tokens per agent when knowledge is irrelevant. Also saves qmd query latency.

#### O6: Agent System Prompt Trimming (MEDIUM IMPACT)

**Current**: `shared-contracts.md` says to strip examples and output format from Project Agent prompts. But Plugin Agents load system prompts via `subagent_type` — the orchestrator cannot strip those.

**Proposed**: For plugin agents, the agent `.md` files themselves should be leaner. Move verbose examples to a `references/` file that agents can Read if needed, rather than including in the system prompt.

**Impact**: fd-quality is the heaviest (~4,000 tokens due to language-specific sections). If agents loaded language-specific sections on-demand (Read the relevant section after detecting language), system prompts could be ~2,000 tokens.

**Risk**: Extra Read tool call per agent. Adds ~1s latency, saves ~2,000 tokens × 12 = ~24,000 tokens.

#### O7: Domain Criteria Dedup (LOW IMPACT, PREVENTS BLOAT)

**Current design**: Domain criteria are separate from agent system prompts (additive injection).

**Potential bloat**: If an agent's system prompt already covers a criterion from the domain profile (e.g., fd-correctness already checks "state transitions are atomic"), injecting the same check from game-simulation.md is redundant.

**Proposed**: During injection, the orchestrator checks for semantic overlap between domain criteria and agent system prompt bullets. Skip criteria that duplicate existing checklist items. Simple heuristic: if >60% of words in a domain criterion appear in the agent's Review Approach section, skip it.

**Impact**: Prevents token waste from redundant criteria. Small savings (~50 tokens per duplicated item) but keeps prompts clean.

### Priority Ranking

| Optimization | Impact | Effort | Risk | Recommendation |
|-------------|--------|--------|------|----------------|
| O3: File reference | ~44% reduction | Low | Low (agents have Read access) | **Do first** |
| O1: Document slicing for all inputs | ~36% reduction | Medium | Medium (cross-section issues) | **Do second** |
| O4: Output format compression | ~1% reduction | Trivial | None | **Do immediately** |
| O6: Agent prompt trimming | ~8% reduction | Medium | Low (extra Read latency) | **Do in v2** |
| O2: Progressive depth | ~15% reduction | Medium | Medium (quality impact) | **Evaluate after O1** |
| O5: Conditional knowledge | ~2% reduction | Low | None | **Do immediately** |
| O7: Domain criteria dedup | Prevents bloat | Low | Low | **Do during injection implementation** |

### Implementation Sketch: O3 (File Reference)

**What changes**: Instead of pasting document content into each agent's prompt, write it to a file and tell agents to Read it.

**Changes to `phases/launch.md`**:

In Step 2.0 (Prepare output directory), add:

```markdown
### Step 2.0b: Write document content to shared file

Write the review input to a shared file that agents will read:

For INPUT_TYPE = file:
  Write the document content to: {OUTPUT_DIR}/_input.md

For INPUT_TYPE = diff:
  Write the diff content to: {OUTPUT_DIR}/_input.diff

For INPUT_TYPE = directory:
  Write the structural summary + key file contents to: {OUTPUT_DIR}/_input.md

This file is the single source of truth for review content.
Agents will Read this file as their first action.
```

**Changes to prompt template** (in `phases/launch.md`):

Replace the current `## Document to Review` section:

```markdown
## BEFORE — Current (document inline, ~12,000 tokens per agent)

## Document to Review
[Full document content pasted here]
```

With:

```markdown
## AFTER — O3 (file reference, ~50 tokens per agent)

## Document to Review

Read the document from: {OUTPUT_DIR}/_input.md
This is the complete document for review.
Read it in full before beginning your analysis.
```

For **sliced agents** (O1, see below), the instruction changes:

```markdown
## Document to Review

Read the document from: {OUTPUT_DIR}/_input.md

Your focus sections (read carefully): {section_list}
Other sections (skim for cross-cutting issues): {other_sections}

If you find an issue in a non-focus section, still flag it —
but prioritize depth in your focus sections.
```

**Agent behavior**: Each agent's first tool call becomes `Read({OUTPUT_DIR}/_input.md)`. This costs the same context window tokens but removes the duplication from the orchestrator's prompt construction. The orchestrator only sends ~50 tokens of instruction instead of ~12,000 tokens of document content per agent.

**Why this works**: All flux-drive agents (plugin and project) have Read tool access. The file is written before agents launch. Agents running in background can all read the same file concurrently.

**Edge case — Oracle**: Oracle uses the `--files` flag to read input files natively. Pass `{OUTPUT_DIR}/_input.md` as `-f`. No prompt change needed.

---

### Implementation Sketch: O1 (Universal Document Slicing)

**What changes**: Extend the diff slicing pattern to file/directory inputs. Domain-specific agents get focus sections in full + summaries for the rest.

**Prerequisite**: Requires the Pyramid Scan (Step 1.2c) to already produce section-to-agent mappings. This mapping currently exists but is only used for the prompt's "Focus Areas" section — not for actual content trimming.

**Changes to `phases/launch.md`**:

Replace lines 105-109 (current document content rules):

```markdown
## BEFORE — Current

**Document content**: Include the full document in each agent's prompt
without trimming. Each agent gets the complete document content.

**Exception for very large file/directory inputs** (1000+ lines):
Include only the sections relevant to the agent's focus area plus
Summary, Goals, and Non-Goals.
```

With:

```markdown
## AFTER — O1 (universal document slicing)

### Step 2.0c: Prepare per-agent document views

For INPUT_TYPE = file or directory:

1. Write full document to {OUTPUT_DIR}/_input.md (shared, from O3)

2. If document has ≥3 sections (## headings) AND ≥300 lines:
   Generate per-agent sliced views using the section-agent mapping
   from Step 1.2c (Pyramid Scan):

   For each agent:
   a. Identify FOCUS sections (tagged `full` in section mapping)
   b. Identify CONTEXT sections (tagged `skim` or untagged)
   c. Write sliced view to {OUTPUT_DIR}/_input-{agent-name}.md:
      - Include full content for FOCUS sections
      - Include 2-line summary for CONTEXT sections:
        `## {Section Name} [SUMMARY: {2-line summary from Pyramid Scan}]`
      - Always include: title, Summary/Goals/Non-Goals sections in full

   Cross-cutting agents (fd-architecture, fd-quality) get the full
   document — no sliced view is created for them.

3. If document has <3 sections OR <300 lines:
   Skip slicing. All agents read {OUTPUT_DIR}/_input.md in full.
   Small documents don't benefit from slicing.

4. Update agent prompts:
   - Cross-cutting agents: "Read {OUTPUT_DIR}/_input.md"
   - Domain agents with sliced view:
     "Read {OUTPUT_DIR}/_input-{agent-name}.md
      (This is a focused view. Full document at _input.md if needed.)"
```

**How section-agent mapping works** (extending existing Step 1.2c):

The Pyramid Scan already identifies sections and classifies them. We extend the mapping:

```
Section → Agent Tag:
  "Architecture" → fd-architecture: full, fd-quality: skim
  "Security"     → fd-safety: full, fd-architecture: skim
  "Data Model"   → fd-correctness: full, fd-architecture: full
  "User Flows"   → fd-user-product: full, fd-game-design: full
  "Performance"  → fd-performance: full
  "Testing"      → fd-quality: full
  "Game Design"  → fd-game-design: full, fd-user-product: skim
```

Each agent gets sections tagged `full` as complete content, sections tagged `skim` as 2-line summaries.

**Token savings math**:

A 2,000-line document with 6 sections, reviewed by 12 agents:
- 3 cross-cutting agents: read full (2,000 lines each)
- 9 domain agents: read ~2 focus sections (~700 lines) + ~4 summaries (~50 lines) = ~750 lines each

Before O1: 12 × 2,000 lines = 24,000 lines read total
After O1: 3 × 2,000 + 9 × 750 = 12,750 lines read total → **47% reduction**

Combined with O3 (file reference), the orchestrator's prompt shrinks from 24,000 lines of inline content to 12 lines of file paths.

---

### Implementation Sketch: O4 (Output Format Compression)

**What changes**: Compress the 50-line output format override to ~15 lines.

Replace in prompt template:

```markdown
## BEFORE — Current (~400 tokens)

## CRITICAL: Output Format Override

Your agent definition has a default output format. IGNORE IT for this task.
You MUST use the format specified below. This is a flux-drive review task
and synthesis depends on a machine-parseable Findings Index.

### Required Output

Your FIRST action MUST be: use the Write tool to create
`{OUTPUT_DIR}/{agent-name}.md.partial`.
[... 40 more lines of format specification ...]
```

With:

```markdown
## AFTER — O4 (~120 tokens)

## Output: flux-drive format (overrides your default)
Write to `{OUTPUT_DIR}/{agent-name}.md.partial`. Start with:
### Findings Index
- SEVERITY | ID | "Section" | Title
Verdict: safe|needs-changes|risky

Then: Summary (3-5 lines), Issues (numbered P0/P1/P2), Improvements
(numbered), Assessment (1-2 sentences). Match Issues to Findings Index.
Zero findings: empty index + `Verdict: safe`.
When done: add `<!-- flux-drive:complete -->`, rename .partial → .md.
```

**Risk**: Minimal. Sonnet and opus follow compressed instructions reliably. The key structural requirements (Findings Index format, completion signal, file rename) are all preserved.

---

### Implementation Sketch: O5 (Conditional Knowledge)

**What changes**: Skip qmd queries when knowledge layer is sparse or irrelevant.

In Step 2.1 (Retrieve knowledge context), add a pre-check:

```markdown
### Step 2.1: Retrieve knowledge context (enhanced)

**Pre-check**: Before querying, verify the knowledge layer has content:
1. Check if config/flux-drive/knowledge/ contains any .md files (excluding README.md)
2. If 0-2 entries exist: SKIP knowledge retrieval for all agents
   (too few entries to be useful, saves 6-12 qmd queries)
3. If 3+ entries exist: proceed with retrieval

**Per-agent skip**: After retrieval, if an agent's top result has
relevance score < 0.3, discard all results for that agent
(below noise threshold).
```

---

### Combined Impact

If we implement O3 + O1 + O4 + O5:

```
Before: ~301,000 tokens (12 agents, 2000-line document)
After O3: ~169,000 tokens (document via file reference)
After O1: ~121,000 tokens (document slicing for domain agents)
After O4: ~117,800 tokens (compressed output format)
After O5: ~114,800 tokens (skip empty knowledge queries)

Total reduction: ~62% (301K → 115K tokens)
```

At ~$3/M input tokens (sonnet), that's $0.90 → $0.35 per review. For 12 agents, the per-review cost drops below the current 8-agent cost.

### Token Budget with Domain Features

After optimizations, adding domain awareness costs very little:

| New Feature | Token Cost | Notes |
|------------|-----------|-------|
| Domain detection (Step 1.0) | ~0 | Uses existing project docs already read |
| Domain injection (per agent) | ~200 tokens | 5 bullets, trivial |
| fd-game-design (new agent) | ~3,000 tokens | Same as other core agents |
| /flux-gen agents (2-3 extra) | ~9,000 tokens | Only when user opts in |
| Adaptive ceiling (12 vs 8) | +50% slot cost | But O3+O1 reduce per-slot cost by 60% |

**Net effect**: Domain-aware flux-drive with 12 agents and optimizations costs **less** than the current 8-agent setup without optimizations.

---

## Open Questions (Resolved)

1. **Should domain profiles be editable by users?** → No, curated profiles are plugin-shipped (read-only). Users add custom criteria via `extra_criteria` in `flux-drive.yaml`. This keeps the source of truth clean while allowing per-project customization.

2. **Multi-domain projects?** → Yes, inject criteria from all matched profiles. Cap at 5 bullets per agent. Primary domain (highest confidence) gets priority for `/flux-gen`.

3. **Profile quality control?** → Profiles ship with the plugin and follow the same review process as agent definitions. Best-practices-researcher provides the initial content; domain experts refine.

4. **Knowledge layer interaction?** → Separate. Domain profiles are prescriptive expertise ("always check X"). Knowledge entries are observational findings ("we found X in past reviews"). Different provenance, different lifecycle.

## Open Questions (Remaining)

1. **Agent count after adding fd-game-design**: Currently 16 agents (9 review + 5 research + 2 workflow). Adding fd-game-design makes it 17 (10 review). Need to update regression tests, plugin.json, CLAUDE.md counts, and gen-catalog.py.

2. **Domain profiles in test suite**: Should structural tests validate domain profile format (Detection Signals section exists, Injection Criteria has agent subsections, etc.)? Probably yes — prevents profile rot.

3. **Generated criteria quality**: When LLM generates criteria for an unrecognized domain, how do we validate quality? Could use a self-check: "Are these criteria specific enough to be actionable? Would a reviewer know what to look for?"

4. **Orchestrator migration path**: The scoring/slot/expansion changes are significant. Ship domain profiles + injection first (low risk), then orchestrator overhaul second (higher risk, needs testing)?

5. **Adaptive ceiling resource impact**: 12 concurrent agents is 12 API calls. Should we monitor and throttle based on actual response times? Add a `--max-agents` flag for users on constrained setups?

6. **Domain adjacency maintenance**: The adjacency map (which agents are related) needs updating when new agents are added. Should this be auto-derived from domain profiles or manually maintained?

## Original Intent (for future iterations)

### Triggers → Features Not Yet Designed

- **Domain profile marketplace**: Community-contributed profiles — validate core design first
- **Cross-project learning**: "Rails projects always benefit from fd-safety" — needs usage data
- **Profile versioning**: Domain expertise evolves — use plugin versioning for now
- **Agent composition**: Compose from reusable review "modules" — overengineering for v1
- **Profile auto-refinement**: After N reviews with a profile, suggest criteria additions/removals based on what agents actually flagged — needs the compounding system to support profile-aware entries
