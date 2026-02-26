# Clavain Vision & Philosophy Research

**Research Date:** 2026-02-14  
**Purpose:** Understand Clavain's current state, design philosophy, and existing vision documents to inform vision statement creation

## Executive Summary

Clavain has **no formal vision or mission statement**. The project's philosophy is embedded in:
- README.md's "My Workflow" section (personal perspective)
- AGENTS.md architecture decisions (technical choices)
- CLAUDE.md "Design Decisions (Do Not Re-Ask)" (historical rulings)
- Plugin.json description (one-line summary)
- Multiple brainstorm documents revealing evolving thinking

The closest thing to a vision statement is the README opening: "a highly opinionated Claude Code agent rig that encapsulates how I personally like to use Claude Code to build things."

## Key Finding: No Vision Documents Found

Search for dedicated vision/mission/philosophy files:
- `**/vision.md` — NOT FOUND
- `**/roadmap.md` — NOT FOUND
- `**/philosophy.md` — NOT FOUND
- `**/mission.md` — NOT FOUND
- `docs/philosophy/` — DOES NOT EXIST
- `docs/why/` — DOES NOT EXIST

## Current Self-Description Across Artifacts

### Plugin Manifest (plugin.json)

**Version:** 0.6.1  
**Description:** "General-purpose engineering discipline plugin. 10 agents, 36 commands, 27 skills, 1 MCP servers — combining workflow discipline with specialized execution agents. Includes Codex dispatch, cross-AI review (interpeer with quick/deep/council/mine modes), and structured debate. Companions: interphase, interline, interflux."

**Keywords:** engineering-discipline, code-review, workflow-automation, tdd, debugging, planning, agents, general-purpose, cross-ai-review, oracle, council

### README.md Philosophy

**Opening Statement:**
"Clavain, named after one of the protagonists from Alastair Reynolds's Revelation Space series, is a **highly** opinionated Claude Code agent rig that encapsulates how I personally like to use Claude Code to build things."

**Definition of "Agent Rig":**
"An agent rig, as I define it, is a collection of plugins, skills, and integrations that serves as a cohesive system for working with agents."

**Modpack Philosophy:**
"Clavain is designed as an **agent rig**, inspired by PC game mod packs. It is an opinionated integration layer that configures companion plugins into a cohesive rig. Instead of duplicating their capabilities, Clavain routes to them and wires them together."

**Personal Workflow (README "My Workflow" section):**
- For simple requests: `/lfg add user export feature` → autonomous orchestration through brainstorm/plan/review/implement/ship
- For complex work: Use pieces individually based on phase
- Focus on "product strategy, user pain points, and finding new leverage points" while Clavain handles execution
- Most-used standalone command: `/flux-drive` for multi-agent review

### AGENTS.md Technical Philosophy

**Merged Lineage:**
"General-purpose engineering discipline plugin for Claude Code. Merged from superpowers, superpowers-lab, superpowers-developing-for-claude-code, and compound-engineering."

**Component Counts (regression-guarded):**
- 27 skills
- 10 agents (3 review + 5 research + 2 workflow)
- 36 commands
- 7 hooks
- 1 MCP server

**Architecture Principle:**
"SessionStart Hook... reads skills/using-clavain/SKILL.md... outputs hookSpecificOutput.additionalContext JSON... Claude Code injects this as system context. This means every session starts with the 3-layer routing table."

**3-Layer Routing Philosophy:**
1. Stage (explore/plan/execute/debug/review/ship/meta)
2. Domain (code/data/deploy/docs/research/workflow/design/infra)
3. Concern (architecture/safety/correctness/quality/user-product/performance)

### CLAUDE.md Design Decisions

**Identity:**
- Namespace: `clavain:` (NOT superpowers, NOT compound-engineering)
- General-purpose only — no domain-specific components (Rails, Ruby, Every.to, Figma, Xcode, browser-automation)

**Companion Architecture:**
- 7 core review agents now live in **interflux** companion plugin (fd-architecture, fd-safety, fd-correctness, fd-quality, fd-user-product, fd-performance, fd-game-design)
- Phase tracking/gates/discovery live in **interphase** companion
- Statusline rendering in **interline** companion

**Development Workflow:**
- Trunk-based development — no branches/worktrees skills
- Always publish after pushing — use `/interpub:release <version>` or `scripts/bump-version.sh`

### using-clavain Skill (Injected Every Session)

**Bootstrap Philosophy:**
"Proactive skill invocation is required. When a skill matches the current task — even partially — invoke it before responding. Skills are designed to be triggered automatically; skipping a relevant skill degrades output quality."

**Daily Drivers Listed:**
1. `/lfg` — Full autonomous workflow
2. `/flux-drive` — Deep multi-agent review
3. `/quality-gates` — Quick review from git diff
4. `/interpeer` — Cross-AI second opinion
5. `/write-plan` + `/work` — Plan and execute
6. `/repro-first-debugging` — Bug investigation
7. `/resolve` — Fix findings
8. `/doctor` or `/sprint-status` — Health checks

**Routing Heuristic:**
"When a user message arrives: 1. Detect stage. 2. Detect domain. 3. Invoke the primary skill first (process skills before domain skills before meta skills)."

### setup.md & help.md Framing

**setup.md Purpose:**
"Bootstrap the Clavain modpack — install required plugins, disable conflicts, verify MCP servers, configure hooks"

**Modpack Components Listed:**
- Required: clavain, interdoc, tool-time, context7, agent-sdk-dev, plugin-dev, serena, security-guidance, explanatory-output-style
- Language servers: gopls-lsp, pyright-lsp, typescript-lsp, rust-analyzer-lsp
- Companions: interphase, interline (statusline), beads (issue tracking)
- Conflicts (must disable): code-review, pr-review-toolkit, code-simplifier, commit-commands, feature-dev, claude-md-management, frontend-design, hookify

**help.md Organization:**
Commands organized as: Daily Drivers first, THEN by workflow stage (explore/plan/execute/review/ship/debug/meta)

### lfg.md Workflow Philosophy

**Full Autonomous Lifecycle:**
9 steps: brainstorm → strategize → write-plan → review-plan → execute → test → quality-gates → resolve → ship

**Work Discovery (no-args mode):**
When invoked without arguments, scans open beads, ranks by priority, presents top options via AskUserQuestion. User picks a bead and gets routed to the right command.

**Phase Tracking Integration:**
After each step, records phase transitions via interphase plugin shims. Tracks: brainstorm → strategized → planned → plan-reviewed → executing → shipping → done.

**Gate Enforcement:**
Before execution: plan must be reviewed (flux-drive). Before shipping: quality gates must pass. Gates can be skipped with `CLAVAIN_SKIP_GATE='reason'`.

**Error Recovery Principle:**
"Do NOT skip the failed step — each step's output feeds into later steps. Retry once with tighter scope. If retry fails, stop and report."

## Brainstorm Documents — Evolving Philosophy

### 2026-02-08: Flux-Drive Improvements

**Motivation:** "Flux-drive is Clavain's flagship multi-agent review skill."

**Key Insight:** Self-review proved the system works (v1: 29 issues, v2: 28 issues) but revealed token waste and untested code paths.

**Token Efficiency Philosophy:** 47% of tokens are the document repeated 12 times across agents — addressed with document slicing and file references.

### 2026-02-12: Domain-Aware Flux-Drive

**Core Philosophy Shift:** "Make flux-drive adaptable to project domains"

**Three-Channel Design:**
1. Dynamic injection (default, automatic) — domain-specific checklists appended to core agents
2. `/flux-gen` command (opt-in) — generate 2-4 domain-specific agents in `.claude/agents/`
3. Core domain agents (fd-game-design) — shipped with plugin for universal domains

**Why This Approach:**
"Project-level fd-*.md agents are a 'dead feature' — only 2 projects ever created them. Friction too high. Dynamic injection is automatic and zero-friction."

**11 Curated Domains:** game-simulation, ml-pipeline, web-api, cli-tool, mobile-app, embedded-systems, library-sdk, data-pipeline, claude-code-plugin, tui-app, desktop-tauri

**Detection Philosophy:** Auto-detect on first run, cache in `.claude/flux-drive.yaml`, re-detect only when project docs change.

**Token Optimization Philosophy:**
Combined O3 (file reference) + O1 (document slicing) + O4 (format compression) + O5 (conditional knowledge) → 62% reduction (301K → 115K tokens).

**Agent Expansion Philosophy:** "Domain-aware flux-drive with 12 agents and optimizations costs LESS than the current 8-agent setup without optimizations."

## Implicit Philosophy Extracted from Architecture

### 1. Modularity via Companions

**Pattern:** Core capabilities extracted into companion plugins (interphase, interline, interflux) with shim discovery in Clavain.

**Philosophy:** Clavain is a "modpack" — an integration layer, not a monolith. Companions can be swapped, upgraded, or disabled independently.

### 2. General-Purpose Only

**Explicit Constraint:** "General-purpose only — no Rails, Ruby gems, Every.to, Figma, Xcode, browser-automation"

**Rationale (from AGENTS.md):** Clavain consolidates universal engineering disciplines. Domain-specific tooling lives in separate plugins.

### 3. Trunk-Based Development

**Decision:** "Trunk-based development — no branches/worktrees skills"

**Philosophy:** Simplicity over flexibility. Git worktrees add complexity; Clavain optimizes for fast iteration on main.

### 4. Upstream Sync as Core Practice

**6 Upstreams Tracked:** superpowers, superpowers-lab, superpowers-dev, compound-engineering, beads, oracle

**Philosophy:** Clavain is a living artifact, not a fork. Upstream improvements flow downstream automatically via weekly cron + Claude Code + Codex CLI auto-merge.

### 5. Cross-AI Review as First-Class

**Four Modes:** quick (Claude↔Codex), deep (Oracle/GPT-5.2), council (multi-model consensus), mine (disagreement extraction)

**Philosophy:** "Different models genuinely see different things, and the disagreements between them are often more valuable than what either finds alone."

### 6. Token Efficiency as Design Constraint

**From brainstorms:** Document duplication across agents is the elephant in the room (47% of tokens). Every optimization is measured in token reduction %.

**Philosophy:** Make 12-agent reviews cheaper than current 8-agent reviews by optimizing the orchestration, not reducing agent count.

### 7. Phase Tracking & Gates

**Pattern:** Every workflow step advances a phase, gates block execution until pre-conditions met.

**Philosophy:** Rigor through automation. Prevent executing unreviewed plans, prevent shipping code that failed quality gates.

### 8. Knowledge Compounding

**Auto-compound hook:** Detects compoundable signals (commits, resolutions, insights) on Stop, prompts knowledge capture.

**Philosophy:** Continuous learning. Review findings become knowledge entries, which feed into future reviews via qmd semantic search.

### 9. Discovery Over Memory

**Work discovery (lfg no-args):** Scans beads, ranks, presents options via AskUserQuestion.

**Philosophy:** Don't make the user remember what's in-flight. Scan state, offer choices, route automatically.

### 10. Routing as Infrastructure

**3-layer routing table injected every session via SessionStart hook.**

**Philosophy:** Claude shouldn't need to memorize 27 skills + 36 commands. Routing table is always in context, skills self-select based on task.

## Themes Across All Sources

### Theme 1: Opinionated Integration, Not Duplication

README: "Clavain routes to [companions] and wires them together."  
AGENTS.md: "Modpack — opinionated integration layer."  
plugin-audit.md: 8 plugins disabled due to overlap.

**Implication:** Clavain's value is in the ROUTING and ORCHESTRATION, not in containing all capabilities.

### Theme 2: Personal Workflow Made Reusable

README: "highly opinionated... how I personally like to use Claude Code"  
README: "I do not think Clavain is the best workflow for everyone"

**Implication:** This is a dogfooded artifact. The vision should be grounded in real use, not aspirational features.

### Theme 3: Autonomous Orchestration with Human Leverage Points

README: "while Clavain runs... I focus on product strategy, user pain points, and leverage points"  
lfg.md: 9-step autonomous pipeline with gate enforcement

**Implication:** Goal is to offload execution rigor to the system so the human can focus on higher-leverage decisions.

### Theme 4: Multi-Agent as Default

flux-drive: 4-tier agent triage (project/plugin/cross-AI/expansion)  
interpeer: 4-mode escalation stack  
Domain profiles: 11 curated domains × 7 agents × adaptive criteria

**Implication:** One model/agent is insufficient. Multiple perspectives converge on better outcomes.

### Theme 5: Continuous Evolution via Upstream + Community

6 upstreams with weekly auto-merge  
Interagency marketplace publication  
Companion plugins as modular capabilities

**Implication:** Clavain is not a product with releases, it's a living rig that evolves with the ecosystem.

## What's NOT Present (Gaps for Vision Statement)

1. **No articulated "why"** — what problem does Clavain solve that vanilla Claude Code doesn't?
2. **No user archetypes** — who is this for? (solo devs? teams? specific domains?)
3. **No success criteria** — what does "working well" mean? (velocity? quality? learning?)
4. **No principles hierarchy** — when trade-offs arise (e.g., token cost vs agent count), what wins?
5. **No 1-3 year trajectory** — where is this heading? More domains? More companions? Stabilization?
6. **No explicit stance on AI labor division** — when should Claude lead vs Codex? When should human intervene?

## Existing Design Principles (Implicit, Should Be Explicit)

From patterns across all documents:

1. **Skills over tools** — Workflow disciplines (SKILL.md) guide execution, not just commands
2. **Routing over memory** — Agent should self-select the right skill, not recall "what command does X"
3. **Companions over monoliths** — Extract capabilities into focused plugins, integrate via shims
4. **Discovery over CLI flags** — Scan state, present options, let user choose (work discovery pattern)
5. **Gates over trust** — Enforce pre-conditions (plan must be reviewed before execution)
6. **Convergence over consensus** — Multiple agents find different things; synthesis is where value emerges
7. **Compound over repeat** — Knowledge layer: past findings inform future reviews
8. **Token efficiency enables scale** — Optimize orchestration so 12 agents cost less than 8
9. **General-purpose core, domain extensions** — Plugin ships universal skills, domains via profiles/companions
10. **Upstream sync as duty** — Track sources, auto-merge, maintain lineage

## Recommendations for Vision Statement

### Anchor on Existing Identity

- **Name origin:** Clavain = protagonist from hard sci-fi (Revelation Space) — implies long-game strategy, multi-century thinking
- **"Agent rig" framing:** Already established in README, resonates with modpack concept
- **Personal workflow:** Start from "how I work" and generalize to "a way to work" without losing specificity

### Address the Gaps

A vision statement should answer:
1. **For whom?** Solo builders? Small teams? Open-source maintainers? All?
2. **What problem?** Context juggling? Quality inconsistency? Lack of rigor? Learning curve?
3. **How is it different?** Not just "multi-agent" — what's the organizing principle?
4. **Where is it going?** More domains? Stabilization? Ecosystem expansion?

### Possible Framing Angles

**Angle 1: Workflow Discipline as Infrastructure**
"Turn engineering discipline into runnable code. Skills are not documentation — they're executable workflows that guide agents through proven practices."

**Angle 2: Multi-Agent Orchestration**
"One agent is insufficient. Clavain orchestrates multiple models, multiple perspectives, and multiple passes — convergence over consensus."

**Angle 3: The Modpack Pattern for AI**
"Like Minecraft modpacks or Skyrim collections, Clavain curates and integrates the best plugins into a cohesive rig, handling conflicts and wiring."

**Angle 4: Personal Workflow Made Shareable**
"I built this to work the way I want to work. It's opinionated because opinions encode decisions. Use what fits, ignore what doesn't."

**Angle 5: Continuous Improvement System**
"Knowledge compounds. Upstream syncs. Every review teaches future reviews. Clavain is a learning artifact, not a static tool."

## Key Quotes for Vision Synthesis

From README:
> "a highly opinionated Claude Code agent rig that encapsulates how I personally like to use Claude Code to build things"

> "An agent rig, as I define it, is a collection of plugins, skills, and integrations that serves as a cohesive system for working with agents."

> "while Clavain runs through all of these phases, I focus on the usual suspects: product strategy, user pain points, and finding new leverage points"

> "Because different models genuinely see different things, and the disagreements between them are often more valuable than what either finds alone"

From AGENTS.md:
> "General-purpose engineering discipline plugin for Claude Code. Merged from superpowers, superpowers-lab, superpowers-dev, and compound-engineering."

> "This means every session starts with the 3-layer routing table, so the agent knows which skill/agent/command to invoke for any task."

From domain-aware brainstorm:
> "Dynamic injection is automatic and zero-friction."

> "Domain-aware flux-drive with 12 agents and optimizations costs LESS than the current 8-agent setup without optimizations."

From using-clavain skill:
> "Proactive skill invocation is required... Skills are designed to be triggered automatically; skipping a relevant skill degrades output quality."

## Conclusion

Clavain's philosophy is **embedded in practice, not documented as principle**. The vision is latent:

- **What it is:** A curated modpack that turns workflow disciplines into executable skills, orchestrates multi-agent reviews, and integrates companion plugins into a cohesive rig
- **Why it exists:** To offload execution rigor so the human can focus on leverage points (strategy, user pain, system design)
- **How it works:** 3-layer routing, phase tracking, gate enforcement, knowledge compounding, upstream sync, cross-AI review
- **Who it's for:** People who want an opinionated workflow that handles the discipline while they handle the decisions

**The gap:** No explicit articulation of these latent principles. A vision statement should make the implicit explicit, name the philosophy, and point toward where this is heading.

**Next step:** Synthesize these findings into a concise vision statement (200-400 words) that captures the essence without losing the grounded, personal, opinionated voice that makes Clavain distinctive.
