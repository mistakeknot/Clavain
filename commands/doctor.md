---
name: doctor
description: Quick health check — verifies MCP servers, external tools, beads, and plugin configuration without making changes
---

# Clavain Doctor

Run a quick diagnostic to verify everything Clavain depends on is healthy. Unlike `/setup` (which bootstraps), `/doctor` only checks — it never makes changes.

Run all checks in parallel where possible, then present results.

## Checks

### 1. MCP Servers

Test each MCP server with a lightweight call:

- **context7**: Call `resolve-library-id` with `libraryName: "react"` and `query: "test"`. Pass = response received. Fail = timeout or error.
- **qmd**: Call `status`. Pass = response with collection info. Fail = error or not configured.

### 2. External Tools

Check presence of optional companion tools:

```bash
echo "oracle: $(command -v oracle >/dev/null 2>&1 && echo 'installed' || echo 'not found')"
echo "codex: $(command -v codex >/dev/null 2>&1 && echo 'installed' || echo 'not found')"
echo "bd: $(command -v bd >/dev/null 2>&1 && echo 'installed' || echo 'not found')"
echo "qmd: $(command -v qmd >/dev/null 2>&1 && echo 'installed' || echo 'not found')"
```

### 3. Beads

```bash
if [ -d .beads ]; then
  bd stats 2>&1 | head -5
else
  echo "not initialized (run 'bd init' to set up)"
fi
```

### 3b. Beads Lifecycle Companion

```bash
if ls ~/.claude/plugins/cache/*/interphase/*/hooks/lib-gates.sh 2>/dev/null | head -1 >/dev/null; then
  echo "interphase: installed"
else
  echo "interphase: not installed (phase tracking disabled)"
  echo "  Install: claude plugin install interphase@interagency-marketplace"
fi
```

### 4. Conflicting Plugins

Check that known conflicting plugins are disabled:

```bash
python3 -c "
import json, os
settings = os.path.expanduser('~/.claude/settings.json')
try:
    plugins = json.load(open(settings)).get('enabledPlugins', {})
except FileNotFoundError:
    print('  settings.json not found'); exit()
conflicts = [
    'code-review@claude-plugins-official',
    'pr-review-toolkit@claude-plugins-official',
    'code-simplifier@claude-plugins-official',
    'commit-commands@claude-plugins-official',
    'feature-dev@claude-plugins-official',
    'claude-md-management@claude-plugins-official',
    'frontend-design@claude-plugins-official',
    'hookify@claude-plugins-official',
]
active = [p for p in conflicts if plugins.get(p, True)]
if active:
    for p in active:
        print(f'  WARN: {p} is still enabled')
else:
    print('  All conflicts disabled')
"
```

### 5. Plugin Version

```bash
# Compare installed vs published
INSTALLED=$(cat ~/.claude/plugins/cache/interagency-marketplace/clavain/*/plugin.json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['version'])" 2>/dev/null || echo "unknown")
echo "installed: v${INSTALLED}"
```

## Output

Present results as a table:

```
Clavain Doctor
──────────────────────────────────
context7      [PASS|FAIL]
qmd           [PASS|WARN: not installed]
oracle        [installed|not found]
codex         [installed|not found]
beads         [OK (N open, M closed)|not initialized]
interphase [installed|not installed]
conflicts     [clear|WARN: N active]
version       v0.X.Y
──────────────────────────────────
```

If any check shows FAIL or WARN, add a **Recommendations** section with one-line fixes:
- context7 fail → "Restart Claude Code session — context7 is bundled with Clavain"
- qmd not installed → "Install qmd for semantic doc search: https://github.com/tobi/qmd"
- conflicts active → "Run `/clavain:setup` to disable conflicting plugins"
- beads not initialized → "Run `bd init` to enable issue tracking"
