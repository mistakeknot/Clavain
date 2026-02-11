# fd-safety: Clavain Plugin Security & Deployment Review

### Findings Index
- MEDIUM | SAF-01 | "auto-compound.sh JSON Injection" | Stop hook interpolates unsanitized transcript content into JSON reason field
- MEDIUM | SAF-02 | "Upstream Sync Supply Chain Risk" | Seven external repos auto-merged into plugin with limited content verification
- MEDIUM | SAF-03 | "PR Agent Workflow Injection via Focus Parameter" | User-supplied focus text interpolated into Claude and Codex prompts
- LOW | SAF-04 | "session-start.sh curl to Unauthenticated Localhost Service" | Health check and registration to Agent Mail without authentication
- LOW | SAF-05 | "dispatch.sh CLAVAIN_ALLOW_UNSAFE Bypass Gate" | Environment variable gate for dangerous sandbox bypass is weak
- LOW | SAF-06 | "sync-upstreams.sh Shell Interpolation in Python Heredocs" | Upstream names interpolated into Python code via bash variables
- INFO | SAF-07 | "dotfiles-sync.sh Executes External Script from Filesystem" | SessionEnd hook runs arbitrary script from well-known path
- INFO | SAF-08 | "MCP Server Registrations Trust Model" | context7 (external HTTPS) and agent-mail (localhost HTTP) have different trust profiles

Verdict: safe

---

### Summary

Clavain is a Claude Code plugin composed of markdown skills, shell hooks, and upstream sync infrastructure. The primary threat surface is (a) shell hooks executed on every session lifecycle event that construct JSON responses from dynamic content, (b) an automated upstream sync pipeline that pulls markdown and shell content from 7 external GitHub repos into the local plugin, and (c) GitHub Actions workflows that accept issue-comment-triggered commands and pass user-supplied text into AI agent prompts. The overall security posture is reasonable for a single-operator local development tool. The upstream sync system has the most architectural risk due to its supply-chain nature, but it is meaningfully mitigated by the decision-gate workflow and the content-blocklist contamination check. No high-severity exploitable vulnerabilities were found.

### Issues Found

#### SAF-01: auto-compound.sh JSON Injection (MEDIUM)

**File:** `/root/projects/Clavain/hooks/auto-compound.sh`, lines 77-86

The Stop hook builds a JSON response by interpolating the `$REASON` variable (which contains the `$SIGNALS` string) directly into a heredoc JSON body:

```bash
REASON="Auto-compound check: detected compoundable signals [${SIGNALS}] in this turn. ..."

cat <<EOF
{
  "decision": "block",
  "reason": "${REASON}"
}
EOF
```

The `$SIGNALS` variable is constructed from hardcoded string literals (`commit,`, `resolution,`, `investigation,`, `bead-closed,`, `insight,`), so it cannot contain user-controlled content today. However, this pattern is fragile: if future signal detection uses any content extracted from the transcript (e.g., commit messages, file paths), those values would be interpolated directly into JSON without escaping. The `lib.sh` file provides `escape_for_json` specifically for this purpose, but `auto-compound.sh` does not source `lib.sh` or use it.

**Concrete risk today:** Minimal -- the interpolated values are all hardcoded strings. No current exploit path.

**Risk if pattern is extended:** A future developer adding a signal that includes a transcript excerpt (e.g., the commit message) would introduce a JSON injection that could alter the `decision` field or inject additional JSON keys.

**Mitigation:** Source `lib.sh` and pass `$REASON` through `escape_for_json`, or use `jq -n --arg` to build the JSON safely (as `autopilot.sh` already does). This is a defense-in-depth improvement, not an urgent fix.

---

#### SAF-02: Upstream Sync Supply Chain Risk (MEDIUM)

**Files:**
- `/root/projects/Clavain/upstreams.json` (7 upstream definitions)
- `/root/projects/Clavain/scripts/sync-upstreams.sh` (file copy logic)
- `/root/projects/Clavain/.github/workflows/sync.yml` (automated weekly sync)

Clavain pulls content from 7 external GitHub repositories and copies files into its own skill/agent/command directories. The `sync.yml` workflow runs weekly on a cron schedule and automatically creates PRs with the upstream changes. In `--auto` mode (used in CI), files classified as `COPY` (where local content matches upstream after namespace replacement) are overwritten without human review.

**Trust model analysis:**

The upstream repos are all public GitHub repos owned by known individuals (obra, steipete, steveyegge, Dicklesworthstone, EveryInc). A compromise of any upstream repo's main branch would allow injecting arbitrary markdown content into Clavain's skills, agents, and commands. Since these are markdown files that become system prompts for Claude Code, a compromised upstream could inject prompt injection content that alters agent behavior.

**Existing mitigations (meaningful):**
1. `syncConfig.protectedFiles` prevents overwriting critical files like `commands/lfg.md`
2. `syncConfig.deletedLocally` prevents re-creating removed agents
3. `syncConfig.contentBlocklist` checks for domain-specific terms post-sync
4. `syncConfig.namespaceReplacements` rewrites namespace references
5. The `upstream-decision-gate.yml` workflow requires a human decision record with `Gate: approved` before merge
6. Files with local divergence are classified as `REVIEW` and skipped in `--auto` mode
7. The sync creates a PR (not a direct push), so changes are visible before merge

**Gaps:**
- The content blocklist (`rails_model`, `Every.to`, etc.) is designed to catch domain-specific contamination, not malicious prompt injection. There is no check for adversarial content patterns (e.g., system prompt overrides, tool call injection sequences).
- The `COPY` classification only checks whether local content matches the previous upstream version (after namespace replacement). If an attacker modifies the upstream file and the local file was previously in sync, the new content is classified as... not `COPY` -- it is classified as `REVIEW` because the upstream has changed and the local no longer matches. This is actually correct behavior: only files where upstream and local are already identical get `COPY`. New upstream changes always go through `REVIEW` or the PR review process.
- No cryptographic verification (e.g., signed commits, pinned hashes beyond `lastSyncedCommit` which advances automatically).

**Assessment:** For a single-operator tool where the operator reviews PRs before merge, this is acceptable. The decision-gate workflow is the critical control. The risk is that the operator rubber-stamps the automated PR without reading the diff carefully, which is an operational discipline issue, not a code issue. No code change needed, but the operator should be aware that the contamination check does not cover prompt injection.

---

#### SAF-03: PR Agent Workflow Injection via Focus Parameter (MEDIUM)

**File:** `/root/projects/Clavain/.github/workflows/pr-agent-commands.yml`, lines 181-201 and 314-329

The PR agent commands workflow accepts a `focus` parameter from issue comments:

```javascript
const match = firstNonEmpty.match(/^\/clavain:(claude-review|codex-review|dual-review|ai-review)\b(.*)$/i);
// ...
focus = (match[2] || "").trim();
```

This focus text is then interpolated directly into the Claude and Codex prompts:

```yaml
prompt: |
  ...
  Optional focus from commenter: `${{ needs.parse-command.outputs.focus }}`
```

And for Codex:
```bash
codex exec --sandbox read-only -C "$GITHUB_WORKSPACE" -o /tmp/codex-review.md - <<'EOF'
  ...
  Optional focus from commenter: `${{ needs.parse-command.outputs.focus }}`
EOF
```

**Trust boundary analysis:** The workflow already gates on `author_association` being OWNER, MEMBER, or COLLABORATOR. This means only trusted repo collaborators can trigger the command and supply the focus text. Untrusted users get a deny comment.

**Residual risk:** A collaborator could craft a focus parameter that overrides the review instructions (prompt injection into the AI agent). However, collaborators already have write access to the repo and could modify the workflow file itself. The blast radius is limited to the review comment posted on the PR.

**Note on the Codex heredoc:** The `<<'EOF'` is a quoted heredoc, which prevents shell variable expansion. However, the `${{ }}` expressions are GitHub Actions expression interpolations that happen before the shell runs. The focus value is interpolated by Actions, not by bash, so the `'EOF'` quoting does not protect against injection of shell metacharacters via the focus parameter. A collaborator could potentially break out of the heredoc by including `EOF` on a line by itself in their focus text. This would cause the shell to terminate the heredoc early and interpret subsequent text as shell commands.

**Mitigation:** Write the focus value to a file in a previous step using a GitHub Actions environment file or `actions/github-script`, then reference it with `cat` inside the shell step. This eliminates both the prompt injection vector and the shell heredoc breakout risk in the Codex review path. The Claude review path uses `anthropics/claude-code-action@v1` which handles the prompt as a YAML string, so the shell injection aspect does not apply there, though the prompt injection risk remains.

---

#### SAF-04: session-start.sh Curl to Unauthenticated Localhost Service (LOW)

**File:** `/root/projects/Clavain/hooks/session-start.sh`, line 33

```bash
if curl -s -o /dev/null -w '' --connect-timeout 1 http://127.0.0.1:8765/health 2>/dev/null; then
```

**File:** `/root/projects/Clavain/hooks/agent-mail-register.sh`, lines 20, 33, 61

```bash
AGENT_MAIL_URL="${AGENT_MAIL_URL:-http://127.0.0.1:8765/mcp/}"
```

The hooks communicate with a localhost HTTP service (MCP Agent Mail) without any authentication token. The `plugin.json` also registers this as an MCP server:

```json
"mcp-agent-mail": {
  "type": "http",
  "url": "http://127.0.0.1:8765/mcp"
}
```

**Threat model:** This is a localhost-only service. On a single-user development machine, any process running as the user can already access it. The `AGENT_MAIL_URL` environment variable allows overriding the URL, but this requires the attacker to control the environment of the Claude Code process, which already implies full compromise.

**Assessment:** Appropriate for the threat model. No authentication is needed for a localhost service on a single-user machine. The `agent-mail-register.sh` sends the `CLAUDE_PROJECT_DIR` path as `human_key`, which is not sensitive. The 2-second connect timeout is good practice for a hook that should not block session startup.

---

#### SAF-05: dispatch.sh CLAVAIN_ALLOW_UNSAFE Bypass Gate (LOW)

**File:** `/root/projects/Clavain/scripts/dispatch.sh`, lines 142-149

```bash
--dangerously-bypass-approvals-and-sandbox|--yolo)
  if [[ "${CLAVAIN_ALLOW_UNSAFE:-}" == "1" ]]; then
    EXTRA_ARGS+=("$1")
    shift
  else
    echo "Error: $1 is blocked by dispatch.sh safety policy. Set CLAVAIN_ALLOW_UNSAFE=1 to override." >&2
    exit 1
  fi
```

The script blocks the `--dangerously-bypass-approvals-and-sandbox` and `--yolo` flags by default, requiring `CLAVAIN_ALLOW_UNSAFE=1` in the environment. This is a speed bump, not a security boundary -- any user who can run `dispatch.sh` can also set environment variables. The intent is to prevent accidental use of the dangerous flag, and the implementation matches that intent.

**Assessment:** Appropriate for the use case. This is a developer convenience guardrail, not a security control.

---

#### SAF-06: sync-upstreams.sh Shell Interpolation in Python Heredocs (LOW)

**File:** `/root/projects/Clavain/scripts/sync-upstreams.sh`, lines 293-299 and 310-318

```bash
while IFS= read -r name; do
  upstream_names+=("$name")
done < <(python3 -c "
import json
with open('$UPSTREAMS_JSON') as f:
    data = json.load(f)
for u in data['upstreams']:
    print(u['name'])
")
```

And:

```bash
IFS='|' read -r branch base_path last_commit < <(python3 -c "
import json
with open('$UPSTREAMS_JSON') as f:
    data = json.load(f)
for u in data['upstreams']:
    if u['name'] == '$upstream_name':
        bp = u.get('basePath') or '_NONE_'
        print(u.get('branch','main') + '|' + bp + '|' + u['lastSyncedCommit'])
        break
")
```

The variables `$UPSTREAMS_JSON` and `$upstream_name` are interpolated into Python code strings. `$UPSTREAMS_JSON` is derived from the script's own path (`$PROJECT_ROOT/upstreams.json`), and `$upstream_name` comes from the JSON file's `name` fields, which are controlled by the repo owner.

**Concrete risk:** If `upstreams.json` contained a malicious name value, it would be interpolated into the Python code. However, `upstreams.json` is a file committed to the repo, controlled by the repo owner. An attacker who can modify `upstreams.json` already has write access to the repo and can modify any script directly.

**Assessment:** No exploitable risk given the trust model. The pattern could be improved by using `sys.argv` instead of shell interpolation (as `agent-mail-register.sh` does with its Python snippets, and as the `expand_file_map()` and `resolve_local_path()` functions within the same file already do), but this is a code quality improvement, not a security fix.

---

#### SAF-07: dotfiles-sync.sh Executes External Script (INFO)

**File:** `/root/projects/Clavain/hooks/dotfiles-sync.sh`, lines 15-23

```bash
SYNC_SCRIPT="${HOME}/projects/dotfiles-sync/sync-dotfiles.sh"

if [[ ! -x "$SYNC_SCRIPT" ]]; then
    exit 0
fi

bash "$SYNC_SCRIPT" >>/var/log/dotfiles-sync.log 2>&1 || true
```

The SessionEnd hook executes a script from a well-known filesystem path. The script path is hardcoded (not user-configurable), and the hook checks for the executable bit before running it. On a single-user machine, this is equivalent to the user having the script in their PATH.

**Assessment:** No security concern for the single-operator threat model. The script only runs if it exists and is executable. The `|| true` ensures the hook never fails the session end.

---

#### SAF-08: MCP Server Registrations Trust Model (INFO)

**File:** `/root/projects/Clavain/.claude-plugin/plugin.json`, lines 23-36

```json
"mcpServers": {
    "context7": {
      "type": "http",
      "url": "https://mcp.context7.com/mcp"
    },
    "mcp-agent-mail": {
      "type": "http",
      "url": "http://127.0.0.1:8765/mcp"
    },
    "qmd": {
      "type": "stdio",
      "command": "qmd",
      "args": ["mcp"]
    }
}
```

Three MCP servers are registered:
1. **context7** -- external HTTPS service at `mcp.context7.com`. This is a third-party documentation service. Data sent to it (library names, queries) is visible to the service operator.
2. **mcp-agent-mail** -- localhost HTTP. No external exposure.
3. **qmd** -- local stdio process. No network exposure.

**Assessment:** The context7 server is the only external network dependency. It receives query text (library names and search terms) which is not sensitive in a development context. It uses HTTPS, so the transport is encrypted. This is appropriate for a documentation lookup service.

### Improvements Suggested

1. **SAF-01 fix (low effort):** In `auto-compound.sh`, source `lib.sh` and use `jq -n --arg` to build the JSON response, matching the pattern already used in `autopilot.sh`. This prevents future regressions if the signal detection logic evolves to include dynamic content.

2. **SAF-03 fix (medium effort):** In `pr-agent-commands.yml`, sanitize the `focus` output by writing it to a file in the parse step, then referencing the file in subsequent steps. This eliminates both the prompt injection vector and the shell heredoc breakout risk in the Codex review path. Specifically, the Codex review step should use an environment variable rather than direct `${{ }}` interpolation inside the heredoc.

3. **SAF-06 improvement (low effort):** In `sync-upstreams.sh`, pass bash variables as `sys.argv` arguments to the inline Python scripts instead of interpolating them into the Python source code. This is already the pattern used in `agent-mail-register.sh` and in `expand_file_map()` / `resolve_local_path()` within the same file.

4. **Upstream content verification:** Consider adding a post-sync check for known prompt injection patterns (e.g., lines containing "ignore previous instructions", "you are now", or XML-like system tags) in addition to the existing domain-specific content blocklist. This would catch adversarial content from a compromised upstream.

5. **Workflow permissions tightening:** The `codex-refresh-reminder.yml` has `contents: write` permission, but it only posts commit comments. Creating commit comments via the GitHub API requires `contents: read` plus the GITHUB_TOKEN's implicit ability to create comments. The `contents: write` permission is broader than necessary.

### Overall Assessment

Clavain has a security posture appropriate for its threat model: a single-operator Claude Code plugin running on a local development machine. The hooks use `set -euo pipefail` consistently, the autopilot gate correctly uses `jq` for JSON construction, and the upstream sync pipeline has meaningful human-review gates (decision records, PR-based workflow, contamination checks).

The most architecturally significant risk is the upstream supply chain (SAF-02), where 7 external repos can inject markdown content that becomes AI system prompts. This is mitigated by the decision-gate workflow and the operator's PR review. The `COPY` classification in `sync-upstreams.sh` only applies when local and upstream content are already identical, so genuinely new upstream changes always require human review through the PR process.

The SAF-03 heredoc breakout in the Codex review workflow is the most concrete (though still low-likelihood) exploit path, but it requires a trusted collaborator to craft a malicious comment, which already implies the actor has commit access.

No findings require blocking deployment. The MEDIUM findings are defense-in-depth improvements and pattern hardening. The overall verdict is **safe** for continued use with the suggested improvements tracked as non-urgent follow-ups.

<!-- flux-drive:complete -->
