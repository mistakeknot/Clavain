# Clavain Agent Rig Capabilities Analysis

**Date:** 2026-02-08  
**Purpose:** Assess what Clavain provides for building custom agent rigs and identify gaps

---

## Executive Summary

Clavain provides **strong conceptual guidance** and **Claude Code plugin infrastructure** for agent-native applications, but lacks concrete implementations for the Agent SDK layer. The plugin excels at orchestration, coordination, and workflow discipline, but doesn't yet provide hands-on tooling for building standalone Agent SDK applications (Python/TypeScript) or custom MCP servers.

**Gap Priority:** High — users who want to "fully roll their own" need Agent SDK scaffolding, MCP server builders, deployment templates, and monitoring patterns.

---

## 1. Current Agent-Building Skills

### agent-native-architecture (Comprehensive)
- **Location:** `skills/agent-native-architecture/SKILL.md`
- **Scope:** Designing agent-first applications where features = outcomes achieved by autonomous agents
- **Core Principles:**
  - **Parity:** Whatever user can do via UI, agent can do via tools
  - **Dynamic context injection:** System prompt reflects current app state
  - **Prompt-native design:** Features delivered through prompts, not code changes
- **References (12 files):**
  - `mcp-tool-design.md` — Tool design patterns (primitives not workflows, CRUD completeness, dynamic capability discovery)
  - `agent-native-testing.md` — Testing patterns (outcome-focused, parity tests, "can agent do it?" tests)
  - `agent-execution-patterns.md` — Completion signals, model tier selection, context limits
  - `action-parity-discipline.md`, `architecture-patterns.md`, `system-prompt-design.md`, etc.
- **Strengths:**
  - Deep architectural guidance
  - Testing methodology
  - Tool design philosophy
- **Gaps:**
  - No SDK code scaffolding
  - No deployment templates
  - No monitoring/observability patterns

### create-agent-skills (Claude Code Skills, NOT Agent SDK)
- **Location:** `skills/create-agent-skills/SKILL.md`
- **Scope:** Writing Claude Code Skills (SKILL.md files), NOT Agent SDK applications
- **Provides:**
  - YAML frontmatter structure
  - Markdown formatting
  - Progressive disclosure patterns
  - Testing via subagents
- **Does NOT provide:**
  - Agent SDK (Python/TypeScript) scaffolding
  - Tool creation for standalone agents
  - MCP server integration for custom apps

### developing-claude-code-plugins (Plugin Development)
- **Location:** `skills/developing-claude-code-plugins/SKILL.md`
- **Scope:** Building Claude Code plugins (skills, commands, hooks, MCP servers)
- **Provides:**
  - Plugin structure (`plugin.json`, marketplaces)
  - Component patterns (skills, commands, hooks)
  - Local dev workflow
  - Release/distribution process
- **MCP Server Support:**
  - How to bundle MCP servers in plugins
  - Configuration (`${CLAUDE_PLUGIN_ROOT}` variables)
  - Lifecycle management
- **Gaps:**
  - No MCP server creation guide
  - No tool implementation examples
  - Focuses on packaging, not building

### working-with-claude-code (Reference)
- **Location:** `skills/working-with-claude-code/SKILL.md`
- **Scope:** Official Claude Code documentation mirror
- **Relevant Files:**
  - `references/mcp.md` — Connecting to existing MCP servers (not building them)
  - `references/migration-guide.md` — Agent SDK migration (package rename only)
- **What's Missing:**
  - No "getting started with Agent SDK" guide
  - No "build your first MCP server" tutorial
  - Migration guide is package-rename only, not a building guide

---

## 2. Agent SDK Support

### Search Results
**Query:** `Agent SDK|@anthropic-ai/sdk|claude-ai/sdk|agent sdk` across codebase

**Findings:**
- **1 file found:** `skills/working-with-claude-code/references/migration-guide.md`
- **Content:** Package rename guide (`@anthropic-ai/claude-code` → `@anthropic-ai/claude-agent-sdk`)
- **Purpose:** Migrating existing SDK users, NOT teaching SDK usage

### What's Present
- Tool design patterns in `agent-native-architecture/references/mcp-tool-design.md`:
  - `createSdkMcpServer` import example
  - `tool()` function usage
  - TypeScript examples
- Migration guide acknowledges:
  - Python package: `claude-agent-sdk`
  - TypeScript package: `@anthropic-ai/claude-agent-sdk`
  - Breaking changes (system prompt no longer default, settings sources opt-in)

### What's Missing
**No skills or agents for:**
- Initializing an Agent SDK project (Python or TypeScript)
- Structuring Agent SDK applications
- Building custom tools for Agent SDK
- Testing Agent SDK applications
- Deploying Agent SDK applications
- Monitoring Agent SDK agents in production

**Gap:** Users wanting to build standalone Agent SDK apps have no scaffolding, templates, or workflows in Clavain.

---

## 3. MCP Server Building

### Search Results
**Query:** `mcp-builder|mcp server|MCP Server` across skills

**Findings:** 24 files reference MCP, but focused on:
- **Using** existing MCP servers (`skills/mcp-cli/SKILL.md`)
- **Bundling** MCP servers in plugins (`developing-claude-code-plugins`)
- **Connecting** to remote MCP servers (`working-with-claude-code/references/mcp.md`)

### mcp-cli Skill
- **Purpose:** Use `mcp` CLI to invoke MCP servers on-demand without pre-configuring
- **Capabilities:**
  - Discover tools from MCP servers
  - Invoke tools dynamically
  - Test MCP servers
- **NOT a builder:** No guidance on creating MCP servers

### Plugin MCP Integration
- **Supported:** Bundling pre-built MCP servers in plugins
- **Configuration:** `plugin.json` `mcpServers` field, `.mcp.json` file
- **Example:** Clavain bundles `context7` (HTTP) and `mcp-agent-mail` (HTTP)
- **Gap:** No guidance on implementing the server itself

### Tool Design Patterns (Present)
`agent-native-architecture/references/mcp-tool-design.md` provides:
- Tool naming conventions
- CRUD completeness checklist
- Dynamic capability discovery pattern
- Rich output guidelines
- Tool design template with `createSdkMcpServer`

**BUT:** This is architectural guidance, not a step-by-step builder workflow.

### What's Missing
**No skills or workflows for:**
- Scaffolding a new MCP server project
- Implementing stdio/HTTP/SSE transports
- Testing MCP servers locally
- Publishing MCP servers (npm, PyPI, GitHub)
- Debugging MCP server connections
- MCP server deployment patterns

**Gap:** Users can design tools conceptually but have no practical guide to implementing and deploying MCP servers.

---

## 4. Plugin Development Support

### Strong Coverage
- **Skill:** `developing-claude-code-plugins/SKILL.md`
- **References:** 
  - `plugin-structure.md` — Directory layout, manifests
  - `common-patterns.md` — When to use each pattern
  - `polyglot-hooks.md` — Cross-platform hook wrappers
  - `troubleshooting.md` — Common issues

### What It Provides
- Plugin directory structure
- `plugin.json` format
- Marketplace creation
- Local testing via `localPlugins`
- Release workflow (versioning, tagging, distribution)
- Hook system (session-start, pre-commit, etc.)

### Hooks
- **2 hooks active in Clavain:**
  - `session-start.sh` — Injects `using-clavain` skill, checks upstream staleness
- **Reference:** `polyglot-hooks.md` for Windows/macOS/Linux compatibility

### Commands
- **24 commands in Clavain** (e.g., `/clavain:brainstorm`, `/clavain:work`, `/clavain:flux-drive`)
- **Creation support:** `/clavain:generate-command` command exists
- **Format:** Markdown with YAML frontmatter

### Skills
- **32 skills in Clavain**
- **Creation support:** `/clavain:create-agent-skill` command + `create-agent-skills` skill
- **Format:** SKILL.md with progressive disclosure pattern

### Strong Points
- Plugin lifecycle well-documented
- Template patterns for all components
- Marketplace distribution covered
- Local dev workflow clear

### Gaps
- No "plugin blueprint" generator
- No automated testing for plugins
- No CI/CD templates for plugin releases

---

## 5. Upstream Sources

### upstreams.json Analysis
**File:** `/root/projects/Clavain/upstreams.json`

**4 upstream repositories:**

1. **superpowers** (obra)
   - Skills: brainstorming, dispatching-parallel-agents, executing-plans, subagent-driven-development, systematic-debugging, TDD, verification-before-completion, writing-plans, writing-skills
   - Commands: brainstorm, execute-plan, write-plan
   - Agents: code-reviewer → plan-reviewer

2. **superpowers-lab** (obra)
   - Skills: finding-duplicate-functions, mcp-cli, slack-messaging, using-tmux-for-interactive-commands

3. **superpowers-dev** (obra)
   - Skills: developing-claude-code-plugins (with 4 reference files), working-with-claude-code (with references/*)

4. **compound-engineering** (EveryInc)
   - Skills: agent-native-architecture (with references/*), create-agent-skills (with references/*, templates/*, workflows/*), file-todos
   - Agents: 5 research agents, 11 review agents, 3 workflow agents
   - Commands: 15 commands (agent-native-audit, changelog, create-agent-skill, generate-command, heal-skill, lfg, plan-review, resolve-*, triage, brainstorm, review, work)

### What Upstreams Provide
- **Workflow discipline:** Planning, execution, debugging, TDD
- **Agent coordination:** Parallel dispatch, subagent-driven development
- **Plugin development:** Creating skills, commands, plugins
- **Agent-native architecture:** Design patterns, testing

### What Upstreams DON'T Provide
- Agent SDK project templates
- MCP server builders/scaffolders
- Deployment automation
- Production monitoring
- Multi-agent coordination beyond subagents (see interclode/agent-mail below)

---

## 6. Installed Plugins Analysis

### Installed Plugins (from cache)
**Directory:** `/root/.claude/plugins/cache/interagency-marketplace/`

**Installed:**
1. **clavain** (this plugin)
2. **gurgeh-plugin**
3. **interclode** (v0.2.3) — Cross-AI delegation (Codex from Claude Code)
4. **interdoc** — AGENTS.md generator
5. **interpeer** — Cross-AI peer review
6. **tldrs**
7. **tldr-swinton**
8. **tool-time**
9. **tuivision**

### interclode Plugin
- **Purpose:** Dispatch Codex agents from Claude Code for parallel autonomous work
- **Relevant Skills:** `skills/delegate/SKILL.md`
- **Capability:** Cross-AI orchestration (Claude Code → Codex CLI)
- **Clavain Integration:**
  - `skills/codex-delegation/SKILL.md`
  - `skills/codex-first-dispatch/SKILL.md`
  - Commands: `/clavain:clodex`, `/clavain:codex-first`

**Note:** This is orchestration, not agent rig building. It delegates to an external AI (Codex), not building standalone agents.

### interdoc Plugin
- **Purpose:** Generate AGENTS.md documentation files
- **Relevance:** Documentation automation, not agent building

### interpeer Plugin
- **Purpose:** Cross-AI peer review (dispatch review agents)
- **Relevance:** Orchestration, not agent SDK building

### What Plugins DON'T Provide
- None of the installed plugins provide Agent SDK scaffolding
- None provide MCP server builders
- None provide deployment/monitoring templates

---

## 7. Multi-Agent Coordination

### agent-mail-coordination Skill
- **Location:** `skills/agent-mail-coordination/SKILL.md`
- **MCP Server:** `mcp-agent-mail` (bundled in Clavain's `plugin.json`)
- **Purpose:** Messaging, file reservations, coordination between AI agents on same codebase
- **Features:**
  - Session startup macro (`macro_start_session`)
  - File reservations (reserve before editing)
  - Thread-based messaging
  - Link to beads issues
- **Use Cases:**
  - Multiple agents active on one project
  - Editing shared files
  - Cross-repo coordination
  - Audit trail of agent decisions

### dispatching-parallel-agents Skill
- **Purpose:** When/how to parallelize agent work
- **Pattern:** Dispatch subagents via Claude Code's subagent system
- **NOT multi-agent rig building:** This is Claude Code orchestrating subagents, not building standalone agent systems

### flux-drive Skill
- **Purpose:** Intelligent document/repo review with agent triage
- **Pattern:** Dispatch multiple agents to analyze a codebase/document set
- **Coordination:** Via Claude Code's subagent dispatch

### What's Present
- Coordination within Claude Code ecosystem (subagents, agent-mail)
- Cross-AI delegation (interclode → Codex)
- File reservation protocol

### What's Missing
- Building distributed agent systems (beyond Claude Code)
- Agent-to-agent communication protocols (custom, not just agent-mail)
- State synchronization patterns
- Conflict resolution strategies
- Load balancing/work stealing patterns

---

## 8. Testing Support

### agent-native-testing.md
- **Location:** `skills/agent-native-architecture/references/agent-native-testing.md`
- **Philosophy:** Test outcomes, not procedures
- **Patterns:**
  - "Can Agent Do It?" tests
  - Location awareness tests
  - Surprise tests (open-ended requests)
  - Parity testing (UI action → agent tool mapping)
  - Integration testing (end-to-end flows)
  - Failure recovery tests
- **CI/CD:** GitHub Actions examples with cost-aware testing
- **Test Utilities:** Agent test harness example

### test-driven-development Skill
- **Purpose:** RED-GREEN-REFACTOR cycle for code
- **NOT agent testing:** This is traditional TDD, not agent capability testing

### What's Present
- Testing philosophy for agent-native apps
- Automated parity testing
- CI/CD integration patterns

### What's Missing
- Unit testing for custom tools
- Integration testing for MCP servers
- End-to-end testing for Agent SDK apps
- Test fixtures for agent scenarios
- Mocking/stubbing patterns for agent tools

---

## 9. Deployment & Monitoring

### Search Results
**Query:** `deployment|deploy|production|monitoring|observability` across skills

**Findings:** 49 files mention these terms, but in context of:
- Code deployment (git push, CI/CD)
- Agent-native app deployment patterns (conceptual)
- NOT standalone agent deployment

### deployment-verification-agent
- **Location:** `agents/review/deployment-verification-agent.md`
- **Purpose:** Review agent that checks deployment safety
- **NOT a deployment guide:** This is a reviewer, not a deployment workflow

### What's Missing
**No skills or workflows for:**
- Deploying Agent SDK applications (serverless, containers, etc.)
- Monitoring agent performance in production
- Logging/observability for agent loops
- Cost tracking for agent API usage
- Error tracking/alerting for agent failures
- Health checks for agent systems
- Scaling patterns (horizontal/vertical)
- Circuit breakers for runaway agents

**Gap:** Users can build agents but have no guidance on running them in production reliably.

---

## 10. Complete Gaps Analysis

### What Clavain Provides Well
1. **Conceptual Architecture** — agent-native design principles, parity discipline, tool design patterns
2. **Claude Code Plugin Development** — skills, commands, hooks, marketplaces, local dev
3. **Workflow Discipline** — planning, execution, debugging, TDD, code review
4. **Agent Coordination (within Claude Code)** — subagents, parallel dispatch, agent-mail
5. **Testing Philosophy** — outcome-focused testing, parity tests, CI/CD patterns
6. **Tool Design Patterns** — primitives not workflows, CRUD completeness, dynamic discovery

### Critical Gaps for "Roll Your Own Agent Rig"

#### 1. Agent SDK Layer (HIGH PRIORITY)
**Missing:**
- Project scaffolding (Python/TypeScript)
- Quickstart templates
- "Hello World" agent examples
- Tool implementation patterns
- Custom tool libraries
- Model selection guidance
- Permission modes/user confirmation patterns
- Session management
- Context window management
- Cost optimization strategies

**What users need:**
- `clavain:new-agent-sdk-project` command
- Template repos for Python/TypeScript
- Step-by-step skill: "Building Your First Agent SDK App"
- Agent SDK best practices skill

#### 2. MCP Server Creation (HIGH PRIORITY)
**Missing:**
- MCP server scaffolding
- Transport implementation (stdio/HTTP/SSE)
- Tool registration patterns
- Resource/prompt patterns
- Testing MCP servers
- Publishing workflows
- MCP server templates (starter kits)

**What users need:**
- `clavain:new-mcp-server` command
- Skill: "Building MCP Servers"
- MCP server testing framework
- MCP server deployment guide

#### 3. Deployment & Operations (MEDIUM PRIORITY)
**Missing:**
- Deployment templates (Docker, serverless, cloud run)
- Infrastructure as Code (Terraform, Pulumi)
- CI/CD pipelines for agents
- Environment configuration management
- Secrets management patterns

**What users need:**
- Agent deployment skill
- Cloud platform integration skills (AWS/GCP/Azure)
- Containerization patterns
- Deployment verification checklists

#### 4. Monitoring & Observability (MEDIUM PRIORITY)
**Missing:**
- Logging patterns for agent loops
- Metrics collection (tool calls, latency, costs)
- Error tracking integrations (Sentry, Rollbar)
- Dashboards for agent performance
- Alerting on agent failures
- Cost tracking/budgets
- Health check endpoints

**What users need:**
- Agent observability skill
- Monitoring setup templates
- Cost tracking tools
- Production readiness checklist

#### 5. Multi-Agent Systems (LOW PRIORITY - Nice to Have)
**Missing beyond agent-mail:**
- Agent discovery protocols
- Work distribution patterns
- State synchronization
- Consensus mechanisms
- Agent communication protocols (beyond messaging)
- Load balancing

**What users need:**
- Multi-agent architecture skill
- Distributed agent patterns
- Consensus/coordination algorithms

#### 6. Advanced Agent Patterns (LOW PRIORITY - Nice to Have)
**Missing:**
- Long-running agents (background workers)
- Event-driven agents (webhooks, queues)
- Stateful agents (session persistence)
- Agent composition (agent calling agent)
- Agent delegation patterns
- Retry/circuit breaker patterns

**What users need:**
- Advanced agent patterns skill
- Event-driven architecture guide
- State management patterns

---

## 11. Recommended Additions

### Tier 1: Essential (Agent SDK + MCP Server Basics)

**New Skills:**
1. **`building-agent-sdk-apps`** — Quickstart for Python/TypeScript Agent SDK projects
   - Project scaffolding
   - Tool creation patterns
   - Testing Agent SDK apps
   - Local development workflow

2. **`creating-mcp-servers`** — Build MCP servers from scratch
   - Scaffolding new servers
   - Implementing transports (stdio/HTTP/SSE)
   - Tool/resource/prompt patterns
   - Testing/publishing workflow

3. **`agent-sdk-testing`** — Testing patterns for Agent SDK applications
   - Unit testing tools
   - Integration testing agents
   - Mocking/stubbing patterns
   - CI/CD integration

**New Commands:**
1. **`/clavain:new-agent-sdk-app`** — Scaffold Python or TypeScript Agent SDK project
2. **`/clavain:new-mcp-server`** — Scaffold MCP server (stdio/HTTP/SSE)
3. **`/clavain:test-mcp-server`** — Test MCP server locally

**Templates (new directory):**
```
templates/
├── agent-sdk/
│   ├── python-starter/
│   │   ├── pyproject.toml
│   │   ├── src/agent.py
│   │   ├── src/tools.py
│   │   └── tests/
│   └── typescript-starter/
│       ├── package.json
│       ├── src/agent.ts
│       ├── src/tools.ts
│       └── tests/
└── mcp-server/
    ├── stdio-python/
    ├── stdio-typescript/
    ├── http-python/
    └── sse-typescript/
```

### Tier 2: Production-Ready (Deployment + Monitoring)

**New Skills:**
4. **`deploying-agents`** — Deploy Agent SDK apps to production
   - Docker/containerization
   - Serverless deployment (AWS Lambda, Cloud Run)
   - Environment configuration
   - Secrets management
   - Health checks

5. **`agent-observability`** — Monitor agents in production
   - Logging patterns
   - Metrics collection
   - Error tracking
   - Cost monitoring
   - Dashboards

**New Commands:**
4. **`/clavain:deploy-agent`** — Deploy agent to cloud platform
5. **`/clavain:setup-monitoring`** — Configure logging/metrics/alerts

**Templates:**
```
templates/
└── deployment/
    ├── docker/
    │   └── Dockerfile
    ├── serverless/
    │   ├── aws-lambda/
    │   ├── gcp-cloud-run/
    │   └── azure-functions/
    ├── k8s/
    │   └── deployment.yaml
    └── monitoring/
        ├── prometheus/
        ├── datadog/
        └── cloudwatch/
```

### Tier 3: Advanced (Multi-Agent + Patterns)

**New Skills:**
6. **`multi-agent-systems`** — Building distributed agent systems
   - Agent coordination patterns
   - Work distribution
   - State synchronization
   - Load balancing

7. **`advanced-agent-patterns`** — Event-driven, stateful, long-running agents
   - Background workers
   - Webhook handlers
   - Session persistence
   - Retry/circuit breakers

**New Agents:**
- **deployment-architect** — Reviews deployment plans for agents
- **observability-engineer** — Reviews monitoring/logging setups
- **cost-optimizer** — Reviews agent API usage for cost efficiency

---

## 12. Comparison: What's Here vs. What's Needed

| Capability | Clavain Has | Gap |
|------------|-------------|-----|
| **Agent-native design patterns** | ✅ Comprehensive | - |
| **Tool design philosophy** | ✅ Excellent | - |
| **Agent SDK project scaffolding** | ❌ No | High |
| **Agent SDK quickstart** | ❌ No | High |
| **MCP server creation** | ❌ No guidance | High |
| **MCP server templates** | ❌ No | High |
| **Agent testing patterns** | ✅ Philosophy | ⚠️ No SDK-specific tests |
| **Deployment templates** | ❌ No | Medium |
| **Monitoring/observability** | ❌ No | Medium |
| **Multi-agent coordination** | ✅ agent-mail | ⚠️ Limited to Claude Code ecosystem |
| **Production readiness** | ❌ No checklist | Medium |
| **Cost tracking** | ❌ No | Medium |
| **Claude Code plugin dev** | ✅ Excellent | - |
| **Skill/command creation** | ✅ Strong | - |
| **Hook system** | ✅ Documented | - |

**Legend:**
- ✅ Comprehensive coverage
- ⚠️ Partial coverage
- ❌ Missing

---

## 13. Actionable Next Steps

### Immediate (Tier 1)
1. **Create `building-agent-sdk-apps` skill** with Python/TypeScript quickstarts
2. **Create `creating-mcp-servers` skill** with stdio/HTTP/SSE examples
3. **Add Agent SDK templates** to `templates/agent-sdk/`
4. **Add MCP server templates** to `templates/mcp-server/`
5. **Create `/clavain:new-agent-sdk-app` command** (scaffolder)
6. **Create `/clavain:new-mcp-server` command** (scaffolder)

### Short-term (Tier 2)
7. **Create `deploying-agents` skill** with Docker/serverless patterns
8. **Create `agent-observability` skill** with logging/metrics
9. **Add deployment templates** to `templates/deployment/`
10. **Create `/clavain:deploy-agent` command**
11. **Create production readiness checklist**

### Medium-term (Tier 3)
12. **Create `multi-agent-systems` skill** (beyond subagents)
13. **Create `advanced-agent-patterns` skill** (event-driven, stateful)
14. **Add deployment/observability review agents**

### Documentation
15. **Update README** to clarify Agent SDK vs. Claude Code plugin focus
16. **Add "Building Agent Rigs" section** to AGENTS.md
17. **Create `docs/agent-sdk-quickstart.md`** walkthrough
18. **Create `docs/mcp-server-guide.md`** step-by-step

---

## 14. Conclusion

**Clavain's Strength:** Architectural wisdom, workflow discipline, and Claude Code plugin infrastructure.

**Clavain's Gap:** Practical implementation tooling for standalone Agent SDK applications and MCP servers.

**The Missing Layer:** Users who want to "fully roll their own custom agent rig" need:
1. Agent SDK project templates (Python/TypeScript)
2. MCP server scaffolding and examples
3. Deployment automation
4. Production monitoring/observability
5. Testing frameworks for Agent SDK apps
6. Cost tracking/optimization patterns

**Current State:** Clavain teaches you HOW to think about agent-native design but doesn't give you the starter kits, deployment pipelines, or monitoring templates to ship production agent systems.

**Recommendation:** Add Tier 1 capabilities (Agent SDK + MCP Server basics) to bridge the gap between architectural knowledge and working code.
