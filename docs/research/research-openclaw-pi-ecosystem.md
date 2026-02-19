# Research: Pi Agent Harness & OpenClaw Ecosystem

**Date:** 2026-02-19
**Scope:** Architecture and ecosystem analysis of Pi (coding agent harness), OpenClaw (personal AI assistant), and their relationship to Claude Code and Codex CLI.

---

## 1. Pi: The Minimal Coding Agent Harness

### Origin & Creator

**Pi** was created by **Mario Zechner** ([@badlogicgames](https://x.com/badlogicgames)), the developer behind the LibGDX game framework. He built Pi in late 2025 out of frustration with Claude Code's growing complexity — describing it as "a spaceship with 80% of functionality I have no use for." His core complaints about existing harnesses:

- System prompts and tools change on every release, breaking workflows and altering model behavior
- Existing harnesses inject context behind the scenes, making genuine context engineering "extremely hard or impossible"
- Sub-agents provide "zero visibility into what that sub-agent does — a black box within a black box"
- Plan Mode forces approval of excessive command invocations with poor observability

### Design Philosophy

Pi is built on a radical minimalism thesis: **context engineering is paramount**, and the way to achieve it is to minimize everything entering the model's context window.

Key architectural decisions:

| Decision | Rationale |
|----------|-----------|
| **4 tools only** (read, write, edit, bash) | Models are already RL-trained on tools with similar schemas; bash covers file ops, search, and execution |
| **~300-word system prompt** | Frontier models don't need 10,000-token system prompts; smaller prompts = better prompt caching |
| **No sub-agents** | Mid-session sub-agents signal you "didn't plan ahead"; better to gather context in a separate session |
| **No plan mode** | You can just ask the agent to think without modifying files; file-based plans (markdown) are version-controllable |
| **No MCP support** (original) | Popular MCP servers consume 7-9% of context before any work begins |
| **No background bash** | Use tmux instead for better observability |
| **YOLO mode by default** | Security measures in coding agents are largely "security theater" once code execution exists |

### Repository & Package Architecture

Pi lives in the **[badlogic/pi-mono](https://github.com/badlogic/pi-mono)** monorepo — a TypeScript project using npm workspaces with lockstep versioning (all packages share the same version, currently ~0.52.x).

The architecture is a strict three-tier dependency graph with no circular dependencies:

```
Foundation Layer (no internal deps):
  @mariozechner/pi-ai       — unified multi-provider LLM API (Anthropic, OpenAI, Google, xAI, Groq, Cerebras, OpenRouter, any OpenAI-compatible)
  @mariozechner/pi-tui      — terminal rendering (differential updates, component architecture, also shared by web UI)

Core Framework Layer:
  @mariozechner/pi-agent-core — agent loop, tool execution, state management (depends on pi-ai only)

Application Layer:
  @mariozechner/pi-coding-agent — full coding agent with tools, sessions, extensions (depends on all three below)
  @mariozechner/pi-mom          — Slack bot embedding (wraps pi-coding-agent via delegation)
  @mariozechner/pi-web-ui       — browser components (depends on pi-ai + pi-tui)
  @mariozechner/pi-pods          — vLLM pod management (depends on pi-agent-core only)
  @mariozechner/pi-proxy         — standalone CORS/auth proxy (zero internal deps)
```

Dependency graph:
```
pi-ai <── pi-agent-core <── pi-coding-agent <── pi-mom
pi-tui <──────────────────── pi-coding-agent
pi-tui <──────────────────── pi-web-ui
pi-ai  <──────────────────── pi-web-ui
```

### The Agent Loop

The core agent loop in `pi-agent-core` is intentionally minimal — a simple while loop that:

1. Streams an LLM response
2. If no tool calls, breaks (done)
3. Executes tools sequentially
4. Adds results to context
5. Repeats

```
AgentSession (pi-coding-agent) → Agent class (pi-agent-core) → agentLoop() → AgentTool.execute()
```

Key design principles:
- All agent state held in a single `AgentState` object for easy persistence and inspection
- UI components subscribe to events rather than polling (reactive updates)
- Queue-based control: user input during execution is queued and delivered at safe points, preventing race conditions
- The loop emits events for everything, making it easy to build reactive UIs

### Modes of Operation

Pi runs in four modes:
1. **Interactive** — full TUI with session management
2. **Print/JSON** — single-shot execution for scripting
3. **RPC** — JSON protocol over stdin/stdout for non-Node integrations
4. **SDK** — direct embedding in applications (this is how OpenClaw uses it)

---

## 2. Pi's Extension System

Pi's extensibility is its central architectural feature. The system has four layers:

### 2.1 TypeScript Extensions

Extensions are TypeScript modules loaded via [jiti](https://github.com/unjs/jiti) (no compilation needed). Each exports a default function receiving an `ExtensionAPI`:

```typescript
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
export default function (pi: ExtensionAPI) { ... }
```

**Placement & Discovery:**
- `~/.pi/agent/extensions/*.ts` — global
- `.pi/extensions/*.ts` — project-local
- Hot-reload via `/reload` command

**Key capabilities:**

1. **Lifecycle Events** — extensions subscribe to a rich event system:
   - Session events: `session_start`, `session_before_switch`/`session_switch`, `session_before_compact`/`session_compact`, `session_shutdown`
   - Agent events: `before_agent_start`, `agent_start`/`agent_end`, `turn_start`/`turn_end`
   - Tool events: `tool_call` (can block), `tool_execution_start`/`tool_execution_end`, `tool_result` (can modify)
   - Context event: `context` — fires per turn, can modify the message list sent to the model
   - Input events: `input` (can intercept user prompts), `model_select`

2. **Tool Registration** — extensions can register new LLM-callable tools with TypeBox schemas, custom rendering for TUI, and abort signal support

3. **Command Registration** — `/name` slash commands with handler functions

4. **UI Helpers** — `ctx.ui.notify()`, `ctx.ui.confirm()`, `ctx.ui.input()`, `ctx.ui.select()`, `ctx.ui.setStatus()`, `ctx.ui.setWidget()`, `ctx.ui.custom()` — all of which are no-ops in non-interactive modes

5. **State Persistence** — `pi.appendEntry(type, data)` persists extension data in the session file, surviving restarts

6. **Dynamic Context** — extensions can inject messages before each turn, filter message history, implement RAG, or build long-term memory

### 2.2 Skills

Skills are capability packages with instructions and tools, loaded on demand. This enables **progressive disclosure** — skills aren't in the context until needed, preserving the prompt cache and keeping context lean.

### 2.3 Prompt Templates

Reusable prompts stored as Markdown files. Type `/name` to expand them. Placed in:
- `~/.pi/agent/prompts/` (global)
- `.pi/prompts/` (project-local)
- The default system prompt can be replaced via `.pi/SYSTEM.md` or appended to via `APPEND_SYSTEM.md`

### 2.4 Pi Packages

Extensions, skills, prompt templates, and themes can be bundled into **Pi Packages** — distributable via npm or git:

```bash
pi install npm:@foo/pi-tools
pi install git:github.com/badlogic/pi-doom
```

Packages declare resources in `package.json` under the `pi` key. Version pinning, update, and list management are built in.

**Security note:** Extensions and packages run with full system permissions. There is no sandboxing — this is intentional per Pi's "YOLO mode" philosophy.

---

## 3. OpenClaw: The Personal AI Agent

### History

**OpenClaw** was created by **Peter Steinberger**, the Austrian developer who founded PSPDFKit (enterprise document SDK, sold to Insight Partners). The project went through three name changes:

1. **Clawdbot** (Nov 2025) — named after the lobster monster in Claude Code's loading screen. Anthropic contacted Steinberger about trademark similarity to "Claude"
2. **Moltbot** (Jan 27, 2026) — keeping the lobster theme. During the GitHub rename, crypto scammers hijacked the released @clawdbot handle within ~10 seconds, launched a fake $CLAWD token that pumped to $16M market cap before crashing
3. **OpenClaw** (Jan 30, 2026) — final name. Trademark searches confirmed clear

### Viral Growth

OpenClaw became one of the fastest-growing open-source projects in history:
- 9,000 to 60,000+ GitHub stars in days
- Reached 100K stars in ~2 days (Jan 29-30, 2026) — peak growth of 710 stars/hour
- Eventually 145,000+ stars and 20,000+ forks

### What OpenClaw Is

OpenClaw is a **self-hosted, model-agnostic AI agent runtime and message router**. It runs as a long-running Node.js service that connects chat platforms to an AI agent that can execute real-world tasks. Key characteristics:

- **Multi-channel inbox** — WhatsApp, Telegram, Slack, Discord, Signal, iMessage, Google Chat, Microsoft Teams, Matrix, and more
- **Persistent long-term memory** — context stored locally, adapts to user habits
- **Model-agnostic** — works with Claude, OpenAI, DeepSeek, local Ollama instances
- **Proactive intelligence** — recurring tasks, condition monitoring, unsolicited suggestions
- **Extensible skills ecosystem** — hundreds of community-built skills; the AI can generate and install new skills autonomously

### How OpenClaw Uses Pi

OpenClaw consumes Pi as an **embedded SDK**, not as a subprocess or RPC client. Specifically:

1. OpenClaw directly imports and instantiates Pi's `AgentSession` via `createAgentSession()`
2. All four Pi packages are pinned at the same version in OpenClaw's `package.json`
3. Pi provides the core agent loop, LLM provider abstraction, tool execution, and session persistence
4. OpenClaw adds on top: messaging gateway, multi-channel routing, channel-specific tools, policy enforcement, workspace files, and skill management

**OpenClaw's additions to Pi's tool set:**
- Messaging tools (send, reply across channels)
- Browser, canvas, and cron tools
- Channel-specific tools (Discord, Telegram, Slack, WhatsApp)
- Tool filtering by policy, schema cleaning for provider quirks
- Claude Code parameter compatibility aliases (e.g., `file_path` to `path`, `old_string` to `oldText`)

**OpenClaw's context engineering on top of Pi:**
- Workspace files: `SOUL`, `IDENTITY`, `AGENTS.default`, `TOOLS`, `MEMORY`, `USER`, and runtime templates (`BOOT`/`BOOTSTRAP`/`HEARTBEAT`)
- Context pruning extensions (silently trimming oversized tool results)
- Custom compaction (replacing Pi's default summarization with a multi-stage pipeline preserving file operation history and tool failure data)

### ClawHub (Skill Registry)

**ClawHub** is OpenClaw's minimal skill registry. With ClawHub enabled, the agent can search for skills automatically and pull in new ones as needed — similar to how Claude Code's plugin marketplace works, but for OpenClaw's messaging-gateway context.

### Moltbook

One notable product built on OpenClaw: **Moltbook** — a social network designed exclusively for AI agents, where agents generate posts, comment, argue, joke, and upvote each other. Humans may observe but cannot participate.

### Acquisition by OpenAI

On February 14, 2026, Peter Steinberger announced he was joining **OpenAI** to "drive the next generation of personal agents." The OpenClaw project was transferred to an independent open-source foundation. Sam Altman confirmed the hire.

---

## 4. oh-my-pi: A Notable Fork

**[can1357/oh-my-pi](https://github.com/can1357/oh-my-pi)** (`omp`) is a batteries-included fork of pi-mono that adds features Mario Zechner deliberately excluded:

- **Subagents** — with full output access via `agent://<id>` resources, isolated execution in git worktrees, and in-process task execution
- **LSP integration** — 40+ language configs, workspace diagnostics, hover docs, symbol references, code actions
- **Model roles** — role-based routing (`default`, `smol`, `slow`, `plan`, `commit`) with auto-resolution and per-role overrides
- **TTSR** (Time-Traveling Stream Rules) — a novel extension mechanism

oh-my-pi demonstrates that Pi's minimal architecture successfully supports significant feature additions without forking the core loop.

---

## 5. Relationship to Claude Code and Codex CLI

### Architectural Comparison

| Aspect | Pi | Claude Code | Codex CLI |
|--------|-----|-------------|-----------|
| **Core philosophy** | Minimal, user-controlled context | Full-featured "spaceship" | Cloud-scalable + local |
| **System prompt** | ~300 words | Thousands of tokens, changes per release | AGENTS.md-driven |
| **Default tools** | 4 (read, write, edit, bash) | ~15+ (including sub-agents, search, MCP) | Minimal set + sandboxed bash |
| **Extension model** | TypeScript extensions, skills, packages | Hooks + skills + MCP plugins | MCP + AGENTS.md |
| **Source** | Open (MIT) | Closed | Open |
| **Execution** | Local, terminal-first | Local, terminal-first | Cloud sandboxed + local CLI |
| **Sub-agents** | Rejected (use bash to invoke self) | Built-in | Native parallel tasks |
| **MCP support** | None by default (rejected) | Full STDIO + HTTP | Full + can serve as MCP server |
| **Session storage** | Local files | Local transcripts | Cloud-based |
| **Security model** | YOLO by default | Permission prompts (manual approval) | Sandboxed, network off by default |

### Philosophical Divergence

Pi and Claude Code represent opposite ends of the agent harness design spectrum:

- **Pi** bets that frontier models don't need hand-holding — a 300-word system prompt and 4 tools are sufficient when you control context precisely. The extension system exists so you can build what you need, not so the harness can ship everything.

- **Claude Code** bets on a comprehensive out-of-box experience with MCP, sub-agents, plan mode, memory, skills, hooks, and deep tooling. The cost is a large, opaque system prompt and frequent breaking changes.

- **Codex CLI** takes a middle path — minimal local tools but cloud-native parallel execution. Its open-source nature and AGENTS.md convention share Pi's "user controls the context" philosophy, but its cloud sandbox approach is architecturally different from both.

### What Pi Demonstrates

Pi's competitive performance on Terminal-Bench 2.0 (with Claude Opus 4.5) against Cursor, Codex, and Windsurf validates the thesis that **minimal tooling performs comparably to complex harnesses**. The key insight: context engineering matters more than tool count.

### Extension System Comparison

| Capability | Pi Extensions | Claude Code Plugins | Codex CLI |
|-----------|---------------|-------------------|-----------|
| Language | TypeScript (jiti, no compile) | JSON config + shell scripts | AGENTS.md (declarative) |
| Lifecycle hooks | ~20 events (session, agent, tool, input, context) | ~6 hook events (PreToolUse, PostToolUse, Notification, etc.) | None (MCP only) |
| Tool registration | Full TypeScript with TypeBox schemas | MCP servers only (no native tool registration) | MCP servers |
| Context manipulation | `context` event can rewrite messages per turn | Not possible (system prompt is opaque) | Not possible |
| Dynamic loading | Hot-reload via `/reload` | Session restart required | N/A |
| Distribution | npm/git packages | GitHub-based marketplace | N/A |
| Sandboxing | None (full system access) | Hook scripts sandboxed by approval system | Cloud sandbox |

Pi's extension system is significantly more powerful than Claude Code's plugin/hook system because extensions can **intercept and modify the context sent to the model**, register native tools, and react to fine-grained lifecycle events. Claude Code's hooks are primarily observational (pre/post tool use) with limited ability to modify agent behavior.

---

## 6. Relevance to Clavain / Interverse

### Patterns Worth Noting

1. **Layered package architecture** — Pi's strict `pi-ai` -> `pi-agent-core` -> `pi-coding-agent` layering with no circular dependencies is a clean model for structuring agent infrastructure. Compare to Interverse's flatter plugin structure.

2. **Context engineering as first principle** — Pi's success with a 300-word system prompt suggests that Clavain's context management could benefit from more aggressive pruning and progressive disclosure (load skills on demand, not at session start).

3. **Extension event model** — Pi's ~20 lifecycle events (especially `context` for per-turn message rewriting and `tool_call` for gating) are more expressive than Claude Code's hook system. If Clavain builds agent orchestration, consider whether it needs richer event hooks.

4. **SDK embedding pattern** — OpenClaw's approach of consuming Pi via `createAgentSession()` (SDK mode) rather than subprocess/RPC is architecturally cleaner for tight integration. Relevant if Clavain ever needs to embed agent loops.

5. **Workspace files convention** — OpenClaw's `SOUL`, `IDENTITY`, `TOOLS`, `MEMORY`, `USER`, `BOOT`/`BOOTSTRAP`/`HEARTBEAT` workspace files for per-agent configuration is a structured alternative to monolithic AGENTS.md files.

6. **Community fork viability** — oh-my-pi demonstrates that a minimal core with clean extension points enables substantial feature additions (LSP, subagents, model roles) without forking the core loop. This validates the "small core, rich extensions" architecture.

### Ecosystem Map

```
Mario Zechner ─────── pi-mono (agent toolkit, MIT, ~9K stars)
                          │
                          ├── Pi Coding Agent (terminal harness)
                          ├── Pi Mom (Slack bot)
                          ├── Pi Pods (vLLM management)
                          └── Pi Web UI
                          │
                ┌─────────┴──────────┐
                │                    │
        OpenClaw (145K+ stars)    oh-my-pi (fork)
        Peter Steinberger         can1357
        → acquired by OpenAI      (adds LSP, subagents,
        → foundation-maintained    model roles)
                │
                ├── ClawHub (skill registry)
                ├── Moltbook (agent social network)
                └── Multi-channel gateway
```

---

## Sources

- [Mario Zechner's blog post on building Pi](https://mariozechner.at/posts/2025-11-30-pi-coding-agent/)
- [Pi website (shittycodingagent.ai)](https://shittycodingagent.ai/)
- [pi-mono GitHub repository](https://github.com/badlogic/pi-mono)
- [Pi extension system documentation](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/extensions.md)
- [Pi package architecture (DeepWiki)](https://deepwiki.com/badlogic/pi-mono/1.1-package-architecture)
- [OpenClaw GitHub repository](https://github.com/openclaw/openclaw)
- [OpenClaw Wikipedia article](https://en.wikipedia.org/wiki/OpenClaw)
- [OpenClaw/Pi integration docs](https://github.com/openclaw/openclaw/blob/main/docs/pi.md)
- [Nader Dabit: How to Build a Custom Agent Framework with PI](https://nader.substack.com/p/how-to-build-a-custom-agent-framework)
- [Syntax Podcast #976: Pi - The AI Harness That Powers OpenClaw](https://syntax.fm/976)
- [oh-my-pi (can1357 fork)](https://github.com/can1357/oh-my-pi)
- [awesome-pi-agent curated list](https://github.com/qualisero/awesome-pi-agent)
- [CNBC: OpenClaw creator joining OpenAI](https://www.cnbc.com/2026/02/15/openclaw-creator-peter-steinberger-joining-openai-altman-says.html)
- [VentureBeat: OpenAI's acquisition of OpenClaw](https://venturebeat.com/technology/openais-acquisition-of-openclaw-signals-the-beginning-of-the-end-of-the)
- [Pi npm package](https://www.npmjs.com/package/@mariozechner/pi-coding-agent)
