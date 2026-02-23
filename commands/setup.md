---
name: setup
description: Bootstrap the Clavain modpack — install required plugins, disable conflicts, verify MCP servers, configure hooks
argument-hint: "[optional: --check-only to verify without making changes, --scope=clavain|interlock|all]"
---

# Clavain Modpack Setup

Bootstrap the full Clavain engineering rig from a fresh Claude Code install. Run this once to install everything, or re-run to verify and repair configuration.

## Arguments

<setup_args> #$ARGUMENTS </setup_args>

If `--check-only` is in the arguments, only verify the configuration — do not make changes.

`--scope=interlock` focuses on intermute service install/health only, while
`--scope=clavain` (default) runs the full Clavain modpack setup flow. Use
`--scope=all` to force both.

## Step 1: Verify Clavain Itself

Confirm this plugin is installed and active:
```bash
# Clavain should already be installed if you're running this command
ls ~/.claude/plugins/cache/interagency-marketplace/clavain/*/skills/using-clavain/SKILL.md
```

## Step 2: Install Required & Recommended Plugins

> **Automated install:** Use `scripts/modpack-install.sh` which reads `agent-rig.json` at runtime — no hardcoded lists to go stale.

Locate the modpack install script:
```bash
CLAVAIN_DIR=$(dirname "$(ls ~/.claude/plugins/cache/interagency-marketplace/clavain/*/agent-rig.json 2>/dev/null | head -1)")
INSTALL_SCRIPT="${CLAVAIN_DIR}/scripts/modpack-install.sh"
```

If `--check-only` was passed, use dry-run mode:
```bash
# Check-only: report what would change without installing
result=$("$INSTALL_SCRIPT" --dry-run --quiet)
```

Otherwise, install required and recommended plugins automatically:
```bash
# Install core + required + recommended, disable conflicts — all in one pass
result=$("$INSTALL_SCRIPT" --quiet)
```

Parse the result JSON and report to the user:
- **installed**: plugins that were just installed (list them)
- **already_present**: plugins that were already installed (report count)
- **failed**: plugins that failed to install (warn about each one)
- **disabled**: conflicting plugins that were disabled
- **optional_available**: optional plugins not yet installed (presented in Step 2b)

If `$INSTALL_SCRIPT` is not found or `jq` is not available, fall back to the manual lists below.

**Language servers (install based on what languages you work with):**
Use AskUserQuestion to ask which languages to enable:
<!-- agent-rig:begin:install-infrastructure -->
- Go → `claude plugin install gopls-lsp@claude-plugins-official`
- Python → `claude plugin install pyright-lsp@claude-plugins-official`
- TypeScript → `claude plugin install typescript-lsp@claude-plugins-official`
- Rust → `claude plugin install rust-analyzer-lsp@claude-plugins-official`
<!-- agent-rig:end:install-infrastructure -->

## Step 2b: Optional Plugins

Check the `optional_available` field from the install result above. If any optional plugins are not yet installed, present them via AskUserQuestion (multi-select) with descriptions from `agent-rig.json`:

```bash
# Get optional plugins not yet installed
optional=$("$INSTALL_SCRIPT" --dry-run --quiet --category=optional | jq -r '.optional_available[]')
```

For each plugin the user selects, install it:
```bash
claude plugin install <selected-plugin>
```

If the script is unavailable, use the fallback list:

<!-- agent-rig:begin:install-optional -->
- `interfluence@interagency-marketplace` — Voice profile and style adaptation
- `interject@interagency-marketplace` — Ambient discovery and research engine (MCP)
- `internext@interagency-marketplace` — Work prioritization and tradeoff analysis
- `interstat@interagency-marketplace` — Token efficiency benchmarking
- `interkasten@interagency-marketplace` — Notion sync and documentation
- `interlens@interagency-marketplace` — Cognitive augmentation lenses (MCP)
- `intersearch@interagency-marketplace` — Shared embedding and Exa search library
- `interserve@interagency-marketplace` — Codex spark classifier and context compression (MCP)
- `interpub@interagency-marketplace` — Plugin publishing automation
- `tuivision@interagency-marketplace` — TUI automation and visual testing (MCP)
- `intermux@interagency-marketplace` — Agent activity visibility and tmux monitoring (MCP)
- `interleave@interagency-marketplace` — Deterministic skeleton + LLM islands pattern
- `intermem@interagency-marketplace` — Memory synthesis (auto-memory → AGENTS.md/CLAUDE.md)
- `interlearn@interagency-marketplace` — Cross-repo institutional knowledge index
- `intercache@interagency-marketplace` — Cross-session semantic cache (MCP)
- `interchart@interagency-marketplace` — Interactive ecosystem diagram generator
<!-- agent-rig:end:install-optional -->

## Step 3: Disable Conflicting Plugins

> Conflicts are handled automatically by `modpack-install.sh` in Step 2. This step only runs if the script was unavailable.

If the automated install ran, conflicts are already disabled — skip to Step 4.

Otherwise, manually disable these plugins:

<!-- agent-rig:begin:disable-conflicts -->
```bash
claude plugin disable code-review@claude-plugins-official
claude plugin disable pr-review-toolkit@claude-plugins-official
claude plugin disable code-simplifier@claude-plugins-official
claude plugin disable commit-commands@claude-plugins-official
claude plugin disable feature-dev@claude-plugins-official
claude plugin disable claude-md-management@claude-plugins-official
claude plugin disable frontend-design@claude-plugins-official
claude plugin disable hookify@claude-plugins-official
```
<!-- agent-rig:end:disable-conflicts -->

## Step 4: Verify MCP Servers

Check that required MCP servers are configured:

**context7** — should be declared in Clavain's plugin.json (automatic)

**qmd** — check if available:
```bash
command -v qmd && qmd status
```
If qmd is not installed, inform the user: "qmd is not installed. Install from https://github.com/tobi/qmd for semantic search across project documentation."

**Oracle** (optional) — check if available:
```bash
command -v oracle && pgrep -f "Xvfb :99"
```
If Oracle is available, confirm it's working. If not, inform the user it's optional.

## Step 5: Initialize Beads (if not configured)

Check if the current project uses beads:
```bash
ls .beads/ 2>/dev/null
```
If `.beads/` doesn't exist, ask: "Initialize beads issue tracking for this project? (bd init)"

## Step 6: Verify Configuration

Run a final verification. This script reads `~/.claude/settings.json` to check actual enabled/disabled state (plugins missing from `enabledPlugins` are enabled by default — only explicit `false` means disabled):

<!-- agent-rig:begin:verify-script -->
```bash
python3 -c "
import json, os, subprocess

settings_path = os.path.expanduser('~/.claude/settings.json')
with open(settings_path) as f:
    plugins = json.load(f).get('enabledPlugins', {})

# Required plugins: absent = enabled (default), True = enabled, False = disabled
required = {
    'agent-sdk-dev@claude-plugins-official',
    'clavain@interagency-marketplace',
    'context7@claude-plugins-official',
    'explanatory-output-style@claude-plugins-official',
    'intercheck@interagency-marketplace',
    'intercraft@interagency-marketplace',
    'interdev@interagency-marketplace',
    'interdoc@interagency-marketplace',
    'interflux@interagency-marketplace',
    'interform@interagency-marketplace',
    'interline@interagency-marketplace',
    'interlock@interagency-marketplace',
    'intermap@interagency-marketplace',
    'interpath@interagency-marketplace',
    'interpeer@interagency-marketplace',
    'interphase@interagency-marketplace',
    'interslack@interagency-marketplace',
    'intersynth@interagency-marketplace',
    'intertest@interagency-marketplace',
    'interwatch@interagency-marketplace',
    'plugin-dev@claude-plugins-official',
    'security-guidance@claude-plugins-official',
    'serena@claude-plugins-official',
    'tldr-swinton@interagency-marketplace',
    'tool-time@interagency-marketplace',
}

conflicts = {
    'claude-md-management@claude-plugins-official',
    'code-review@claude-plugins-official',
    'code-simplifier@claude-plugins-official',
    'commit-commands@claude-plugins-official',
    'feature-dev@claude-plugins-official',
    'frontend-design@claude-plugins-official',
    'hookify@claude-plugins-official',
    'pr-review-toolkit@claude-plugins-official',
}

print('=== Required Plugins ===')
req_ok = 0
for p in sorted(required):
    enabled = plugins.get(p, True)  # absent = enabled by default
    status = 'enabled' if enabled else 'DISABLED'
    if enabled: req_ok += 1
    print(f'  {p}: {status}')
print(f'  ({req_ok}/{len(required)} enabled)')

print()
print('=== Conflicting Plugins ===')
conf_ok = 0
for p in sorted(conflicts):
    enabled = plugins.get(p, True)
    status = 'STILL ENABLED' if enabled else 'disabled'
    if not enabled: conf_ok += 1
    print(f'  {p}: {status}')
print(f'  ({conf_ok}/{len(conflicts)} disabled)')
"
```
<!-- agent-rig:end:verify-script -->

Then check MCP servers and companions:

```bash
echo "=== MCP Servers ==="
echo "context7: $(ls ~/.claude/plugins/cache/*/context7/*/plugin.json 2>/dev/null | head -1 >/dev/null && echo 'OK' || echo 'MISSING')"
echo "qmd: $(command -v qmd >/dev/null 2>&1 && echo 'installed' || echo 'not installed')"

echo "=== Companions ==="
echo "codex dispatch: $(ls ~/.claude/plugins/cache/interagency-marketplace/clavain/*/scripts/dispatch.sh 2>/dev/null | head -1 >/dev/null && echo 'OK' || echo 'MISSING')"
echo "interline: $(ls ~/.claude/plugins/cache/*/interline/*/scripts/statusline.sh 2>/dev/null | head -1 >/dev/null && echo 'installed' || echo 'not installed')"
echo "oracle: $(command -v oracle >/dev/null 2>&1 && echo 'installed' || echo 'not installed')"
echo "interlock: $(ls ~/.claude/plugins/cache/*/interlock/*/scripts/interlock-register.sh 2>/dev/null | head -1 >/dev/null && echo 'installed' || echo 'not installed')"
echo "beads: $(ls .beads/ 2>/dev/null | head -1 >/dev/null && echo 'configured' || echo 'not configured')"
```

## Step 7: Summary

Present results:

```
Clavain Modpack Setup Complete

Required plugins:  [X/10 enabled]
Conflicts disabled: [X/8 disabled]
Language servers:   [list enabled]
MCP servers:       context7 ✓ | qmd [status]
Infrastructure:    oracle [status]
Beads:             [status]

Next steps:
- Try `/clavain:brainstorm improve error handling in this project` for a quick demo
- Or run `/clavain:route [task]` for the adaptive workflow entry point
- Run `/tool-time:tool-time` to see tool usage analytics
- Run `/clavain:upstream-sync` to check for updates
```
