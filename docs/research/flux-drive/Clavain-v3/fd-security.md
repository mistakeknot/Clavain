---
agent: fd-security
tier: 1
issues:
  - id: SEC-01
    severity: high
    section: "GitHub Actions: PR Agent Commands Workflow"
    title: "Script injection via unsanitized PR comment body interpolated into JS template literals"
  - id: SEC-02
    severity: high
    section: "GitHub Actions: Upstream Sync Workflow"
    title: "Codex runs with danger-full-access sandbox granting unrestricted filesystem and network access"
  - id: SEC-03
    severity: medium
    section: "dispatch.sh: Passthrough of Dangerous Flags"
    title: "dispatch.sh accepts and forwards --dangerously-bypass-approvals-and-sandbox and --yolo flags"
  - id: SEC-04
    severity: medium
    section: "GitHub Actions: pull_request_target Workflows"
    title: "Three workflows use pull_request_target trigger which runs in base branch context with write permissions"
  - id: SEC-05
    severity: medium
    section: "hooks/lib.sh: Incomplete JSON Escaping"
    title: "escape_for_json omits control characters U+0000-U+001F beyond tab/CR/LF, producing invalid JSON"
  - id: SEC-06
    severity: medium
    section: "hooks/agent-mail-register.sh: Environment-Controlled URL"
    title: "AGENT_MAIL_URL is overridable via environment, allowing redirection of registration traffic to arbitrary endpoints"
  - id: SEC-07
    severity: low
    section: "hooks/autopilot.sh: Flag File Bypass"
    title: "Autopilot gate relies on a plain file whose creation and deletion are not access-controlled"
  - id: SEC-08
    severity: low
    section: "hooks/dotfiles-sync.sh: Unconstrained Sync Script Execution"
    title: "Session-end hook executes an external script from a hardcoded path without integrity verification"
  - id: SEC-09
    severity: low
    section: "debate.sh: Predictable Temp File Paths"
    title: "Temp files in /tmp use predictable names derived from --topic, enabling symlink attacks"
  - id: SEC-10
    severity: low
    section: "MCP Server Configuration"
    title: "Agent Mail MCP server bound to localhost without authentication"
  - id: SEC-11
    severity: info
    section: "install-codex.sh: CLAVAIN_REPO_URL Override"
    title: "Clone source URL is overridable via environment variable, allowing substitution of a malicious repository"
improvements:
  - id: IMP-01
    title: "Sanitize all workflow output interpolations with environment variables instead of direct expression substitution"
    section: "GitHub Actions: PR Agent Commands Workflow"
  - id: IMP-02
    title: "Downgrade sync workflow sandbox from danger-full-access to workspace-write with explicit network allowlist"
    section: "GitHub Actions: Upstream Sync Workflow"
  - id: IMP-03
    title: "Remove --dangerously-bypass-approvals-and-sandbox and --yolo from dispatch.sh passthrough whitelist"
    section: "dispatch.sh: Passthrough of Dangerous Flags"
  - id: IMP-04
    title: "Extend escape_for_json to handle all JSON-illegal control characters (U+0000 through U+001F)"
    section: "hooks/lib.sh: Incomplete JSON Escaping"
  - id: IMP-05
    title: "Use mktemp for debate.sh intermediate files instead of predictable /tmp paths"
    section: "debate.sh: Predictable Temp File Paths"
  - id: IMP-06
    title: "Pin pull_request_target workflow checkouts to the base ref and avoid checking out PR head code that runs in privileged context"
    section: "GitHub Actions: pull_request_target Workflows"
verdict: PASS WITH CONDITIONS -- no critical vulnerabilities found; two high-severity issues require remediation before the plugin is safe for multi-user or CI-facing deployment
---

# Clavain Plugin Security Audit

## Summary

This audit covers the Clavain Claude Code plugin (v0.4.6) with focus on its shell hooks, dispatch scripts, MCP server configuration, and GitHub Actions workflows. The plugin is a general-purpose engineering discipline layer for Claude Code with 34 skills, 29 agents, 27 commands, 3 hooks, and 3 MCP servers.

**Threat model**: The primary attack surfaces are (1) the hooks that run automatically in every Claude Code session, (2) the dispatch script that wraps Codex CLI invocations, (3) the GitHub Actions workflows that respond to comments and PRs from potentially untrusted contributors, and (4) the MCP server declarations that expose network services.

**Overall finding**: No critical vulnerabilities were found. Two high-severity issues exist in the GitHub Actions workflows -- one script injection vector and one overly permissive sandbox configuration. Several medium-severity issues around JSON escaping, environment variable trust, and `pull_request_target` usage deserve attention. The local hooks are well-structured with appropriate fail-open behavior and reasonable defensive coding, though the autopilot gate has inherent limitations by design.

---

## Section-by-Section Review

### 1. hooks/autopilot.sh -- Codex-First Access Gate

**File**: `/root/projects/Clavain/hooks/autopilot.sh`

**Purpose**: PreToolUse hook that denies Edit/Write/MultiEdit tool calls when autopilot mode is active (signaled by a flag file), redirecting changes through Codex agents.

**Positive observations**:
- Uses `set -euo pipefail` for strict error handling.
- Fails open (exits 0) when `CLAUDE_PROJECT_DIR` is unset, preventing hook errors from blocking normal operation.
- Uses `jq` for JSON output when available, falling back to a static heredoc that avoids interpolation entirely (line 53: `cat <<'ENDJSON'`). This is a correct defensive pattern.
- The `jq -n --arg` pattern on line 44 properly escapes the deny reason string through jq's argument encoding.

**Concerns**:

**SEC-07 (Low)**: The autopilot gate depends entirely on the existence of `$PROJECT_DIR/.claude/autopilot.flag`. Any process with write access to the project directory can create or delete this file. Since Claude Code sessions run as the same user, the LLM could potentially be prompted to remove this file via Bash before attempting a write. However, this is mitigated by the fact that an attacker who can run arbitrary bash commands in the session already has full filesystem access, making the gate moot. The flag file is a policy signal, not a security boundary.

**File path extraction** (line 30): `FILE_PATH` is extracted from stdin via jq and used only in a `$DENY_REASON` string that is later encoded through `jq --arg`. No command injection is possible here.

---

### 2. hooks/session-start.sh -- Context Injection

**File**: `/root/projects/Clavain/hooks/session-start.sh`

**Purpose**: SessionStart hook that reads the `using-clavain/SKILL.md` content, detects companion tools, and injects context into the session via `additionalContext`.

**Positive observations**:
- Uses `escape_for_json` (from lib.sh) for the large skill content block before embedding in JSON.
- Companion detection uses safe local checks: file existence (`-d`), curl with 1-second timeout, `command -v`, and `pgrep`.
- No user-controlled input is processed.

**Concerns**:

The `file_age_days` arithmetic on line 52 uses `$(date +%s)` and `$(stat -c %Y ...)` -- both safe internal system calls.

The `find` on line 22 could theoretically match an adversarial filename if someone placed a file named `dispatch.sh` with special characters in the scripts directory, but since this path is only used in a `companions` string that goes through `\\n-` prefix formatting and is embedded via the heredoc, the worst case is a malformed companion message, not code execution.

The heredoc on line 61-67 uses `${}` variable expansion within a non-quoted `<<EOF` block. The `using_clavain_escaped` content has been processed through `escape_for_json`, and the `companion_context` and `upstream_warning` variables contain only hardcoded strings with `\\n` literals. This is safe for the current content but relies on `escape_for_json` being complete (see SEC-05).

---

### 3. hooks/agent-mail-register.sh -- MCP Registration

**File**: `/root/projects/Clavain/hooks/agent-mail-register.sh`

**Purpose**: SessionStart hook that registers the current session with the MCP Agent Mail server and injects identity/inbox context.

**Positive observations**:
- Uses Python's `json.dumps()` (line 41-56) to safely construct the JSON payload, avoiding shell interpolation of the session ID and project directory into raw JSON.
- Curl calls use `--max-time` (2s and 5s) to prevent hangs.
- Graceful failure on all error paths (exits 0 silently).
- Response parsing uses Python's `json.load()` with try/except.

**Concerns**:

**SEC-06 (Medium)**: The `AGENT_MAIL_URL` variable (line 20) defaults to `http://127.0.0.1:8765/mcp/` but is overridable through the environment:

```bash
AGENT_MAIL_URL="${AGENT_MAIL_URL:-http://127.0.0.1:8765/mcp/}"
```

If an attacker can set environment variables before the hook runs, they could redirect registration traffic (including `CLAUDE_PROJECT_DIR` as `human_key`) to an arbitrary HTTP endpoint. In the Claude Code hook execution model, environment variables are inherited from the parent process, so this requires control over the shell environment rather than just the conversation. The practical risk is low in single-user deployments but worth hardening for shared environments.

**Session ID from stdin** (line 30): The session ID is extracted via Python's `json.load()` which safely parses the input. Even if the session ID contained special characters, it flows through `json.dumps()` on line 41-56, which properly escapes it for JSON output.

---

### 4. hooks/dotfiles-sync.sh -- Session-End Sync

**File**: `/root/projects/Clavain/hooks/dotfiles-sync.sh`

**Purpose**: SessionEnd hook that runs a dotfiles sync script if it exists.

**Positive observations**:
- Checks for script existence and executability before running (`-x`).
- Redirects output to a log file with `|| true` to prevent hook failures from blocking session exit.

**Concerns**:

**SEC-08 (Low)**: The script executes `$HOME/projects/dotfiles-sync/sync-dotfiles.sh` without verifying its integrity (no checksum, no signature). If an attacker can modify that external script, they gain code execution at the end of every Claude Code session. However, this requires filesystem write access to the user's home directory, which would already constitute full compromise.

The log file `/var/log/dotfiles-sync.log` is world-readable by default on most systems and could leak information about synced configuration files. This is an informational concern.

---

### 5. hooks/lib.sh -- Shared Utilities

**File**: `/root/projects/Clavain/hooks/lib.sh`

**Purpose**: Provides `escape_for_json` function used by all hooks that embed content in JSON output.

**Concerns**:

**SEC-05 (Medium)**: The `escape_for_json` function handles backslash, double-quote, newline, carriage return, and tab -- but omits other control characters that are illegal in JSON strings per RFC 8259. Specifically, characters U+0000 through U+001F (excluding the three it handles: `\t` U+0009, `\n` U+000A, `\r` U+000D) are not escaped. These include:

- U+0000 (NUL) -- could cause string truncation in some JSON parsers
- U+0008 (BS/backspace) -- should be `\b`
- U+000C (FF/form feed) -- should be `\f`
- U+0001-U+0007, U+000B, U+000E-U+001F -- should be `\uXXXX`

In practice, the input to this function is primarily the SKILL.md file content (UTF-8 markdown) which is unlikely to contain control characters. But if a malformed or adversarial file were synced upstream, a control character could produce invalid JSON that breaks the hook output, potentially causing the session to lose its injected context or producing parse errors.

The function also does not handle forward slashes (`/`), but JSON does not require escaping them, so this is correct.

---

### 6. scripts/dispatch.sh -- Codex CLI Wrapper

**File**: `/root/projects/Clavain/scripts/dispatch.sh`

**Purpose**: Wraps `codex exec` with defaults for sandbox mode, working directory, doc injection, template assembly, and output routing.

**Positive observations**:
- Uses bash arrays (`CMD=()`) for command construction, which properly handles arguments with spaces and special characters without shell injection risk.
- The final execution uses `exec "${CMD[@]}"` (line 359), which is safe because array expansion preserves argument boundaries.
- Prompt content flows as a single array element (line 330: `CMD+=("$PROMPT")`), not through shell interpolation.
- Template assembly uses Perl with `$ARGV[]` (line 239-245), passing values as arguments rather than interpolating them into the Perl script. The `\Q...\E` in the regex ensures the marker is treated as a literal string.
- The `--inject-docs` scope is validated against an allowlist (line 269-273).
- `require_arg` prevents empty values for flags that need arguments.

**Concerns**:

**SEC-03 (Medium)**: The dispatch script explicitly whitelists dangerous Codex CLI flags for passthrough on line 143:

```bash
--json|--full-auto|--skip-git-repo-check|--oss|--dangerously-bypass-approvals-and-sandbox|--yolo|--search|--no-alt-screen)
```

The `--dangerously-bypass-approvals-and-sandbox` and `--yolo` flags disable Codex's safety guardrails entirely. While dispatch.sh is invoked by the LLM (or by skills that the LLM runs), allowing these flags means a prompt injection or adversarial skill could instruct the LLM to pass `--yolo` to dispatch, bypassing Codex's approval flow.

The `-s` / `--sandbox` flag (line 89-92) also accepts `danger-full-access` as a valid value with no restriction. In combination with `--yolo`, this grants the dispatched Codex agent full filesystem and network access with no approval gates.

**No command injection risk**: Despite the initial concern flagged in the review request, dispatch.sh does not use `eval`, does not interpolate variables into commands via string expansion, and constructs all commands via proper bash arrays. The prompt content -- even if it contains shell metacharacters -- is passed as a single argument to `codex exec` and never interpreted by the shell.

---

### 7. scripts/debate.sh -- Structured Debate

**File**: `/root/projects/Clavain/scripts/debate.sh`

**Purpose**: Two-round structured debate between Claude and Codex using dispatch.sh.

**Concerns**:

**SEC-09 (Low)**: Temp files use predictable paths based on the `--topic` argument:

```bash
ROUND1_PROMPT="/tmp/debate-r1-prompt-${TOPIC}.md"
ROUND1_OUTPUT="/tmp/debate-r1-output-${TOPIC}.md"
ROUND2_PROMPT="/tmp/debate-r2-prompt-${TOPIC}.md"
```

On a multi-user system, an attacker could pre-create these as symlinks pointing to sensitive files, causing the debate script to overwrite them (via `cat > "$ROUND1_PROMPT"`). On a single-user server (which is the deployment model here), this is low risk. Using `mktemp` would eliminate the concern entirely.

The script properly delegates to dispatch.sh with `-s read-only`, which is a positive security practice for analysis-only tasks.

---

### 8. scripts/upstream-check.sh -- Upstream Repo Checker

**File**: `/root/projects/Clavain/scripts/upstream-check.sh`

**Purpose**: Checks upstream repositories for new commits/releases and optionally updates a versions file.

**Positive observations**:
- Uses `jq --arg` for safe JSON value injection throughout (lines 81-103).
- Repo names come from a hardcoded array, not from user input.
- All `gh api` calls use `2>/dev/null || true` for graceful failure.

**No significant security concerns.** The script reads from a hardcoded list of upstream repos and uses `gh api` which handles authentication via the `gh` CLI's own credential management.

---

### 9. scripts/install-codex.sh -- Codex Installation

**File**: `/root/projects/Clavain/scripts/install-codex.sh`

**Concerns**:

**SEC-11 (Info)**: The clone URL and target directory are overridable via environment variables:

```bash
CLONE_DIR="${CLAVAIN_CLONE_DIR:-$HOME/.codex/clavain}"
REPO_URL="${CLAVAIN_REPO_URL:-$REPO_URL_DEFAULT}"
```

An attacker who can set `CLAVAIN_REPO_URL` before the script runs could cause it to clone a malicious repository containing trojanized skills. The script does validate that the source directory looks like a Clavain root (`is_clavain_root` checks for README.md, skills/, commands/, scripts/), but this is easily spoofed.

The `safe_link` function (line 120-140) properly checks for existing non-symlink files and refuses to overwrite them, which prevents accidental destruction of local content.

---

### 10. .claude-plugin/plugin.json -- MCP Server Declarations

**File**: `/root/projects/Clavain/.claude-plugin/plugin.json`

**Concerns**:

**SEC-10 (Low)**: The Agent Mail MCP server is declared as:

```json
"mcp-agent-mail": {
  "type": "http",
  "url": "http://127.0.0.1:8765/mcp"
}
```

This binds to localhost over plain HTTP without any authentication token or API key. On a single-user server, localhost binding provides adequate isolation. However:

- Any process on the machine can connect to this endpoint and send/receive messages as any registered agent.
- The `qmd` MCP server uses stdio transport, which is inherently scoped to the process -- no network exposure.
- The `context7` server connects to an external service (`https://mcp.context7.com/mcp`) over HTTPS, which is appropriate.

If Agent Mail is ever deployed in a multi-user or container environment, authentication should be added.

---

### 11. GitHub Actions: PR Agent Commands Workflow

**File**: `/root/projects/Clavain/.github/workflows/pr-agent-commands.yml`

**Positive observations**:
- Implements trust gating: only OWNER, MEMBER, or COLLABORATOR can trigger reviews (line 36-37).
- Checks for required secrets before launching expensive AI operations.
- Claude review uses `--allowedTools` to restrict tool access (line 193).
- Codex review uses `--sandbox read-only` (line 302).

**Concerns**:

**SEC-01 (High)**: The `deny-untrusted` job and several other jobs interpolate workflow outputs directly into JavaScript template literals without sanitization:

```javascript
// Line 75 of deny-untrusted job:
const pr = Number("${{ needs.parse-command.outputs.pr_number }}");
const command = "${{ needs.parse-command.outputs.command }}";
const association = "${{ needs.parse-command.outputs.association }}";
```

While `pr_number` is derived from `context.payload.issue.number` (an integer) and `command` is regex-matched to a fixed set of known commands, the `association` and `actor` values come from the GitHub event payload. The `actor` value (line 65: `core.setOutput("actor", context.actor)`) is later interpolated on line 203:

```javascript
const actor = "${{ needs.parse-command.outputs.actor }}";
```

A GitHub username containing a double-quote and JS payload (e.g., `user"; process.exit(1); //`) would break out of the string literal. While GitHub usernames have strict character restrictions (alphanumeric and hyphens only), the `focus` output on line 47 passes through arbitrary text from the comment body:

```javascript
focus = (match[2] || "").trim();
```

This `focus` value is later interpolated into the Codex prompt heredoc on line 309:

```
Optional focus from commenter: `${{ needs.parse-command.outputs.focus }}`
```

Inside the heredoc this is safe (it is prompt text, not executed code). But the pattern of direct `${{ }}` interpolation into JavaScript strings establishes an unsafe precedent. The correct pattern is to use environment variables:

```yaml
env:
  FOCUS: ${{ needs.parse-command.outputs.focus }}
```

and access them via `process.env.FOCUS` in the script.

The `deny-missing-secrets` job correctly uses environment variables for secret presence checks (lines 97-100), demonstrating that the author knows the safe pattern but did not apply it consistently.

---

### 12. GitHub Actions: Upstream Sync Workflow

**File**: `/root/projects/Clavain/.github/workflows/sync.yml`

**Concerns**:

**SEC-02 (High)**: The Codex CLI is invoked with `--sandbox danger-full-access` on line 84:

```bash
codex exec --sandbox danger-full-access -C "$GITHUB_WORKSPACE" -o /tmp/codex-upstream-sync.md - <<'EOF'
```

This grants the Codex agent full filesystem access (can read/write anywhere on the runner) and unrestricted network access. The justification noted in the prompt is "upstream sync needs outbound network access for cloning upstream repos," but this is an overly broad grant.

The risk: the Codex agent is running an AI model that processes a complex multi-step prompt. If the prompt is manipulated (e.g., through a poisoned upstream repo's commit messages or file content that gets read during the merge step), the agent could be directed to exfiltrate secrets, modify the workflow, or install persistent backdoors on the runner.

**Mitigating factors**:
- The workflow runs on `ubuntu-latest` ephemeral runners (no persistent state).
- The "Enforce no direct commits" step (lines 151-158) catches if Codex committed directly.
- `persist-credentials: false` is set on checkout (line 30), limiting git push capability.

However, the Codex agent still has access to environment variables (which include `CODEX_AUTH_JSON` from the secrets context via the earlier step's `~/.codex/auth.json` file) and can read `~/.codex/auth.json` which was written on line 73.

**SEC-04 (Medium)**: Applies to three workflows: `upstream-impact.yml`, `upstream-decision-gate.yml`, and `codex-refresh-reminder-pr.yml`. All use `pull_request_target` which runs workflow code from the base branch (main) with write permissions, even when triggered by a forked PR. This is the correct approach (safer than `pull_request` with write permissions for forks), but requires careful attention:

- `upstream-impact.yml` checks out the PR head SHA (line 24: `ref: ${{ github.event.pull_request.head.sha }}`) but only runs Python against local config files and `gh api` calls. The Python script does not execute any code from the checked-out PR content.
- `upstream-decision-gate.yml` does not check out code at all -- it reads the decision record file via the GitHub API.
- `codex-refresh-reminder-pr.yml` does not check out code.

These are safe usage patterns of `pull_request_target`. The risk would increase if any of these workflows were modified to run scripts from the checked-out PR head.

---

### 13. GitHub Actions: Other Workflows

**upstream-check.yml**: Runs on schedule and manual dispatch. Uses `GH_TOKEN` from secrets only for `gh` CLI calls. Issue body is constructed via `jq` from the check script's JSON output, avoiding shell interpolation of upstream data into the issue body. This is well done.

**codex-refresh-reminder.yml**: Runs on push to main. The `changed_files` output is interpolated into a JavaScript template literal on line 47:

```javascript
const changed = `${{ steps.detect.outputs.changed_files }}`.trim();
```

File paths in a git diff could theoretically contain backticks or `${` sequences that break template literals. This is a minor script injection vector, but since it only triggers on pushes to main (which requires write access), the attacker would already have full repository control.

**upstream-sync-issue-command.yml**: Properly gates on trusted associations. The `actor` interpolation on line 127 has the same pattern as SEC-01 but is low risk due to GitHub username restrictions.

---

## Issues Found

### High Severity

| ID | Issue | Location | Impact |
|----|-------|----------|--------|
| SEC-01 | Script injection via unsanitized workflow output interpolation | `.github/workflows/pr-agent-commands.yml` lines 75, 203 | A crafted GitHub event payload could inject JavaScript into the `actions/github-script` execution context, potentially creating malicious PR comments or accessing the GITHUB_TOKEN |
| SEC-02 | Codex runs with danger-full-access sandbox in CI | `.github/workflows/sync.yml` line 84 | A prompt injection through upstream repo content could direct Codex to read `~/.codex/auth.json` and exfiltrate credentials via network access |

### Medium Severity

| ID | Issue | Location | Impact |
|----|-------|----------|--------|
| SEC-03 | Dangerous Codex flags whitelisted in dispatch.sh | `scripts/dispatch.sh` line 143 | LLM or adversarial skill could disable Codex safety guardrails via `--yolo` |
| SEC-04 | Three workflows use pull_request_target | `.github/workflows/upstream-impact.yml`, `upstream-decision-gate.yml`, `codex-refresh-reminder-pr.yml` | Currently safe but fragile -- future modifications could introduce privilege escalation |
| SEC-05 | Incomplete JSON escaping in lib.sh | `hooks/lib.sh` lines 6-14 | Control characters in skill content could produce invalid JSON, breaking context injection |
| SEC-06 | Environment-controlled Agent Mail URL | `hooks/agent-mail-register.sh` line 20 | Registration traffic could be redirected to a malicious endpoint |

### Low Severity

| ID | Issue | Location | Impact |
|----|-------|----------|--------|
| SEC-07 | Autopilot flag file has no access control | `hooks/autopilot.sh` line 20 | Autopilot gate can be bypassed by deleting the flag file |
| SEC-08 | External sync script executed without integrity check | `hooks/dotfiles-sync.sh` line 23 | Compromised sync script gains code execution at session end |
| SEC-09 | Predictable temp file paths in debate.sh | `scripts/debate.sh` lines 152-154 | Symlink attacks on multi-user systems |
| SEC-10 | Agent Mail MCP server has no authentication | `.claude-plugin/plugin.json` line 29 | Any local process can impersonate agents or read messages |

### Informational

| ID | Issue | Location | Impact |
|----|-------|----------|--------|
| SEC-11 | Clone URL overridable via environment | `scripts/install-codex.sh` line 19 | Supply chain risk if environment is compromised |

---

## Improvements Suggested

### IMP-01: Sanitize workflow output interpolations (addresses SEC-01)

Replace all direct `${{ }}` interpolations in `actions/github-script` blocks with environment variable passing:

```yaml
# Before (unsafe):
script: |
  const actor = "${{ needs.parse-command.outputs.actor }}";

# After (safe):
env:
  ACTOR: ${{ needs.parse-command.outputs.actor }}
script: |
  const actor = process.env.ACTOR;
```

Apply this pattern consistently across `pr-agent-commands.yml`, `upstream-sync-issue-command.yml`, and `codex-refresh-reminder.yml`.

### IMP-02: Restrict sync workflow sandbox (addresses SEC-02)

Replace `danger-full-access` with `workspace-write` in the sync workflow. If network access is required for cloning upstream repos, perform the cloning in a separate shell step before invoking Codex, and pass the cloned content to Codex via the workspace:

```yaml
- name: Clone upstreams
  run: |
    # Clone all upstream repos to /tmp/upstream/ using gh or git
    # This step has network access natively

- name: Run Codex sync (workspace-only)
  run: |
    codex exec --sandbox workspace-write -C "$GITHUB_WORKSPACE" ...
```

Additionally, delete `~/.codex/auth.json` before the Codex exec step to prevent credential access, or use a separate step that does not expose the auth file to the Codex sandbox.

### IMP-03: Remove dangerous flag passthrough (addresses SEC-03)

Remove `--dangerously-bypass-approvals-and-sandbox` and `--yolo` from the known-boolean-flags case in dispatch.sh, or add an explicit opt-in guard:

```bash
# Reject dangerous flags unless CLAVAIN_ALLOW_UNSAFE=1
--dangerously-bypass-approvals-and-sandbox|--yolo)
  if [[ "${CLAVAIN_ALLOW_UNSAFE:-}" != "1" ]]; then
    echo "Error: $1 is blocked by dispatch.sh. Set CLAVAIN_ALLOW_UNSAFE=1 to override." >&2
    exit 1
  fi
  EXTRA_ARGS+=("$1")
  shift
  ;;
```

### IMP-04: Complete JSON escaping (addresses SEC-05)

Extend `escape_for_json` in `hooks/lib.sh` to handle all control characters:

```bash
escape_for_json() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\r'/\\r}"
    s="${s//$'\t'/\\t}"
    s="${s//$'\x08'/\\b}"
    s="${s//$'\x0c'/\\f}"
    # Strip remaining control chars (U+0000-U+001F except those handled above)
    s="$(printf '%s' "$s" | tr -d '\000-\007\013\016-\037')"
    printf '%s' "$s"
}
```

Alternatively, delegate to Python or jq for JSON encoding, which handle all edge cases natively.

### IMP-05: Use mktemp in debate.sh (addresses SEC-09)

Replace predictable paths with `mktemp`:

```bash
TMPDIR="$(mktemp -d "/tmp/clavain-debate-${TOPIC}-XXXXXX")"
ROUND1_PROMPT="$TMPDIR/r1-prompt.md"
ROUND1_OUTPUT="$TMPDIR/r1-output.md"
ROUND2_PROMPT="$TMPDIR/r2-prompt.md"
```

### IMP-06: Document pull_request_target safety constraints (addresses SEC-04)

Add a comment block at the top of each `pull_request_target` workflow documenting the safety invariant:

```yaml
# SECURITY: This workflow uses pull_request_target and runs with write permissions.
# It MUST NOT execute any code from the PR head (e.g., checked-out scripts).
# Only GitHub API calls and base-branch code are safe to run here.
```

This makes the constraint visible to future contributors who might modify the workflows.

---

## Overall Assessment

The Clavain plugin demonstrates generally sound security practices for a Claude Code plugin:

**Strengths**:
- Shell scripts use `set -euo pipefail` consistently.
- Command construction in dispatch.sh uses proper bash arrays, completely avoiding command injection.
- JSON construction uses `jq --arg` or Python `json.dumps()` rather than string interpolation.
- Hook scripts fail open gracefully, preventing security mechanisms from blocking normal operation.
- GitHub Actions workflows implement trust gating for comment-triggered commands.
- The autopilot gate's jq fallback uses a heredoc with single-quoted delimiter, preventing any interpolation in the no-jq path.

**Weaknesses**:
- The `danger-full-access` sandbox in CI combined with accessible auth credentials creates a credential exfiltration path.
- Inconsistent use of environment variables vs. direct expression interpolation in GitHub Actions JavaScript blocks.
- The dispatch script's passthrough of dangerous flags could be exploited by prompt injection to disable safety guardrails on dispatched Codex agents.
- JSON escaping is incomplete for edge-case control characters.

**Verdict**: The plugin is safe for its current single-user, single-server deployment model. For multi-user, CI-facing, or public-contributor scenarios, SEC-01 and SEC-02 should be remediated before deployment. SEC-03 should be addressed to prevent prompt injection from escalating privileges through the dispatch chain.
