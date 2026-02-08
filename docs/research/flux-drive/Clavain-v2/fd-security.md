---
agent: fd-security
tier: 1
issues:
  - id: P0-1
    severity: P0
    section: "Upstream Sync Workflow"
    title: "AI-driven auto-merge of untrusted upstream content enables prompt injection into plugin skills"
  - id: P1-1
    severity: P1
    section: "Hook Scripts"
    title: "JSON injection via unescaped variables in agent-mail-register.sh heredoc"
  - id: P1-2
    severity: P1
    section: "Upstream Sync Workflow"
    title: "sync.yml grants broad Bash tool access to AI agent processing untrusted upstream content"
  - id: P2-1
    severity: P2
    section: "Hook Scripts"
    title: "dotfiles-sync.sh hardcodes absolute path and runs external script without integrity check"
  - id: P2-2
    severity: P2
    section: "Upstream Check Workflow"
    title: "Upstream commit messages rendered unescaped in GitHub issue body via jq"
improvements:
  - id: IMP-1
    title: "Add human review gate before merging AI-generated sync PRs"
    section: "Upstream Sync Workflow"
  - id: IMP-2
    title: "Use jq for JSON construction in agent-mail-register.sh instead of heredoc interpolation"
    section: "Hook Scripts"
  - id: IMP-3
    title: "Scope sync.yml workflow permissions more tightly and pin action versions"
    section: "Upstream Sync Workflow"
  - id: IMP-4
    title: "Add CODEOWNERS protection for hooks/ and .github/workflows/"
    section: "General"
verdict: needs-changes
---

# Security Review: Clavain Plugin

## Summary

Clavain is a Claude Code plugin consisting of markdown skills, agents, commands, bash hook scripts, two MCP server configurations, and a GitHub Actions-based upstream sync system. The primary attack surface is the upstream sync pipeline, which uses AI agents (Claude Code + Codex CLI) to automatically merge content from 4 upstream repositories into plugin files that are then injected as system context into Claude Code sessions. A secondary concern is JSON injection in a hook script's heredoc construction.

The plugin itself has no runtime code execution beyond bash hooks -- it is primarily markdown content that influences LLM behavior. This means the threat model centers on **prompt injection via content supply chain**, not traditional code vulnerabilities.

## Threat Model Context

**What the project is:** A Claude Code plugin that loads markdown files as system prompts/skills to guide agent behavior. The `session-start.sh` hook injects content from `skills/using-clavain/SKILL.md` into every session as `additionalContext` wrapped in `<EXTREMELY_IMPORTANT>` tags.

**Attack surface:**
1. **Hook scripts** -- executed automatically on session start/end; outputs become LLM system context
2. **MCP servers** -- context7 (external HTTPS, read-only docs API) and agent-mail (localhost HTTP, inter-agent messaging)
3. **Upstream sync** -- GitHub Actions workflow that clones 4 external repos and uses AI to merge their content into Clavain skills/agents/commands
4. **Plugin content itself** -- markdown files that become LLM instructions

**Trust boundaries:**
- Upstream repo maintainers are semi-trusted (open-source authors whose repos Clavain forks from)
- GitHub Actions environment has access to ANTHROPIC_API_KEY and OPENAI_API_KEY secrets
- The local user running Claude Code with the plugin installed is fully trusted
- The agent-mail MCP server is localhost-only (127.0.0.1:8765)

---

## Section-by-Section Review

### 1. Hook Scripts

#### session-start.sh (`/root/projects/Clavain/hooks/session-start.sh`)

**Purpose:** Reads `skills/using-clavain/SKILL.md`, JSON-escapes it, and outputs it as `additionalContext` in the hook's JSON response. Also checks staleness of upstream versions file.

**Analysis:**
- Lines 16-24: The `escape_for_json()` function uses bash parameter substitution to escape backslash, double-quote, newline, carriage return, and tab. This covers the necessary JSON special characters.
- Line 11: Uses `cat` to read from a local file within the plugin directory. The path is constructed from `PLUGIN_ROOT` which is derived from the script's own location -- no user-controlled input here.
- Lines 31-39: Upstream staleness check reads file modification time via `stat`. No external input involved.
- Line 46: The escaped content is interpolated into a heredoc. Since the content source is a local file within the plugin repo (not user input), this is acceptable. However, if that file were compromised (see P0-1), the injected content would become system-level instructions.

**Verdict:** Sound for its purpose. The risk is upstream to it (what gets written to SKILL.md), not in the script itself.

#### agent-mail-register.sh (`/root/projects/Clavain/hooks/agent-mail-register.sh`)

**Purpose:** Registers the current session with the MCP Agent Mail server on localhost. Sends a JSON-RPC request with session/project info and parses the response for display.

**Analysis:**
- Lines 39-54: The heredoc `PAYLOAD` is **not quoted** (it uses `<<PAYLOAD` not `<<'PAYLOAD'`), meaning bash performs variable expansion inside it. The variables `${session_id}` and `${PROJECT_DIR}` are interpolated directly into JSON without JSON-escaping.
- Line 26: `session_id` is extracted from stdin via Python's `json.load()`, which returns a string. If the input JSON contains a `session_id` value with double-quotes, backslashes, or newlines, those will be inserted raw into the JSON payload, breaking the JSON structure or enabling injection.
- Line 47: `PROJECT_DIR` comes from `CLAUDE_PROJECT_DIR` environment variable. Directory paths containing double-quotes (rare but possible on some systems) would break the JSON.
- Lines 93-101: The response from Agent Mail is processed through Python and then through the same `escape_for_json()` function before being output. This is the safe path.
- **Mitigant:** The target is localhost Agent Mail (127.0.0.1:8765), so the blast radius of malformed JSON is limited to a failed registration, not a security exploit. But the principle matters.

#### dotfiles-sync.sh (`/root/projects/Clavain/hooks/dotfiles-sync.sh`)

**Purpose:** On SessionEnd, runs an external dotfiles sync script if it exists.

**Analysis:**
- Line 14: Hardcoded path `/root/projects/dotfiles-sync/sync-dotfiles.sh`. This is host-specific and only works on the author's machine.
- Line 17: Checks `-x` (executable) before running -- good.
- Line 22: Output goes to `/var/log/dotfiles-sync.log`. The `|| true` means failures are swallowed silently.
- **Risk:** If someone gained write access to `/root/projects/dotfiles-sync/sync-dotfiles.sh`, they could execute arbitrary code on every session end. However, this requires local root access, which is already game over.

### 2. MCP Servers

#### context7 (`https://mcp.context7.com/mcp`)

- External HTTPS endpoint. Read-only documentation lookup. No credentials sent. Acceptable risk -- the worst case is the service returns misleading documentation, which is a generic concern for any external API.

#### agent-mail (`http://127.0.0.1:8765/mcp`)

- Localhost HTTP (no TLS). This is acceptable for a local-only service. The agent-mail server must be running independently for this to function.
- The `AGENT_MAIL_URL` environment variable (line 16 of agent-mail-register.sh) allows overriding the URL, which could redirect requests to a remote server. However, this requires the attacker to control the user's environment variables -- equivalent to full local access.
- HTTP (not HTTPS) means no transport encryption, but on loopback this is standard practice.

### 3. Upstream Sync Workflow (`/root/projects/Clavain/.github/workflows/sync.yml`)

This is the most security-critical component in the project.

**What it does:**
1. Runs weekly on cron or manual dispatch
2. Installs Codex CLI with `OPENAI_API_KEY`
3. Launches Claude Code with a long prompt instructing it to clone upstream repos, diff them, and merge changes using Codex
4. Creates a PR with the merged changes

**Tool allowlist (line 112):**
```
Read,Write,Edit,Bash(git:*),Bash(codex:*),Bash(ls:*),Bash(cat:*),Bash(mkdir:*),Bash(cp:*),Bash(echo:*)
```

**Analysis:**

- **Prompt injection via upstream content (P0-1):** The workflow instructs Claude to `cat` upstream file content and embed it in a `codex exec -p "..."` command. If an upstream repo maintainer inserts prompt injection payloads into their markdown files (e.g., instructions that override the merge prompt, or that instruct the AI to write malicious content to other files), the AI agent would process those instructions. The merged content then becomes part of Clavain skills/agents that are injected as system context into every Claude Code session. This is a **content supply chain attack** -- the chain is: upstream repo -> AI merge -> Clavain skill -> session-start.sh -> system context for all sessions.

- **Broad Bash access (P1-2):** `Bash(git:*)` allows any git command. `Bash(echo:*)` plus `Write` and `Edit` means the AI can write to any file in the workspace. While this is necessary for the merge task, a prompt-injected AI could write to `.github/workflows/` or `hooks/` to establish persistence.

- **API key exposure:** `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` are passed as secrets. The tool allowlist does not include `Bash(curl:*)` or `Bash(wget:*)`, which limits exfiltration vectors. However, `Bash(git:*)` could theoretically be used to push to a remote (`git push` to an attacker-controlled URL with secrets embedded in commit messages), though this is a stretch.

- **Permissions (lines 15-18):** `contents: write`, `pull-requests: write`, `issues: write`. The `contents: write` permission is necessary but also means the workflow can push directly to branches. The PR-based flow (using `peter-evans/create-pull-request@v7`) is the right approach -- changes go to a branch, not directly to main.

- **Action pinning:** Uses `actions/checkout@v4`, `anthropics/claude-code-action@v1`, `openai/codex-action@v1`, `peter-evans/create-pull-request@v7`. These use major version tags, not SHA pins. A compromised action could run arbitrary code in the workflow. This is a common practice but not best practice for high-security workflows.

### 4. Upstream Check Workflow (`/root/projects/Clavain/.github/workflows/upstream-check.yml`)

**Analysis:**

- Line 60: `\(.latest_commit_msg)` is interpolated into the issue body via jq string interpolation. Commit messages from upstream repos are under upstream author control. If a commit message contained markdown injection (e.g., links, images, or GitHub-flavored markdown that triggers actions), it would render in the GitHub issue. This is a P2 because GitHub already sanitizes dangerous HTML in markdown, but malicious markdown links or misleading content could still appear.
- The `--body-file` approach (line 89, 97) is good -- it avoids shell injection when passing the body to `gh`.
- Permissions are minimal: `contents: read`, `issues: write`.

### 5. upstreams.json (`/root/projects/Clavain/upstreams.json`)

**Analysis:**
- Contains hardcoded git URLs (`https://github.com/...`). These are used in the sync workflow to clone repos. If someone could modify this file to point to a different repo URL (e.g., a fork with malicious content), the sync would pull from there.
- The `fileMap` specifies which upstream paths map to which local paths. Glob patterns like `references/*` expand at runtime. A malicious upstream could add new files in a `references/` directory that would be automatically pulled in -- this is by design but worth noting.
- The file is committed to the repo and protected by normal git access controls.

### 6. Plugin Content (Prompt Injection Surface)

The `session-start.sh` hook wraps the `using-clavain` skill content in `<EXTREMELY_IMPORTANT>` tags (line 46). This means the content of that skill file has elevated influence over the LLM's behavior. If a supply-chain compromise injected malicious instructions into this file (or any file that gets merged into it via upstream sync), those instructions would be followed by every Claude Code session using the plugin.

---

## Issues Found

### P0-1 (Critical): AI-Driven Auto-Merge of Untrusted Upstream Content Enables Prompt Injection

**Location:** `.github/workflows/sync.yml` lines 47-110 (the Claude Code prompt)

**Threat:** An upstream repository maintainer (or someone who compromises their repo) could embed prompt injection payloads in markdown skill files. The sync workflow instructs Claude Code to read this content and pass it to `codex exec -p "..."` as part of a merge prompt. The injected instructions could:
1. Instruct the AI to write arbitrary content to Clavain skill files
2. Override the merge instructions to insert hidden instructions
3. Modify `hooks/session-start.sh` or other hook scripts (Write and Edit tools are available)

The merged content becomes system-level context in every Claude Code session via `session-start.sh`.

**Likelihood:** Medium. The upstream repos are maintained by known open-source authors, and the sync creates a PR (not a direct push to main). However, if the PR is auto-merged or reviewed only superficially, malicious content could slip through. The attack is also feasible if an upstream repo is compromised via a supply chain attack on its own dependencies.

**Mitigation:**
1. Never auto-merge sync PRs -- require manual human review with a checklist for prompt injection patterns
2. Add a CODEOWNERS file requiring specific reviewers for `skills/using-clavain/`, `hooks/`, and `.github/workflows/`
3. Consider adding a post-merge validation step that scans for known prompt injection patterns (e.g., `<EXTREMELY_IMPORTANT>`, `system:`, `ignore previous instructions`, etc.)
4. Restrict the tool allowlist: remove `Bash(echo:*)` (use Write/Edit instead) and explicitly exclude `Bash(git:push*)` to prevent exfiltration

### P1-1 (High): JSON Injection via Unescaped Variables in agent-mail-register.sh Heredoc

**Location:** `/root/projects/Clavain/hooks/agent-mail-register.sh` lines 39-54

**Threat:** The heredoc `<<PAYLOAD` (not `<<'PAYLOAD'`) performs bash variable expansion. The variables `${session_id}` (from parsed stdin JSON) and `${PROJECT_DIR}` (from `CLAUDE_PROJECT_DIR` env var) are interpolated directly into a JSON string without JSON-escaping. If either contains a double-quote character, the JSON structure breaks. More critically, a `session_id` containing `","method":"tools/call","params":{"name":"send_message"...` could inject additional JSON-RPC parameters.

**Likelihood:** Low-Medium. `session_id` comes from Claude Code's internal hook protocol (likely a UUID), and `CLAUDE_PROJECT_DIR` is a filesystem path (unlikely to contain quotes). But the code is structurally wrong -- it constructs JSON via string interpolation instead of proper serialization.

**Mitigation:** Use `jq` to construct the JSON payload:
```bash
payload=$(jq -n \
  --arg session_id "$session_id" \
  --arg project_dir "$PROJECT_DIR" \
  '{
    jsonrpc: "2.0",
    id: ("register-" + $session_id),
    method: "tools/call",
    params: {
      name: "macro_start_session",
      arguments: {
        human_key: $project_dir,
        program: "claude-code",
        model: "claude-opus-4-6",
        task_description: ("session " + $session_id)
      }
    }
  }')
curl -sf --max-time 5 "${AGENT_MAIL_URL}" \
    -H "Content-Type: application/json" \
    -d "$payload" 2>/dev/null
```

### P1-2 (High): sync.yml Grants Broad Bash Tool Access to AI Agent Processing Untrusted Content

**Location:** `.github/workflows/sync.yml` line 112

**Threat:** The `allowedTools` list includes `Bash(git:*)`, `Write`, and `Edit`. While necessary for the merge task, `Bash(git:*)` includes `git push`, `git remote add`, etc. A prompt-injected AI (see P0-1) could use these to exfiltrate content or establish persistence by modifying workflow files in the working tree.

**Likelihood:** Low on its own (requires P0-1 to be exploited first), but the permissions are broader than needed.

**Mitigation:**
1. Narrow the Bash patterns: `Bash(git:diff*),Bash(git:log*),Bash(git:clone*),Bash(git:fetch*),Bash(git:show*)` instead of `Bash(git:*)`
2. Remove `Bash(echo:*)` -- `Write` and `Edit` cover file writing
3. The `peter-evans/create-pull-request` action handles git add/commit/push, so the Claude agent does not need those capabilities

### P2-1 (Medium): dotfiles-sync.sh Hardcodes Absolute Path and Runs External Script

**Location:** `/root/projects/Clavain/hooks/dotfiles-sync.sh` line 14

**Threat:** The script runs `/root/projects/dotfiles-sync/sync-dotfiles.sh` on every session end. This external script is outside the plugin repository and not tracked by Clavain's version control. If that script were modified (maliciously or accidentally), it would execute arbitrary code in the context of every session end.

**Likelihood:** Very Low. Requires local root access to modify the external script, which already grants full system access.

**Mitigation:** This is an acceptable risk for a single-user development server. For a distributed plugin, this hook should be removed or made configurable. As-is, it will silently no-op on any machine where the path does not exist (line 17 check), so it does not affect other plugin users.

### P2-2 (Medium): Upstream Commit Messages Rendered Unescaped in GitHub Issue Body

**Location:** `.github/workflows/upstream-check.yml` line 60

**Threat:** The `latest_commit_msg` field from upstream repos is interpolated into the GitHub issue body via jq string interpolation. While GitHub sanitizes HTML in markdown, a crafted commit message could contain misleading markdown (fake links, phishing URLs, or confusing formatting) that appears in the automated issue.

**Likelihood:** Low. The upstream repos are known projects, and the impact is limited to misleading issue content (not code execution).

**Mitigation:** Truncate commit messages to first 80 characters and wrap in backtick code fences in the jq template to prevent markdown interpretation.

---

## Improvements Suggested

### IMP-1: Add Human Review Gate for Sync PRs

The `sync.yml` workflow creates PRs, which is good. Add explicit documentation or branch protection rules requiring manual review before merge. Consider adding a PR template checklist that includes "Checked for prompt injection patterns" and "Reviewed all skill/agent content changes for unexpected instructions."

### IMP-2: Use jq for JSON Construction in agent-mail-register.sh

Replace the heredoc-with-interpolation pattern (lines 39-54) with `jq -n` construction as shown in the P1-1 mitigation. This eliminates the structural JSON injection risk regardless of input content.

### IMP-3: Scope Workflow Permissions and Pin Action Versions

- In `sync.yml`, change action references from `@v1`/`@v4`/`@v7` to full SHA pins (e.g., `actions/checkout@<sha>`). This prevents a compromised upstream action from executing arbitrary code.
- Consider splitting `contents: write` into a more targeted permission if GitHub supports it in the future. Currently, `contents: write` is required for the create-pull-request action but also allows direct branch pushes.
- Add `concurrency` controls to prevent parallel sync runs that could conflict.

### IMP-4: Add CODEOWNERS Protection for Security-Critical Paths

Create a `.github/CODEOWNERS` file requiring explicit review for:
```
hooks/                    @mistakeknot
.github/workflows/        @mistakeknot
skills/using-clavain/     @mistakeknot
upstreams.json            @mistakeknot
.claude-plugin/           @mistakeknot
```

This ensures PRs modifying hook scripts, workflows, or the bootstrap skill cannot be merged without owner review, even if an automated sync PR tries to modify them.

---

## Overall Assessment

**Real risk level: Medium**

The most significant risk is the content supply chain: upstream repos -> AI merge -> plugin skills -> system context for all Claude Code sessions. This is a novel attack surface specific to AI plugin architectures. The sync workflow is well-designed (creates PRs, not direct pushes), but the lack of explicit guardrails against prompt injection in upstream content is a real gap.

The hook scripts are generally well-written with proper `set -euo pipefail` and graceful error handling. The JSON injection in `agent-mail-register.sh` is structurally wrong but has low practical exploitability given the input sources.

The MCP server configuration is straightforward -- one external HTTPS API and one localhost HTTP service. Neither introduces significant risk.

**Must-fix items:**
- P0-1: Add branch protection rules and CODEOWNERS to ensure sync PRs receive human review with prompt-injection awareness. Document this as a security requirement.
- P1-1: Rewrite the JSON payload construction in `agent-mail-register.sh` to use `jq`.
- P1-2: Narrow the `allowedTools` in `sync.yml` to remove unnecessary Bash capabilities.

**Nice-to-have hardening:**
- P2-1: The hardcoded dotfiles path is fine for single-user use; remove if publishing the plugin for others.
- P2-2: Sanitize commit messages in issue body generation.
- IMP-3: Pin action versions to SHAs.
- IMP-4: Add CODEOWNERS file.
