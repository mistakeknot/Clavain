# Clavain Modpack — Plugin Audit

Audited 2026-02-08. 32 plugins enabled, 1 local dev.

## Verdict Summary

| Action | Count | Plugins |
|--------|-------|---------|
| **KEEP** | 16 | clavain, interclode, interpeer, interdoc, gurgeh-plugin, auracoil, tool-time, context7, agent-sdk-dev, plugin-dev, serena, gopls-lsp, pyright-lsp, typescript-lsp, rust-analyzer-lsp, security-guidance |
| **KEEP** (user pref) | 1 | explanatory-output-style |
| **DISABLE** | 8 | code-review, code-simplifier, commit-commands, feature-dev, claude-md-management, frontend-design, pr-review-toolkit, hookify |
| **EVALUATE** | 3 | tldrs, tldr-swinton, tuivision |
| **CONDITIONAL** | 3 | supabase, vercel, github |

## Detailed Audit

### DISABLE — Redundant with Clavain

| Plugin | Components | Clavain Equivalent | Why Disable |
|--------|-----------|-------------------|-------------|
| **code-review** | 1 cmd (`/review-pr`) | `/review` + `/flux-drive` + 15 review agents | Clavain's review is multi-agent with convergence mapping. The official plugin is a single-pass PR review. |
| **pr-review-toolkit** | 6 agents, 1 cmd | Clavain has equivalent agents: `code-simplicity-reviewer`, `security-sentinel`, `pattern-recognition-specialist`, `architecture-strategist`, `concurrency-reviewer`, `plan-reviewer` | Same agents by different names. Having both means duplicate agents in the Task tool roster, confusing routing. Clavain's versions are opinionated and integrated with flux-drive. |
| **code-simplifier** | 1 agent | `code-simplicity-reviewer` agent | Direct duplicate. |
| **commit-commands** | 3 cmds (`/commit`, `/clean-gone`, `/commit-push-pr`) | `landing-a-change` skill | Clavain's landing skill includes commit but also verification, issue updates, and push. `/clean-gone` is useful but niche — if needed, make it a Clavain command. |
| **feature-dev** | 3 agents, 1 cmd (`/feature-dev`) | `/work` + `/lfg` + `/brainstorm` + explore agents | Clavain's workflow is more comprehensive: brainstorm → plan → execute → review → ship. |
| **claude-md-management** | 1 skill, 1 cmd | `engineering-docs` skill + AGENTS.md conventions | Clavain already manages CLAUDE.md/AGENTS.md with its own opinions. |
| **frontend-design** | 1 skill | `distinctive-design` skill | Same skill, Clavain's is customized. |
| **hookify** | 1 skill, 1 agent, 4 cmds, hooks | Clavain manages hooks directly | Already OFF. Clavain owns hook management. Hookify would conflict. |
| ~~explanatory-output-style~~ | ~~hooks only~~ | ~~Could be a Clavain hook option~~ | **KEPT — user preference.** Injects educational insights output style. |

### KEEP — Complementary

| Plugin | Why Keep |
|--------|----------|
| **clavain** | The modpack itself. |
| **interclode** | Codex CLI dispatch. Clavain's codex-first depends on it. |
| **interpeer** | Cross-AI review (Oracle/GPT). Distinct from Clavain's Claude-only agents. |
| **interdoc** | AGENTS.md generation. Different from Clavain's engineering-docs (which captures solutions, not generates AGENTS.md). |
| **gurgeh-plugin** | Codebase-aware T1 agents (fd-architecture, fd-code-quality, fd-security, fd-performance, fd-user-experience). Used by flux-drive. |
| **auracoil** | GPT-5.2 review of AGENTS.md specifically. Different scope from interpeer. |
| **tool-time** | Tool usage analytics. Nothing in Clavain does this. |
| **context7** | Runtime doc fetching MCP server. Also declared in Clavain's plugin.json. |
| **agent-sdk-dev** | Agent SDK scaffolding (`/new-sdk-app`, verifier agents). Fills a gap Clavain doesn't cover. |
| **plugin-dev** | Plugin development (7 skills, 3 agents). More comprehensive than Clavain's `developing-claude-code-plugins`. Includes agent-creator, skill-reviewer, plugin-validator. |
| **serena** | Semantic code analysis via LSP. Different tool class entirely. |
| **gopls-lsp** | Go language server. Infrastructure, not workflow. |
| **pyright-lsp** | Python type checking. Infrastructure. |
| **typescript-lsp** | TypeScript language server. Infrastructure. |
| **rust-analyzer-lsp** | Rust language server. Infrastructure. |
| **security-guidance** | Security warning hooks on file edits. Complements Clavain's `security-sentinel` agent (which reviews, doesn't prevent). |

### EVALUATE — Decide Based on Usage

| Plugin | What It Does | Keep If... |
|--------|-------------|------------|
| **tldrs** | Token-efficient code reconnaissance. 84% token savings with semantic search, diff-context, symbol analysis. | You frequently hit context limits or want cheaper exploration. Try disabling for a week and see if you miss it. |
| **tldr-swinton** | The underlying tool for tldrs. Required if tldrs stays. | Keep if tldrs stays, disable if tldrs goes. |
| **tuivision** | TUI visual testing with Playwright for terminals. | You're actively building terminal apps. Otherwise disable. |

### CONDITIONAL — Domain-Specific

| Plugin | Keep When... |
|--------|-------------|
| **supabase** | Working on projects with Supabase backends. Disable otherwise. |
| **vercel** | Deploying to Vercel. Disable otherwise. |
| **github** | Unclear what this adds beyond `gh` CLI. Investigate. |

## Plugin Count After Audit

| Status | Before | After |
|--------|--------|-------|
| Enabled | 32 | 17-20 (depending on evaluate/conditional) |
| Disabled | 1 | 13-16 |

## Notes

- **explanatory-output-style**: The hook logic could be merged into Clavain as a modpack setting. It currently injects an educational output style. If you want this, add it as a config option in Clavain's session-start.sh rather than a separate plugin.
- **commit-commands**: The `/commit` shortcut is convenient. Consider adding a thin `/commit` command to Clavain that delegates to `landing-a-change` with a "just commit" flag.
- **pr-review-toolkit**: The biggest overlap. 6 agents with near-identical function to Clavain agents. Keeping both doubles the agent roster and causes routing confusion.
